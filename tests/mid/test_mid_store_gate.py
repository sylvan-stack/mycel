"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_store_gate as _support
from test_store_gate import (
    CoverageError,
    Path,
    PostgresBackend,
    StoreGateTests,
    disposable_store,
    initialize_probe,
    os,
    patch,
    run_checks,
    signal,
    subprocess,
    sys,
    tempfile,
    textwrap,
    time,
    tomllib,
    unittest,
    urlsplit,
)


class StoreGateTests(_support.StoreGateTests):
# TEST-TIER-BEGIN tests/test_store_gate.py::StoreGateTests.test_source_runner_cleans_real_store_after_failure_and_cancellation
    def test_source_runner_cleans_real_store_after_failure_and_cancellation(self):
        fixture = self.store_fixture
        runner = Path(_support.__file__).resolve().parents[1] / "scripts" / "run_checks.py"
        with tempfile.TemporaryDirectory(prefix="runner_cleanup_", dir=fixture.root) as directory:
            root = Path(directory)
            module = root / "test_child_cleanup.py"
            ready = root / "database.ready"
            for mode, expected_status in (("failure", 1), ("cancel", 130)):
                with self.subTest(mode=mode):
                    ready.unlink(missing_ok=True)
                    module.write_text(textwrap.dedent(f"""\
                        from pathlib import Path
                        import time
                        import unittest

                        class ChildCleanupTests(unittest.TestCase):
                            check_kind = "store"
                            initialize_store = staticmethod(lambda backend, settings: None)

                            def test_cleanup(self):
                                fixture = self.store_fixture
                                ready = Path(__file__).with_name("database.ready")
                                pending = ready.with_suffix(".pending")
                                pending.write_text(fixture.database + "\\n" + str(fixture.settings_file))
                                pending.chmod(0o600)
                                pending.replace(ready)
                                if {mode!r} == "failure":
                                    self.fail("intentional disposable-store assertion failure")
                                while True:
                                    time.sleep(1)
                        """), encoding="utf-8")
                    command = [sys.executable, str(runner), "--tests", str(root),
                               "--select", "test_child_cleanup.ChildCleanupTests.test_cleanup",
                               "--workers", "2", "--store-settings", str(fixture.settings_file)]
                    process = subprocess.Popen(command, cwd=runner.parents[1],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        deadline = time.monotonic() + 30
                        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.05)
                        self.assertTrue(ready.exists(), "child store check did not publish its fixture")
                        database, settings = ready.read_text(encoding="utf-8").splitlines()
                        self.assertNotEqual(database, fixture.database)
                        if mode == "cancel":
                            self.assertTrue(fixture.backend.database_exists(database))
                            # Interrupt only the runner: it must stop its worker
                            # and let that worker remove the fixture it created.
                            process.send_signal(signal.SIGINT)
                        stdout, stderr = process.communicate(timeout=30)
                        self.assertEqual(process.returncode, expected_status, (stdout, stderr))
                        self.assertFalse(fixture.backend.database_exists(database))
                        self.assertFalse(Path(settings).exists())
                        self.assertTrue(fixture.backend.database_exists(fixture.database))
                        self.assertEqual(os.environ["MYCEL_CONFIG"], str(fixture.settings_file))
                    finally:
                        if process.poll() is None:
                            process.send_signal(signal.SIGINT)
                            try:
                                process.communicate(timeout=30)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.communicate()
# TEST-TIER-END tests/test_store_gate.py::StoreGateTests.test_source_runner_cleans_real_store_after_failure_and_cancellation

# TEST-TIER-BEGIN tests/test_store_gate.py::StoreGateTests.test_real_store_proofs_are_private_executed_and_discarded
    def test_real_store_proofs_are_private_executed_and_discarded(self):
        fixture = self.store_fixture
        backend = fixture.backend
        self.assertIsInstance(backend, PostgresBackend)
        self.assertEqual(os.environ["MYCEL_CONFIG"], str(fixture.settings_file))
        self.assertEqual(fixture.settings_file.stat().st_mode & 0o777, 0o600)
        self.assertTrue(backend.database_exists(fixture.database))
        self.assertEqual(backend.query(fixture.database, "SELECT current_database()"), fixture.database)
        backend.query(fixture.database, "INSERT INTO foundation_probe VALUES ('executed')")
        self.assertEqual(backend.query(fixture.database, "SELECT value FROM foundation_probe"), "executed")

        # Refusal occurs before connecting, even against a real backend.
        with patch.object(backend, "_execute", wraps=backend._execute) as execute:
            for unsafe in ("owner", "mycel_check_", "mycel_check_a;DROP"):
                with self.assertRaises(CoverageError):
                    backend.query(unsafe, "SELECT 1")
            execute.assert_not_called()

        databases = []
        configs = []
        def bootstrap(store, config):
            configs.append(config)
            databases.append(urlsplit(tomllib.loads(config.read_text())["store"]["address"]).path[1:])
            initialize_probe(store, config)

        for fault in (None, AssertionError("check failed"), KeyboardInterrupt()):
            def exercise():
                with disposable_store(backend, initialize=bootstrap) as temporary:
                    self.assertNotEqual(temporary.database, fixture.database)
                    self.assertEqual(backend.query(temporary.database, "SELECT current_database()"), temporary.database)
                    if fault is not None:
                        raise fault
            if fault is None:
                exercise()
            else:
                with self.assertRaises(type(fault)):
                    exercise()
            self.assertFalse(backend.database_exists(databases[-1]))
            self.assertFalse(configs[-1].exists())
            self.assertEqual(os.environ["MYCEL_CONFIG"], str(fixture.settings_file))

        def broken_initialization(store, config):
            bootstrap(store, config)
            raise RuntimeError("test bootstrap failed")
        with self.assertRaisesRegex(RuntimeError, "bootstrap failed"):
            with disposable_store(backend, initialize=broken_initialization):
                self.fail("failed initialization ran the check")
        self.assertFalse(backend.database_exists(databases[-1]))
        self.assertFalse(configs[-1].exists())
        self.assertEqual(len(set(databases)), len(databases))

        # Executed success passes the gate; failed cleanup fails it. No fake
        # backend can qualify this store check.
        class Probe(unittest.TestCase):
            check_kind = "store"
            initialize_store = staticmethod(initialize_probe)

            def runTest(case):
                current = case.store_fixture
                databases.append(current.database)
                configs.append(current.settings_file)
                case.assertEqual(current.backend.query(current.database, "SELECT current_database()"), current.database)

        proof = Probe()
        report = run_checks(unittest.TestSuite([proof]), store_backend=backend)
        self.assertTrue(report.passed, report.errors)
        self.assertEqual([(check.name, check.kind) for check in report.checks], [(proof.id(), "store")])
        self.assertFalse(backend.database_exists(databases[-1]))
        self.assertFalse(configs[-1].exists())

        original_drop = backend.drop_database
        def fail_cleanup(database):
            original_drop(database)
            raise RuntimeError("injected cleanup failure after actual removal")
        with patch.object(backend, "drop_database", side_effect=fail_cleanup):
            report = run_checks(unittest.TestSuite([Probe()]), store_backend=backend)
        self.assertFalse(report.passed)
        self.assertEqual(report.checks[0].status, "failed")
        self.assertIn("cleanup failure", report.checks[0].detail)
        self.assertFalse(backend.database_exists(databases[-1]))
        self.assertFalse(configs[-1].exists())
# TEST-TIER-END tests/test_store_gate.py::StoreGateTests.test_real_store_proofs_are_private_executed_and_discarded
