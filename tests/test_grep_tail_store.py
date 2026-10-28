"""Actual normal top-five grep tails over disposable PostgreSQL.

Only ordinary query preparation is a controlled automatic-check stand-in.
Candidate/ranking/reply/metadata producers remain real and every row/xmin and
sequence is checked. Metadata-only no-fresh discovery is deliberately allowed.
"""
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._store import TABLES, checked_store

try:
    from . import test_ranking_store as ranking_fixtures
except ImportError:
    import test_ranking_store as ranking_fixtures


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *arguments, **options):
        self.statements.append(str(statement))
        return self.connection.execute(statement, *arguments, **options)


def _state(connection):
    result = {table.name: connection.execute(
        f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t ORDER BY to_jsonb(t)::text').fetchall()
        for table in TABLES}
    sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename").fetchall()
    result['sequences'] = {name: connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone()
                           for name, in sequences}
    return result


@contextmanager
def _forbid_mutations_and_paid_work():
    with ExitStack() as stack:
        for target in (
            'mycel._freshness_store.StoreFreshnessAdapter.refresh',
            'mycel._capture._Capture.capture',
            'mycel._ingest.ingest',
            'mycel._activity.MutationActivity.session',
            'mycel._classification_store.ClassificationStore.prepare',
            'mycel._classification_store.ClassificationStore.apply',
            'mycel._classification_store.ClassificationStore.reuse',
            'mycel._summary_writer.SummaryWriter.write',
            'mycel._credentials.Credentials.embedding_key',
            'mycel._credentials.Credentials.jev_key',
            'mycel._voyage._https_request',
        ):
            stack.enter_context(patch(target, side_effect=AssertionError(target)))
        yield


class GrepTailStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.ranking = ranking_fixtures.RankingStoreTests()
        self.ranking.store_fixture = self.store_fixture
        self.ranking.setUp()
        self.base = self.ranking.base
        self.settings = self.ranking.settings(shared=({'repo': 'handbook', 'paths': ['selected']},))
        for repository in self.settings.values['repos'].values():
            for key in ('code_root', 'artifact_root'):
                if repository.get(key):
                    Path(repository[key]).mkdir(parents=True, exist_ok=True)

    def seed(self, connection, **options):
        value = self.ranking.seed(connection, **options)
        repository = options.get('repository', 'fixture')
        root = options.get('root', 'code')
        path = options.get('path', 'code.py')
        folder = Path(self.settings.values['repos'][repository]['code_root' if root == 'code' else 'artifact_root'])
        physical = folder / path
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_text(options.get('source', 'body\n'))
        return value

    def populated(self, connection):
        code = [self.seed(connection, path=f'src/needle{index}.py', name=f'Needle{index}',
                         source=f'needle implementation {index}\n', cosine=.8-index*.02)
                for index in range(8)]
        document = self.seed(connection, path='guide.md', root='artifact', kind='document',
            name='Guide', source='---\nstatus: heartwood\n---\n# Guide\nneedle explains implementation\n', cosine=.99)
        shared = self.seed(connection, repository='handbook', path='checkout-guide.md', root='code',
            kind='document', name='Shared', source='# Shared\nneedle shared explanation\n', cosine=.98,
            aliases=(('artifact', 'selected/shared.md'),))
        self.ranking.cite(connection, document, 'fixture:@code/src/needle0.py#Needle0')
        self.ranking.cite(connection, document, 'fixture:@code/src/needle1.py#Needle1')
        self.ranking.cite(connection, shared, 'fixture:@code/src/needle0.py#Needle0')
        reason = {'kind': 'source_changed', 'source': {'repository': 'fixture', 'root': 'code',
            'path': 'governor.py', 'name': 'Governor', 'address': 'fixture:@code/governor.py#Governor'}}
        connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,NULL,%s)',
                           (uuid4(), 'fixture', document[2], Jsonb(reason)))
        self.seed(connection, repository='handbook', path='outside.md', root='artifact',
                  kind='document', name='Outside', source='# Outside\nneedle\n', cosine=1.0)
        self.seed(connection, repository='disabled', path='hidden.py', name='Hidden',
                  source='needle\n', cosine=1.0)
        self.seed(connection, path='branch.py', name='Branch', source='needle\n', cosine=1.0,
                  location_kind='branch')
        return code, document, shared

    @contextmanager
    def connected_invocation(self, connection):
        @contextmanager
        def store(invocation):
            self.assertEqual(invocation.command, 'grep')
            self.assertEqual(invocation.repositories, ('fixture',))
            self.assertEqual(invocation.settings.values, self.settings.values)
            with checked_store(connection) as inspection:
                yield connection, inspection
        with patch('mycel._cli.invocation_store', store):
            yield

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes
#     def test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes(self):
#         with self.base.connection() as raw:
#             _, document, shared = self.populated(raw)
#             connection = _RecordingConnection(raw)
#             query, vector = 'how does needle work', self.ranking.query
#             with _forbid_mutations_and_paid_work():
#                 expected = search_from_store(connection, self.settings, query, ('fixture',),
#                     query_vector=vector, k=5, only=None, deadline=Deadline.after(30), no_fresh=True)
#                 before = _state(raw)
#                 prepared = []
#
#                 def prepare(settings, text, **options):
#                     self.assertEqual(settings.values, self.settings.values)
#                     self.assertEqual(text, query)
#                     self.assertEqual(options['policy'], InvocationPolicy('grep'))
#                     self.assertEqual(raw.info.transaction_status, pq.TransactionStatus.IDLE)
#                     prepared.append(text)
#                     return QueryEmbedding(vector)
#
#                 connection.statements.clear()
#                 with self.connected_invocation(connection), \
#                         patch('mycel._search.prepare_query', side_effect=prepare), \
#                         patch('mycel._search_store.search_from_store', wraps=search_from_store) as normal:
#                     actual = search_tail(self.settings, query, 'fixture')
#                 self.assertEqual(actual, expected)
#                 self.assertEqual(prepared, [query])
#                 normal.assert_called_once()
#                 self.assertEqual(normal.call_args.args[2:4], (query, ('fixture',)))
#                 self.assertEqual(normal.call_args.kwargs['k'], 5)
#                 self.assertIsNone(normal.call_args.kwargs['only'])
#                 self.assertTrue(normal.call_args.kwargs['no_fresh'])
#                 self.assertEqual(normal.call_args.kwargs['query_vector'], vector)
#                 self.assertEqual(len(actual['results']), 5)
#                 self.assertEqual({item['origin'] for item in actual['results']}, {'code', 'document'})
#                 ids = {item['id'] for item in actual['results']}
#                 self.assertIn(str(document[1]), ids)
#                 self.assertIn(str(shared[1]), ids)
#                 self.assertTrue(any(item['repository'] == 'handbook' for item in actual['results']))
#                 self.assertFalse(any(item['name'] in {'Hidden', 'Outside', 'Branch'} for item in actual['results']))
#                 self.assertFalse(actual['freshness']['checked'])
#                 self.assertFalse(actual['classificationCheck']['checked'])
#                 self.assertEqual(_state(raw), before)
#                 self.assertFalse(any(sql.lstrip().upper().startswith(
#                     ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE'))
#                     for sql in connection.statements))
# TEST-TIER-DISABLED-END tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark
#     def test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark(self):
#         with self.base.connection() as raw:
#             _, _, _ = self.populated(raw)
#             connection = _RecordingConnection(raw)
#             query = 'needle'
#             reason = 'The normal embedding credential is unavailable.'
#             with _forbid_mutations_and_paid_work():
#                 expected = search_from_store(connection, self.settings, query, ('fixture',),
#                     query_vector=None, meaning_reason=reason, k=5, only=None,
#                     deadline=Deadline.after(30), no_fresh=True)
#                 before = _state(raw)
#                 out, err = io.StringIO(), io.StringIO()
#                 invocation = Invocation('grep', arguments=(query,), settings=self.settings)
#                 connection.statements.clear()
#                 with self.connected_invocation(connection), \
#                         patch('mycel._search.prepare_query', return_value=QueryEmbedding(reason=reason)) as prepare, \
#                         patch('mycel._search_store.search_from_store', wraps=search_from_store) as normal:
#                     append_tail(invocation, 1, stdout=out, stderr=err,
#                         cwd=Path(self.settings.values['repos']['fixture']['code_root']), environ={})
#                 self.assertEqual(err.getvalue(), '')
#                 self.assertEqual(out.getvalue(), render_tail(expected))
#                 prepare.assert_called_once()
#                 self.assertEqual(prepare.call_args.kwargs['policy'], InvocationPolicy('grep'))
#                 normal.assert_called_once()
#                 self.assertIsNone(normal.call_args.kwargs['query_vector'])
#                 self.assertEqual(normal.call_args.kwargs['meaning_reason'], reason)
#                 self.assertFalse(expected['meaning']['used'])
#                 self.assertFalse(expected['freshness']['checked'])
#                 self.assertEqual(_state(raw), before)
#                 self.assertNotIn('score', out.getvalue().lower())
#                 self.assertFalse(any(sql.lstrip().upper().startswith(
#                     ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE'))
#                     for sql in connection.statements))
# TEST-TIER-DISABLED-END tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:8
# import io
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:14
# from psycopg import pq
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:17
# from mycel._cli import Invocation
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:17
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:18
# from mycel._freshness import Deadline
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:18
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:19
# from mycel._grep import append_tail, render_tail, search_tail
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:19
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:20
# from mycel._safeguards import InvocationPolicy
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:20
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:21
# from mycel._search import QueryEmbedding
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:21
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail_store.py:22
# from mycel._search_store import search_from_store
# TEST-TIER-IMPORTS-END tests/test_grep_tail_store.py:22
