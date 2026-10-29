# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real-store proofs of complete private summary builds with local services."""

import json
import sys
import unittest

from mycel._cli import Invocation
from mycel._embedding_plan import load_tokenizer
from mycel._freshness import Deadline
from mycel._resolver import SourceResolver
from mycel._search_store import search_from_store
from mycel._settings import load_settings
from mycel._summary_build import build_summaries
from mycel._summary_writer import WriterResult
from mycel._voyage import EmbeddingProgress, PartIdentity, VectorWrite

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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
