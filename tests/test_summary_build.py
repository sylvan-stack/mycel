"""Real-store proofs of complete private summary builds with local services."""

from dataclasses import replace
from hashlib import sha256
import json
import math
import io
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psycopg.types.json import Jsonb

from mycel._cli import Invocation
from mycel._credentials import Secret
from mycel._coverage import proves
from mycel._embedding_plan import load_tokenizer
from mycel._errors import MycelError
from mycel._freshness import Deadline
from mycel._locks import operation_guard, removal_guard
from mycel._resolver import SourceResolver
from mycel._search_store import search_from_store
from mycel._settings import load_settings
from mycel._store import TABLES, checked_store
from mycel._summary_build import build_summaries
from mycel._summary_store import StoreSummaries
from mycel._summary_writer import WriterResult
from mycel._voyage import EmbeddingProgress, HTTPResult, PartIdentity, VectorWrite, VoyageClient

try:
    from . import test_located_reconciliation as located
    from . import test_retrieval_store as embeddings
except ImportError:
    import test_located_reconciliation as located
    import test_retrieval_store as embeddings


class LocalWriter:
    def __init__(self, callback=None, failure=None, response=b' summaryneedle Complete answer \r\n\0end. '):
        self.callback, self.failure, self.requests, self.response = callback, failure, [], response

    def write_many(self, requests):
        self.requests.extend(requests)
        if self.callback:
            self.callback(requests)
        if self.failure:
            return tuple(WriterResult(None, self.failure, 2) for _ in requests)
        return tuple(WriterResult(self.response, None, 1) for _ in requests)


class LocalEmbedding:
    def __init__(self, callback=None, fail=False, cancelled=False, vector=None):
        self.callback, self.fail, self.cancelled = callback, fail, cancelled
        self.vector = vector
        self.batches = []

    def embed_repository(self, repository, batches, *, commit, record_failures):
        self.batches.append(batches)
        if self.callback:
            self.callback(batches)
        if self.fail or self.cancelled:
            return EmbeddingProgress(repository, 0, 0, 0, 0, 0, 0,
                'local failure', 'cancelled' if self.cancelled else 'authentication')
        writes = tuple(VectorWrite(PartIdentity(item.repository, item.chunk_id, item.chunk_version, item.part_order),
            batch.model, batch.dimensions, self.vector(item, batch.dimensions) if self.vector else
                (1.0,) + (0.0,) * (batch.dimensions - 1))
            for batch in batches for item in batch.inputs)
        commit(writes)
        return EmbeddingProgress(repository, len(writes), 0, 0, len(writes), len(batches), 1)


class SummaryBuildStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = located.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()
        self.base.config.write_text(self.base.config.read_text() + '\n[summaries]\nat_once=3\ncommand=' +
            json.dumps([sys.executable, '-c', 'import sys; sys.stdin.buffer.read(); print("summaryneedle")']) + '\n')
        self.reload()
        self.tokenizer = load_tokenizer()
        self.embedding_fixture = embeddings.RetrievalStoreTests()
        self.embedding_fixture.store_fixture = self.store_fixture

    def reload(self):
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)

    def prepare(self, connection, *, count=12):
        for number in range(count - 1):
            (self.base.artifact / f'note{number:02}.md').write_text(f'# Part{number}\nleafneedle section {number}.\n')
        self.base.apply(connection)
        resolver = SourceResolver.from_store(connection, self.base.settings)
        for file in resolver.files:
            for chunk in file.chunks:
                if chunk.kind == 'document':
                    self.embedding_fixture.plan(connection, chunk.identifier, chunk.version,
                        chunk.source.decode(), vectors=((0.0, 1.0),))

    def build(self, connection, *, writer=None, client=None, before_publish=None, repository='fixture', tokenizer=None):
        return build_summaries(Invocation('summaries', repositories=(repository,), arguments=('build',),
            settings=self.base.settings), _store=(connection, None), _writer=None if writer is False else writer or LocalWriter(),
            _client=client or LocalEmbedding(), _tokenizer=tokenizer or self.tokenizer, _before_publish=before_publish)

    def search(self, connection, query='summaryneedle', **options):
        return search_from_store(connection, self.base.settings, query, ('fixture',), no_fresh=True,
            deadline=Deadline.after(30), query_vector=(1.0,) + (0.0,) * 1023, **options)

    def summaries(self, connection):
        return connection.execute("SELECT c.id,v.id,v.source_bytes,g.state FROM public.mycel_chunks c "
            "JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_generated_state g ON g.chunk_id=c.id "
            "WHERE c.kind='summary' ORDER BY g.state->>'level',g.state->>'chunkVersion'").fetchall()

    def state(self, connection):
        return {table: connection.execute(f'SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
            for table in ('mycel_chunks', 'mycel_chunk_versions', 'mycel_locations', 'mycel_dependencies', 'mycel_edges',
                          'mycel_generated_state', 'mycel_embedding_plans', 'mycel_embedding_parts', 'mycel_vectors')}

    def no_leases(self, connection):
        self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL").fetchone(), (0,))

    @proves('MYC-8.13', 'MYC-8.14', 'MYC-8.15', 'MYC-8.26', kind='store')
    def test_public_build_publishes_exact_text_complete_vectors_pins_and_new_versions_atomically(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            result = self.build(connection)
            self.assertEqual((result.status, result.value['written'], result.value['replaced']), (0, 1, True))
            first = self.summaries(connection)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0][2], b' summaryneedle Complete answer \r\n\0end. ')
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='generated'").fetchone(), (12,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p ON p.id=v.plan_id '
                'WHERE p.chunk_version=%s', (first[0][1],)).fetchone(), (1,))
            self.no_leases(connection)
            second_result = self.build(connection)
            second = self.summaries(connection)
            self.assertEqual(second_result.value['written'], 1)
            self.assertNotEqual(first[0][:2], second[0][:2])
            self.assertEqual(second[0][2], first[0][2])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                (first[0][1],)).fetchone(), (0,))
            self.no_leases(connection)

    @proves('MYC-8.14', 'MYC-8.26', kind='store')
    def test_real_lower_response_vectors_feed_higher_groups_with_no_searchable_staging(self):
        with self.base.connect() as connection:
            self.prepare(connection, count=24)
            self.build(connection)
            old = self.state(connection)
            observations = []

            def grouping(nodes):
                observations.append(tuple(nodes))
                if len(observations) == 1:
                    return tuple(tuple(nodes[index:index+2]) for index in range(0, len(nodes), 2))
                self.assertTrue(all(node.place.root == 'index' and node.vector[0] == 1 for node in nodes))
                self.assertTrue(all(node.section.member.chunk.source.startswith(b' summaryneedle') for node in nodes))
                return (tuple(nodes),)

            def during(_):
                self.assertEqual(self.state(connection), old)
                self.assertEqual(sum(row['origin'] == 'summary'
                    for row in self.search(connection, only='docs')['results']), 1)

            writer, client = LocalWriter(during), LocalEmbedding(during)
            with patch('mycel._summary_build.group_summary_nodes', side_effect=grouping):
                result = self.build(connection, writer=writer, client=client)
            self.assertEqual((result.status, result.value['written']), (0, 13))
            self.assertEqual([len(nodes) for nodes in observations], [24, 12])
            self.assertEqual(len(client.batches), 2)
            self.assertEqual(len(self.summaries(connection)), 13)
            upper = next(row for row in self.summaries(connection) if row[3]['level'] == 2)
            self.assertEqual(len(upper[3]['members']), 12)
            self.no_leases(connection)

    @proves('MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_generation_embedding_and_interruption_preserve_old_tree_and_release_private_leases(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.state(connection)
            for writer, client, expected in ((LocalWriter(failure='nonzero_exit'), LocalEmbedding(), 'failed'),
                    (LocalWriter(), LocalEmbedding(fail=True), 'failed'),
                    (LocalWriter(), LocalEmbedding(cancelled=True), 'interrupted')):
                with self.subTest(expected=expected, embedding=client.fail):
                    result = self.build(connection, writer=writer, client=client)
                    self.assertEqual(result.value['stopped'], expected)
                    self.assertFalse(result.value['replaced'])
                    self.assertEqual(self.state(connection), old)
                    self.no_leases(connection)

    @proves('MYC-8.15', 'MYC-8.26', kind='store')
    def test_exact_physical_source_settings_and_late_audit_changes_discard_whole_tree(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.state(connection)
            original = (self.base.artifact / 'guide.md').read_bytes()
            result = self.build(connection, before_publish=lambda: (self.base.artifact / 'guide.md').write_bytes(b'# Guide\nchanged\n'))
            self.assertEqual(result.value['stopped'], 'inputs_changed')
            self.assertEqual(self.state(connection), old)
            (self.base.artifact / 'guide.md').write_bytes(original)
            config = self.base.config.read_bytes()
            result = self.build(connection, before_publish=lambda: self.base.config.write_bytes(config.replace(b'at_once=3', b'at_once=2')))
            self.assertEqual(result.value['stopped'], 'inputs_changed')
            self.assertEqual(self.state(connection), old)
            self.base.config.write_bytes(config)
            self.no_leases(connection)

    @proves('MYC-8.15', 'MYC-8.26', kind='store')
    def test_empty_eligible_replacement_keeps_complete_set_metadata_without_service_calls(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            connection.execute('DELETE FROM public.mycel_vectors')
            writer, client = LocalWriter(lambda _: self.fail('empty build called writer')), LocalEmbedding(lambda _: self.fail('empty build called embedding'))
            result = self.build(connection, writer=writer, client=client)
            self.assertEqual((result.status, result.value['written'], result.value['replaced']), (0, 0, True))
            self.assertEqual(self.summaries(connection), [])
            with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
                status = snapshot.status()
                self.assertEqual(status['levels'], [])
                self.assertEqual(status['sections']['notEmbedded'], 12)
                self.assertEqual(status['groupingProfile'], 'mycel-summary-v1')
                self.assertTrue(status['builtAt'])
                self.assertEqual(set(status['numericalVersions']), {'numpy', 'scipy', 'scikit-learn'})
            self.no_leases(connection)

    @proves('MYC-8.22', 'MYC-8.19', kind='store')
    def test_published_tree_competes_as_own_documents_has_no_file_code_bridge_or_search_mutations(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            before = self.state(connection)
            docs = self.search(connection, only='docs')
            summary = next(row for row in docs['results'] if row['origin'] == 'summary')
            self.assertEqual(summary['root'], 'index')
            self.assertNotIn('file', summary)
            self.assertEqual(summary['documentedIn'], [])
            self.assertFalse(summary.get('via'))
            self.assertTrue(summary['unreadable'])
            mixed = self.search(connection)
            self.assertIn('summary', [row['origin'] for row in mixed['results']])
            code = self.search(connection, only='code')
            self.assertNotIn('summary', [row['origin'] for row in code['results']])
            self.assertEqual(self.state(connection), before)

    @proves('MYC-8.29', 'MYC-8.26', kind='store')
    def test_ingest_pass_is_unlocked_during_calls_competing_mutations_and_removal_are_busy(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.summaries(connection)

            def during(_):
                with self.base.connect() as other, checked_store(other):
                    with operation_guard(other, 'fixture', 'pass'):
                        pass
                    for guard in (lambda: operation_guard(other, 'fixture', 'summaries'),
                                  lambda: removal_guard(other, 'fixture')):
                        with self.assertRaises(MycelError) as error:
                            with guard():
                                self.fail('competing mutation acquired lock')
                        self.assertEqual(error.exception.code, 'busy')
                    (self.base.artifact / 'guide.md').write_bytes(b'# Guide\nchanged while writer ran\n')
                    self.base.apply(other)

            result = self.build(connection, writer=LocalWriter(during))
            self.assertEqual(result.value['stopped'], 'inputs_changed')
            self.assertEqual(self.summaries(connection), old)
            self.no_leases(connection)

    @proves('MYC-8.19', kind='store')
    def test_complete_ingest_does_not_generate_rewrite_or_repin_existing_summaries(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.summaries(connection)
            pins = connection.execute("SELECT to_jsonb(d) FROM public.mycel_dependencies d WHERE kind='generated' ORDER BY id").fetchall()
            (self.base.artifact / 'note00.md').write_text('# Part0\nchanged leaf\n')
            with patch('mycel._summary_writer.SummaryWriter', side_effect=AssertionError('ingest generated')):
                self.base.apply(connection)
            self.assertEqual(self.summaries(connection), old)
            self.assertEqual(connection.execute("SELECT to_jsonb(d) FROM public.mycel_dependencies d WHERE kind='generated' ORDER BY id").fetchall(), pins)

    @proves('MYC-8.22', 'MYC-8.19', kind='store')
    def test_real_tree_uses_shared_document_margin_limit_and_retains_stale_generated_annotations(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            code_path = self.base.code / 'main.py'
            code_path.write_text('def summaryneedle():\n    return 1\n')
            self.base.apply(connection)
            resolver = SourceResolver.from_store(connection, self.base.settings)
            for file in resolver.files:
                for chunk in file.chunks:
                    if chunk.kind == 'function':
                        self.embedding_fixture.plan(connection, chunk.identifier, chunk.version,
                            chunk.source.decode(), vectors=((0.8, 0.6),))

            def vector(item, dimensions):
                ordinal = int(item.input_text.split('\n')[0].split('/')[-1])
                cosine = (0.82, 0.84, 0.95)[ordinal - 1]
                return (cosine, math.sqrt(1 - cosine*cosine)) + (0.0,) * (dimensions - 2)

            with patch('mycel._summary_build.group_summary_nodes',
                    side_effect=lambda nodes: tuple(tuple(nodes[i:i+4]) for i in range(0, len(nodes), 4))):
                self.assertEqual(self.build(connection, client=LocalEmbedding(vector=vector)).value['written'], 3)
            docs = self.search(connection, only='docs')
            self.assertEqual(sum(row['origin'] == 'summary' for row in docs['results']), 3)
            mixed = self.search(connection)
            summary_names = {row['name'] for row in mixed['results'] if row['origin'] == 'summary'}
            self.assertEqual(summary_names, {'1/2', '1/3'})
            code = next(row for row in mixed['results'] if row['kind'] == 'function')
            self.assertEqual(code['documentedIn'], [])
            self.assertNotIn('via', code)
            old = self.summaries(connection)
            (self.base.artifact / 'guide.md').write_text('# Guide\nchanged pinned source.\n')
            self.base.apply(connection)
            self.assertEqual(self.summaries(connection), old)
            stale = [row for row in self.search(connection, only='docs')['results']
                     if row['origin'] == 'summary' and row['stale']]
            self.assertEqual([row['name'] for row in stale], ['1/1'])
            self.assertTrue(stale[0]['staleReasons'])

    @proves('MYC-8.14', 'MYC-8.22', kind='store')
    def test_actual_multipart_summary_search_uses_best_part_and_excludes_other_shared_repository_trees(self):
        from mycel._capture import capture_repository
        from mycel._located_reconciliation import LocatedCaptureStore
        with self.base.connect() as connection:
            self.prepare(connection)
            small = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=60))
            client = LocalEmbedding(vector=lambda item, dimensions:
                ((0.0, 1.0) if item.part_order == 0 else (1.0, 0.0)) + (0.0,) * (dimensions - 2))
            response = ('summaryneedle complete response line.\n' * 60).encode()
            self.assertTrue(self.build(connection, writer=LocalWriter(response=response), client=client,
                                       tokenizer=small).value['replaced'])
            summary = self.summaries(connection)[0]
            count = connection.execute('SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p '
                'ON p.id=v.plan_id WHERE p.chunk_version=%s', (summary[1],)).fetchone()[0]
            self.assertGreater(count, 1)
            found = next(row for row in self.search(connection, only='docs')['results'] if row['origin'] == 'summary')
            self.assertEqual(found['id'], str(summary[0]))
            from mycel._retrieval_store import StoreCandidates
            with StoreCandidates(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
                candidates = snapshot.candidates('unmatchedword', (1.0,) + (0.0,) * 1023, only='docs')[0]
                meaningful = next(item for item in candidates.meaning if item.chunk.identifier == str(summary[0]))
                self.assertAlmostEqual(meaningful.score, 1.0)
                self.assertEqual(meaningful.chunk.part_vectors[0][0], 0.0)
                self.assertEqual(meaningful.chunk.part_vectors[-1][0], 1.0)
                self.assertFalse(any(item.chunk.identifier == str(summary[0]) for item in candidates.wording))
            # Both entire trees come from actual build publication, so shared
            # document aliases cannot accidentally expose a foreign summary.
            other = self.base.base / 'other-documents'
            other.mkdir()
            for number in range(12):
                (other / f'note{number}.md').write_text(f'# Foreign{number}\nforeignneedle leaf.\n')
            self.base.config.write_text(self.base.config.read_text() + '\n[repos.other]\nenabled=true\nartifact_root=' +
                json.dumps(str(other)) + '\n[search]\nshared_documents=[{repo="other",paths=["."]}]\n')
            self.reload()
            LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'other'))
            resolver = SourceResolver.from_store(connection, self.base.settings)
            for file in resolver.files:
                if file.repository == 'other':
                    for chunk in file.chunks:
                        self.embedding_fixture.plan(connection, chunk.identifier, chunk.version,
                            chunk.source.decode(), repository='other', vectors=((0.0, 1.0),))
            foreign = self.build(connection, repository='other', writer=LocalWriter(response=b'foreignsummaryneedle complete summary\n'))
            self.assertTrue(foreign.value['replaced'])
            reply = self.search(connection, 'foreignsummaryneedle', only='docs')
            self.assertFalse(any(row['repository'] == 'other' and row['origin'] == 'summary'
                                 for row in reply['results']))
            from mycel._retrieval_store import StoreCandidates
            with StoreCandidates(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
                candidates = snapshot.candidates('foreignsummaryneedle', (1.0,) + (0.0,) * 1023, only='docs')[0]
                self.assertFalse(any(chunk.repository == 'other' and chunk.origin == 'summary'
                                     for chunk in candidates.chunks))
                self.assertFalse(any(item.chunk.repository == 'other' and item.chunk.origin == 'summary'
                                     for item in (*candidates.meaning, *candidates.wording)))

    @proves('MYC-8.13', 'MYC-8.14', 'MYC-8.15', 'MYC-8.29', kind='store')
    def test_public_cli_uses_real_writer_and_validated_embedding_adapter_with_local_service(self):
        from fixtures import EmbeddingStandIn
        from mycel._cli import run
        with self.base.connect() as connection:
            self.prepare(connection)
            service = EmbeddingStandIn(self.tokenizer.counts)
            requests = []

            def transport(body, key, **options):
                self.assertEqual(key.reveal(), 'public-local-summary-check')
                requests.append(json.loads(body))
                with self.base.connect() as observer:
                    self.assertEqual(self.summaries(observer), [])
                    with checked_store(observer), operation_guard(observer, 'fixture', 'pass'):
                        pass
                return HTTPResult(200, json.dumps(service.request(requests[-1])).encode())

            def client(credentials, policy, **options):
                return VoyageClient(credentials, policy, _transport=transport, **options)

            output, diagnostics = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                    patch('mycel._summary_build.VoyageClient', side_effect=client), \
                    patch('mycel._credentials.Credentials.require_embedding_key', return_value=Secret('public-local-summary-check')):
                status = run(['summaries', 'build', '--repo', 'fixture'], stdout=output, stderr=diagnostics)
            self.assertEqual(diagnostics.getvalue(), '')
            self.assertEqual(status, 0, output.getvalue())
            reply = json.loads(output.getvalue())
            self.assertTrue(reply['replaced'])
            self.assertEqual(reply['notEmbedded'], 0)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]['input_type'], 'document')
            self.assertFalse(requests[0]['truncation'])
            self.assertEqual(self.summaries(connection)[0][2], b'summaryneedle\n')
            self.no_leases(connection)

    @proves('MYC-8.15', 'MYC-8.29', kind='store')
    def test_interrupt_after_confirmed_commit_reports_the_actual_published_tree(self):
        from mycel._summary_publication import SummaryPublicationStore
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.summaries(connection)
            original = SummaryPublicationStore.confirm_release

            def committed_then_interrupted(store):
                original(store)
                raise KeyboardInterrupt

            with patch.object(SummaryPublicationStore, 'confirm_release', committed_then_interrupted):
                result = self.build(connection)
            self.assertEqual(result.status, 0)
            self.assertEqual((result.value['written'], result.value['replaced']), (1, True))
            self.assertNotIn('stopped', result.value)
            self.assertNotEqual(self.summaries(connection)[0][:2], old[0][:2])
            self.no_leases(connection)

    @proves('MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_configuration_changed_at_actual_writer_launch_stops_without_child_retry_or_replacement(self):
        from mycel._summary_writer import SummaryWriter
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.state(connection)
            config = self.base.config.read_bytes()
            launches = []

            def writer(command, at_once, *, before_launch):
                def changed_guard():
                    launches.append('guard')
                    self.base.config.write_bytes(config.replace(b'at_once=3', b'at_once=2'))
                    before_launch()
                return SummaryWriter(command, at_once, before_launch=changed_guard)

            with patch('mycel._summary_build.SummaryWriter', side_effect=writer), \
                    patch('mycel._summary_writer.subprocess', SimpleNamespace(
                        PIPE=-1, Popen=lambda *a, **kw: self.fail('obsolete request launched a child'))):
                result = self.build(connection, writer=False)
            self.assertEqual(result.value['stopped'], 'inputs_changed')
            self.assertFalse(result.value['replaced'])
            self.assertEqual(result.value['written'], 0)
            self.assertEqual(launches, ['guard'])
            self.assertEqual(self.state(connection), old)
            self.no_leases(connection)
