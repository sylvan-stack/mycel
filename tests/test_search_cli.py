"""Search syntax and offline query fallback across real bounded adapters."""
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import EmbeddingStandIn

from mycel._credentials import Credentials
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._settings import load_settings
from mycel._voyage import HTTPResult, ProviderFailure, VoyageClient


class SearchCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='mycel_search_query_')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'config.toml'
        self.config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n'
            '[search]\nshared_documents=[]\n[embedding]\ndimensions=256\n'
            '[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(self.root)) + '\n')
        self.settings = load_settings(path=self.config)
        self.key_reads, self.requests = [], []

    def credentials(self, *, present=True):
        def reader(argv, **kwargs):
            self.key_reads.append(argv)
            return CompletedChild(0 if present else 1, b'fixture-private-key\n', b'', 0.0)
        return Credentials(self.settings, InvocationPolicy('search'), home=self.root, _runner=reader)

    def factory(self, *, failure=None, invalid=False, zero=False):
        def create(credentials, policy, **options):
            service = EmbeddingStandIn(options['tokenizer'].counts)
            def transport(body, key, **limits):
                request = json.loads(body)
                self.requests.append(request)
                if failure is not None:
                    raise ProviderFailure(failure)
                if invalid:
                    return HTTPResult(200, b'{"private":"fixture-private-key"}')
                result = service.request(request)
                if zero:
                    for row in result['data']:
                        row['embedding'] = [0.0] * request['output_dimension']
                return HTTPResult(200, json.dumps(result).encode())
            return VoyageClient(credentials, policy, **options, attempts=1, _transport=transport)
        return create

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_complete_query_is_embedded_once_with_query_type_and_no_truncation
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_complete_query_is_embedded_once_with_query_type_and_no_truncation

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_missing_credential_keeps_wording_available_without_provider_access
#     def test_missing_credential_keeps_wording_available_without_provider_access(self):
#         value = prepare_query(self.settings, 'renewal', credentials=self.credentials(present=False),
#                               _client_factory=self.factory())
#         self.assertIsNone(value.vector)
#         self.assertIn('credential', value.reason)
#         self.assertEqual(len(self.key_reads), 1)
#         self.assertFalse(self.requests)
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_missing_credential_keeps_wording_available_without_provider_access

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_every_provider_failure_and_invalid_response_has_safe_wording_fallback
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_every_provider_failure_and_invalid_response_has_safe_wording_fallback

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_overlong_complete_query_refuses_embedding_before_credentials_or_send
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_overlong_complete_query_refuses_embedding_before_credentials_or_send

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_query_cancellation_is_not_converted_to_fallback
#     def test_query_cancellation_is_not_converted_to_fallback(self):
#         def interrupted(*args, **kwargs):
#             raise KeyboardInterrupt()
#         with self.assertRaises(KeyboardInterrupt):
#             prepare_query(self.settings, 'renewal', _client_factory=interrupted)
#         with self.assertRaises(KeyboardInterrupt):
#             prepare_query(self.settings, 'renewal', credentials=self.credentials(),
#                           _client_factory=self.factory(failure='cancelled'))
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_query_cancellation_is_not_converted_to_fallback

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_public_handler_retains_success_and_reason_when_query_vector_is_unavailable
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_public_handler_retains_success_and_reason_when_query_vector_is_unavailable

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_dimension_mismatch_uses_wording_without_query_credential_or_provider_access
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_dimension_mismatch_uses_wording_without_query_credential_or_provider_access

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_invalid_or_unknown_scope_stops_before_provider_or_store_access
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
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_invalid_or_unknown_scope_stops_before_provider_or_store_access

# TEST-TIER-DISABLED-BEGIN tests/test_search_cli.py::SearchCliTests.test_syntax_keeps_literal_option_shaped_queries_and_advertises_schema3
#     def test_syntax_keeps_literal_option_shaped_queries_and_advertises_schema3(self):
#         invocation = parse(['search', '--repo', 'fixture', '--', '--no-fresh'])
#         self.assertEqual(invocation.arguments, ('--k', '10', '--', '--no-fresh'))
#         command = help_reply('search')['commands'][0]
#         self.assertTrue(command['available'])
#         self.assertIn('--only code|docs', command['options'])
#         self.assertIn('--k <count>', command['options'])
#         self.assertIn('--no-fresh', command['options'])
# TEST-TIER-DISABLED-END tests/test_search_cli.py::SearchCliTests.test_syntax_keeps_literal_option_shaped_queries_and_advertises_schema3

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:2
# from contextlib import contextmanager
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:3
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:4
# import io
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:7
# from types import SimpleNamespace
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:10
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:12
# from mycel._cli import parse, run
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:13
# from mycel._commands import help_reply
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:15
# from mycel._embedding_plan import load_tokenizer
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:16
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_search_cli.py:18
# from mycel._search import QueryEmbedding, prepare_query
# TEST-TIER-IMPORTS-END tests/test_search_cli.py:18
