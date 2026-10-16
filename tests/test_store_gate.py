"""Real PostgreSQL proof of the foundation gate, not product-schema acceptance."""

import os
import tomllib
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from mycel._coverage import (CoverageError, PostgresBackend, disposable_store,
                             proves, run_checks)


def initialize_probe(backend, settings_file):
    """Explicit test bootstrap until feature checks supply Mycel's initializer."""
    settings = tomllib.loads(settings_file.read_text())
    if set(settings) != {"store"} or set(settings["store"]) != {"address"}:
        raise AssertionError("fixture copied settings unrelated to the test store")
    database = urlsplit(settings["store"]["address"]).path.removeprefix("/")
    backend.query(database, "CREATE TABLE foundation_probe (value text NOT NULL)")


class StoreGateTests(unittest.TestCase):
    initialize_store = staticmethod(initialize_probe)

    @proves("MYC-0.11", kind="store")
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

        # Executed success qualifies a named claim; uncovered claims and failed
        # cleanup fail the same gate. No fake backend can qualify this proof.
        class Probe(unittest.TestCase):
            initialize_store = staticmethod(initialize_probe)

            @proves("MYC-0.11", kind="store")
            def runTest(case):
                current = case.store_fixture
                databases.append(current.database)
                configs.append(current.settings_file)
                case.assertEqual(current.backend.query(current.database, "SELECT current_database()"), current.database)

        proof = Probe()
        claim = {"MYC-0.11": [proof.id()]}
        report = run_checks(unittest.TestSuite([proof]), store_backend=backend, claims=claim)
        self.assertTrue(report.passed, report.errors)
        self.assertEqual(report.requirements["MYC-0.11"]["verified_by"], [proof.id()])
        self.assertFalse(backend.database_exists(databases[-1]))
        self.assertFalse(configs[-1].exists())

        report = run_checks(unittest.TestSuite([Probe()]), store_backend=backend,
                            claims={"MYC-0.11": ["unexecuted.proof"]})
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-0.11"]["status"], "pending")

        original_drop = backend.drop_database
        def fail_cleanup(database):
            original_drop(database)
            raise RuntimeError("injected cleanup failure after actual removal")
        with patch.object(backend, "drop_database", side_effect=fail_cleanup):
            report = run_checks(unittest.TestSuite([Probe()]), store_backend=backend, claims=claim)
        self.assertFalse(report.passed)
        self.assertEqual(report.requirements["MYC-0.11"]["status"], "pending")
        self.assertIn("cleanup failure", report.checks[0].detail)
        self.assertFalse(backend.database_exists(databases[-1]))
        self.assertFalse(configs[-1].exists())


if __name__ == "__main__":
    unittest.main()
