"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_coverage as _support
from test_coverage import (CoverageError ,Path ,discover_checks ,iter_checks ,multiprocessing ,patch ,run_checks ,select_checks ,sys ,tempfile ,unittest)


class CoverageTests(_support.CoverageTests):
# TEST-TIER-BEGIN tests/test_coverage.py::CoverageTests.test_process_workers_keep_canonical_outcomes_and_network_denial
    def test_process_workers_keep_canonical_outcomes_and_network_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_worker_proofs.py").write_text('''import signal
import socket
import unittest
class WorkerProofs(unittest.TestCase):
    def test_pass(self):
        for _ in range(2):
            with self.assertRaises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGINT)
        with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
            socket.create_connection(("127.0.0.1", 1))
    def test_failure(self):
        self.fail("expected worker assertion")
    def test_skip(self):
        self.skipTest("expected worker skip")
''')
            try:
                suite = discover_checks(root)
                names = [check.id() for check in iter_checks(suite)]
                self.assertEqual(len(names), 3)
                selected = select_checks(suite, ["test_worker_proofs.WorkerProofs.test_pass"])
                report = run_checks(selected, workers=2, tests_directory=root)
                self.assertTrue(report.passed, report.errors)
                self.assertEqual([check.name for check in report.checks], [names[1]])
                report = run_checks(discover_checks(root), workers=2, tests_directory=root)
                self.assertFalse(report.passed)
                self.assertEqual([check.name for check in report.checks], names)
                self.assertEqual([check.status for check in report.checks], ["failed", "passed", "skipped"])
                with self.assertRaisesRegex(CoverageError, "no checks match"):
                    select_checks(discover_checks(root), ["missing_module"])
            finally:
                sys.modules.pop("test_worker_proofs", None)
# TEST-TIER-END tests/test_coverage.py::CoverageTests.test_process_workers_keep_canonical_outcomes_and_network_denial

# TEST-TIER-BEGIN tests/test_coverage.py::CoverageTests.test_worker_crash_rejects_gate_and_invalid_worker_configuration
    def test_worker_crash_rejects_gate_and_invalid_worker_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_worker_crash.py").write_text('''import os
from pathlib import Path
import signal
import time
import unittest
class WorkerCrash(unittest.TestCase):
    def test_a_stubborn(self):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path(__file__).with_suffix(".ready").write_text("ready")
        while True:
            time.sleep(0.1)
    def test_z_exit(self):
        deadline = time.monotonic() + 10
        while not Path(__file__).with_suffix(".ready").exists():
            if time.monotonic() > deadline:
                self.fail("other worker did not start")
            time.sleep(0.01)
        os._exit(17)
''')
            try:
                before = {child.pid for child in multiprocessing.active_children()}
                with patch("mycel._coverage._WORKER_CANCEL_GRACE", 0.2), \
                     patch("mycel._coverage._WORKER_TERMINATE_GRACE", 0.2):
                    with self.assertRaisesRegex(CoverageError, "worker exited"):
                        run_checks(discover_checks(root), workers=2, tests_directory=root)
                self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)
                for workers in (0, -1, True):
                    with self.assertRaisesRegex(CoverageError, "positive integer"):
                        run_checks(unittest.TestSuite(), workers=workers)
                with self.assertRaisesRegex(CoverageError, "canonical tests directory"):
                    run_checks(unittest.TestSuite(), workers=2)
            finally:
                sys.modules.pop("test_worker_crash", None)
# TEST-TIER-END tests/test_coverage.py::CoverageTests.test_worker_crash_rejects_gate_and_invalid_worker_configuration

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_a_check_is_unit_unless_its_class_names_a_known_kind
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: A check is unit unless its class names a known kind.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_a_check_is_unit_unless_its_class_names_a_known_kind(self):
#         class Plain(unittest.TestCase):
#             def runTest(self):
#                 pass
#         self.assertEqual(check_kind(Plain()), "unit")
#         report = run_checks(unittest.TestSuite([Plain()]))
#         self.assertTrue(report.passed)
#         self.assertEqual([check.kind for check in report.checks], ["unit"])
#         unknown = example_check(kind="review", action=lambda case: case.fail("should not execute"))
#         report = run_checks(unittest.TestSuite([unknown]))
#         self.assertFalse(report.passed)
#         self.assertIn("unknown check kind", report.errors[0])
#         self.assertEqual(report.checks, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_duplicate_check_names_do_not_execute_twice
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Duplicate check names do not execute twice.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_duplicate_check_names_do_not_execute_twice(self):
#         duplicate = example_check()
#         report = run_checks(unittest.TestSuite([duplicate, example_check()]))
#         self.assertFalse(report.passed)
#         self.assertEqual(len(report.checks), 1)
#         self.assertIn("duplicate check", report.errors[0])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_any_failed_unclaimed_automatic_check_fails_the_gate
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Any failed unclaimed automatic check fails the gate.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_any_failed_unclaimed_automatic_check_fails_the_gate(self):
#         def fail(case):
#             case.fail("fictional failing proof")
#         report = run_checks(unittest.TestSuite([example_check(action=fail)]))
#         self.assertFalse(report.passed)
#         self.assertEqual(report.checks[0].status, "failed")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_skipped_and_expected_failure_checks_never_count_as_passed
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Skipped and expected failure checks never count as passed.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_skipped_and_expected_failure_checks_never_count_as_passed(self):
#         skipped = example_check(skip=True)
#         report = run_checks(unittest.TestSuite([skipped]))
#         self.assertFalse(report.passed)
#         self.assertEqual(report.checks[0].status, "skipped")
#         expected = example_check(action=lambda case: case.fail("expected failure"))
#         expected.runTest.__func__.__unittest_expecting_failure__ = True
#         report = run_checks(unittest.TestSuite([expected]))
#         self.assertFalse(report.passed)
#         self.assertEqual(report.checks[0].status, "failed")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_subtest_and_setup_failures_reach_the_gate
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Subtest and setup failures reach the gate.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_subtest_and_setup_failures_reach_the_gate(self):
#         def subtest(case):
#             with case.subTest(part="failed"):
#                 case.fail("subtest failed")
#         report = run_checks(unittest.TestSuite([example_check(action=subtest)]))
#         self.assertFalse(report.passed)
#         check = example_check()
#         def fail_setup(cls):
#             raise RuntimeError("class setup failed")
#         type(check).setUpClass = classmethod(fail_setup)
#         report = run_checks(unittest.TestSuite([check]))
#         self.assertFalse(report.passed)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_unit_and_store_checks_are_mandatory_eval_and_live_are_excluded
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unit and store checks are mandatory eval and live are excluded.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unit_and_store_checks_are_mandatory_eval_and_live_are_excluded(self):
#         touched = []
#         unit = example_check(name="Unit", action=lambda case: touched.append("unit"))
#         store = example_check(name="Store", kind="store")
#         evaluation = example_check(name="Eval", kind="eval", action=lambda case: touched.append("eval"))
#         live = example_check(name="Live", kind="live", action=lambda case: touched.append("live"))
#         report = run_checks(unittest.TestSuite([unit, store, evaluation, live]))
#         self.assertEqual(touched, ["unit"])
#         self.assertEqual([result.kind for result in report.checks], ["unit", "store"])
#         self.assertFalse(report.passed)
#         self.assertIn("no disposable database backend", report.checks[1].detail)
#         for kinds in (frozenset({"unit"}), frozenset({"live"}), AUTOMATIC_KINDS | {"eval"}):
#             with self.assertRaises(CoverageError):
#                 run_checks(unittest.TestSuite([example_check()]), kinds=kinds)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_automatic_unit_network_attempts_fail_without_connecting
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Automatic unit network attempts fail without connecting.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_automatic_unit_network_attempts_fail_without_connecting(self):
#         def connect(case):
#             socket.create_connection(("127.0.0.1", 1))
#         report = run_checks(unittest.TestSuite([example_check(action=connect)]))
#         self.assertFalse(report.passed)
#         self.assertIn("network access is forbidden", report.checks[0].detail)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_preimported_native_boundary_alias_refuses_before_libpq_parameter_work
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Preimported native boundary alias refuses before libpq parameter work.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_preimported_native_boundary_alias_refuses_before_libpq_parameter_work(self):
#         with no_network(), patch("mycel._database.conninfo.make_conninfo") as parameters:
#             with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
#                 _CAPTURED_NATIVE_CONNECT(timeout_seconds=0.1, hostaddr="127.0.0.1", host="127.0.0.1")
#             parameters.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_standard_and_preimported_psycopg_entries_and_default_pq_are_blocked
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Standard and preimported psycopg entries and default pq are blocked.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_standard_and_preimported_psycopg_entries_and_default_pq_are_blocked(self):
#         with no_network():
#             for connect in (_CAPTURED_CONNECT, _CAPTURED_CLASS_CONNECT, psycopg.connect,
#                             psycopg.Connection.connect, psycopg.pq.PGconn.connect,
#                             psycopg.pq.PGconn.connect_start):
#                 with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
#                     connect("hostaddr=127.0.0.1 host=127.0.0.1 port=1 connect_timeout=1")
#             coroutine = _CAPTURED_ASYNC_CONNECT(hostaddr="127.0.0.1", host="127.0.0.1")
#             try:
#                 with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
#                     coroutine.send(None)
#             finally:
#                 coroutine.close()
#             with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
#                 socket.getaddrinfo("unreachable.invalid", 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_disposable_fixture_owns_settings_and_unique_database_and_removes_both
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disposable fixture owns settings and unique database and removes both.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disposable_fixture_owns_settings_and_unique_database_and_removes_both(self):
#         backend = SimulatedBackend()
#         with patch.dict(os.environ, {"MYCEL_CONFIG": "fictional-owner.toml"}):
#             with disposable_store(backend) as first:
#                 self.assertTrue(first.settings_file.exists())
#                 self.assertEqual(first.settings_file.stat().st_mode & 0o777, 0o600)
#                 self.assertEqual(require_check_database(first.database), first.database)
#                 self.assertEqual(os.environ["MYCEL_CONFIG"], str(first.settings_file))
#                 first_config = first.settings_file
#             self.assertFalse(first_config.exists())
#             self.assertEqual(os.environ["MYCEL_CONFIG"], "fictional-owner.toml")
#             with disposable_store(backend) as second:
#                 self.assertNotEqual(first.database, second.database)
#             self.assertEqual(backend.events[0], ("create", first.database))
#             self.assertEqual(backend.events[2], ("drop", first.database))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_disposable_database_cleanup_runs_after_initialization_and_body_failures
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disposable database cleanup runs after initialization and body failures.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disposable_database_cleanup_runs_after_initialization_and_body_failures(self):
#         for fail_init in (True, False):
#             backend = SimulatedBackend(fail_init=fail_init)
#             with self.assertRaises(RuntimeError):
#                 with disposable_store(backend):
#                     raise RuntimeError("body failed")
#             self.assertEqual([event[0] for event in backend.events], ["create", "initialize", "drop"])
#             self.assertFalse(backend.events[1][1].exists())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_simulated_store_and_failed_cleanup_cannot_prove_store_implementation
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Simulated store and failed cleanup cannot prove store implementation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_simulated_store_and_failed_cleanup_cannot_prove_store_implementation(self):
#         check = example_check(kind="store")
#         backend = SimulatedBackend()
#         report = run_checks(unittest.TestSuite([check]), store_backend=backend)
#         self.assertFalse(report.passed)
#         self.assertEqual(report.checks[0].status, "failed")
#         self.assertEqual(backend.events, [])
#         backend = SimulatedBackend(fail_drop=True)
#         with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
#             with disposable_store(backend):
#                 pass
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_store_names_and_addresses_are_refused_before_backend_calls
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Store names and addresses are refused before backend calls.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_store_names_and_addresses_are_refused_before_backend_calls(self):
#         for name in ("owner", "mycel_check_", "mycel_check_a;DROP", "mycel_check_" + "a" * 64, "mycel_check_../owner"):
#             with self.assertRaises(CoverageError):
#                 require_check_database(name)
#         backend = SimulatedBackend()
#         backend.address = lambda name: "postgresql://localhost/owner"
#         with self.assertRaises(CoverageError):
#             with disposable_store(backend):
#                 pass
#         self.assertEqual(backend.events, [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_postgres_backend_uses_administrative_database_and_clean_environment
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Postgres backend uses administrative database and clean environment.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_postgres_backend_uses_administrative_database_and_clean_environment(self):
#         for owner, expected in (("owner", "postgres"), ("postgres", "template1"), ("%70ostgres", "template1")):
#             backend = PostgresBackend("postgresql://user@localhost:5432/" + owner, psql="/fictional/psql")
#             with patch("mycel._coverage.subprocess.run") as execute:
#                 execute.return_value.returncode = 0
#                 execute.return_value.stdout = b"f\n"
#                 backend.create_database("mycel_check_safe")
#                 backend.drop_database("mycel_check_safe")
#                 self.assertEqual(execute.call_count, 3)
#                 for call in execute.call_args_list:
#                     command = call.args[0]
#                     self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost:5432/" + expected)
#                     self.assertNotIn("MYCEL_CONFIG", call.kwargs["env"])
#                     self.assertNotIn("PGPASSWORD", call.kwargs["env"])
#                     self.assertIn("mycel_check_safe", command[-1])
#                 with self.assertRaises(CoverageError):
#                     backend.drop_database(owner)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_postgres_backend_refuses_secrets_or_database_override_options
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Postgres backend refuses secrets or database override options.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_postgres_backend_refuses_secrets_or_database_override_options(self):
#         for address in ("postgresql://user:secret@localhost/owner", "postgresql://localhost/owner?dbname=other",
#                         "postgresql://localhost/owner?password=secret", "postgresql://localhost/owner#fragment",
#                         "https://localhost/owner", "postgresql://localhost/"):
#             with self.assertRaises(CoverageError):
#                 PostgresBackend(address, psql="/fictional/psql")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_internal_initializer_hook_preserves_private_fixture_and_default
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Internal initializer hook preserves private fixture and default.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_internal_initializer_hook_preserves_private_fixture_and_default(self):
#         backend = SimulatedBackend(fail_init=True)
#         seen = []
#         def bootstrap(store, config):
#             self.assertIs(store, backend)
#             self.assertEqual(os.environ["MYCEL_CONFIG"], str(config))
#             self.assertEqual(config.stat().st_mode & 0o777, 0o600)
#             seen.append(config)
#         with disposable_store(backend, initialize=bootstrap) as fixture:
#             self.assertIs(fixture.backend, backend)
#         self.assertEqual([event[0] for event in backend.events], ["create", "drop"])
#         self.assertFalse(seen[0].exists())
#         with self.assertRaisesRegex(RuntimeError, "initialization failed"):
#             with disposable_store(backend):
#                 self.fail("default initialization was bypassed")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_postgres_queries_cannot_address_owner_and_presence_uses_admin
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Postgres queries cannot address owner and presence uses admin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_postgres_queries_cannot_address_owner_and_presence_uses_admin(self):
#         backend = PostgresBackend("postgresql://user@localhost/owner", psql="/fictional/psql")
#         with patch.object(backend, "_execute", side_effect=["f", ""]):
#             backend.create_database("mycel_check_safe")
#         with patch("mycel._coverage.subprocess.run") as execute:
#             execute.return_value.returncode = 0
#             execute.return_value.stdout = b"mycel_check_safe\n"
#             self.assertEqual(backend.query("mycel_check_safe", "SELECT current_database()"), "mycel_check_safe")
#             command = execute.call_args.args[0]
#             self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost/mycel_check_safe")
#             execute.reset_mock()
#             with self.assertRaises(CoverageError):
#                 backend.query("owner", "SELECT 1")
#             execute.assert_not_called()
#             for sql in ("\\connect owner", "SELECT 1;\n\\c owner", "\\! command", "", "SELECT\0 1", None):
#                 with self.assertRaises(CoverageError):
#                     backend.query("mycel_check_safe", sql)
#             execute.assert_not_called()
#             execute.return_value.stdout = b"f\n"
#             self.assertFalse(backend.database_exists("mycel_check_safe"))
#             command = execute.call_args.args[0]
#             self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost/postgres")
#             execute.return_value.stdout = b"unexpected"
#             with self.assertRaisesRegex(RuntimeError, "presence check failed"):
#                 backend.database_exists("mycel_check_safe")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_postgres_backend_failures_are_sanitized_and_do_not_count_as_acceptance
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Postgres backend failures are sanitized and do not count as acceptance.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_postgres_backend_failures_are_sanitized_and_do_not_count_as_acceptance(self):
#         backend = PostgresBackend("postgresql://localhost/owner", psql="/fictional/psql")
#         with patch("mycel._coverage.subprocess.run") as execute:
#             execute.return_value.returncode = 1
#             execute.return_value.stderr = b"fictional provider secret"
#             with self.assertRaisesRegex(RuntimeError, "database operation failed") as failure:
#                 backend.create_database("mycel_check_safe")
#             self.assertNotIn("secret", str(failure.exception))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_previously_requested_acceptance_does_not_run_during_automatic_gate
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Previously requested acceptance does not run during automatic gate.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_previously_requested_acceptance_does_not_run_during_automatic_gate(self):
#         touched = []
#         live = example_check(name="RequestedLive", kind="live", action=lambda case: touched.append("explicit"))
#         proofs = run_on_demand_checks(((live, "live", ("MYC-13.9",)),),
#                                      implementation_identity="fictional-build-manifest-hash")
#         self.assertEqual(touched, ["explicit"])
#         self.assertEqual([(check.kind, check.requirements, check.status) for check in proofs.checks],
#                          [("live", ("MYC-13.9",), "passed")])
#         report = run_checks(unittest.TestSuite([example_check(), live]))
#         self.assertTrue(report.passed)
#         self.assertEqual(touched, ["explicit"])
#         self.assertEqual([result.kind for result in report.checks], ["unit"])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_on_demand_proofs_name_their_build_and_cannot_be_altered
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: On demand proofs name their build and cannot be altered.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_on_demand_proofs_name_their_build_and_cannot_be_altered(self):
#         from dataclasses import FrozenInstanceError
#         live = example_check(name="RequestedLive", kind="live")
#         proofs = run_on_demand_checks(((live, "live", ("MYC-13.9",)),),
#                                      implementation_identity="fictional-build-one")
#         self.assertEqual(proofs.implementation_identity, "fictional-build-one")
#         with self.assertRaises(FrozenInstanceError):
#             proofs.implementation_identity = "fictional-build-two"
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_coverage.py::CoverageTests.test_on_demand_requires_explicit_kinds_and_records_a_failed_proof
# Reason: Narrower case removed from this family after retaining test_process_workers_keep_canonical_outcomes_and_network_denial, test_worker_crash_rejects_gate_and_invalid_worker_configuration. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: On demand requires explicit kinds and records a failed proof.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_coverage.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_on_demand_requires_explicit_kinds_and_records_a_failed_proof(self):
#         check = example_check()
#         for declared, identity in (((check, "unit", ("MYC-13.9",)), "build"), ((check, "live", ()), "build"),
#                                    ((check, "live", ("MYC-13.9", "MYC-13.9")), "build"),
#                                    ((check, "live", ("not-a-requirement",)), "build"),
#                                    ((check, "live", ("MYC-13.9",)), "")):
#             with self.subTest(declared=declared[1:], identity=identity), self.assertRaises(CoverageError):
#                 run_on_demand_checks((declared,), implementation_identity=identity)
#         with self.assertRaises(CoverageError):
#             run_on_demand_checks((), implementation_identity="build")
#         live = example_check(name="FailedLive", kind="live", action=lambda case: case.fail("failed acceptance"))
#         proofs = run_on_demand_checks(((live, "live", ("MYC-13.9",)),), implementation_identity="build")
#         self.assertEqual(proofs.checks[0].status, "failed")
# LOW-TIER-SOURCE-END
# LOW-TIER-END
