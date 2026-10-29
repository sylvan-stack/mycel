#!/usr/bin/env python3
"""Run explicitly selected tests with private store fixtures; see TESTS.md."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import tomllib
import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
# Avoid multiplying numeric-library threads by the number of check processes.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "1"

from mycel._coverage import CoverageError, check_kind, iter_checks, run_checks, select_checks
from mycel._check_store import NativePostgresBackend


class UnavailableStore:
    """Fail each store check after one failed preflight, without retrying SQL."""

    real_store = True

    def __init__(self, backend, reason):
        self.backend, self.reason = backend, reason

    def address(self, database):
        return self.backend.address(database)

    def create_database(self, database):
        raise RuntimeError(self.reason)


@contextmanager
def ownership_journal():
    directory = Path(tempfile.mkdtemp(prefix="mycel_check_run_"))
    try:
        yield directory
    finally:
        if any(directory.iterdir()):
            print(f"Cleanup incomplete; private ownership records retained at {directory}", file=sys.stderr)
        else:
            directory.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, default=REPOSITORY / "tests" / "top")
    parser.add_argument("--select", action="append", default=[], metavar="MODULE.CLASS.METHOD")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--store-settings", type=Path, help="read only store.address from this settings file")
    parser.add_argument("--report", type=Path, help="write the complete JSON report outside the repository")
    arguments = parser.parse_args()
    started = time.monotonic()
    try:
        if not arguments.select or any(len(name.split('.')) != 3 for name in arguments.select):
            raise CoverageError('Select exact MODULE.CLASS.METHOD cases; broad testing is disabled. See TESTS.md.')
        if arguments.workers < 1:
            raise CoverageError("check workers must be a positive integer")
        # Case modules live in top/; their existing shared fixtures stay in tests/.
        sys.path.insert(0, str(REPOSITORY / "tests"))
        sys.path.insert(0, str(arguments.tests.resolve()))
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromNames(arguments.select)
        if loader.errors:
            raise CoverageError('Selected tests could not be loaded: ' + '\n'.join(loader.errors))
        suite = select_checks(suite, arguments.select)
        checks = list(iter_checks(suite))
        backend = None
        with ownership_journal() as journal:
            native = None
            try:
                if arguments.store_settings is not None:
                    settings = tomllib.loads(arguments.store_settings.expanduser().read_text(encoding="utf-8"))
                    try:
                        address = settings["store"]["address"]
                    except (KeyError, TypeError) as error:
                        raise CoverageError("test store settings require store.address") from error
                    native = NativePostgresBackend(address, _ownership_journal=Path(journal))
                    backend = native
                    if any(check_kind(check) == "store" for check in checks):
                        try:
                            native.preflight()
                        except (CoverageError, RuntimeError):
                            reason = f"store checks unavailable at {native.server_label}: cannot connect or create a disposable database"
                            print(reason, file=sys.stderr)
                            backend = UnavailableStore(native, reason)
                report = run_checks(suite, store_backend=backend, workers=arguments.workers,
                                    tests_directory=arguments.tests)
            finally:
                # run_checks stops its workers before returning or raising.
                previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    if native is not None:
                        native.recover_owned_databases()
                finally:
                    signal.signal(signal.SIGINT, previous)
        data = report.to_dict()
        if arguments.report is not None:
            arguments.report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        statuses = Counter(check.status for check in report.checks)
        kinds = Counter(check.kind for check in report.checks)
        print(f"{statuses['passed']:,} passed, {statuses['failed']:,} failed, {statuses['skipped']:,} skipped; "
              f"{kinds['unit']:,} unit, {kinds['store']:,} store; {(time.monotonic()-started)/60:.2f} minutes")
        print("Selected tests only; this result is not full qualification. See TESTS.md.")
        for check in report.checks:
            if check.status != "passed":
                detail = (check.detail or check.status).strip().splitlines()[-1]
                print(f"{check.name}: {detail}", file=sys.stderr)
        for error in report.errors:
            print(error, file=sys.stderr)
        return 0 if report.passed else 1
    except KeyboardInterrupt:
        print("Check run interrupted; owned disposable databases cleaned.", file=sys.stderr)
        return 130
    except (CoverageError, OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
