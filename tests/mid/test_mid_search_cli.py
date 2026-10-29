
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_complete_query_is_embedded_once_with_query_type_and_no_truncation
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Complete query is embedded once with query type and no truncation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_query_is_embedded_once_with_query_type_and_no_truncation(self):
#         text = 'how does renewal decide 雪 😀\n'
#         value = prepare_query(self.settings, text, credentials=self.credentials(), _client_factory=self.factory())
#         self.assertEqual(len(value.vector), 256)
#         self.assertIsNone(value.reason)
#         self.assertEqual(len(self.requests), 1)
#         self.assertEqual(len(self.key_reads), 1)
#         self.assertEqual(self.requests[0]['input'], [text])
#         self.assertEqual(self.requests[0]['input_type'], 'query')
#         self.assertFalse(self.requests[0]['truncation'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_missing_credential_keeps_wording_available_without_provider_access
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Missing credential keeps wording available without provider access.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_credential_keeps_wording_available_without_provider_access(self):
#         value = prepare_query(self.settings, 'renewal', credentials=self.credentials(present=False),
#                               _client_factory=self.factory())
#         self.assertIsNone(value.vector)
#         self.assertIn('credential', value.reason)
#         self.assertEqual(len(self.key_reads), 1)
#         self.assertFalse(self.requests)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_every_provider_failure_and_invalid_response_has_safe_wording_fallback
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Every provider failure and invalid response has safe wording fallback.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_every_provider_failure_and_invalid_response_has_safe_wording_fallback(self):
#         for kind in ('connection', 'deadline', 'rate_limit', 'server', 'authentication',
#                      'authorization', 'missing_model', 'content', 'invalid_response',
#                      'response_limit', 'provider'):
#             with self.subTest(kind=kind):
#                 value = prepare_query(self.settings, 'renewal', credentials=self.credentials(),
#                                       _client_factory=self.factory(failure=kind))
#                 self.assertIsNone(value.vector)
#                 self.assertTrue(value.reason)
#                 self.assertNotIn('fixture-private-key', value.reason)
#         value = prepare_query(self.settings, 'renewal', credentials=self.credentials(),
#                               _client_factory=self.factory(invalid=True))
#         self.assertIsNone(value.vector)
#         self.assertNotIn('fixture-private-key', value.reason)
#         zero = prepare_query(self.settings, 'renewal', credentials=self.credentials(),
#                              _client_factory=self.factory(zero=True))
#         self.assertIsNone(zero.vector)
#         self.assertTrue(zero.reason)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_overlong_complete_query_refuses_embedding_before_credentials_or_send
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Overlong complete query refuses embedding before credentials or send.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_overlong_complete_query_refuses_embedding_before_credentials_or_send(self):
#         tokenizer = load_tokenizer()
#         tokenizer = replace(tokenizer, catalog=replace(tokenizer.catalog, input_token_cap=2))
#         with patch('mycel._search.load_tokenizer', return_value=tokenizer):
#             value = prepare_query(self.settings, 'renewal word ' * 100,
#                 credentials=self.credentials(), _client_factory=self.factory())
#         self.assertIsNone(value.vector)
#         self.assertIn('limits', value.reason)
#         self.assertFalse(self.key_reads)
#         self.assertFalse(self.requests)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_query_cancellation_is_not_converted_to_fallback
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Query cancellation is not converted to fallback.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_query_cancellation_is_not_converted_to_fallback(self):
#         def interrupted(*args, **kwargs):
#             raise KeyboardInterrupt()
#         with self.assertRaises(KeyboardInterrupt):
#             prepare_query(self.settings, 'renewal', _client_factory=interrupted)
#         with self.assertRaises(KeyboardInterrupt):
#             prepare_query(self.settings, 'renewal', credentials=self.credentials(),
#                           _client_factory=self.factory(failure='cancelled'))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_public_handler_retains_success_and_reason_when_query_vector_is_unavailable
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public handler retains success and reason when query vector is unavailable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_handler_retains_success_and_reason_when_query_vector_is_unavailable(self):
#         called = []
#         @contextmanager
#         def store(invocation):
#             yield object(), SimpleNamespace(dimensions=256)
#         def search(connection, settings, query, names, **options):
#             called.append((query, names, options))
#             return {'schema': 3, 'repository': 'fixture', 'route': 'question',
#                     'meaning': {'used': False, 'reason': options['meaning_reason']},
#                     'results': [{'preview': 'wording result'}]}
#         out, err = io.StringIO(), io.StringIO()
#         with patch.dict('os.environ', {'MYCEL_CONFIG': str(self.config)}), \
#                 patch('mycel._cli.invocation_store', store), \
#                 patch('mycel._search.prepare_query', return_value=QueryEmbedding(reason='The credential is unavailable.')) as prepare, \
#                 patch('mycel._search_store.search_from_store', side_effect=search):
#             status = run(['search', 'how does renewal decide', '--repo', 'fixture', '--k', '5',
#                           '--only', 'docs', '--no-fresh'], stdout=out, stderr=err)
#         self.assertEqual(status, 0)
#         self.assertFalse(json.loads(out.getvalue())['meaning']['used'])
#         self.assertEqual(err.getvalue(), '')
#         prepare.assert_called_once()
#         self.assertEqual(called[0][:2], ('how does renewal decide', ('fixture',)))
#         self.assertEqual(called[0][2]['k'], 5)
#         self.assertEqual(called[0][2]['only'], 'docs')
#         self.assertTrue(called[0][2]['no_fresh'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_dimension_mismatch_uses_wording_without_query_credential_or_provider_access
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Dimension mismatch uses wording without query credential or provider access.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dimension_mismatch_uses_wording_without_query_credential_or_provider_access(self):
#         @contextmanager
#         def store(invocation):
#             yield object(), SimpleNamespace(dimensions=512)
#         out = io.StringIO()
#         with patch.dict('os.environ', {'MYCEL_CONFIG': str(self.config)}), \
#                 patch('mycel._cli.invocation_store', store), \
#                 patch('mycel._search.prepare_query') as prepare, \
#                 patch('mycel._search_store.search_from_store', return_value={'schema': 3}) as search:
#             self.assertEqual(run(['search', '--repo', 'fixture', 'needle'], stdout=out), 0)
#         prepare.assert_not_called()
#         self.assertIsNone(search.call_args.kwargs['query_vector'])
#         self.assertIn('dimensions', search.call_args.kwargs['meaning_reason'])
#         self.assertEqual(json.loads(out.getvalue()), {'schema': 3})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_invalid_or_unknown_scope_stops_before_provider_or_store_access
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Invalid or unknown scope stops before provider or store access.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_invalid_or_unknown_scope_stops_before_provider_or_store_access(self):
#         for args in (['search'], ['search', ''], ['search', 'x', 'y'], ['search', 'x', '--k', '0'],
#                      ['search', 'x', '--k', '101'], ['search', 'x', '--k', '1.5'],
#                      ['search', 'x', '--only', 'all'], ['search', 'x', '--repo', 'absent']):
#             with self.subTest(args=args), patch.dict('os.environ', {'MYCEL_CONFIG': str(self.config)}), \
#                     patch('mycel._search.prepare_query') as prepare, \
#                     patch('mycel._cli.invocation_store') as store:
#                 out = io.StringIO()
#                 self.assertEqual(run(args, stdout=out), 1)
#                 self.assertIn('error', json.loads(out.getvalue()))
#                 prepare.assert_not_called()
#                 store.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_search_cli.py::SearchCliTests.test_syntax_keeps_literal_option_shaped_queries_and_advertises_schema3
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Syntax keeps literal option shaped queries and advertises schema3.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_search_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_syntax_keeps_literal_option_shaped_queries_and_advertises_schema3(self):
#         invocation = parse(['search', '--repo', 'fixture', '--', '--no-fresh'])
#         self.assertEqual(invocation.arguments, ('--k', '10', '--', '--no-fresh'))
#         command = help_reply('search')['commands'][0]
#         self.assertTrue(command['available'])
#         self.assertIn('--only code|docs', command['options'])
#         self.assertIn('--k <count>', command['options'])
#         self.assertIn('--no-fresh', command['options'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
