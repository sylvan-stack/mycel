"""Acceptance for private feature-check helpers, separate from live providers."""

import importlib.util
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


class ServiceFixtureTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::ServiceFixtureTests.test_packaged_prompt_counts_enforce_limits_while_usage_counts_submitted_text
#     def test_packaged_prompt_counts_enforce_limits_while_usage_counts_submitted_text(self):
#         from mycel._embedding_plan import load_tokenizer
#         tokenizer = load_tokenizer()
#         service = EmbeddingStandIn(tokenizer.counts, input_cap=9, batch_cap=9)
#         with self.assertRaises(EmbeddingFixtureFailure) as fault:
#             service.embed(["hello world"], model="voyage-code-4", dimensions=256, input_type="query")
#         self.assertEqual(fault.exception.kind, "content")
#         self.assertEqual(service.attempts[0].tokens, (10,))
#         self.assertEqual(service.attempts[0].submitted_tokens, (2,))
#         service = EmbeddingStandIn(tokenizer.counts)
#         response = service.embed(["hello world"], model="voyage-code-4", dimensions=256, input_type="query")
#         self.assertEqual(response["usage"]["total_tokens"], 2)
#         self.assertEqual((service.input_cap, service.batch_cap, service.inputs_cap),
#                          (tokenizer.catalog.input_token_cap, tokenizer.catalog.batch_token_cap,
#                           tokenizer.catalog.batch_input_cap))
# TEST-TIER-DISABLED-END tests/test_fixtures.py::ServiceFixtureTests.test_packaged_prompt_counts_enforce_limits_while_usage_counts_submitted_text

# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::ServiceFixtureTests.test_deterministic_vectors_keep_word_similarity_and_exact_request_counts
#     def test_deterministic_vectors_keep_word_similarity_and_exact_request_counts(self):
#         calls = []
#
#         def counter(text, kind):
#             calls.append((text, kind))
#             # A fixture of the counting contract. The feature tests pass the
#             # packaged tokenizer here; this helper never chooses an estimate.
#             return {"apple pear fruit": 4, "apple pear orchard": 4, "engine wheel road": 4}[text]
#
#         service = EmbeddingStandIn(counter)
#         texts = ["apple pear fruit", "apple pear orchard", "engine wheel road"]
#         response = service.embed(texts, model="voyage-code-4", dimensions=1024, input_type="document")
#         vectors = [row["embedding"] for row in response["data"]]
#         dot = lambda a, b: sum(left * right for left, right in zip(a, b))
#         self.assertGreater(dot(vectors[0], vectors[1]), dot(vectors[0], vectors[2]))
#         self.assertEqual(vectors[0], service.vector(texts[0], 1024))
#         self.assertEqual(response["usage"]["total_tokens"], 12)
#         self.assertEqual(calls, [(text, "document") for text in texts])
#         self.assertEqual(len(service.attempts), 1)
#         self.assertEqual(service.attempts[0].inputs, tuple(texts))
#         self.assertEqual(service.attempts[0].tokens, (4, 4, 4))
#         self.assertTrue(all(len(vector) == 1024 for vector in vectors))
#         self.assertEqual(service.vector("", 256), service.vector("", 256))
# TEST-TIER-DISABLED-END tests/test_fixtures.py::ServiceFixtureTests.test_deterministic_vectors_keep_word_similarity_and_exact_request_counts

# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::ServiceFixtureTests.test_stand_in_enforces_input_batch_count_and_explicit_request_contract
#     def test_stand_in_enforces_input_batch_count_and_explicit_request_contract(self):
#         counter = lambda text, kind: {"small": 2, "large": 5}[text]
#         for inputs, caps in ((["large"], {"input_cap": 4}),
#                              (["small", "small"], {"batch_cap": 3}),
#                              (["small", "small"], {"inputs_cap": 1})):
#             service = EmbeddingStandIn(counter, **caps)
#             with self.assertRaises(EmbeddingFixtureFailure) as failure:
#                 service.embed(inputs, model="voyage-code-4", dimensions=256, input_type="query")
#             self.assertEqual(failure.exception.kind, "content")
#             self.assertEqual(len(service.attempts), 1)
#             self.assertEqual(service.attempts[0].inputs, tuple(inputs))
#         service = EmbeddingStandIn(counter)
#         body = {"input": ["small"], "model": "voyage-code-4", "output_dimension": 256,
#                 "output_dtype": "float", "input_type": "query", "truncation": False}
#         self.assertEqual(service.request(body)["usage"]["total_tokens"], 2)
#         for mutation in ({"truncation": True}, {"input_type": "other"}, {"output_dtype": "int8"},
#                          {"output_dimension": True}, {"endpoint": "https://example.invalid"}):
#             with self.assertRaises(ValueError):
#                 service.request({**body, **mutation})
#         with self.assertRaises(ValueError):
#             service.request({key: value for key, value in body.items() if key != "truncation"})
# TEST-TIER-DISABLED-END tests/test_fixtures.py::ServiceFixtureTests.test_stand_in_enforces_input_batch_count_and_explicit_request_contract


# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::ServiceFixtureTests.test_installed_settings_and_cli_reject_provider_endpoint_substitution
#     def test_installed_settings_and_cli_reject_provider_endpoint_substitution(self):
#         from io import StringIO
#         with tempfile.TemporaryDirectory() as directory:
#             path = Path(directory) / "config.toml"
#             for key in ("url", "endpoint", "base_url", "api_base", "provider_url"):
#                 path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture_owner"\n'
#                                 '[embedding]\n' + key + '="https://example.invalid"\n')
#                 snapshot = load_settings(path=path)
#                 self.assertIn("embedding." + key, snapshot.report()["unknownKeys"])
#                 self.assertFalse(snapshot.valid)
#             path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture_owner"\n')
#             with patch.dict("os.environ", {"MYCEL_CONFIG": str(path),
#                                           "MYCEL_EMBEDDING_ENDPOINT": "https://example.invalid"}):
#                 self.assertNotIn("https://example.invalid", json.dumps(load_settings().report()))
#                 for option in ("--endpoint", "--base-url", "--provider-url"):
#                     output = StringIO()
#                     status = run(["embed", option, "https://example.invalid"], stdout=output,
#                                  stderr=StringIO())
#                     self.assertEqual(status, 1)
#                     self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
# TEST-TIER-DISABLED-END tests/test_fixtures.py::ServiceFixtureTests.test_installed_settings_and_cli_reject_provider_endpoint_substitution


class RunnerFixtureTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def source_runner():
        source = Path(__file__).resolve().parents[1] / "scripts" / "run_checks.py"
        name = "_mycel_runner_fixture"
        specification = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(specification)
        with patch.dict(os.environ), patch.object(sys, "path", list(sys.path)):
            sys.modules[name] = module
            try:
                specification.loader.exec_module(module)
                yield module
            finally:
                sys.modules.pop(name, None)

# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::RunnerFixtureTests.test_runner_preflight_fails_every_store_check_once_without_repeating_provider_attempts
#     def test_runner_preflight_fails_every_store_check_once_without_repeating_provider_attempts(self):
#         with tempfile.TemporaryDirectory() as directory, self.source_runner() as runner:
#             root = Path(directory)
#             (root / "test_runner_preflight.py").write_text('''import unittest
# class CliStoreChecks(unittest.TestCase):
#     check_kind = "store"
#     def test_first(self):
#         self.fail("unavailable store body unexpectedly executed")
#     def test_second(self):
#         self.fail("unavailable store body unexpectedly executed")
# class CliChecks(unittest.TestCase):
#     def test_unit(self):
#         pass
# ''')
#             config = root / "config.toml"
#             config.write_text('[store]\naddress="postgresql://private-user@host%0aheader:6543/private-owner?sslmode=require"\n')
#             prefix = "test_runner_preflight."
#             report = root / "report.json"
#             arguments = ["run_checks.py", "--tests", str(root), "--select", "test_runner_preflight",
#                          "--workers", "1", "--store-settings", str(config), "--report", str(report)]
#             try:
#                 for connected, expected_attempts in ((False, 1), (True, 4)):
#                     with self.subTest(connected=connected):
#                         statements = []
#
#                         def execute(backend, database, statement, **kwargs):
#                             statements.append(statement)
#                             if connected and statement.startswith("SELECT EXISTS"):
#                                 return "f"
#                             raise RuntimeError("private-provider-sentinel\nprivate-auth-body")
#
#                         original_preflight = runner.NativePostgresBackend.preflight
#                         output, errors = StringIO(), StringIO()
#                         with patch.object(sys, "argv", arguments), \
#                                 patch.object(runner.NativePostgresBackend, "_execute", autospec=True,
#                                              side_effect=execute), \
#                                 patch.object(runner.NativePostgresBackend, "preflight", autospec=True,
#                                              side_effect=original_preflight) as preflight, \
#                                 redirect_stdout(output), redirect_stderr(errors):
#                             self.assertEqual(runner.main(), 1)
#                         preflight.assert_called_once()
#                         self.assertEqual(len(statements), expected_attempts)
#                         self.assertEqual(sum(statement.startswith("CREATE") for statement in statements), int(connected))
#                         data = json.loads(report.read_text())
#                         self.assertFalse(data["passed"])
#                         self.assertEqual([(check["name"], check["status"]) for check in data["checks"]],
#                                          [(prefix + "CliChecks.test_unit", "passed"),
#                                           (prefix + "CliStoreChecks.test_first", "failed"),
#                                           (prefix + "CliStoreChecks.test_second", "failed")])
#                         reason = "store checks unavailable at host?0aheader:6543: cannot connect or create a disposable database"
#                         self.assertEqual(errors.getvalue().splitlines().count(reason), 1)
#                         for check in data["checks"][1:]:
#                             self.assertEqual(check["detail"], "RuntimeError: " + reason)
#                         self.assertIn("1 passed, 2 failed, 0 skipped", output.getvalue())
#                         for private in ("private-user", "private-owner", "private-provider", "private-auth", "postgresql://"):
#                             self.assertNotIn(private, output.getvalue() + errors.getvalue() + report.read_text())
#             finally:
#                 sys.modules.pop("test_runner_preflight", None)
# TEST-TIER-DISABLED-END tests/test_fixtures.py::RunnerFixtureTests.test_runner_preflight_fails_every_store_check_once_without_repeating_provider_attempts

# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::RunnerFixtureTests.test_runner_retains_private_ownership_record_and_reports_path_when_recovery_fails
#     def test_runner_retains_private_ownership_record_and_reports_path_when_recovery_fails(self):
#         journals = []
#         with tempfile.TemporaryDirectory() as directory, self.source_runner() as runner:
#             root = Path(directory)
#             (root / "test_runner_recovery.py").write_text('''import unittest
# class CliChecks(unittest.TestCase):
#     def test_unit(self):
#         pass
# ''')
#             config = root / "config.toml"
#             config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture-owner"\n')
#
#             def fail_recovery(backend):
#                 journal = backend._ownership_journal
#                 journals.append(journal)
#                 record = journal / "mycel_check_fictional_recovery.json"
#                 record.write_text(json.dumps({"database": "mycel_check_fictional_recovery",
#                                               "server": backend._journal_server}))
#                 record.chmod(0o600)
#                 raise RuntimeError("injected ownership recovery failure")
#
#             output, errors = StringIO(), StringIO()
#             arguments = ["run_checks.py", "--tests", str(root), "--select", "test_runner_recovery",
#                          "--workers", "1", "--store-settings", str(config)]
#             try:
#                 with patch.object(sys, "argv", arguments), \
#                         patch.object(runner.NativePostgresBackend, "recover_owned_databases", autospec=True,
#                                      side_effect=fail_recovery) as recover, \
#                         patch.object(runner.NativePostgresBackend, "_execute") as boundary, \
#                         redirect_stdout(output), redirect_stderr(errors):
#                     self.assertEqual(runner.main(), 1)
#                 recover.assert_called_once()
#                 boundary.assert_not_called()
#                 self.assertEqual(len(journals), 1)
#                 journal = journals[0]
#                 self.assertTrue(journal.is_dir())
#                 self.assertEqual(journal.stat().st_mode & 0o777, 0o700)
#                 record = journal / "mycel_check_fictional_recovery.json"
#                 self.assertEqual(record.stat().st_mode & 0o777, 0o600)
#                 self.assertEqual(json.loads(record.read_text())["database"], "mycel_check_fictional_recovery")
#                 self.assertIn(str(journal), errors.getvalue())
#                 self.assertNotIn("1 passed", output.getvalue())
#             finally:
#                 sys.modules.pop("test_runner_recovery", None)
#                 for journal in journals:
#                     shutil.rmtree(journal, ignore_errors=True)
# TEST-TIER-DISABLED-END tests/test_fixtures.py::RunnerFixtureTests.test_runner_retains_private_ownership_record_and_reports_path_when_recovery_fails


class RepositoryFixtureTests(unittest.TestCase):
    # The backend runs actual product init for this fixture. These checks remain
    # store-backed and cannot qualify against an in-memory substitute.

    check_kind = "store"


# TEST-TIER-DISABLED-BEGIN tests/test_fixtures.py::RepositoryFixtureTests.test_private_store_fixture_has_safe_name_private_settings_and_real_database
#     def test_private_store_fixture_has_safe_name_private_settings_and_real_database(self):
#         fixture = self.store_fixture
#         self.assertEqual(require_check_database(fixture.database), fixture.database)
#         self.assertEqual(fixture.settings_file.stat().st_mode & 0o777, 0o600)
#         self.assertIn(fixture.database, fixture.settings_file.read_text())
#         self.assertEqual(fixture.backend.query(fixture.database, "SELECT current_database()"), fixture.database)
#         for name in ("owner_database", "mycel_check_", "mycel_check_bad;DROP DATABASE owner", "mycel_check_Upper"):
#             with self.assertRaises(CoverageError):
#                 fixture.backend.query(name, "SELECT 1")
# TEST-TIER-DISABLED-END tests/test_fixtures.py::RepositoryFixtureTests.test_private_store_fixture_has_safe_name_private_settings_and_real_database


if __name__ == "__main__":
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:3
# from contextlib import contextmanager, redirect_stderr, redirect_stdout
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:5
# from io import StringIO
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:6
# import json
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:9
# import shutil
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:9
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:11
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:15
# from mycel._cli import run
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:16
# from mycel._coverage import CoverageError, require_check_database
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:17
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:17
# TEST-TIER-IMPORTS-BEGIN tests/test_fixtures.py:18
# from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn
# TEST-TIER-IMPORTS-END tests/test_fixtures.py:18
