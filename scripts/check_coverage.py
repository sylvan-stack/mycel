#!/usr/bin/env python3
"""Run the automatic Build checks and validate named requirement proofs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tomllib
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from mycel._coverage import (CoverageError, PostgresBackend, load_claims,
                             load_registry, run_checks, verify_specification_snapshot)
from mycel._check_store import NativePostgresBackend


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="require proofs for all active requirements")
    parser.add_argument("--claims", type=Path, default=REPOSITORY / "checks/claims.json")
    parser.add_argument("--tests", type=Path, default=REPOSITORY / "tests")
    parser.add_argument("--specifications", type=Path, help="also verify the authoritative specification snapshots")
    parser.add_argument("--store-settings", type=Path,
                        help="explicit settings file from which only the database server address is read")
    arguments = parser.parse_args()
    try:
        registry = load_registry()
        if arguments.specifications is not None:
            verify_specification_snapshot(arguments.specifications)
        claims = load_claims(arguments.claims)
        backend = None
        if arguments.store_settings is not None:
            settings = tomllib.loads(arguments.store_settings.read_text(encoding="utf-8"))
            try:
                address = settings["store"]["address"]
            except (KeyError, TypeError) as error:
                raise CoverageError("test store settings require store.address") from error
            backend = NativePostgresBackend(address)
        suite = unittest.defaultTestLoader.discover(str(arguments.tests))
        report = run_checks(suite, registry=registry, claims=claims, release=arguments.release,
                            store_backend=backend)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.passed else 1
    except (CoverageError, OSError, ValueError) as error:
        print(json.dumps({"passed": False, "errors": [str(error)]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
