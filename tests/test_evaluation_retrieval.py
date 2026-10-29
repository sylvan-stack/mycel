# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Actual retrieval producers inside the evaluator's sole read-only snapshot.

These store checks cover actual normal retrieval and explicitly selected-kind
dispatch for MYC-13.11. They neither qualify the separate full Drift pipeline
nor measure semantic quality/MYC-4.25.
"""

import unittest
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from psycopg import pq

from mycel._evaluation import (
    EvaluationSet,
    PreparedQueryVector,
    run_retrieval_evaluation,
)
from mycel._evaluation_store import StoreRetrieval
from mycel._retrieval_store import StoreCandidates
from mycel._store import TABLES

try:
    pass
    from . import test_ranking_store as ranking_fixtures
    pass
except ImportError:
    import test_ranking_store as ranking_fixtures


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *arguments, **options):
        self.statements.append(statement)
        return self.connection.execute(statement, *arguments, **options)


class _Vectors:
    def __init__(self, connection, vector, *, reasons=None):
        self.connection, self.vector = connection, vector
        self.reasons, self.queries = reasons or {}, []

    def prepare(self, query):
        if self.connection.info.transaction_status != pq.TransactionStatus.IDLE:
            raise AssertionError('Query preparation entered an index transaction.')
        self.queries.append(query)
        reason = self.reasons.get(query.text)
        return PreparedQueryVector(None, reason) if reason is not None else PreparedQueryVector(self.vector)


def _state(connection):
    rows = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}
    names = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
                               "WHERE schemaname='public' ORDER BY sequencename").fetchall()
    rows['sequences'] = {name: connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone()
                         for name, in names}
    return rows


@contextmanager
def _forbid_side_effects():
    """Actual ranking is allowed; freshness, publication and transports are not."""
    with ExitStack() as stack:
        for target in (
            'mycel._search_store._run_search_freshness',
            'mycel._freshness_store.StoreFreshnessAdapter.discover',
            'mycel._capture._Capture.capture', 'mycel._ingest.ingest',
            'mycel._activity.MutationActivity.session',
            'mycel._classification_store.ClassificationStore.prepare',
            'mycel._classification_store.ClassificationStore.apply',
            'mycel._classification_store.ClassificationStore.reuse',
            'mycel._summary_writer.SummaryWriter.write',
            'mycel._voyage._https_request',
        ):
            stack.enter_context(patch(target, side_effect=AssertionError(target)))
        # The evaluator borrows its existing transaction; a nested ordinary
        # search snapshot would violate the sole-snapshot contract.
        stack.enter_context(patch.object(StoreCandidates, 'snapshot', side_effect=AssertionError('nested snapshot')))
        yield


class EvaluationRetrievalUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class EvaluationRetrievalStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.ranking = ranking_fixtures.RankingStoreTests()
        self.ranking.store_fixture = self.store_fixture
        self.ranking.setUp()
        self.base = self.ranking.base
        self.vector = self.ranking.query
        self.settings = self.ranking.settings(shared=({'repo': 'handbook', 'paths': ['selected']},))

    def seed(self, connection, **options):
        result = self.ranking.seed(connection, **options)
        # Exact file-location corpus ownership is part of the evaluator's
        # input contract. The older ranking fixture supplies no such metadata.
        connection.execute('UPDATE public.mycel_file_locations fl SET metadata=fl.metadata || '
            'jsonb_build_object(\'corpus\',f.corpus) FROM public.mycel_file_versions fv '
            'JOIN public.mycel_files f ON f.id=fv.file_id WHERE fl.file_version=fv.id AND f.id=%s', (result[0],))
        return result

    def suite(self, *queries):
        return EvaluationSet(Path('/fictional/evaluation.toml'), sha256(b'controlled labelled query set').hexdigest(),
                             tuple(queries))

    def measure(self, connection, queries, *, settings=None, vectors=None):
        vectors = vectors or _Vectors(connection, self.vector)
        return run_retrieval_evaluation(self.suite(*queries), repository='fixture', build='1f',
            model='voyage-code-4', query_vectors=vectors,
            retrieval=StoreRetrieval(connection, settings or self.settings))

    def normal(self, connection, queries, *, settings=None, vector=None):
        selected = self.settings if settings is None else settings
        result = []
        with StoreCandidates(connection, selected).snapshot(('fixture',)) as snapshot:
            for query in queries:
                ranked, = snapshot.ranked(query.text, vector, k=10, only=query.only)
                result.append((ranked.route, [(entry.chunk.identifier, entry.chunk.version,
                                              entry.chunk.place.address) for entry in ranked.results]))
        return result

    @staticmethod
    def actual(report):
        return [(row['route'], [(place['id'], place['version'], place['address']) for place in row['returned']])
                for row in report['results']]


# Archived complete imports; restore needed names in their original scope, not at this file tail.
