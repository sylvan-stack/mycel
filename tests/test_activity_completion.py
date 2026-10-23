"""Complete injected mutation accounting on configured disposable stores."""

from uuid import uuid4
import unittest
from unittest.mock import patch

from psycopg.types.json import Jsonb

from mycel import _activity as activity
from mycel import _locks as locks
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._source_refs import SourceAddress


class ActivityCompletionStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def seed(self, connection):
        connection.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) "
                           "VALUES ('fixture','{}'),('unchanged','{}')")

    def write(self, counts, **details):
        def callback(connection):
            connection.execute("UPDATE public.mycel_repository_state SET read_locations=%s "
                               "WHERE repository='fixture'", (Jsonb(counts),))
            return activity.AppliedMutation(True, counts, **details)
        return callback

    def rows(self, connection):
        return connection.execute('SELECT id,repository,kind,outcome,counts '
                                  'FROM public.mycel_activity ORDER BY id').fetchall()

    @proves('MYC-12.1', 'MYC-12.2', 'MYC-12.3', 'MYC-12.4', 'MYC-12.13', kind='store')
    def test_every_kind_keeps_one_changed_scope_and_exact_complete_final_reply(self):
        with self.connect() as connection, self.connect() as observer:
            self.seed(connection)
            expected = {}
            with activity.MutationActivity(connection, build=37).session() as audit:
                invocation = audit.invocation
                for kind in sorted(activity.KINDS):
                    repository = None if kind in {'init', 'remove'} else 'fixture'
                    key = (repository, kind)
                    audit.apply(repository, kind, lambda _: activity.AppliedMutation(False, {'checked': 1}))
                    self.assertNotIn(key, {(row[1], row[2]) for row in self.rows(observer)})
                    audit.apply(repository, kind, self.write({'applied': 1, 'checked': 2}))
                    audit.apply(repository, kind, self.write({'applied': 2, 'checked': 3}))
                    # A completed unchanged check is part of the producer's
                    # final reply, but does not add a third mutation or row.
                    audit.apply(repository, kind, lambda _: activity.AppliedMutation(False, {'applied': 2, 'checked': 4}))
                    reply = {'applied': 2, 'checked': 4, 'reply': {'items': [kind, None, True]}}
                    if kind == 'remove':
                        reply['removed'] = 'fixture'
                    expected[key] = reply
                audit.apply('unchanged', 'ingest', lambda _: activity.AppliedMutation(False, {'checked': 9}))
                final = {**expected, ('unchanged', 'ingest'): {'checked': 9, 'applied': 0}}
                audit.finish('done', counts=final)
                self.assertTrue(locks.invocation_is_live(observer, invocation))
                for row in self.rows(observer):
                    detail = activity.activity_state(observer, row[0])
                    self.assertEqual(detail['invocation'], invocation.id)
                    self.assertEqual(detail['build'], 37)
                    self.assertEqual(detail['startedBy'], 'command')
                    self.assertGreaterEqual(detail['endedAt'], detail['startedAt'])
                    self.assertIsNone(detail['error'])
                # The accepted final snapshots cannot be changed by aliases
                # to the producer reply after the transaction commits.
                final[('fixture', 'classify')]['reply']['items'].append('later')
            rows = self.rows(observer)
            self.assertEqual(len(rows), len(activity.KINDS))
            self.assertFalse(locks.invocation_is_live(observer, invocation))
            for row in rows:
                self.assertEqual(row[3], 'done')
                self.assertEqual(row[4]['checked'], 4)
                self.assertEqual(row[4]['reply']['items'], [row[2], None, True])
                self.assertEqual((row[1] is None), row[2] in {'init', 'remove'})

    @proves('MYC-12.3', 'MYC-12.4', 'MYC-12.7', kind='store')
    def test_refusal_closes_applied_prefix_with_command_error_and_exact_counts(self):
        with self.connect() as connection:
            self.seed(connection)
            with self.assertRaises(MycelError) as error:
                with activity.MutationActivity(connection, build=37, started_by='freshness_check').session() as audit:
                    invocation = audit.invocation
                    audit.apply('fixture', 'ingest', self.write({'filesChanged': 1, 'refsChecked': 2}))
                    raise MycelError('busy', 'The later repository is in use.')
            self.assertEqual(error.exception.code, 'busy')
            row, = self.rows(connection)
            detail = activity.activity_state(connection, row[0])
            self.assertEqual(detail['outcome'], 'refused')
            self.assertEqual(detail['error'], {'code': 'busy', 'message': 'The later repository is in use.'})
            self.assertEqual(detail['counts'], {'filesChanged': 1, 'refsChecked': 2})
            self.assertEqual(detail['startedBy'], 'freshness_check')
            self.assertIsNotNone(detail['endedAt'])
            self.assertFalse(locks.invocation_is_live(connection, invocation))

    @proves('MYC-12.4', 'MYC-12.7', 'MYC-12.8', kind='store')
    def test_final_replies_validate_before_write_and_late_native_close_rolls_back_all_scopes(self):
        with self.connect() as connection, self.connect() as observer:
            self.seed(connection)
            with activity.MutationActivity(connection, build=37).session() as audit:
                audit.apply('fixture', 'embed', self.write({'embedded': 1}))
                audit.apply('fixture', 'confirm', self.write({'confirmed': 1}))
                before = self.rows(observer)
                for counts in ([], 1, {('fixture', 'embed'): {'embedded': float('nan')}},
                               {('fixture', 'embed'): {'embedded': 2}, ('fixture', 'confirm'): []}):
                    with self.assertRaises(MycelError) as invalid:
                        audit.finish('done', counts=counts)
                    self.assertEqual(invalid.exception.code, 'invalid_input')
                    self.assertEqual(self.rows(observer), before)
                original = activity._execute
                attempted = []

                def fail_second_close(current, sql, parameters=None):
                    if sql == activity._CLOSE_SQL:
                        attempted.append(parameters[-1])
                        if len(attempted) == 2:
                            sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
                    return original(current, sql, parameters)

                final = {('fixture', 'embed'): {'embedded': 1, 'checked': 3},
                         ('fixture', 'confirm'): {'confirmed': 1, 'checked': 2}}
                with patch('mycel._activity._execute', side_effect=fail_second_close):
                    with self.assertRaises(MycelError) as failure:
                        audit.finish('done', counts=final)
                self.assertEqual(failure.exception.code, 'internal')
                self.assertEqual(set(attempted), {row[0] for row in before})
                self.assertNotIn('mycel_missing_activity', str(failure.exception))
                self.assertEqual(self.rows(observer), before)
                self.assertTrue(locks.invocation_is_live(observer, audit.invocation))
                # A caught close failure may safely retry within the same
                # live invocation; no partial final reply was published.
                audit.finish('done', counts=final)
            for row in self.rows(observer):
                self.assertEqual(row[3:], ('done', final[(row[1], row[2])]))

    @proves('MYC-12.4', 'MYC-12.7', 'MYC-12.8', 'MYC-12.13', kind='store')
    def test_classification_references_rollback_with_native_detail_fault_and_keep_only_summaries(self):
        with self.connect() as connection:
            self.seed(connection)
            place = SourceAddress('fixture', 'code', 'worker.py', 'run')
            reference = activity.ClassificationReference('retained-bundle-7', place, 'needsReview')
            counts = {'selected': 1, 'completed': 0, 'needsReview': 1, 'errors': 0, 'obsolete': 0,
                      'jevCalls': 1, 'reviewerCalls': 0}
            original = activity._execute

            def fail_reference(current, sql, parameters=None):
                if sql.startswith('INSERT INTO public.mycel_activity_classifications'):
                    sql = sql.replace('public.mycel_activity_classifications', 'public.mycel_missing_activity')
                return original(current, sql, parameters)

            with activity.MutationActivity(connection, build=37).session() as audit:
                foreign = activity.ClassificationReference('retained-bundle-8',
                    SourceAddress('unchanged', 'code', 'worker.py', 'run'), 'needsReview')
                for kind, invalid_reference in (('ingest', reference), ('classify', foreign)):
                    with self.assertRaises(MycelError) as invalid:
                        audit.apply('fixture', kind, self.write(counts, classifications=(invalid_reference,)))
                    self.assertEqual(invalid.exception.code, 'invalid_input')
                    self.assertEqual(self.rows(connection), [])
                    self.assertEqual(connection.execute("SELECT read_locations FROM public.mycel_repository_state "
                                                        "WHERE repository='fixture'").fetchone()[0], {})
                with patch('mycel._activity._execute', side_effect=fail_reference):
                    with self.assertRaises(MycelError) as failure:
                        audit.apply('fixture', 'classify', self.write(counts, classifications=(reference,)))
                self.assertEqual(failure.exception.code, 'internal')
                self.assertEqual(self.rows(connection), [])
                self.assertEqual(connection.execute("SELECT read_locations FROM public.mycel_repository_state "
                                                    "WHERE repository='fixture'").fetchone()[0], {})
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity_classifications').fetchone()[0], 0)
                audit.apply('fixture', 'classify', self.write(counts, classifications=(reference,)))
            row, = self.rows(connection)
            detail = activity.activity_state(connection, row[0])
            self.assertEqual(detail['counts'], counts)
            self.assertEqual(detail['classifications'], [{'bundle': 'retained-bundle-7', 'dependant': {
                'repository': 'fixture', 'root': 'code', 'path': 'worker.py', 'name': 'run',
                'address': place.address}, 'outcome': 'needsReview'}])
            self.assertEqual((detail['files'], detail['decisions']), ([], []))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()[0], 0)

    @proves('MYC-12.5', 'MYC-12.6', 'MYC-12.7', kind='store')
    def test_added_changed_removed_files_and_all_identity_decisions_keep_exact_locations(self):
        with self.connect() as connection:
            self.seed(connection)
            files = (activity.FileChange('artifact', 'same.md', 'topic', 'changed'),
                     activity.FileChange('code', 'same.md', 'disk', 'added'),
                     activity.FileChange('code', 'old.py', 'stash-commit', 'removed'))
            decisions = tuple(activity.IdentityChange('artifact', 'same.md', 'topic', uuid4(),
                                                     decision, name, old)
                              for decision, name, old in (('unchanged', '', None), ('unchanged', 'A', None), ('edited', 'B', None),
                                                          ('renamed', 'C', 'Before'), ('new', 'D', None))) + (
                activity.IdentityChange('code', 'same.md', 'disk', uuid4(), 'new', 'Function'),
                activity.IdentityChange('code', 'old.py', 'stash-commit', uuid4(), 'removed', 'Gone'))
            with activity.MutationActivity(connection, build=37).session() as audit:
                audit.apply('fixture', 'ingest', self.write({'files': 3, 'chunks': 7}, files=files, decisions=decisions))
            row, = self.rows(connection)
            detail = activity.activity_state(connection, row[0])
            self.assertEqual(detail['files'], [{'root': item.root, 'path': item.path,
                                               'location': item.location, 'change': item.change}
                                              for item in sorted(files, key=lambda item: (item.root, item.path, item.location))])
            self.assertEqual({item['decision'] for item in detail['decisions']},
                             {'unchanged', 'edited', 'renamed', 'new', 'removed'})
            self.assertEqual([item['name'] for item in detail['decisions']], ['', 'A', 'B', 'C', 'D', 'Gone', 'Function'])
            self.assertEqual(detail['decisions'][3]['previousName'], 'Before')
            self.assertEqual(detail['decisions'][-2]['location'], 'stash-commit')

    @proves('MYC-12.7', 'MYC-12.14', kind='store')
    def test_running_and_unfinished_diagnostics_execute_read_only_without_changing_rows(self):
        with self.connect() as connection, self.connect() as observer:
            self.seed(connection)
            original = activity._execute

            def fail_close(current, sql, parameters=None):
                if sql == activity._CLOSE_SQL:
                    sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(current, sql, parameters)

            with patch('mycel._activity._execute', side_effect=fail_close):
                with self.assertRaises(MycelError) as failure:
                    with activity.MutationActivity(connection, build=37).session() as audit:
                        audit.apply('fixture', 'ingest', self.write({'changed': 1}))
                        row, = self.rows(observer)
                        before = observer.execute('SELECT * FROM public.mycel_activity').fetchall()
                        # PostgreSQL rejects row updates in this connection's
                        # snapshots. Diagnostics still compute exact liveness.
                        observer.execute('SET default_transaction_read_only = on')
                        self.assertEqual(activity.activity_state(observer, row[0])['outcome'], 'running')
                        self.assertEqual(observer.execute('SELECT * FROM public.mycel_activity').fetchall(), before)
                self.assertEqual(failure.exception.code, 'internal')
            # The failed session's final close leaves an open entry; its own
            # liveness disappears when the session context releases the lock.
            self.assertEqual(activity.activity_state(observer, row[0])['outcome'], 'unfinished')
            self.assertEqual(observer.execute('SELECT * FROM public.mycel_activity').fetchall(), before)
