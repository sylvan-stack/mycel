"""Executed proof for the requirement registry and automatic gate machinery."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from importlib.resources import files
import json
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import psycopg

from mycel._coverage import ACTIVE_REQUIREMENTS, SPECIFICATION_COUNT
from mycel._coverage import (AUTOMATIC_KINDS, CoverageError, PostgresBackend,
                             disposable_store, discover_checks, iter_checks, select_checks, load_claims, load_registry,
                             proves, require_check_database, run_checks, run_on_demand_checks,
                             verify_specification_snapshot, no_network)
from mycel._database import _native_connect as _CAPTURED_NATIVE_CONNECT


_CAPTURED_CONNECT = psycopg.connect
_CAPTURED_CLASS_CONNECT = psycopg.Connection.connect
_CAPTURED_ASYNC_CONNECT = psycopg.AsyncConnection.connect


def example_check(*, name="Example", requirement="MYC-13.3", kind="unit", action=None, skip=False):
    def runTest(self):
        if skip:
            self.skipTest("deliberately not executed")
        if action:
            action(self)
    return type(name, (unittest.TestCase,), {"runTest": proves(requirement, kind=kind)(runTest)})()


class SimulatedBackend:
    real_store = False

    def __init__(self, *, fail_init=False, fail_drop=False):
        self.events = []
        self.fail_init = fail_init
        self.fail_drop = fail_drop

    def address(self, database):
        return "postgresql://localhost/" + database

    def create_database(self, database):
        self.events.append(("create", database))

    def initialize(self, settings_file):
        self.events.append(("initialize", settings_file))
        data = tomllib.loads(settings_file.read_text())
        if set(data) != {"store"} or set(data["store"]) != {"address"}:
            raise AssertionError("copied owner settings")
        if os.environ.get("MYCEL_CONFIG") != str(settings_file):
            raise AssertionError("test did not own MYCEL_CONFIG")
        if self.fail_init:
            raise RuntimeError("initialization failed")

    def drop_database(self, database):
        self.events.append(("drop", database))
        if self.fail_drop:
            raise RuntimeError("cleanup failed")


class CoverageTests(unittest.TestCase):
    @proves('MYC-13.15')
    def test_passing_draft_requirement_keeps_its_snapshot_status(self):
        check = example_check(requirement='MYC-17.2')
        report = run_checks(unittest.TestSuite([check]), claims={'MYC-17.2': [check.id()]})
        self.assertTrue(report.passed)
        self.assertEqual(report.requirements['MYC-17.2']['status'], 'implemented')
        self.assertEqual(report.requirements['MYC-17.2']['specification_status'], 'draft')
        self.assertEqual(report.requirements['MYC-13.3']['specification_status'], 'accepted')

    @proves("MYC-13.3", "MYC-13.15")
    def test_process_workers_keep_canonical_outcomes_claims_and_network_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_worker_proofs.py").write_text('''import signal
import socket
import unittest
from mycel._coverage import proves
class WorkerProofs(unittest.TestCase):
    @proves("MYC-13.3")
    def test_pass(self):
        for _ in range(2):
            with self.assertRaises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGINT)
        with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
            socket.create_connection(("127.0.0.1", 1))
    @proves("MYC-13.3")
    def test_failure(self):
        self.fail("expected worker assertion")
    @proves("MYC-13.3")
    def test_skip(self):
        self.skipTest("expected worker skip")
''')
            try:
                suite = discover_checks(root)
                names = [check.id() for check in iter_checks(suite)]
                self.assertEqual(len(names), 3)
                selected = select_checks(suite, ["test_worker_proofs.WorkerProofs.test_pass"])
                report = run_checks(selected, workers=2, tests_directory=root,
                                    claims={"MYC-13.3": [names[1]]})
                self.assertTrue(report.passed, report.errors)
                self.assertEqual(report.requirements["MYC-13.3"]["verified_by"], [names[1]])
                report = run_checks(discover_checks(root), workers=2, tests_directory=root,
                                    claims={"MYC-13.3": [names[1]]})
                self.assertFalse(report.passed)
                self.assertEqual([check.name for check in report.checks], names)
                self.assertEqual([check.status for check in report.checks], ["failed", "passed", "skipped"])
                with self.assertRaisesRegex(CoverageError, "no checks match"):
                    select_checks(discover_checks(root), ["missing_module"])
            finally:
                sys.modules.pop("test_worker_proofs", None)

    @proves("MYC-13.3", "MYC-13.15")
    def test_worker_crash_rejects_gate_and_invalid_worker_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_worker_crash.py").write_text('''import os
from pathlib import Path
import signal
import time
import unittest
from mycel._coverage import proves
class WorkerCrash(unittest.TestCase):
    @proves("MYC-13.3")
    def test_a_stubborn(self):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path(__file__).with_suffix(".ready").write_text("ready")
        while True:
            time.sleep(0.1)
    @proves("MYC-13.3")
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

    @proves("MYC-13.15")
    def test_complete_registry_keeps_negative_requirement_active(self):
        registry = load_registry()
        self.assertEqual(len(registry), ACTIVE_REQUIREMENTS)
        counts = [sum(row.specification == f"MYC-{number}" for row in registry.values())
                  for number in range(SPECIFICATION_COUNT)]
        self.assertEqual(counts, [12, 39, 27, 21, 29, 18, 23, 18, 29, 13, 14, 13, 15, 21, 28, 12, 15, 15])
        self.assertEqual(registry["MYC-9.10"].origin, "Dropped")
        self.assertEqual(registry["MYC-9.10"].kind, "store")
        self.assertIn("not show", registry["MYC-9.10"].text)

    @proves("MYC-13.15")
    def test_registry_rejects_missing_duplicate_unknown_kind_and_unaccepted_rows(self):
        original = json.loads(files("mycel").joinpath("data/requirements.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            for mutation in (lambda data: data["requirements"].pop(),
                             lambda data: data["requirements"].append(data["requirements"][0]),
                             lambda data: data["requirements"][0].update(kind="reviewed"),
                             lambda data: data.update(schema_version=True),
                             lambda data: next(iter(data["specifications"].values())).update(specification_status="review")):
                data = json.loads(json.dumps(original))
                mutation(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(CoverageError):
                    load_registry(path)

    @proves("MYC-13.15")
    def test_snapshot_verification_detects_a_changed_authoritative_source(self):
        data = json.loads(files("mycel").joinpath("data/requirements.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, metadata in data["specifications"].items():
                contents = ("fictional source: " + filename).encode()
                (root / filename).write_bytes(contents)
                metadata["sha256"] = sha256(contents).hexdigest()
            registry_path = root / "requirements.json"
            registry_path.write_text(json.dumps(data))
            verify_specification_snapshot(root, registry_path)
            filename = next(iter(data["specifications"]))
            (root / filename).write_text("changed source")
            with self.assertRaisesRegex(CoverageError, "specification changed"):
                verify_specification_snapshot(root, registry_path)

    @proves("MYC-13.3", "MYC-13.15")
    def test_check_declarations_require_distinct_requirement_identifiers(self):
        for requirements, kind in (((), "unit"), (("MYC-13.3", "MYC-13.3"), "unit"),
                                   (("MYC-18.1",), "unit"), (("MYC-13.3",), "review")):
            with self.assertRaises(CoverageError):
                proves(*requirements, kind=kind)
        decorated = proves("MYC-13.3")(lambda: None)
        with self.assertRaises(CoverageError):
            proves("MYC-13.15")(decorated)

    @proves("MYC-13.3", "MYC-13.15")
    def test_a_check_without_requirement_metadata_is_rejected(self):
        class Unnamed(unittest.TestCase):
            def runTest(self):
                raise AssertionError("should not execute")
        report = run_checks(unittest.TestSuite([Unnamed()]))
        self.assertFalse(report.passed)
        self.assertIn("names no requirements", report.errors[0])

    @proves("MYC-13.3", "MYC-13.15")
    def test_duplicate_check_names_and_wrong_kinds_do_not_execute(self):
        duplicate = example_check()
        report = run_checks(unittest.TestSuite([duplicate, example_check()]))
        self.assertFalse(report.passed)
        self.assertEqual(len(report.checks), 1)
        report = run_checks(unittest.TestSuite([example_check(requirement="MYC-13.4")]))
        self.assertFalse(report.passed)
        self.assertIn("does not prove", report.errors[0])
        self.assertEqual(report.checks, ())

    @proves("MYC-13.15")
    def test_reserved_unknown_requirement_does_not_qualify(self):
        check = example_check(requirement="MYC-7.1")
        self.assertNotIn("MYC-7.1", load_registry())
        report = run_checks(unittest.TestSuite([check]), claims={"MYC-7.1": [check.id()]})
        self.assertFalse(report.passed)
        self.assertIn("unknown requirement", report.errors[0])
        self.assertTrue(any("unknown implemented requirement" in error for error in report.errors))

    @proves("MYC-13.15")
    def test_staged_claim_requires_the_named_passing_executed_proof(self):
        check = example_check()
        report = run_checks(unittest.TestSuite([check]), claims={"MYC-13.3": [check.id()]})
        self.assertTrue(report.passed)
        self.assertEqual(report.to_dict()["summary"], {"active": ACTIVE_REQUIREMENTS, "implemented": 1, "pending": ACTIVE_REQUIREMENTS - 1})
        self.assertEqual(report.requirements["MYC-13.3"]["verified_by"], [check.id()])
        self.assertEqual(report.requirements["MYC-13.3"]["specification_status"], "accepted")
        report = run_checks(unittest.TestSuite([example_check()]), claims={"MYC-13.3": ["imaginary.Check.test"]})
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.3"]["status"], "pending")

    @proves("MYC-13.15")
    def test_a_passing_unrelated_test_cannot_prove_a_claim(self):
        check = example_check()
        report = run_checks(unittest.TestSuite([check]), claims={"MYC-13.15": [check.id()]})
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.15"]["status"], "pending")

    @proves("MYC-13.15")
    def test_full_release_gate_rejects_all_pending_requirements(self):
        report = run_checks(unittest.TestSuite([example_check()]), release=True)
        self.assertFalse(report.passed)
        self.assertEqual(report.to_dict()["summary"]["pending"], ACTIVE_REQUIREMENTS)
        self.assertIn("MYC-9.10", report.errors[-1])
        self.assertIn("MYC-16.14", report.errors[-1])
        registry = load_registry()
        registry.pop("MYC-0.1")
        with self.assertRaisesRegex(CoverageError, "complete active"):
            run_checks(unittest.TestSuite([example_check()]), registry=registry, release=True)

    @proves("MYC-13.1", "MYC-13.15")
    def test_any_failed_unclaimed_automatic_check_fails_the_gate(self):
        def fail(case):
            case.fail("fictional failing proof")
        report = run_checks(unittest.TestSuite([example_check(action=fail)]))
        self.assertFalse(report.passed)
        self.assertEqual(report.checks[0].status, "failed")

    @proves("MYC-13.1", "MYC-13.15")
    def test_skipped_and_expected_failure_checks_never_count_as_passed(self):
        skipped = example_check(skip=True)
        report = run_checks(unittest.TestSuite([skipped]), claims={"MYC-13.3": [skipped.id()]})
        self.assertFalse(report.passed)
        self.assertEqual(report.checks[0].status, "skipped")
        expected = example_check(action=lambda case: case.fail("expected failure"))
        expected.runTest.__func__.__unittest_expecting_failure__ = True
        report = run_checks(unittest.TestSuite([expected]), claims={"MYC-13.3": [expected.id()]})
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.3"]["status"], "pending")

    @proves("MYC-13.1", "MYC-13.15")
    def test_subtest_and_setup_failures_reach_the_gate(self):
        def subtest(case):
            with case.subTest(part="failed"):
                case.fail("subtest failed")
        report = run_checks(unittest.TestSuite([example_check(action=subtest)]))
        self.assertFalse(report.passed)
        check = example_check()
        def fail_setup(cls):
            raise RuntimeError("class setup failed")
        type(check).setUpClass = classmethod(fail_setup)
        report = run_checks(unittest.TestSuite([check]))
        self.assertFalse(report.passed)

    @proves("MYC-13.1", "MYC-13.2")
    def test_unit_and_store_checks_are_mandatory_eval_and_live_are_excluded(self):
        touched = []
        unit = example_check(name="Unit", action=lambda case: touched.append("unit"))
        store = example_check(name="Store", requirement="MYC-13.4", kind="store")
        evaluation = example_check(name="Eval", requirement="MYC-13.20", kind="eval", action=lambda case: touched.append("eval"))
        live = example_check(name="Live", requirement="MYC-13.9", kind="live", action=lambda case: touched.append("live"))
        report = run_checks(unittest.TestSuite([unit, store, evaluation, live]))
        self.assertEqual(touched, ["unit"])
        self.assertEqual([result.kind for result in report.checks], ["unit", "store"])
        self.assertFalse(report.passed)
        self.assertIn("no disposable database backend", report.checks[1].detail)
        for kinds in (frozenset({"unit"}), frozenset({"live"}), AUTOMATIC_KINDS | {"eval"}):
            with self.assertRaises(CoverageError):
                run_checks(unittest.TestSuite([example_check()]), kinds=kinds)

    @proves("MYC-13.15")
    def test_automatic_unit_network_attempts_fail_without_connecting(self):
        def connect(case):
            socket.create_connection(("127.0.0.1", 1))
        report = run_checks(unittest.TestSuite([example_check(action=connect)]))
        self.assertFalse(report.passed)
        self.assertIn("network access is forbidden", report.checks[0].detail)

    @proves("MYC-13.15")
    def test_preimported_native_boundary_alias_refuses_before_libpq_parameter_work(self):
        with no_network(), patch("mycel._database.conninfo.make_conninfo") as parameters:
            with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
                _CAPTURED_NATIVE_CONNECT(timeout_seconds=0.1, hostaddr="127.0.0.1", host="127.0.0.1")
            parameters.assert_not_called()

    @proves("MYC-13.15")
    def test_standard_and_preimported_psycopg_entries_and_default_pq_are_blocked(self):
        with no_network():
            for connect in (_CAPTURED_CONNECT, _CAPTURED_CLASS_CONNECT, psycopg.connect,
                            psycopg.Connection.connect, psycopg.pq.PGconn.connect,
                            psycopg.pq.PGconn.connect_start):
                with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
                    connect("hostaddr=127.0.0.1 host=127.0.0.1 port=1 connect_timeout=1")
            coroutine = _CAPTURED_ASYNC_CONNECT(hostaddr="127.0.0.1", host="127.0.0.1")
            try:
                with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
                    coroutine.send(None)
            finally:
                coroutine.close()
            with self.assertRaisesRegex(RuntimeError, "network access is forbidden"):
                socket.getaddrinfo("unreachable.invalid", 1)

    @proves("MYC-13.15")
    def test_claims_file_rejects_empty_repeated_or_wrong_schema_proofs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            for value in ({"schema_version": 1, "implemented": {"MYC-13.3": []}},
                          {"schema_version": 1, "implemented": {"MYC-13.3": ["same", "same"]}},
                          {"schema_version": True, "implemented": {}},
                          {"schema_version": 1, "implemented": {}, "accepted": True}):
                path.write_text(json.dumps(value))
                with self.assertRaises(CoverageError):
                    load_claims(path)
            path.write_text(json.dumps({"schema_version": 1, "implemented": {"MYC-13.3": ["named.proof"]}}))
            self.assertEqual(load_claims(path), {"MYC-13.3": ("named.proof",)})

    @proves("MYC-13.15")
    def test_disposable_fixture_owns_settings_and_unique_database_and_removes_both(self):
        backend = SimulatedBackend()
        with patch.dict(os.environ, {"MYCEL_CONFIG": "fictional-owner.toml"}):
            with disposable_store(backend) as first:
                self.assertTrue(first.settings_file.exists())
                self.assertEqual(first.settings_file.stat().st_mode & 0o777, 0o600)
                self.assertEqual(require_check_database(first.database), first.database)
                self.assertEqual(os.environ["MYCEL_CONFIG"], str(first.settings_file))
                first_config = first.settings_file
            self.assertFalse(first_config.exists())
            self.assertEqual(os.environ["MYCEL_CONFIG"], "fictional-owner.toml")
            with disposable_store(backend) as second:
                self.assertNotEqual(first.database, second.database)
            self.assertEqual(backend.events[0], ("create", first.database))
            self.assertEqual(backend.events[2], ("drop", first.database))

    @proves("MYC-13.15")
    def test_disposable_database_cleanup_runs_after_initialization_and_body_failures(self):
        for fail_init in (True, False):
            backend = SimulatedBackend(fail_init=fail_init)
            with self.assertRaises(RuntimeError):
                with disposable_store(backend):
                    raise RuntimeError("body failed")
            self.assertEqual([event[0] for event in backend.events], ["create", "initialize", "drop"])
            self.assertFalse(backend.events[1][1].exists())

    @proves("MYC-13.15")
    def test_simulated_store_and_failed_cleanup_cannot_prove_store_implementation(self):
        check = example_check(requirement="MYC-13.4", kind="store")
        backend = SimulatedBackend()
        report = run_checks(unittest.TestSuite([check]), store_backend=backend, claims={"MYC-13.4": [check.id()]})
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.4"]["status"], "pending")
        self.assertEqual(backend.events, [])
        backend = SimulatedBackend(fail_drop=True)
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            with disposable_store(backend):
                pass

    @proves("MYC-13.15")
    def test_store_names_and_addresses_are_refused_before_backend_calls(self):
        for name in ("owner", "mycel_check_", "mycel_check_a;DROP", "mycel_check_" + "a" * 64, "mycel_check_../owner"):
            with self.assertRaises(CoverageError):
                require_check_database(name)
        backend = SimulatedBackend()
        backend.address = lambda name: "postgresql://localhost/owner"
        with self.assertRaises(CoverageError):
            with disposable_store(backend):
                pass
        self.assertEqual(backend.events, [])

    @proves("MYC-13.15")
    def test_postgres_backend_uses_administrative_database_and_clean_environment(self):
        for owner, expected in (("owner", "postgres"), ("postgres", "template1"), ("%70ostgres", "template1")):
            backend = PostgresBackend("postgresql://user@localhost:5432/" + owner, psql="/fictional/psql")
            with patch("mycel._coverage.subprocess.run") as execute:
                execute.return_value.returncode = 0
                execute.return_value.stdout = b"f\n"
                backend.create_database("mycel_check_safe")
                backend.drop_database("mycel_check_safe")
                self.assertEqual(execute.call_count, 3)
                for call in execute.call_args_list:
                    command = call.args[0]
                    self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost:5432/" + expected)
                    self.assertNotIn("MYCEL_CONFIG", call.kwargs["env"])
                    self.assertNotIn("PGPASSWORD", call.kwargs["env"])
                    self.assertIn("mycel_check_safe", command[-1])
                with self.assertRaises(CoverageError):
                    backend.drop_database(owner)

    @proves("MYC-13.15")
    def test_postgres_backend_refuses_secrets_or_database_override_options(self):
        for address in ("postgresql://user:secret@localhost/owner", "postgresql://localhost/owner?dbname=other",
                        "postgresql://localhost/owner?password=secret", "postgresql://localhost/owner#fragment",
                        "https://localhost/owner", "postgresql://localhost/"):
            with self.assertRaises(CoverageError):
                PostgresBackend(address, psql="/fictional/psql")

    @proves("MYC-13.15")
    def test_internal_initializer_hook_preserves_private_fixture_and_default(self):
        backend = SimulatedBackend(fail_init=True)
        seen = []
        def bootstrap(store, config):
            self.assertIs(store, backend)
            self.assertEqual(os.environ["MYCEL_CONFIG"], str(config))
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            seen.append(config)
        with disposable_store(backend, initialize=bootstrap) as fixture:
            self.assertIs(fixture.backend, backend)
        self.assertEqual([event[0] for event in backend.events], ["create", "drop"])
        self.assertFalse(seen[0].exists())
        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            with disposable_store(backend):
                self.fail("default initialization was bypassed")

    @proves("MYC-13.15")
    def test_postgres_queries_cannot_address_owner_and_presence_uses_admin(self):
        backend = PostgresBackend("postgresql://user@localhost/owner", psql="/fictional/psql")
        with patch.object(backend, "_execute", side_effect=["f", ""]):
            backend.create_database("mycel_check_safe")
        with patch("mycel._coverage.subprocess.run") as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = b"mycel_check_safe\n"
            self.assertEqual(backend.query("mycel_check_safe", "SELECT current_database()"), "mycel_check_safe")
            command = execute.call_args.args[0]
            self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost/mycel_check_safe")
            execute.reset_mock()
            with self.assertRaises(CoverageError):
                backend.query("owner", "SELECT 1")
            execute.assert_not_called()
            for sql in ("\\connect owner", "SELECT 1;\n\\c owner", "\\! command", "", "SELECT\0 1", None):
                with self.assertRaises(CoverageError):
                    backend.query("mycel_check_safe", sql)
            execute.assert_not_called()
            execute.return_value.stdout = b"f\n"
            self.assertFalse(backend.database_exists("mycel_check_safe"))
            command = execute.call_args.args[0]
            self.assertEqual(command[command.index("--dbname") + 1], "postgresql://user@localhost/postgres")
            execute.return_value.stdout = b"unexpected"
            with self.assertRaisesRegex(RuntimeError, "presence check failed"):
                backend.database_exists("mycel_check_safe")

    @proves("MYC-13.15")
    def test_postgres_backend_failures_are_sanitized_and_do_not_count_as_acceptance(self):
        backend = PostgresBackend("postgresql://localhost/owner", psql="/fictional/psql")
        with patch("mycel._coverage.subprocess.run") as execute:
            execute.return_value.returncode = 1
            execute.return_value.stderr = b"fictional provider secret"
            with self.assertRaisesRegex(RuntimeError, "database operation failed") as failure:
                backend.create_database("mycel_check_safe")
            self.assertNotIn("secret", str(failure.exception))

    @proves("MYC-13.2", "MYC-13.15")
    def test_previously_requested_acceptance_does_not_run_during_automatic_gate(self):
        touched = []
        live = example_check(name="RequestedLive", requirement="MYC-13.9", kind="live", action=lambda case: touched.append("explicit"))
        proofs = run_on_demand_checks(unittest.TestSuite([live]), kinds=frozenset({"live"}),
                                     implementation_identity="fictional-build-manifest-hash")
        self.assertEqual(touched, ["explicit"])
        report = run_checks(unittest.TestSuite([example_check()]), claims={"MYC-13.9": [live.id()]},
                            on_demand_proofs=[proofs], implementation_identity="fictional-build-manifest-hash")
        self.assertTrue(report.passed)
        self.assertEqual(touched, ["explicit"])
        self.assertEqual(report.requirements["MYC-13.9"]["status"], "implemented")
        self.assertEqual(len(report.on_demand_checks), 1)
        self.assertEqual([result.kind for result in report.checks], ["unit"])

    @proves("MYC-13.2", "MYC-13.15")
    def test_on_demand_proofs_cannot_be_reused_for_a_different_build_or_registry(self):
        live = example_check(name="RequestedLive", requirement="MYC-13.9", kind="live")
        proofs = run_on_demand_checks(unittest.TestSuite([live]), kinds=frozenset({"live"}),
                                     implementation_identity="fictional-build-one")
        report = run_checks(unittest.TestSuite([example_check()]), claims={"MYC-13.9": [live.id()]},
                            on_demand_proofs=[proofs], implementation_identity="fictional-build-two")
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.9"]["status"], "pending")
        registry = load_registry()
        registry["MYC-0.1"] = replace(registry["MYC-0.1"], text="changed requirement contract")
        report = run_checks(unittest.TestSuite([example_check()]), registry=registry,
                            claims={"MYC-13.9": [live.id()]}, on_demand_proofs=[proofs],
                            implementation_identity="fictional-build-one")
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.9"]["status"], "pending")

    @proves("MYC-13.2", "MYC-13.15")
    def test_on_demand_requires_explicit_kinds_and_failed_proof_stays_pending(self):
        for kinds, identity in ((frozenset({"unit"}), "build"), (frozenset(), "build"), (frozenset({"live"}), "")):
            with self.assertRaises(CoverageError):
                run_on_demand_checks(unittest.TestSuite([example_check()]), kinds=kinds, implementation_identity=identity)
        live = example_check(name="FailedLive", requirement="MYC-13.9", kind="live", action=lambda case: case.fail("failed acceptance"))
        proofs = run_on_demand_checks(unittest.TestSuite([live]), kinds=frozenset({"live"}), implementation_identity="build")
        report = run_checks(unittest.TestSuite([example_check()]), claims={"MYC-13.9": [live.id()]},
                            on_demand_proofs=[proofs], implementation_identity="build")
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-13.9"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
