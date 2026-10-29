"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_grep_tail_store as _support
from test_grep_tail_store import (
    Deadline,
    ExitStack,
    GrepTailStoreTests,
    Invocation,
    InvocationPolicy,
    Jsonb,
    Path,
    QueryEmbedding,
    TABLES,
    _RecordingConnection,
    _forbid_mutations_and_paid_work,
    _state,
    append_tail,
    checked_store,
    contextmanager,
    io,
    patch,
    pq,
    ranking_fixtures,
    render_tail,
    search_from_store,
    search_tail,
    unittest,
    uuid4,
)


class GrepTailStoreTests(_support.GrepTailStoreTests):
# TEST-TIER-BEGIN tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes
    def test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes(self):
        with self.base.connection() as raw:
            _, document, shared = self.populated(raw)
            connection = _RecordingConnection(raw)
            query, vector = 'how does needle work', self.ranking.query
            with _forbid_mutations_and_paid_work():
                expected = search_from_store(connection, self.settings, query, ('fixture',),
                    query_vector=vector, k=5, only=None, deadline=Deadline.after(30), no_fresh=True)
                before = _state(raw)
                prepared = []

                def prepare(settings, text, **options):
                    self.assertEqual(settings.values, self.settings.values)
                    self.assertEqual(text, query)
                    self.assertEqual(options['policy'], InvocationPolicy('grep'))
                    self.assertEqual(raw.info.transaction_status, pq.TransactionStatus.IDLE)
                    prepared.append(text)
                    return QueryEmbedding(vector)

                connection.statements.clear()
                with self.connected_invocation(connection), \
                        patch('mycel._search.prepare_query', side_effect=prepare), \
                        patch('mycel._search_store.search_from_store', wraps=search_from_store) as normal:
                    actual = search_tail(self.settings, query, 'fixture')
                self.assertEqual(actual, expected)
                self.assertEqual(prepared, [query])
                normal.assert_called_once()
                self.assertEqual(normal.call_args.args[2:4], (query, ('fixture',)))
                self.assertEqual(normal.call_args.kwargs['k'], 5)
                self.assertIsNone(normal.call_args.kwargs['only'])
                self.assertTrue(normal.call_args.kwargs['no_fresh'])
                self.assertEqual(normal.call_args.kwargs['query_vector'], vector)
                self.assertEqual(len(actual['results']), 5)
                self.assertEqual({item['origin'] for item in actual['results']}, {'code', 'document'})
                ids = {item['id'] for item in actual['results']}
                self.assertIn(str(document[1]), ids)
                self.assertIn(str(shared[1]), ids)
                self.assertTrue(any(item['repository'] == 'handbook' for item in actual['results']))
                self.assertFalse(any(item['name'] in {'Hidden', 'Outside', 'Branch'} for item in actual['results']))
                self.assertFalse(actual['freshness']['checked'])
                self.assertFalse(actual['classificationCheck']['checked'])
                self.assertEqual(_state(raw), before)
                self.assertFalse(any(sql.lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE'))
                    for sql in connection.statements))
# TEST-TIER-END tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_default_tail_matches_normal_combined_top_five_with_shared_documents_and_no_freshness_or_writes

# TEST-TIER-BEGIN tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark
    def test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark(self):
        with self.base.connection() as raw:
            _, _, _ = self.populated(raw)
            connection = _RecordingConnection(raw)
            query = 'needle'
            reason = 'The normal embedding credential is unavailable.'
            with _forbid_mutations_and_paid_work():
                expected = search_from_store(connection, self.settings, query, ('fixture',),
                    query_vector=None, meaning_reason=reason, k=5, only=None,
                    deadline=Deadline.after(30), no_fresh=True)
                before = _state(raw)
                out, err = io.StringIO(), io.StringIO()
                invocation = Invocation('grep', arguments=(query,), settings=self.settings)
                connection.statements.clear()
                with self.connected_invocation(connection), \
                        patch('mycel._search.prepare_query', return_value=QueryEmbedding(reason=reason)) as prepare, \
                        patch('mycel._search_store.search_from_store', wraps=search_from_store) as normal:
                    append_tail(invocation, 1, stdout=out, stderr=err,
                        cwd=Path(self.settings.values['repos']['fixture']['code_root']), environ={})
                self.assertEqual(err.getvalue(), '')
                self.assertEqual(out.getvalue(), render_tail(expected))
                prepare.assert_called_once()
                self.assertEqual(prepare.call_args.kwargs['policy'], InvocationPolicy('grep'))
                normal.assert_called_once()
                self.assertIsNone(normal.call_args.kwargs['query_vector'])
                self.assertEqual(normal.call_args.kwargs['meaning_reason'], reason)
                self.assertFalse(expected['meaning']['used'])
                self.assertFalse(expected['freshness']['checked'])
                self.assertEqual(_state(raw), before)
                self.assertNotIn('score', out.getvalue().lower())
                self.assertFalse(any(sql.lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE'))
                    for sql in connection.statements))
# TEST-TIER-END tests/test_grep_tail_store.py::GrepTailStoreTests.test_actual_append_uses_normal_wording_fallback_and_retains_every_row_xmin_sequence_and_cited_mark
