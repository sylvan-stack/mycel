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
