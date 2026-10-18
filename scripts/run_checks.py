#!/usr/bin/env python3
"""Run all automatic checks, or selected checks, with private store fixtures."""

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

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
# Avoid multiplying numeric-library threads by the number of check processes.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "1"

from mycel._coverage import (CoverageError, declaration, discover_checks, iter_checks,
                             load_claims, load_registry, run_checks, select_checks,
                             verify_specification_snapshot)
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


def main(*, json_output: bool = False) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="require proofs for every active requirement")
    parser.add_argument("--claims", type=Path, default=REPOSITORY / "checks/claims.json")
    parser.add_argument("--tests", type=Path, default=REPOSITORY / "tests")
    parser.add_argument("--select", action="append", default=[], metavar="MODULE[.CLASS[.METHOD]]")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--specifications", type=Path)
    parser.add_argument("--store-settings", type=Path, help="read only store.address from this settings file")
    parser.add_argument("--report", type=Path, help="write the complete JSON report outside the repository")
    arguments = parser.parse_args()
    started = time.monotonic()
    try:
        if arguments.workers < 1:
            raise CoverageError("check workers must be a positive integer")
        if arguments.release and arguments.select:
            raise CoverageError("a release gate cannot select only part of the check inventory")
        registry = load_registry()
        if arguments.specifications is not None:
            verify_specification_snapshot(arguments.specifications)
        claims = load_claims(arguments.claims)
        suite = select_checks(discover_checks(arguments.tests), arguments.select)
        checks = list(iter_checks(suite))
        if arguments.select:
            names = {check.id() for check in checks}
            # Focused runs retain only claims whose complete proof list is present.
            claims = {identifier: proofs for identifier, proofs in claims.items() if set(proofs) <= names}
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
                    if any(declaration(check) and declaration(check).kind == "store" for check in checks):
                        try:
                            native.preflight()
                        except (CoverageError, RuntimeError):
                            reason = f"store checks unavailable at {native.server_label}: cannot connect or create a disposable database"
                            print(reason, file=sys.stderr)
                            backend = UnavailableStore(native, reason)
                report = run_checks(suite, registry=registry, claims=claims, release=arguments.release,
                                    store_backend=backend, workers=arguments.workers,
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
        if json_output:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            statuses = Counter(check.status for check in report.checks)
            kinds = Counter(check.kind for check in report.checks)
            summary = data["summary"]
            print(f"{statuses['passed']:,} passed, {statuses['failed']:,} failed, {statuses['skipped']:,} skipped; "
                  f"{kinds['unit']:,} unit, {kinds['store']:,} store; "
                  f"{summary['implemented']} requirements proven; {(time.monotonic()-started)/60:.2f} minutes")
            pending = [name for name, row in data["requirements"].items() if row["status"] == "pending"]
            if arguments.select:
                print(f"Pending: {len(pending)} requirements in this focused run.")
                print("Focused run; full requirement acceptance requires the complete make check run.")
            else:
                print("Pending: " + ", ".join(pending))
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
        if json_output:
            print(json.dumps({"passed": False, "errors": [str(error)]}))
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
