"""Configured disposable-store proofs for index-only code projections."""
import json
import math
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._credentials import Secret
from mycel._embedding_plan import load_tokenizer
from mycel._store import TABLES
from mycel._voyage import HTTPResult, VoyageClient

try:
    from . import test_ingest as fixtures
    from .fixtures import EmbeddingStandIn
except ImportError:
    import test_ingest as fixtures
    from fixtures import EmbeddingStandIn


class OverviewStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.IngestStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def write(self, path, source):
        file = self.base.code / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source)
        return file

    def ingest(self, *options):
        status, reply = self.fixture.invoke('--repo', 'fixture', *options)
        self.assertEqual(status, 0, reply)
        return reply['repositories']['fixture']

    def report(self, *options, repository='fixture'):
        output, error = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(['overview', '--repo', repository, *options], stdout=output, stderr=error)
        self.assertEqual((status, error.getvalue()), (0, ''))
        return json.loads(output.getvalue())

    def overview_rows(self, connection):
        return connection.execute("SELECT c.id,v.id,v.source_bytes,l.metadata,l.xmin::text,v.xmin::text,g.state "
            "FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id "
            "JOIN public.mycel_locations l ON l.chunk_version=v.id "
            "JOIN public.mycel_generated_state g ON g.chunk_id=c.id WHERE c.kind='overview' "
            "ORDER BY l.metadata->>'name'").fetchall()

    def state(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    def embed(self, *, fixed_cosines=False):
        service = EmbeddingStandIn(load_tokenizer().counts)
        def transport(body, key, **kwargs):
            request = json.loads(body)
            response = service.request(request)
            if fixed_cosines:
                for row, text in zip(response['data'], request['input'], strict=True):
                    cosine = .9 if text.startswith('overview › ') else .8 if ' (function)\n' in text else .7
                    row['embedding'] = [cosine, math.sqrt(1-cosine*cosine)] + [0.] * 1022
            return HTTPResult(200, json.dumps(response).encode())
        def client(credentials, policy, **kwargs):
            return VoyageClient(credentials, policy, _transport=transport, **kwargs)
        with patch('mycel._embed.VoyageClient', side_effect=client), \
                patch('mycel._credentials.Credentials.require_embedding_key', return_value=Secret('fixture-key')):
            self.ingest('--embed')
        self.assertTrue(service.attempts)
        return service

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_complete_ingest_publishes_all_disk_files_without_checkout_writes_or_branch_stash_names
#     def test_complete_ingest_publishes_all_disk_files_without_checkout_writes_or_branch_stash_names(self):
#         self.write('base/retained.py', 'def branch_only():\n    pass\n')
#         self.base.commit()
#         self.base.git('branch', 'retained')
#         (self.base.code / 'base/retained.py').unlink()
#         self.write('disk/empty.py', '')
#         self.write('disk/run.sh', 'echo loose\n')
#         self.write('disk/symbols.py', 'class One:\n    def first(self):\n        pass\n\ndef other():\n    pass\n')
#         before = self.fixture.physical()
#         with patch('mycel._credentials.Credentials.require_embedding_key') as credential, \
#                 patch('mycel._embed.VoyageClient') as provider:
#             self.ingest()
#             credential.assert_not_called()
#             provider.assert_not_called()
#         self.assertEqual(self.fixture.physical(), before)
#         reply = self.report()
#         self.assertEqual(reply['repository'], 'fixture')
#         self.assertEqual([(section['directory'], section['files'], section['symbols'])
#                           for section in reply['sections']], [('disk', 3, 3)])
#         text = reply['sections'][0]['text']
#         self.assertIn('- **empty.py**\n', text)
#         self.assertIn('- **run.sh**\n', text)
#         self.assertNotIn('branch_only', text)
#         with self.base.connect() as connection:
#             rows = self.overview_rows(connection)
#             self.assertEqual(len(rows), 1)
#             self.assertEqual(bytes(rows[0][2]).decode(), text)
#             self.assertEqual(connection.execute("SELECT file_id,kind FROM public.mycel_chunks WHERE kind='overview'").fetchall(),
#                              [(None, 'overview')])
#             self.assertEqual(connection.execute("SELECT l.file_location,l.kind,l.location FROM public.mycel_locations l "
#                 "JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version JOIN public.mycel_chunks c ON c.id=v.chunk_id "
#                 "WHERE c.kind='overview'").fetchall(), [(None, 'index', 'fixture:@index/overview#disk')])
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_complete_ingest_publishes_all_disk_files_without_checkout_writes_or_branch_stash_names

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_normal_embedding_is_preserved_on_body_only_edits_and_changed_outline_becomes_pending
#     def test_normal_embedding_is_preserved_on_body_only_edits_and_changed_outline_becomes_pending(self):
#         file = self.write('src/work.py', 'def work():\n    return 1\n')
#         self.embed()
#         with self.base.connect() as connection:
#             before = self.overview_rows(connection)
#             version = before[0][1]
#             vectors = connection.execute('SELECT to_jsonb(v),v.xmin::text FROM public.mycel_vectors v '
#                 'JOIN public.mycel_embedding_plans p ON p.id=v.plan_id WHERE p.chunk_version=%s', (version,)).fetchall()
#             self.assertTrue(vectors)
#             contexts, captured = retained_contexts(connection, 'fixture')
#             self.assertEqual((contexts[version].kind, contexts[version].place_line), ('document', 'overview › src'))
#             planned = EmbeddingStore(connection, self.base.settings).prepare('fixture', contexts=contexts,
#                 _captured=captured, persist=False)
#             self.assertTrue(next(item for item in planned.versions if int(item.version.version) == version).complete)
#         file.write_text('def work():\n    return 200\n')
#         self.ingest()
#         with self.base.connect() as connection:
#             self.assertEqual(self.overview_rows(connection), before)
#             self.assertEqual(connection.execute('SELECT to_jsonb(v),v.xmin::text FROM public.mycel_vectors v '
#                 'JOIN public.mycel_embedding_plans p ON p.id=v.plan_id WHERE p.chunk_version=%s', (version,)).fetchall(), vectors)
#         file.write_text('def changed():\n    return 200\n')
#         self.ingest()
#         with self.base.connect() as connection:
#             updated = self.overview_rows(connection)[0]
#             self.assertEqual(updated[0], before[0][0])
#             self.assertNotEqual(updated[1], version)
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_embedding_plans WHERE chunk_version=%s',
#                                                 (updated[1],)).fetchone())
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_normal_embedding_is_preserved_on_body_only_edits_and_changed_outline_becomes_pending

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_order_kind_membership_and_path_changes_update_exact_directories
#     def test_order_kind_membership_and_path_changes_update_exact_directories(self):
#         file = self.write('src/work.py', 'class A:\n    def first(self):\n        pass\n\ndef z():\n    pass\n\ndef a():\n    pass\n')
#         self.write('stable/same.py', 'def unchanged():\n    pass\n')
#         self.ingest()
#         with self.base.connect() as connection:
#             stable = next(row for row in self.overview_rows(connection) if row[3]['name'] == 'stable')
#         file.write_text('class A:\n    pass\n\ndef first():\n    pass\n\ndef a():\n    pass\n\ndef z():\n    pass\n')
#         self.ingest()
#         self.assertIn('A [class]; first, a, z', self.report('--dir', 'src')['sections'][0]['text'])
#         file.write_text('def A():\n    pass\n\ndef first():\n    pass\n\ndef a():\n    pass\n\ndef z():\n    pass\n')
#         self.ingest()
#         self.assertIn('A, first, a, z', self.report('--dir', 'src')['sections'][0]['text'])
#         target = self.base.code / 'dest/renamed.py'
#         target.parent.mkdir()
#         file.rename(target)
#         self.ingest()
#         self.assertEqual(self.report('--dir', 'src')['sections'], [])
#         self.assertIn('**renamed.py**', self.report('--dir', 'dest')['sections'][0]['text'])
#         with self.base.connect() as connection:
#             self.assertEqual(next(row for row in self.overview_rows(connection) if row[3]['name'] == 'stable'), stable)
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_order_kind_membership_and_path_changes_update_exact_directories

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_missing_sections_rebuild_from_store_and_empty_directory_sections_delete
#     def test_missing_sections_rebuild_from_store_and_empty_directory_sections_delete(self):
#         file = self.write('src/work.py', 'def work():\n    pass\n')
#         self.ingest()
#         text = self.report()['sections'][0]['text']
#         with self.base.connect() as connection:
#             original = self.overview_rows(connection)[0]
#             connection.execute("DELETE FROM public.mycel_locations WHERE chunk_version IN "
#                 "(SELECT v.id FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id "
#                 "WHERE c.kind='overview')")
#             file_rows = connection.execute('SELECT to_jsonb(f),xmin::text FROM public.mycel_files f ORDER BY id').fetchall()
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection), \
#                     patch('mycel._capture.capture_repository', side_effect=AssertionError('projection cannot scan')), \
#                     patch.object(Path, 'read_bytes', side_effect=AssertionError('projection cannot reread files')):
#                 self.assertTrue(OverviewStore(connection).reconcile_in_transaction('fixture'))
#             self.assertEqual(connection.execute('SELECT to_jsonb(f),xmin::text FROM public.mycel_files f ORDER BY id').fetchall(),
#                              file_rows)
#             self.assertEqual(self.overview_rows(connection)[0][:3], original[:3])
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind='overview'").fetchone()[0], 1)
#         self.assertEqual(self.report()['sections'][0]['text'], text)
#         file.unlink()
#         self.ingest('--confirm-empty')
#         self.assertEqual(self.report()['sections'], [])
#         with self.base.connect() as connection:
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind='overview'").fetchone()[0], 0)
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_missing_sections_rebuild_from_store_and_empty_directory_sections_delete

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_failed_final_projection_rolls_back_code_and_overview_and_stopped_pass_keeps_committed_prefix
#     def test_failed_final_projection_rolls_back_code_and_overview_and_stopped_pass_keeps_committed_prefix(self):
#         file = self.write('src/work.py', 'def before():\n    pass\n')
#         self.ingest()
#         with self.base.connect() as connection:
#             before = self.fixture.state(connection)
#             overview_before = self.overview_rows(connection)
#         file.write_text('def after():\n    pass\n')
#         original = OverviewStore.reconcile_in_transaction
#         def fail(store, repository):
#             original(store, repository)
#             raise MycelError('refused', 'Fictional final projection failure')
#         with patch.object(OverviewStore, 'reconcile_in_transaction', fail):
#             status, reply = self.fixture.invoke('--repo', 'fixture')
#         self.assertEqual(status, 1, reply)
#         with self.base.connect() as connection:
#             self.assertEqual(self.fixture.state(connection), before)
#             self.assertEqual(self.overview_rows(connection), overview_before)
#             activity_before = connection.execute('SELECT to_jsonb(a),a.xmin::text FROM public.mycel_activity a ORDER BY id').fetchall()
#         def change_physical(store, repository):
#             changed = original(store, repository)
#             file.write_text('def changed_after_projection():\n    pass\n')
#             return changed
#         with patch.object(OverviewStore, 'reconcile_in_transaction', change_physical):
#             status, reply = self.fixture.invoke('--repo', 'fixture')
#         # Since 20 October 2026 the pass publishes the capture it read (MYC-1.37):
#         # the file that changed after the projection is named, and the next
#         # pass takes it up; the overview follows the published capture.
#         self.assertEqual(status, 0, reply)
#         self.assertEqual(reply['repositories']['fixture']['changedDuringPass'], ['fixture:@code/src/work.py'])
#         self.assertIn('after', self.report()['sections'][0]['text'])
#         self.assertNotIn('projection', self.report()['sections'][0]['text'])
#         with self.base.connect() as connection:
#             self.assertNotEqual(self.fixture.state(connection), before)
#             self.assertGreater(len(connection.execute('SELECT id FROM public.mycel_activity').fetchall()),
#                                len(activity_before))
#         status, reply = self.fixture.invoke('--repo', 'fixture')
#         self.assertEqual(status, 0, reply)
#         self.assertNotIn('changedDuringPass', reply['repositories']['fixture'])
#         self.assertIn('projection', self.report()['sections'][0]['text'])
#         file.write_text('def after():\n    pass\n')
#         self.fixture.add_repository('later', b'# Later\nBody\n')
#         from mycel._located_reconciliation import LocatedCaptureStore
#         original_capture = LocatedCaptureStore.capture
#         def capture(store, settings, name):
#             if name == 'later':
#                 raise KeyboardInterrupt()
#             return original_capture(store, settings, name)
#         with patch.object(LocatedCaptureStore, 'capture', capture):
#             status, reply = self.fixture.invoke('--repo', 'fixture', '--repo', 'later')
#         self.assertEqual(status, 2, reply)
#         self.assertTrue(reply['repositories']['fixture']['ran'])
#         self.assertFalse(reply['repositories']['later']['ran'])
#         self.assertIn('after', self.report()['sections'][0]['text'])
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_failed_final_projection_rolls_back_code_and_overview_and_stopped_pass_keeps_committed_prefix

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_search_read_report_origin_no_edges_shared_exclusion_and_document_margin_limit
#     def test_search_read_report_origin_no_edges_shared_exclusion_and_document_margin_limit(self):
#         for directory in ('a', 'b', 'c'):
#             self.write(directory + '/work.py', 'def needle():\n    pass\n')
#         self.base.artifact.joinpath('guide.md').write_text('---\nsources: ["fixture:@index/overview#a"]\n---\n# Guide\nneedle\n')
#         self.embed(fixed_cosines=True)
#         vector = (1.,) + (0.,) * 1023
#         with self.base.connect() as connection:
#             overviews = self.overview_rows(connection)
#             versions = [row[1] for row in overviews]
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_dependencies WHERE dependant_version=ANY(%s)',
#                                                 (versions,)).fetchone())
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_edges WHERE source_version=ANY(%s)',
#                                                 (versions,)).fetchone())
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_stale_reasons WHERE chunk_version=ANY(%s)',
#                                                 (versions,)).fetchone())
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_drifts WHERE dependant_version=ANY(%s)',
#                                                 (versions,)).fetchone())
#             self.assertTrue(connection.execute('SELECT 1 FROM public.mycel_ref_faults').fetchone())
#             before = self.state(connection)
#             options = dict(query_vector=vector, deadline=Deadline.after(30), no_fresh=True)
#             mixed = search_from_store(connection, self.base.settings, 'how needle works', ('fixture',), **options)
#             self.assertEqual(sum(row['origin'] == 'overview' for row in mixed['results']), 2)
#             self.assertTrue(all(row['documentedIn'] == [] for row in mixed['results'] if row['origin'] == 'code'))
#             code = search_from_store(connection, self.base.settings, 'needle', ('fixture',), only='code', **options)
#             self.assertTrue(code['results'])
#             self.assertTrue(all(row['origin'] == 'code' for row in code['results']))
#             docs = search_from_store(connection, self.base.settings, 'needle', ('fixture',), only='docs', **options)
#             self.assertEqual(sum(row['origin'] == 'overview' for row in docs['results']), 3)
#             self.assertTrue(all('file' not in row for row in docs['results'] if row['origin'] == 'overview'))
#             read = read_from_store(connection, self.base.settings, 'fixture:@index/overview#a',
#                                    deadline=Deadline.after(30), no_fresh=True)
#             self.assertEqual((read['origin'], read['text']), ('overview', bytes(overviews[0][2]).decode()))
#             self.assertNotIn('file', read)
#             with StoreCandidates(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
#                 generated = [row for row in snapshot.chunks if row.origin == 'overview']
#                 self.assertEqual(len(generated), 3)
#                 self.assertTrue(all(row.root == 'index' and row.artifact_paths == () for row in generated))
#             with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
#                 self.assertEqual(len(snapshot.sections), 1)
#                 self.assertTrue(all(section.member.chunk.kind == 'document' for section in snapshot.sections))
#                 self.assertTrue(all(section.member.place.root in {'code', 'artifact'} for section in snapshot.sections))
#                 self.assertEqual(snapshot.status()['sections'], {'inSummary': 0, 'inNone': 1, 'notEmbedded': 0})
#             # Shared artifact selection must never import generated sections.
#             other = self.fixture.add_repository('other', b'# Other\nneedle\n')
#             self.base.config.write_text(self.base.config.read_text() +
#                 '\n[search]\nshared_documents=[{repo="fixture",paths=["."]}]\n')
#             settings = load_settings(path=self.base.config, home=self.base.base)
#             with StoreCandidates(connection, settings).snapshot(('other',)) as snapshot:
#                 self.assertFalse(any(row.origin == 'overview' for row in snapshot.candidates('needle')[0].chunks))
#             self.assertEqual(self.state(connection), before)
#         self.assertEqual([row['directory'] for row in self.report()['sections']], ['a', 'b', 'c'])
#         self.assertEqual(len(self.report('--dir', 'b')['sections']), 1)
#         self.assertEqual(self.report(repository='other')['sections'], [])
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_search_read_report_origin_no_edges_shared_exclusion_and_document_margin_limit

# TEST-TIER-DISABLED-BEGIN tests/test_overview_store.py::OverviewStoreTests.test_fresh_search_pass_builds_and_reconciles_the_applied_outline
#     def test_fresh_search_pass_builds_and_reconciles_the_applied_outline(self):
#         file = self.write('src/work.py', 'def needle():\n    return 1\n')
#         with self.base.connect() as connection:
#             reply = search_from_store(connection, self.base.settings, 'needle', ('fixture',), only='code',
#                 deadline=Deadline.after(30), no_fresh=False)
#             self.assertTrue(reply['freshness']['checked'])
#             self.assertTrue(reply['freshness']['finished'])
#             self.assertTrue(self.overview_rows(connection))
#         self.assertIn('needle', self.report()['sections'][0]['text'])
#         file.write_text('def renamed():\n    return 1\n')
#         with self.base.connect() as connection:
#             search_from_store(connection, self.base.settings, 'renamed', ('fixture',), only='code',
#                               deadline=Deadline.after(30), no_fresh=False)
#         self.assertIn('renamed', self.report()['sections'][0]['text'])
# TEST-TIER-DISABLED-END tests/test_overview_store.py::OverviewStoreTests.test_fresh_search_pass_builds_and_reconciles_the_applied_outline

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:2
# from contextlib import ExitStack
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:3
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:8
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:14
# from mycel._embed import retained_contexts
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:16
# from mycel._embedding_store import EmbeddingStore
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:17
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:17
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:18
# from mycel._freshness import Deadline
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:18
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:19
# from mycel._locks import atomic_transaction, operation_guard, snapshot_transaction
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:19
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:20
# from mycel._overview_store import OverviewStore
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:20
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:21
# from mycel._read_store import read_from_store
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:21
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:22
# from mycel._retrieval_store import StoreCandidates
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:22
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:23
# from mycel._search_store import search_from_store
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:23
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:24
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:24
# TEST-TIER-IMPORTS-BEGIN tests/test_overview_store.py:26
# from mycel._summary_store import StoreSummaries
# TEST-TIER-IMPORTS-END tests/test_overview_store.py:26
