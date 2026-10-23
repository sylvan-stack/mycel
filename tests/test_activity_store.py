"""Transaction/audit acceptance on the configured per-check disposable store."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import time
import unittest
from unittest.mock import patch
import psycopg
from psycopg.types.json import Jsonb
from mycel import _activity as activity
from mycel import _locks as locks
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._source_refs import SourceAddress
from mycel._declared_refs import DeclaredRefStore
from mycel._markdown import split_markdown
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import read_document_declarations
from mycel._store import search_text


class ActivityStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def seed(self, c):
        c.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) VALUES ('fixture','{}'),('downstream','{}')")

    def write(self, counts=None, **details):
        def callback(c):
            c.execute("UPDATE public.mycel_repository_state SET read_locations = %s WHERE repository='fixture'", (Jsonb(counts or {'applied':1}),))
            return activity.AppliedMutation(True, counts or {'applied':1}, **details)
        return callback

    def entries(self, c):
        return c.execute('SELECT id,repository,kind,outcome,counts FROM public.mycel_activity ORDER BY id').fetchall()

    @proves('MYC-12.1','MYC-12.2','MYC-12.3','MYC-12.4',kind='store')
    def test_lazy_entries_scoped_downstream_counts_and_final_reply_are_exact(self):
        with self.connect() as c:
            self.seed(c)
            with activity.MutationActivity(c,build=1,started_by='freshness_check').session() as audit:
                audit.apply('fixture','ingest',lambda _:activity.AppliedMutation(False))
                self.assertEqual(self.entries(c),[])
                audit.apply('fixture','ingest',self.write({'files':1,'chunks':{'new':2}}))
                audit.apply('fixture','ingest',self.write({'files':2,'chunks':{'new':3}}))
                audit.apply('downstream','ingest',lambda c: (c.execute("UPDATE public.mycel_repository_state SET read_locations='{" + '"stale":true' + "}' WHERE repository='downstream'"),activity.AppliedMutation(True,{'stale':1}))[1])
                self.assertEqual(len(self.entries(c)),2)
                invocation=audit.invocation.id
                audit.finish('done',counts={('fixture','ingest'):{'files':2,'chunks':{'new':3},'reply':'exact'}})
                self.assertTrue(locks.invocation_is_live(c,invocation))
            self.assertFalse(locks.invocation_is_live(c,invocation))

            rows=self.entries(c)
            self.assertEqual(rows[0][1:],('fixture','ingest','done',{'files':2,'chunks':{'new':3},'reply':'exact'}))
            self.assertEqual(rows[1][1:],('downstream','ingest','done',{'stale':1}))
            for row in rows:
                detail=activity.activity_state(c,row[0])
                self.assertEqual(detail['startedBy'],'freshness_check')
                self.assertEqual(detail['build'],1)
                self.assertIsNotNone(detail['endedAt'])
                self.assertEqual(detail['files'],[])
                self.assertEqual(detail['decisions'],[])

    @proves('MYC-12.5','MYC-12.6','MYC-12.7',kind='store')
    def test_file_and_all_code_document_decisions_rollback_with_the_file_and_retry(self):
        with self.connect() as c:
            self.seed(c)
            files=(activity.FileChange('code','a.py','disk','changed'),activity.FileChange('artifact','a.md','topic','added'))
            decisions=(activity.IdentityChange('code','a.py','disk',uuid4(),'renamed','new','old'),
                       activity.IdentityChange('artifact','a.md','topic',uuid4(),'new','section'),
                       activity.IdentityChange('code','a.py','disk',uuid4(),'unchanged','same'))
            with activity.MutationActivity(c,build=1).session() as audit:
                original=audit._details
                def fault(identifier,result):
                    original(identifier,result)
                    raise RuntimeError('public file fault')
                with patch.object(audit,'_details',side_effect=fault):
                    with self.assertRaises(RuntimeError): audit.apply('fixture','ingest',self.write(files=files,decisions=decisions))
                self.assertEqual(self.entries(c),[])
                self.assertEqual(c.execute("SELECT read_locations FROM public.mycel_repository_state WHERE repository='fixture'").fetchone()[0],{})
                audit.apply('fixture','ingest',self.write(files=files,decisions=decisions))
            detail=activity.activity_state(c,self.entries(c)[0][0])
            self.assertEqual(len(detail['files']),2)
            self.assertEqual([r['decision'] for r in detail['decisions']],['new','renamed','unchanged'])
            self.assertEqual(detail['decisions'][1]['previousName'],'old')

    @proves('MYC-12.6','MYC-12.7','MYC-12.4',kind='store')
    def test_later_file_failure_retains_only_applied_prefix_and_sanitized_failure(self):
        with self.connect() as c:
            self.seed(c)
            with self.assertRaises(RuntimeError):
                with activity.MutationActivity(c,build=7).session() as audit:
                    audit.apply('fixture','ingest',self.write({'files':1},files=(activity.FileChange('code','first.py','disk','added'),)))
                    def broken(c):
                        c.execute("UPDATE public.mycel_repository_state SET read_locations='{"+'"files":2'+"}' WHERE repository='fixture'")
                        raise RuntimeError('private-native-sentinel')
                    audit.apply('fixture','ingest',broken)
            rows=self.entries(c)
            self.assertEqual(rows[0][3:],('failed',{'files':1}))
            detail=activity.activity_state(c,rows[0][0])
            self.assertEqual([r['path'] for r in detail['files']],['first.py'])
            self.assertEqual(detail['error'],{'code':'internal','message':'The invocation failed.'})
            self.assertNotIn('private-native-sentinel',str(detail))
            self.assertEqual(c.execute("SELECT read_locations FROM public.mycel_repository_state WHERE repository='fixture'").fetchone()[0],{'files':1})

    @proves('MYC-12.8',kind='store')
    def test_audit_insert_detail_and_close_failures_are_internal_and_atomic(self):
        for point in ('INSERT INTO public.mycel_activity\n','INSERT INTO public.mycel_activity_files','UPDATE public.mycel_activity SET ended_at'):
            with self.connect() as c:
                c.execute('TRUNCATE public.mycel_repository_state CASCADE')
                self.seed(c)
                audit=activity.MutationActivity(c,build=1)
                original=activity._execute
                def failing(connection,statement,parameters=None):
                    if statement.startswith(point):
                        raise activity._audit_failure()
                    return original(connection,statement,parameters)
                with patch('mycel._activity._execute',side_effect=failing):
                    with self.assertRaises(MycelError) as error:
                        with audit.session():
                            audit.apply('fixture','ingest',self.write(files=(activity.FileChange('code','first.py','disk','added'),)))
                self.assertEqual(error.exception.code,'internal')
                rows=self.entries(c)
                if 'ended_at' in point:
                    self.assertEqual(len(rows),1)
                    self.assertEqual(activity.activity_state(c,rows[0][0])['outcome'],'unfinished')
                else:
                    self.assertEqual(rows,[])
                    self.assertEqual(c.execute("SELECT read_locations FROM public.mycel_repository_state WHERE repository='fixture'").fetchone()[0],{})
        with self.connect() as c:
            with patch.object(activity,'_execute',wraps=activity._execute):
                class Faulty:
                    def execute(self,*args): raise psycopg.errors.UniqueViolation('private-native-sentinel')
                with self.assertRaises(MycelError) as error: activity._execute(Faulty(),'INSERT')
                self.assertEqual(error.exception.code,'internal')
                self.assertNotIn('private',str(error.exception))

    @proves('MYC-12.7','MYC-12.14',kind='store')
    def test_exact_session_loss_and_recycled_pid_or_other_lock_never_protect_open_work(self):
        with self.connect() as owner, self.connect() as observer:
            self.seed(owner)
            audit=activity.MutationActivity(owner,build=1)
            session=audit.session(); session.__enter__()
            try:
                audit.apply('fixture','ingest',self.write())
                invocation=audit.invocation
                identifier=self.entries(observer)[0][0]
                self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'running')
                observer.execute('UPDATE public.mycel_invocations SET backend_start=backend_start-interval \'1 second\' WHERE id=%s',(invocation.id,))
                self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                observer.execute('UPDATE public.mycel_invocations SET backend_start=%s WHERE id=%s',(invocation.backend_start,invocation.id))
                # Own generated sessions only; backend PID is not an owner-store target.
                self.assertTrue(observer.execute('SELECT pg_terminate_backend(%s)',(invocation.backend_pid,)).fetchone()[0])
                until=time.monotonic()+2
                while locks.invocation_is_live(observer,invocation) and time.monotonic()<until: time.sleep(.01)
                with locks.operation_guard(observer,'fixture','pass'):
                    self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                with locks._session_guard(observer,invocation.liveness_key,shared=False,message='fixture'):
                    self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                self.assertIsNone(observer.execute('SELECT ended_at FROM public.mycel_activity WHERE id=%s',(identifier,)).fetchone()[0])
            finally:
                try: session.__exit__(RuntimeError,RuntimeError('ended session'),None)
                except MycelError: pass

    @proves('MYC-12.7','MYC-12.14',kind='store')
    def test_live_invocation_cannot_be_adopted_by_another_connection(self):
        with self.connect() as owner, self.connect() as other:
            self.seed(owner)
            with activity.MutationActivity(owner,build=1).session() as audit:
                alien=activity.MutationActivity(other,build=1)
                alien.invocation=audit.invocation
                with self.assertRaises(MycelError) as error:
                    alien.apply('fixture','ingest',self.write())
                self.assertEqual(error.exception.code,'internal')
                self.assertEqual(self.entries(other),[])

    @proves('MYC-12.1','MYC-12.2','MYC-12.3',kind='store')
    def test_global_init_remove_and_noop_reports_leave_only_applied_entries(self):
        with self.connect() as c:
            self.seed(c)
            with activity.MutationActivity(c,build=1).session(): pass
            self.assertEqual(self.entries(c),[])
            with activity.MutationActivity(c,build=1).session() as audit:
                audit.apply(None,'init',self.write({'changed':True}))
                audit.apply(None,'remove',self.write({'removed':'fixture'}))
                audit.apply('fixture','embed',lambda _:activity.AppliedMutation(False,{'parts':0}))
            self.assertEqual([(r[1],r[2],r[4]) for r in self.entries(c)],[(None,'init',{'changed':True}),(None,'remove',{'removed':'fixture'})])

    @proves('MYC-12.1', 'MYC-12.4', 'MYC-12.6', 'MYC-12.7', kind='store')
    def test_caller_transaction_publishes_multiple_repository_audits_together(self):
        with self.connect() as c, self.connect() as observer:
            self.seed(c)
            files = (activity.FileChange('artifact', 'input.md', 'disk', 'added'),)
            decisions = (activity.IdentityChange('artifact', 'input.md', 'disk', uuid4(), 'new', 'Input'),)
            with activity.MutationActivity(c, build=17, started_by='freshness_check').session() as audit:
                with locks.mutation_guard(c, 'fixture'), locks.mutation_guard(c, 'downstream'):
                    with locks.atomic_transaction(c):
                        audit.record_in_transaction('fixture', 'ingest', activity.AppliedMutation(False))
                        self.assertEqual(self.entries(c), [])
                        result = self.write({'files': 1, 'chunksNew': 1}, files=files, decisions=decisions)(c)
                        audit.record_in_transaction('fixture', 'ingest', result)
                        c.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='downstream'",
                                  (Jsonb({'refsChanged': 1}),))
                        audit.record_in_transaction('downstream', 'ingest',
                                                    activity.AppliedMutation(True, {'refsChanged': 1}))
                        self.assertEqual(len(self.entries(c)), 2)
                        self.assertEqual(self.entries(observer), [])
                        self.assertEqual(observer.execute('SELECT read_locations FROM public.mycel_repository_state '
                                                          'ORDER BY repository').fetchall(), [({},), ({},)])
                    self.assertEqual(len(self.entries(observer)), 2)
                invocation = audit.invocation.id
                audit.finish('done', counts={('fixture', 'ingest'): {'files': 1, 'chunksNew': 1, 'refsChecked': 2}})
            rows = self.entries(observer)
            self.assertEqual([row[1:4] for row in rows], [('fixture', 'ingest', 'done'), ('downstream', 'ingest', 'done')])
            self.assertEqual(rows[0][4], {'files': 1, 'chunksNew': 1, 'refsChecked': 2})
            for row in rows:
                detail = activity.activity_state(observer, row[0])
                self.assertEqual(detail['invocation'], invocation)
                self.assertEqual(detail['startedBy'], 'freshness_check')
            self.assertEqual(len(activity.activity_state(observer, rows[0][0])['decisions']), 1)
            self.assertEqual(activity.activity_state(observer, rows[1][0])['files'], [])

    @proves('MYC-12.1', 'MYC-12.6', 'MYC-12.7', 'MYC-12.8', kind='store')
    def test_caller_transaction_late_audit_failure_rolls_back_all_scopes_and_retry(self):
        with self.connect() as c:
            self.seed(c)
            files = (activity.FileChange('code', 'worker.py', 'disk', 'changed'),)
            decisions = (activity.IdentityChange('code', 'worker.py', 'disk', uuid4(), 'unchanged', 'work'),)
            original = activity._execute

            def fail_downstream(connection, statement, parameters=None):
                if statement == activity._OPEN_SQL and parameters[0] == 'downstream':
                    statement = statement.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(connection, statement, parameters)

            with activity.MutationActivity(c, build=17).session() as audit:
                with locks.mutation_guard(c, 'fixture'), locks.mutation_guard(c, 'downstream'):
                    with patch('mycel._activity._execute', side_effect=fail_downstream):
                        with self.assertRaises(MycelError) as error:
                            with locks.atomic_transaction(c):
                                audit.record_in_transaction('fixture', 'ingest',
                                                            self.write(files=files, decisions=decisions)(c))
                                c.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='downstream'",
                                          (Jsonb({'refsChanged': 1}),))
                                audit.record_in_transaction('downstream', 'ingest',
                                                            activity.AppliedMutation(True, {'refsChanged': 1}))
                    self.assertEqual(error.exception.code, 'internal')
                    self.assertNotIn('mycel_missing_activity', str(error.exception))
                    self.assertEqual(self.entries(c), [])
                    self.assertEqual(c.execute('SELECT read_locations FROM public.mycel_repository_state '
                                               'ORDER BY repository').fetchall(), [({},), ({},)])
                    self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_identity_decisions').fetchone()[0], 0)
                    with locks.atomic_transaction(c):
                        audit.record_in_transaction('fixture', 'ingest', self.write(files=files, decisions=decisions)(c))
                        c.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='downstream'",
                                  (Jsonb({'refsChanged': 1}),))
                        audit.record_in_transaction('downstream', 'ingest',
                                                    activity.AppliedMutation(True, {'refsChanged': 1}))
            self.assertEqual([row[1:4] for row in self.entries(c)],
                             [('fixture', 'ingest', 'done'), ('downstream', 'ingest', 'done')])
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_identity_decisions').fetchone()[0], 1)

    @proves('MYC-12.7', 'MYC-12.14', kind='store')
    def test_caller_transaction_requires_own_guarded_live_connection(self):
        with self.connect() as owner, self.connect() as other:
            self.seed(owner)
            with activity.MutationActivity(owner, build=17).session() as audit:
                with self.assertRaises(MycelError) as error:
                    audit.record_in_transaction('fixture', 'ingest', activity.AppliedMutation(True, {'files': 1}))
                self.assertEqual(error.exception.code, 'invalid_input')
                with locks.mutation_guard(other, 'fixture'):
                    # A different connection's removal lock cannot protect
                    # this caller's transaction, even while both are live.
                    with self.assertRaises(MycelError) as error:
                        with locks.atomic_transaction(owner):
                            audit.record_in_transaction('fixture', 'ingest', self.write()(owner))
                    self.assertEqual(error.exception.code, 'invalid_input')
                    alien = activity.MutationActivity(other, build=17)
                    alien.invocation = audit.invocation
                    with self.assertRaises(MycelError) as error:
                        with locks.atomic_transaction(other):
                            alien.record_in_transaction('fixture', 'ingest', self.write()(other))
                    self.assertEqual(error.exception.code, 'internal')
                with locks.mutation_guard(owner, 'fixture'), locks.atomic_transaction(owner):
                    with self.assertRaises(MycelError) as error:
                        audit.record_in_transaction('fixture', 'ingest', {'changed': True})
                    self.assertEqual(error.exception.code, 'internal')
                self.assertEqual(self.entries(owner), [])
                self.assertEqual(owner.execute("SELECT read_locations FROM public.mycel_repository_state WHERE repository='fixture'").fetchone()[0], {})

    @proves('MYC-12.13','MYC-12.4',kind='store')
    def test_classify_bundle_references_counts_and_mechanical_ingest_are_separate(self):
        with self.connect() as c:
            self.seed(c)
            place=SourceAddress('fixture','artifact','note.md','section')
            reference=activity.ClassificationReference('bundle-1',place,'needsReview')
            counts={'selected':1,'completed':0,'needsReview':1,'errors':0,'obsolete':0,'jevCalls':1,'reviewerCalls':0}
            with activity.MutationActivity(c,build=1).session() as audit:
                audit.apply('fixture','ingest',self.write({'eligible':1}))
                audit.apply('fixture','classify',self.write(counts,classifications=(reference,)))
            rows=self.entries(c)
            self.assertEqual(rows[0][2],'ingest'); self.assertEqual(rows[1][2],'classify')
            detail=activity.activity_state(c,rows[1][0])
            self.assertEqual(detail['counts'],counts)
            self.assertEqual(detail['classifications'][0]['dependant'],{'repository':'fixture','root':'artifact','path':'note.md','name':'section','address':place.address})
            self.assertEqual(detail['classifications'][0]['bundle'],'bundle-1')

    @proves('MYC-12.3','MYC-12.7',kind='store')
    def test_cancellation_closes_applied_work_before_releasing_liveness(self):
        with self.connect() as c:
            self.seed(c)
            with self.assertRaises(KeyboardInterrupt):
                with activity.MutationActivity(c,build=1).session() as audit:
                    invocation=audit.invocation
                    audit.apply('fixture','ingest',self.write())
                    raise KeyboardInterrupt()
            row=self.entries(c)[0]
            self.assertEqual(row[3],'stopped')
            self.assertEqual(activity.activity_state(c,row[0])['error'],{'code':'refused','message':'Stopped by the caller.'})
            self.assertFalse(locks.invocation_is_live(c,invocation))


class ActivityDeclaredRefStoreTests(unittest.TestCase):
    """Audit actual retained-reference writes; fixture Builds are test inputs."""
    check_kind = "store"


    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def settings(self, *, target_enabled=True):
        return SettingsSnapshot(Path('/fictional/activity-settings.toml'), _freeze({
            'repos': {'fixture': {'enabled': True}, 'downstream': {'enabled': True},
                      'target': {'enabled': target_enabled}}, 'store': {},}), True, True)

    def document(self, c, repository, path, source, name):
        raw = source.encode()
        file_id, file_version, file_location, chunk_id = (uuid4() for _ in range(4))
        c.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                  (repository, Jsonb([])))
        c.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)',
                  (file_id, repository, 'artifact', path, 'documents'))
        c.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s)',
                  (file_version, file_id, sha256(raw).hexdigest(), raw, Jsonb({})))
        c.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                  (file_location, file_version, 'disk', 'disk', Jsonb({})))
        c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
                  (chunk_id, repository, file_id, 'document', Jsonb({})))
        metadata = {'name': name, 'kind': 'document', 'title': name,
                    'span': {'start': 0, 'end': len(raw)}}
        version = c.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
            (chunk_id, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb({}), Jsonb(metadata))).fetchone()[0]
        c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                  (uuid4(), version, file_location, 'disk', 'disk', Jsonb({})))
        return str(file_location)

    def seed(self, c):
        settings = self.settings()
        store = DeclaredRefStore(c)
        self.document(c, 'target', 'input.md', '# Input\nExact input.\n', 'Input')
        for repository, name in (('fixture', 'Owner'), ('downstream', 'Dependant')):
            source = f'# {name}\n<!-- sources: target:@artifact/input.md#Input -->\n'
            location = self.document(c, repository, 'owner.md', source, name)
            store.retain(settings, location, read_document_declarations(split_markdown(source), file='owner.md'))
        return settings, store

    def entries(self, c):
        return c.execute('SELECT id,repository,kind,outcome,counts FROM public.mycel_activity ORDER BY id').fetchall()

    def dependency_snapshot(self, c):
        return tuple(c.execute(statement).fetchall() for statement in (
            'SELECT id,source_place,state,baseline_owner FROM public.mycel_dependencies ORDER BY id',
            'SELECT dependency,source_version FROM public.mycel_edges ORDER BY dependency,source_version',
            'SELECT id,fault FROM public.mycel_ref_faults ORDER BY id'))

    @proves('MYC-12.1', 'MYC-12.2', 'MYC-12.4', 'MYC-12.7', kind='store')
    def test_real_reference_pass_scopes_downstream_audit_and_unchanged_retry_has_no_entry(self):
        with self.connect() as c:
            settings, store = self.seed(c)
            with activity.MutationActivity(c, build=23, started_by='freshness_check').session() as audit:
                reply = store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
                self.assertEqual((reply.checked, reply.changed), (2, 2))
                invocation = audit.invocation.id
                self.assertEqual([row[3] for row in self.entries(c)], [None, None])
            rows = self.entries(c)
            self.assertEqual([row[1:4] for row in rows],
                             [('downstream', 'ingest', 'done'), ('fixture', 'ingest', 'done')])
            for row in rows:
                detail = activity.activity_state(c, row[0])
                self.assertEqual(detail['invocation'], invocation)
                self.assertEqual(detail['startedBy'], 'freshness_check')
                self.assertEqual(detail['counts'], {'refsChecked': 1, 'refsChanged': 1, 'refFaults': 0})
                self.assertEqual((detail['files'], detail['decisions']), ([], []))
            self.assertEqual(sum(row[4]['refsChanged'] for row in rows), reply.changed)
            before = self.dependency_snapshot(c)
            with activity.MutationActivity(c, build=23, started_by='freshness_check').session() as audit:
                unchanged = store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
                store.list()
            self.assertEqual((unchanged.checked, unchanged.changed), (2, 0))
            self.assertEqual(self.entries(c), rows)
            self.assertEqual(self.dependency_snapshot(c), before)
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()[0], 0)

    @proves('MYC-12.1', 'MYC-12.4', kind='store')
    def test_settings_only_reference_fault_changes_audit_each_unchanged_owner(self):
        with self.connect() as c:
            settings, store = self.seed(c)
            with activity.MutationActivity(c, build=23).session() as audit:
                store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
            sources = c.execute('SELECT id,source_bytes FROM public.mycel_chunk_versions ORDER BY id').fetchall()
            with activity.MutationActivity(c, build=23, started_by='freshness_check').session() as audit:
                reply = store.recheck(self.settings(target_enabled=False), repository='fixture', activity=audit, reply_counts=lambda owner, local: local)
            self.assertEqual((reply.checked, reply.changed, len(reply.faults)), (2, 2, 2))
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_ref_faults').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT id,source_bytes FROM public.mycel_chunk_versions ORDER BY id').fetchall(), sources)
            for row in self.entries(c)[2:]:
                detail = activity.activity_state(c, row[0])
                self.assertEqual(detail['counts'], {'refsChecked': 1, 'refsChanged': 1, 'refFaults': 1})
                self.assertEqual((detail['files'], detail['decisions']), ([], []))
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()[0], 0)

    @proves('MYC-12.7', 'MYC-12.8', kind='store')
    def test_real_reference_writes_rollback_on_native_audit_insert_failure(self):
        with self.connect() as c:
            settings, store = self.seed(c)
            before = self.dependency_snapshot(c)
            original = activity._execute

            def fail_open(connection, statement, parameters=None):
                if statement == activity._OPEN_SQL:
                    statement = statement.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(connection, statement, parameters)

            with patch('mycel._activity._execute', side_effect=fail_open):
                with self.assertRaises(MycelError) as error:
                    with activity.MutationActivity(c, build=23).session() as audit:
                        store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
            self.assertEqual(error.exception.code, 'internal')
            self.assertNotIn('mycel_missing_activity', str(error.exception))
            self.assertEqual(self.entries(c), [])
            self.assertEqual(self.dependency_snapshot(c), before)

    @proves('MYC-12.4', 'MYC-12.7', 'MYC-12.8', kind='store')
    def test_later_owner_audit_failure_preserves_real_applied_prefix_and_retry(self):
        with self.connect() as c:
            settings, store = self.seed(c)
            original = activity._execute

            def fail_second_owner(connection, statement, parameters=None):
                if statement == activity._OPEN_SQL and parameters[0] == 'fixture':
                    statement = statement.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(connection, statement, parameters)

            with patch('mycel._activity._execute', side_effect=fail_second_owner):
                with self.assertRaises(MycelError) as error:
                    with activity.MutationActivity(c, build=23).session() as audit:
                        store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
            self.assertEqual(error.exception.code, 'internal')
            row, = self.entries(c)
            self.assertEqual(row[1:4], ('downstream', 'ingest', 'failed'))
            detail = activity.activity_state(c, row[0])
            self.assertEqual(detail['counts'], {'refsChecked': 1, 'refsChanged': 1, 'refFaults': 0})
            self.assertEqual(detail['error']['code'], 'internal')
            owners = c.execute('SELECT d.repository FROM public.mycel_edges e JOIN '
                'public.mycel_dependencies d ON d.id=e.dependency ORDER BY d.repository').fetchall()
            self.assertEqual(owners, [('downstream',)])
            with activity.MutationActivity(c, build=23).session() as audit:
                reply = store.recheck(settings, repository='target', activity=audit, reply_counts=lambda owner, local: local)
            self.assertEqual((reply.checked, reply.changed), (2, 1))
            self.assertEqual([row[1:4] for row in self.entries(c)],
                             [('downstream', 'ingest', 'failed'), ('fixture', 'ingest', 'done')])

    @proves('MYC-12.2', 'MYC-12.4', kind='store')
    def test_repeated_reference_passes_use_producer_cumulative_and_final_noop_counts(self):
        with self.connect() as c:
            settings, store = self.seed(c)
            committed = {}

            def cumulative(owner, local):
                # A pure preview of the caller's reply: publish counters only
                # after the pass successfully commits, never in this callback.
                previous = committed.get(owner, {})
                return {key: previous.get(key, 0) + value for key, value in local.items()}

            with activity.MutationActivity(c, build=23).session() as audit:
                with self.assertRaises(MycelError) as error:
                    store.recheck(settings, repository='target', activity=audit)
                self.assertEqual(error.exception.code, 'invalid_input')
                self.assertEqual(self.entries(c), [])
                first = store.recheck(settings, repository='target', activity=audit, reply_counts=cumulative)
                self.assertEqual((first.checked, first.changed), (2, 2))
                committed = {owner: {'refsChecked': 1, 'refsChanged': 1, 'refFaults': 0}
                             for owner in ('fixture', 'downstream')}
                second = store.recheck(self.settings(target_enabled=False), repository='fixture',
                                       activity=audit, reply_counts=cumulative)
                self.assertEqual((second.checked, second.changed), (2, 2))
                committed = {owner: {'refsChecked': 2, 'refsChanged': 2, 'refFaults': 1}
                             for owner in committed}
                for row in self.entries(c):
                    self.assertEqual(row[4], committed[row[1]])
                unchanged = store.recheck(self.settings(target_enabled=False), repository='fixture',
                                          activity=audit, reply_counts=cumulative)
                self.assertEqual((unchanged.checked, unchanged.changed), (2, 0))
                # The no-op has no feature write or new audit entry. The
                # producer's final reply includes its completed checks too.
                committed = {owner: {'refsChecked': 3, 'refsChanged': 2, 'refFaults': 2}
                             for owner in committed}
                audit.finish('done', counts={(owner, 'ingest'): counts for owner, counts in committed.items()})
            rows = self.entries(c)
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual(row[3:], ('done', committed[row[1]]))
