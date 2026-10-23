"""Configured disposable-store proofs for complete repository removal."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._activity import MutationActivity
from mycel._collection import CollectionStore
from mycel._coverage import require_check_database
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._freshness import Deadline
from mycel._locks import invocation_guard, mutation_guard, operation_guard, structure_guard
from mycel._repository_removal import RepositoryRemovalStore
from mycel._read_store import read_from_store
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._store import TABLES, search_text
from mycel._verification import ConfirmationStore


class RepositoryRemovalStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('Repository removal checks require a configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_removal_')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.code, self.artifacts = self.root / 'checkout', self.root / 'artifacts'
        self.code.mkdir()
        self.artifacts.mkdir()
        (self.code / 'worker.py').write_text('def work():\n    return 1\n')
        (self.artifacts / 'guide.md').write_text('# Guide\nHistorical source files stay.\n')
        self.config = self.root / 'settings.toml'
        self.configure()

    def configure(self, *, known=True, enabled=True):
        value = '[store]\naddress=' + json.dumps(self.store_fixture.backend.address(self.store_fixture.database)) + '\n'
        if known:
            value += '[repos.fixture]\nenabled=' + str(enabled).lower() + '\ncode_root=' + json.dumps(str(self.code))
            value += '\nartifact_root=' + json.dumps(str(self.artifacts)) + '\n'
        self.config.write_text(value)
        self.settings = load_settings(path=self.config, home=self.root)
        return self.settings

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def state(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
                if table.name not in {'mycel_store', 'mycel_lock_keys', 'mycel_invocations'}}

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    @staticmethod
    def owner(connection, repository, kind, label, *, invocation=None):
        owner = uuid4()
        raw = ('Shared immutable fixture bytes: ' + label).encode()
        digest = sha256(raw).hexdigest()
        manifest = b'{"fixture":"immutable manifest"}'
        manifest_hash = sha256(manifest).hexdigest()
        connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,\'{}\') '
            'ON CONFLICT DO NOTHING', (repository, digest, raw))
        connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,\'baseline\',%s,\'{}\') '
            'ON CONFLICT DO NOTHING', (repository, manifest_hash, manifest))
        connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
            (owner, repository, kind, label, invocation))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
            (owner, repository, digest))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,1)',
            (owner, repository, manifest_hash))
        return owner

    @staticmethod
    def chunk(connection, repository, *, path='guide.md', corpus='documents', synthetic=False):
        file_id, file_version, file_location, chunk = uuid4(), uuid4(), uuid4(), uuid4()
        raw = ('# Guide\n' + repository + ' exact bytes.\n').encode()
        kind = 'summary' if synthetic else 'document' if corpus == 'documents' else 'function'
        if not synthetic:
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,\'artifact\',%s,%s)',
                (file_id, repository, path, corpus))
            connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,\'code\',%s)', (file_id, path))
            connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,\'{}\')',
                (file_version, file_id, sha256(raw).hexdigest(), raw))
            connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,\'disk\',\'disk\',\'{}\')',
                (file_location, file_version))
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,\'{}\')',
            (chunk, repository, None if synthetic else file_id, kind))
        version = connection.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
            'VALUES (%s,%s,%s,%s,\'{}\',\'{}\') RETURNING id',
            (chunk, sha256(raw).hexdigest(), raw, search_text(raw))).fetchone()[0]
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,\'{}\')',
            (uuid4(), version, None if synthetic else file_location,
             'index' if synthetic else 'disk', 'index' if synthetic else 'disk'))
        if synthetic:
            connection.execute('INSERT INTO public.mycel_generated_state VALUES (%s,%s,\'summary\',\'{}\')',
                (chunk, repository))
        return chunk, version

    def seed(self, connection, repository, *, complete=False):
        connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,\'[]\')', (repository,))
        chunk, version = self.chunk(connection, repository)
        baseline = self.owner(connection, repository, 'baseline', 'copied source evidence')
        dependency = uuid4()
        connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,\'asserted\',\'{}\',%s)',
            (dependency, repository, version, 'fixture:@artifact/guide.md#Guide',
             'fixture:@artifact/guide.md#Guide', baseline))
        connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,\'{}\',%s)',
            (uuid4(), repository, version, 'fixture:@artifact/guide.md#Guide', baseline))
        connection.execute('INSERT INTO public.mycel_embedding_receipts (id,repository,model,dimensions,payload) '
            'VALUES (%s,%s,\'voyage-code-4\',1024,%s)', (uuid4(), repository, b'obsolete result'))
        if complete:
            _, code_version = self.chunk(connection, repository, path='worker.py', corpus='code')
            self.chunk(connection, repository, synthetic=True)
            plan = uuid4()
            connection.execute('INSERT INTO public.mycel_embedding_plans VALUES '
                '(%s,%s,\'voyage-code-4\',1024,\'plan\',\'fixture place\',\'{}\',NULL)', (plan, version))
            connection.execute('INSERT INTO public.mycel_embedding_parts VALUES (%s,0,0,1,%s,1,1,NULL)', (plan, b'x'))
            vector = '[' + ','.join(['1'] + ['0'] * 1023) + ']'
            connection.execute('INSERT INTO public.mycel_vectors VALUES (%s,0,\'voyage-code-4\',1024,%s::vector)',
                (plan, vector))
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (dependency, code_version))
            connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,\'fixture ref\',\'{}\')',
                (dependency, repository, version))
            connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,%s,\'{}\')',
                (uuid4(), repository, version, dependency))
            for current in (version, None):
                owner = self.owner(connection, repository, 'drift', str(uuid4()))
                connection.execute('INSERT INTO public.mycel_drifts VALUES '
                    '(%s,%s,%s,clock_timestamp(),NULL,\'{}\',%s)', (uuid4(), repository, current, owner))
            verification = self.owner(connection, repository, 'verification', str(uuid4()))
            connection.execute('INSERT INTO public.mycel_verifications VALUES '
                '(%s,%s,%s,clock_timestamp(),\'{}\',%s)', (uuid4(), repository, chunk, verification))
            lease = self.owner(connection, repository, 'classification', str(uuid4()))
            connection.execute('INSERT INTO public.mycel_classification_work VALUES (%s,%s,%s,NULL,\'{}\',%s)',
                (uuid4(), repository, dependency, lease))
            with invocation_guard(connection) as invocation:
                self.owner(connection, repository, 'classification_lease', str(uuid4()), invocation=invocation.id)
                activity = connection.execute('INSERT INTO public.mycel_activity '
                    '(repository,invocation,index_generation,kind,trigger,build,started_at,ended_at,outcome,counts) '
                    'VALUES (%s,%s,%s,\'ingest\',\'command\',1,clock_timestamp(),clock_timestamp(),\'done\',\'{}\') '
                    'RETURNING id', (repository, invocation.id, invocation.index_generation)).fetchone()[0]
                connection.execute('INSERT INTO public.mycel_activity_files VALUES '
                    '(%s,0,\'artifact\',\'guide.md\',\'disk\',\'added\')', (activity,))
                connection.execute('INSERT INTO public.mycel_identity_decisions VALUES '
                    '(%s,0,\'artifact\',\'guide.md\',\'disk\',%s,\'new\',NULL,\'Guide\')', (activity, chunk))
                connection.execute('INSERT INTO public.mycel_activity_classifications VALUES '
                    '(%s,0,\'fixture bundle\',\'fixture dependant\',\'done\')', (activity,))
        return dependency, version

    def test_removal_counts_complete_owned_state_and_preserves_files_and_foreign_rows(self):
        with self.connect() as connection:
            other_dependency, _ = self.seed(connection, 'other', complete=True)
            foreign = self.state(connection)
            _, version = self.seed(connection, 'fixture', complete=True)
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (other_dependency, version))
            before_files = self.files()
            reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertEqual(reply, {'repository': 'fixture', 'known': True, 'removed': {
                'documents': 1, 'chunks': 3, 'versions': 3, 'vectors': 1, 'edges': 2,
                'evidenceBlobs': 6, 'evidenceManifests': 1, 'drifts': 2, 'verifications': 1}})
            self.assertEqual(self.state(connection), foreign)
            self.assertEqual(self.files(), before_files)

    def test_disabled_forgotten_and_receipt_only_repository_owners_are_removable(self):
        with self.connect() as connection:
            for known, enabled in ((True, False), (False, False)):
                with self.subTest(known=known):
                    self.configure(known=known, enabled=enabled)
                    self.seed(connection, 'fixture')
                    reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                    self.assertIs(reply['known'], known)
                    self.assertEqual(reply['removed']['documents'], 1)
                    self.assertTrue(all(not rows for rows in self.state(connection).values()))
            connection.execute('INSERT INTO public.mycel_embedding_receipts (id,repository,model,dimensions,payload) '
                'VALUES (%s,\'fixture\',\'voyage-code-4\',1024,%s)', (uuid4(), b'receipt without source'))
            reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertFalse(reply['known'])
            self.assertTrue(all(count == 0 for count in reply['removed'].values()))
            self.assertTrue(all(not rows for rows in self.state(connection).values()))

    def test_every_active_operation_and_evidence_mutation_refuses_without_feature_changes(self):
        with self.connect() as connection, self.connect() as peer:
            self.seed(connection, 'fixture')
            for guard in [*(lambda operation=operation: operation_guard(peer, 'fixture', operation)
                           for operation in ('pass', 'embed', 'classify', 'summaries')),
                          lambda: mutation_guard(peer, 'fixture')]:
                with guard():
                    before = self.state(connection)
                    with self.assertRaises(MycelError) as error:
                        RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                    self.assertEqual(error.exception.code, 'busy')
                    self.assertEqual(self.state(connection), before)
            with structure_guard(peer, exclusive=True):
                with self.assertRaises(MycelError) as error:
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                self.assertEqual(error.exception.code, 'busy')

    def test_live_lease_and_running_activity_prevent_removal_until_the_invocation_ends(self):
        with self.connect() as connection, self.connect() as peer:
            self.seed(connection, 'fixture')
            with invocation_guard(peer) as invocation:
                owner = self.owner(peer, 'fixture', 'classification_lease', 'live lease', invocation=invocation.id)
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                self.assertEqual(error.exception.code, 'busy')
                self.assertEqual(self.state(connection), before)
                peer.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (owner,))
                peer.execute('INSERT INTO public.mycel_activity '
                    '(repository,invocation,index_generation,kind,trigger,build,started_at,counts) '
                    'VALUES (\'fixture\',%s,%s,\'classify\',\'command\',1,clock_timestamp(),\'{}\')',
                    (invocation.id, invocation.index_generation))
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                self.assertEqual(error.exception.code, 'busy')
                self.assertEqual(self.state(connection), before)
            RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertTrue(all(not rows for rows in self.state(connection).values()))

    def test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards(self):
        with self.connect() as connection, self.connect() as peer:
            self.seed(connection, 'fixture', complete=True)
            before = self.state(connection)
            actual = CollectionStore.remove_repository_in_transaction
            def fail(store, *args, **kwargs):
                actual(store, *args, **kwargs)
                raise RuntimeError('Fixture failure after repository deletion.')
            with patch.object(CollectionStore, 'remove_repository_in_transaction', fail):
                with self.assertRaises(RuntimeError):
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertEqual(self.state(connection), before)
            reply = RepositoryRemovalStore(peer).remove(self.settings, 'fixture')
            self.assertEqual(reply['removed']['chunks'], 3)

    def test_busy_foreign_dependant_blocks_edge_cascade_without_partial_removal(self):
        with self.connect() as connection, self.connect() as peer:
            foreign, _ = self.seed(connection, 'other')
            _, source = self.seed(connection, 'fixture')
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (foreign, source))
            with operation_guard(peer, 'other', 'pass'):
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
                self.assertEqual(error.exception.code, 'busy')
                self.assertEqual(self.state(connection), before)

    def test_configured_empty_repository_is_noop_and_unknown_absent_name_is_refused(self):
        with self.connect() as connection:
            reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertTrue(all(count == 0 for count in reply['removed'].values()))
            before = self.state(connection)
            with self.assertRaises(MycelError) as error:
                RepositoryRemovalStore(connection).remove(self.settings, 'forgotten')
            self.assertEqual(error.exception.code, 'unknown_repository')
            self.assertEqual(self.state(connection), before)
            self.configure(enabled=False)
            with self.assertRaises(MycelError) as error:
                RepositoryRemovalStore(connection).remove(load_settings(path=self.config, home=self.root), '\0')
            self.assertEqual(error.exception.code, 'invalid_input')

    def test_settings_change_before_commit_rolls_back_the_whole_removal(self):
        with self.connect() as connection:
            self.seed(connection, 'fixture')
            before = self.state(connection)
            actual = CollectionStore.remove_repository_in_transaction
            def change_settings(store, *args, **kwargs):
                result = actual(store, *args, **kwargs)
                self.configure(enabled=False)
                return result
            with patch.object(CollectionStore, 'remove_repository_in_transaction', change_settings):
                with self.assertRaises(MycelError) as error:
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(self.state(connection), before)

    def test_numbered_removal_records_exact_global_activity_and_audit_failure_rolls_back(self):
        with self.connect() as connection:
            self.seed(connection, 'fixture', complete=True)
            before = self.state(connection)
            with patch.object(MutationActivity, 'record_in_transaction',
                              side_effect=MycelError('internal', 'Fixture audit failure.')):
                with self.assertRaises(MycelError):
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
            self.assertEqual(self.state(connection), before)
            reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
            rows = connection.execute('SELECT repository,kind,outcome,counts FROM public.mycel_activity').fetchall()
            self.assertEqual(rows, [(None, 'remove', 'done', reply)])
            self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
                'WHERE repository=\'fixture\'').fetchone())

    def test_activity_close_failure_preserves_committed_counts_and_reports_error(self):
        with self.connect() as connection:
            self.seed(connection, 'fixture')
            with patch.object(MutationActivity, 'finish',
                              side_effect=MycelError('internal', 'Fixture activity close failure.')):
                reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
            self.assertEqual(reply['removed']['documents'], 1)
            self.assertEqual(reply['countsState'], 'committed_prefix')
            self.assertEqual(reply['error']['code'], 'internal')
            self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
                'WHERE repository=\'fixture\'').fetchone())
            audit = connection.execute('SELECT repository,kind,counts FROM public.mycel_activity').fetchall()
            self.assertEqual(audit, [(None, 'remove', {key: value for key, value in reply.items()
                if key not in {'error', 'countsState'}})])

    def test_interrupt_after_commit_preserves_removed_counts_and_reports_interruption(self):
        with self.connect() as connection:
            self.seed(connection, 'fixture')
            with patch.object(MutationActivity, 'finish', side_effect=KeyboardInterrupt):
                reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
            self.assertEqual(reply['removed']['documents'], 1)
            self.assertEqual(reply['countsState'], 'committed_prefix')
            self.assertEqual(reply['stopped'], 'interrupted')
            self.assertEqual(reply['error']['code'], 'refused')
            self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
                'WHERE repository=\'fixture\'').fetchone())


class RepositoryRemovalEvidenceStoreTests(unittest.TestCase):
    check_kind = "store"

    def test_removed_source_keeps_dependant_baseline_and_projects_missing_source_without_writing(self):
        try:
            from . import test_dependency_source_refresh as fixtures
        except ImportError:
            import test_dependency_source_refresh as fixtures
        fixture = fixtures.DependencySourceRefreshStoreTests()
        fixture.store_fixture = self.store_fixture
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with fixture.base.connect() as connection:
            fixture.prepare(connection)
            dependency = fixture.dependencies(connection)[0]
            baseline = EvidenceStore(connection).read_baseline('downstream', dependency[7])
            owned_tables = [table for table in TABLES if any(column.name == 'repository' for column in table.columns)]
            def foreign():
                return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                    'WHERE repository=\'downstream\' ORDER BY to_jsonb(t)::text').fetchall() for table in owned_tables}
            before = foreign()
            reply = RepositoryRemovalStore(connection).remove(fixture.base.settings, 'fixture')
            self.assertGreater(reply['removed']['edges'], 0)
            self.assertEqual(foreign(), before)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', dependency[7]), baseline)
            resolver = SourceResolver.from_store(connection, fixture.base.settings)
            self.assertEqual(resolver.resolve(dependency[3]).fault, 'missing_file')
            read = read_from_store(connection, fixture.base.settings, 'downstream:@artifact/answer.md#Answer',
                no_fresh=True, deadline=Deadline.after(30))
            self.assertEqual(read['dependencyCheck']['faults'][0]['fault'], 'not_found')
            self.assertEqual(read['dependencyCheck']['faults'][0]['ref'], dependency[3])
            self.assertEqual(foreign(), before)

    def test_repin_and_evidence_collection_roll_back_together_and_keep_protected_history(self):
        try:
            from . import test_dependency_source_refresh as fixtures
        except ImportError:
            import test_dependency_source_refresh as fixtures
        fixture = fixtures.DependencySourceRefreshStoreTests()
        fixture.store_fixture = self.store_fixture
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with fixture.base.connect() as connection:
            fixture.prepare(connection)
            ConfirmationStore(connection).apply(fixture.base.settings, 'downstream:@artifact/answer.md#Answer',
                by='owner', captured_at='2026-10-09T12:00:00Z')
            protected_id = fixture.dependencies(connection)[0][7]
            protected = EvidenceStore(connection).read_baseline('downstream', protected_id)
            fixture.source.write_bytes(b'# Source\nChanged source for authorized repin.\n')
            fixture.publish(connection)
            orphan = b'Wholly unreferenced disposable evidence.'
            orphan_hash = sha256(orphan).hexdigest()
            connection.execute('INSERT INTO public.mycel_snapshots VALUES (\'downstream\',%s,%s,\'{}\')',
                (orphan_hash, orphan))
            def contents():
                return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                    'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
                    if table.name not in {'mycel_store', 'mycel_lock_keys', 'mycel_invocations'}}
            before = contents()
            actual = EvidenceStore._collect
            def fail_after_collection(store, repository):
                actual(store, repository)
                self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
                    'WHERE repository=\'downstream\' AND hash=%s', (orphan_hash,)).fetchone())
                self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_manifests '
                    'WHERE repository=\'downstream\' AND hash=%s', (protected_id,)).fetchone())
                raise RuntimeError('Fixture failure after new capture, repin and evidence collection.')
            with patch.object(EvidenceStore, '_collect', fail_after_collection):
                with self.assertRaises(RuntimeError):
                    fixture.apply_assertions(connection, mode='confirm')
            self.assertEqual(contents(), before)
            fixture.apply_assertions(connection, mode='confirm')
            self.assertNotEqual(fixture.dependencies(connection)[0][7], protected_id)
            self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
                'WHERE repository=\'downstream\' AND hash=%s', (orphan_hash,)).fetchone())
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', protected_id), protected)
            RepositoryRemovalStore(connection).remove(fixture.base.settings, 'fixture')
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', protected_id), protected)
            RepositoryRemovalStore(connection).remove(fixture.base.settings, 'downstream')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_references').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone(), (0,))
