"""Complete public activity history over genuine read-only store snapshots."""

from contextlib import contextmanager
from io import StringIO
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mycel import _activity as activity
from mycel import _locks as locks
from mycel._activity_reader import activity_from_store
from mycel._cli import parse, run
from mycel._errors import MycelError
from mycel._source_refs import SourceAddress

try:
    from .test_activity_retention import _History
except ImportError:
    from test_activity_retention import _History


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **options):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **options)


class ActivityHistoryUnitTests(unittest.TestCase):
    def test_count_kind_and_exclusive_detail_filters_refuse_before_any_store_access(self):
        invalid = (('--k', '0'), ('--k', '-1'), ('--k', '1.5'), ('--k', 'many'),
            ('--kind', 'search'), ('--entry', '01'), ('--entry', '0'),
            ('--entry', str(2**63)), ('--entry', '1', '--kind', 'ingest'),
            ('--entry', '1', '--k', '25'), ('--entry', '1', '--all'),
            ('--entry', '1', '--repo', 'fixture'), ('--repo', 'fixture', '--repo', 'other'),
            ('--repo', 'fixture', '--all'), ('unexpected',))
        with patch('mycel._activity_reader.invocation_store') as store:
            for arguments in invalid:
                with self.subTest(arguments=arguments), self.assertRaises(MycelError) as error:
                    parse(('activity', *arguments))
                self.assertEqual(error.exception.code, 'invalid_input')
            store.assert_not_called()
        self.assertEqual(parse(('activity', '--all', '--kind', 'embed', '--k', '999999999999999999999')).arguments,
                         ('--kind', 'embed', '--k', '500'))


class ActivityHistoryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.history = _History(self.store_fixture)

    def read(self, connection, names=('fixture',), **options):
        return activity_from_store(connection, self.history.settings, names, **options)

    @staticmethod
    def ids(reply):
        return [int(entry['id']) for entry in reply['entries']]

    def test_default_cap_all_kinds_and_repository_cwd_selection_use_exact_start_time_id_order(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture', 'other', 'disabled', 'orphan', 'stored-empty')
            self.history.seed(connection, 'fixture', 550)
            newest = self.history.seed(connection, 'fixture', 2, at='2002-01-01T00:00:00Z')
            for kind in sorted(activity.KINDS):
                self.history.seed(connection, None if kind in {'init', 'remove'} else 'fixture', 1, kind=kind)
            for owner in ('other', 'disabled', 'orphan'):
                self.history.seed(connection, owner, 1)
            expected = self.history.ids(connection, 'fixture')
            before = self.history.state(connection, sequences=True)
            recorded = _RecordingConnection(connection)
            # Lists must not fetch complete detail tables, nor invoke the
            # single-entry reader once for every selected summary.
            with patch('mycel._activity_reader.activity_state', side_effect=AssertionError('per-entry detail')):
                default = self.read(recorded)
                capped = self.read(recorded, k=9999)
                cwd = self.read(recorded, names=(), cwd=self.store_fixture.root / 'work' / 'fixture' / 'src')
                self.assertEqual(self.ids(default), expected[:25])
                self.assertEqual(self.ids(cwd), expected[:25])
                self.assertEqual(self.ids(capped), expected[:500])
                self.assertEqual(self.ids(default)[:2], list(reversed(newest)))
                for kind in sorted(activity.KINDS):
                    filtered = self.read(recorded, names=(), all_repositories=True, kind=kind, k=500)
                    wanted = [row[0] for row in connection.execute('SELECT id FROM public.mycel_activity '
                        'WHERE kind=%s ORDER BY started_at DESC,id DESC LIMIT 500', (kind,)).fetchall()]
                    self.assertEqual(self.ids(filtered), wanted, kind)
                    self.assertTrue(all(entry['kind'] == kind for entry in filtered['entries']))
                all_rows = self.read(recorded, names=(), all_repositories=True, k=500)
                self.assertTrue(any('repository' not in entry for entry in all_rows['entries']))
                self.assertTrue({'disabled', 'orphan'}.issubset(
                    {entry.get('repository') for entry in all_rows['entries']}))
                for name in ('disabled', 'orphan', 'empty', 'stored-empty'):
                    selected = self.read(recorded, names=(name,))
                    self.assertEqual(self.ids(selected), self.history.ids(connection, name)[:25])
                    self.assertTrue(all(entry['repository'] == name for entry in selected['entries']))
            self.assertTrue(all(not {'files', 'decisions', 'classifications'}.intersection(entry)
                                for entry in default['entries']))
            self.assertFalse(any('FROM public.' + table in statement for statement in recorded.statements
                                 for table in ('mycel_activity_files', 'mycel_identity_decisions',
                                               'mycel_activity_classifications')))
            self.assertEqual(self.history.state(connection, sequences=True), before)

    def test_complete_entry_details_keep_root_collisions_names_classification_references_and_build_identity(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture')
            files = (activity.FileChange('code', 'same.py', 'topic', 'changed'),
                     activity.FileChange('artifact', 'same.py', 'disk', 'added'),
                     activity.FileChange('code', 'same.py', 'disk', 'changed'))
            decisions = (
                activity.IdentityChange('code', 'same.py', 'topic', uuid4(), 'renamed', 'Zulu', 'Before'),
                activity.IdentityChange('code', 'same.py', 'disk', uuid4(), 'removed', 'Removed'),
                activity.IdentityChange('artifact', 'same.py', 'disk', uuid4(), 'new', 'Section'),
                activity.IdentityChange('code', 'same.py', 'disk', uuid4(), 'edited', 'Alpha'))
            references = (
                activity.ClassificationReference(str(uuid4()), SourceAddress('fixture', 'code', 'same.py', 'run'), 'needs_review'),
                activity.ClassificationReference(str(uuid4()), SourceAddress('fixture', 'artifact', 'same.py', 'Section'), 'unresolved'))
            with activity.MutationActivity(connection, build=31, started_by='freshness_check').session() as audit:
                audit.apply('fixture', 'ingest', self.history.mutation('fixture', {'filesChanged': 3},
                    files=files, decisions=decisions))
                audit.apply('fixture', 'classify', self.history.mutation('fixture', {'selected': 2},
                    classifications=references))
            entries = {row[1]: row[0] for row in connection.execute('SELECT id,kind FROM public.mycel_activity').fetchall()}
            before = self.history.state(connection, sequences=True)
            detail, = self.read(connection, names=(), identifier=entries['ingest'])['entries']
            self.assertEqual((detail['id'], detail['build'], detail['outcome'], detail['startedBy']),
                             (str(entries['ingest']), '1f', 'done', 'freshness_check'))
            self.assertEqual(detail['indexGeneration'], str(connection.execute(
                'SELECT index_generation FROM public.mycel_store').fetchone()[0]))
            self.assertEqual(detail['counts'], {'filesChanged': 3})
            self.assertEqual([(row['root'], row['path'], row['location']) for row in detail['files']],
                [('artifact', 'same.py', 'disk'), ('code', 'same.py', 'disk'), ('code', 'same.py', 'topic')])
            self.assertEqual([row['name'] for row in detail['decisions']], ['Section', 'Alpha', 'Removed', 'Zulu'])
            self.assertEqual(detail['decisions'][-1]['previousName'], 'Before')
            self.assertTrue(all('previousName' not in row for row in detail['decisions'][:-1]))
            self.assertEqual(detail['classifications'], [])
            classified, = self.read(connection, names=(), identifier=entries['classify'])['entries']
            self.assertEqual((classified['files'], classified['decisions']), ([], []))
            self.assertEqual(classified['classifications'], [{'bundle': ref.bundle, 'dependant': {
                'repository': ref.dependant.repository, 'root': ref.dependant.root, 'path': ref.dependant.path,
                'name': ref.dependant.name, 'address': ref.dependant.address}, 'outcome': ref.outcome} for ref in references])
            self.assertEqual(self.history.state(connection, sequences=True), before)

    def test_running_unfinished_and_over_limit_reads_never_prune_or_write_tables_or_sequences(self):
        with self.history.connect() as connection, self.history.connect() as observer:
            self.history.repositories(connection, 'fixture')
            self.history.seed(connection, 'fixture', 1001)
            dead, = self.history.seed(connection, 'fixture', 1, open_entry=True,
                                      at='2002-01-01T00:00:00Z')
            with locks.invocation_guard(connection) as invocation:
                live, = self.history.seed(connection, 'fixture', 1, open_entry=True, invocation=invocation,
                                          at='2003-01-01T00:00:00Z')
                before = self.history.state(observer, sequences=True)
                with patch('mycel._activity_retention.ActivityRetentionStore.prune_in_transaction',
                           side_effect=AssertionError('pruning')), \
                        patch('mycel._activity.MutationActivity.session', side_effect=AssertionError('activity')), \
                        patch('mycel._capture._Capture.capture', side_effect=AssertionError('freshness')), \
                        patch('mycel._embed.embed', side_effect=AssertionError('embedding')), \
                        patch('mycel._credentials.Credentials.embedding_key', side_effect=AssertionError('model credentials')):
                    listed = self.read(observer)
                    self.assertEqual([(row['id'], row['outcome']) for row in listed['entries'][:2]],
                                     [(str(live), 'running'), (str(dead), 'unfinished')])
                    live_detail, = self.read(observer, names=(), identifier=live)['entries']
                    self.assertEqual(live_detail['outcome'], 'running')
                    self.assertNotIn('endedAt', live_detail)
                    self.assertEqual(self.history.state(observer, sequences=True), before)
            # The lock's disappearance changes the computed reply only.
            before = self.history.state(observer, sequences=True)
            live_detail, = self.read(observer, names=(), identifier=live)['entries']
            self.assertEqual(live_detail['outcome'], 'unfinished')
            self.assertNotIn('endedAt', live_detail)
            self.assertEqual(len(self.history.ids(observer, 'fixture')), 1003)
            self.assertEqual(self.history.state(observer, sequences=True), before)

    def test_empty_lists_succeed_unknown_or_pruned_entries_refuse_and_invalid_filters_leave_no_writes(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture', 'empty')
            identifiers = self.history.seed(connection, 'fixture', 1000)
            with activity.MutationActivity(connection, build=31).session() as audit:
                audit.apply('fixture', 'embed', self.history.mutation('fixture'))
            self.assertNotIn(identifiers[0], self.history.ids(connection, 'fixture'))
            before = self.history.state(connection, sequences=True)
            self.assertEqual(self.read(connection, names=('empty',)), {'entries': []})
            self.assertEqual(self.read(connection, kind='derive'), {'entries': []})
            for identifier in (identifiers[0], 2**63 - 1):
                with self.subTest(identifier=identifier), self.assertRaises(MycelError) as error:
                    self.read(connection, names=(), identifier=identifier)
                self.assertEqual(error.exception.code, 'refused')
            for names, options, code in ((('unknown',), {}, 'unknown_repository'),
                    (('team',), {}, 'invalid_input'), (('fixture', 'other'), {}, 'invalid_input'),
                    (('fixture',), {'all_repositories': True}, 'invalid_input'),
                    ((), {'identifier': identifiers[-1], 'k': 25}, 'invalid_input'),
                    ((), {'identifier': identifiers[-1], 'kind': 'ingest'}, 'invalid_input'),
                    (('fixture',), {'kind': 'not-a-kind'}, 'invalid_input'),
                    (('fixture',), {'k': 0}, 'invalid_input')):
                with self.subTest(names=names, options=options), self.assertRaises(MycelError) as error:
                    self.read(connection, names=names, **options)
                self.assertEqual(error.exception.code, code)
            self.assertEqual(self.history.state(connection, sequences=True), before)

    def test_public_cli_lists_all_or_named_and_returns_one_detail_without_mutation(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture', 'other')
            own = self.history.seed(connection, 'fixture', 2, kind='embed')
            self.history.seed(connection, 'other', 1, kind='embed')
            global_id, = self.history.seed(connection, None, 1, kind='remove')
            self.history.details(connection, own[-1])
            before = self.history.state(connection, sequences=True)

            @contextmanager
            def connected(credentials):
                yield connection

            with patch('mycel._cli.load_settings', return_value=self.history.settings), \
                    patch('mycel._database.store_connection', connected), \
                    patch('mycel._capture._Capture.capture', side_effect=AssertionError('freshness')), \
                    patch('mycel._credentials.Credentials.embedding_key', side_effect=AssertionError('embedding')):
                for arguments, expected in (
                        (('activity', '--repo', 'fixture'), list(reversed(own))),
                        (('activity', '--all', '--kind', 'remove', '--k', '1'), [global_id]),
                        (('activity', '--entry', str(own[-1])), [own[-1]])):
                    output, diagnostic = StringIO(), StringIO()
                    status = run(arguments, stdout=output, stderr=diagnostic)
                    self.assertEqual((status, diagnostic.getvalue()), (0, ''))
                    reply = json.loads(output.getvalue())
                    self.assertEqual(self.ids(reply), expected)
                    if '--entry' in arguments:
                        self.assertEqual(len(reply['entries'][0]['files']), 1)
                    else:
                        self.assertNotIn('files', reply['entries'][0])
            self.assertEqual(self.history.state(connection, sequences=True), before)

