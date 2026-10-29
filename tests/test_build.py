# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Offline fixture proofs for staging; full MYC-15 acceptance stays unclaimed."""
import contextlib
import json
import multiprocessing
import shutil
import subprocess
import sys
import tarfile

from mycel_build.__main__ import main
from mycel_build._core import (BuildError, atomic_json, digest, extract_runtime,
                              file_manifest, install_wheel, json_bytes, load_lock,
                              read_json, seal_program, snapshot_asset, validate_manifest, verify_asset)
from mycel_build._registry import (allocate, build_number, list_records, maintenance,
                                  read_record, update_staging)
from mycel_build._staging import (check_input_manifest, create_stage, exec_installed, input_manifest,
                                 install_build_identity, installed_command, probe_installed,
                                 product_wheel, source_inputs, verify_source)


import base64
import csv
import hashlib
import io
import os
import stat
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mycel_build._core import BuildError, atomic_json, digest, json_bytes
from mycel_build._registry import allocate, list_records, read_record, update_staging
from mycel_build._staging import check_input_manifest, input_manifest, source_inputs

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {"commit": "a" * 40, "dirty": True, "inputsSha256": "b" * 64}


def _race(root, output):
    for _ in range(300):
        try:
            record = allocate(Path(root), target="macos-arm64", version="2.0.0", source=SOURCE)
            output.put(record["build"])
            return
        except BuildError as error:
            if error.code != "busy":
                raise
            time.sleep(0.002)
    raise RuntimeError("fixture allocator failed to acquire a nonwaiting lock")


def _frozen_fixture():
    return {"pyproject.toml": (ROOT / "pyproject.toml").read_bytes(),
            "src/mycel/__init__.py": b"",
            "src/mycel/cli.py": b"from ._cli import main\nraise SystemExit(main())\n",
            "src/mycel/_cli.py": b"def main(): return 0\n",
            "src/mycel/_store.py": b"STORE_FORMAT = 2\n",
            "src/mycel/data/voyage-code-4-tokenizer.json": b"{}\n",
            "src/mycel_build/private.py": b"raise RuntimeError('development code must not ship')\n"}


def _wheel_fixture(path, members, *, modes=None, extra_record=None):
    record = "fixture-1.0.dist-info/RECORD"
    rows = []
    with zipfile.ZipFile(path, "w") as wheel:
        for name, raw in members.items():
            checksum = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
            rows.append((name, "sha256=" + checksum, str(len(raw))))
            info = zipfile.ZipInfo(name)
            info.external_attr = (modes or {}).get(name, stat.S_IFREG | 0o644) << 16
            wheel.writestr(info, raw)
        rows.append((record, "", ""))
        if extra_record:
            rows.append(extra_record)
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerows(rows)
        wheel.writestr(record, output.getvalue())


class BuildInputsTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class BuildSourceBindingTests(unittest.TestCase):
    def stage_fixture(self, base):
        source = base / "source"
        for name, raw in {**_frozen_fixture(), "packaging/build-lock.json": b"{}\n",
                          "tests/test_fixture.py": b"pass\n",
                          "scripts/run_checks.py": b"pass\n", "Makefile": b"check:\n",
                          "docs/builds.md": b"Guide\n"}.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        identity, frozen = source_inputs(source)
        registry = base / "registry"
        allocate(registry, target="macos-arm64", version="2.0.0", source=identity)
        rows = input_manifest(frozen)
        checks = check_input_manifest(rows)
        atomic_json(registry / "1/source-inputs.json", rows)
        atomic_json(registry / "1/check-inputs.json", checks)
        update_staging(registry, "1", fields={"checkInputs": "check-inputs.json",
                       "checkManifestSha256": digest(json_bytes(checks)),
                       "lockSha256": digest(frozen["packaging/build-lock.json"])})
        return source, registry, rows


class BuildWheelTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class BuildManifestTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class BuildRegistryTests(unittest.TestCase):


    def _assert_hard_linked_retained_metadata_stays_damaged(self):
        for member in ("build.json", "checks.json", "build.log", "run.lock"):
            for partial in (False, True):
                with self.subTest(hardlink="existing", member=member, partial=partial), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    root = base / "registry"
                    allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                    folder = root / "1"
                    outside = base / "outside"
                    outside.write_bytes((folder / member).read_bytes())
                    (folder / member).unlink()
                    os.link(outside, folder / member)
                    os.utime(outside, ns=(1_234_567_890_000_000_000, 1_234_567_890_000_000_000))
                    outside_before = (outside.read_bytes(), outside.stat().st_mtime_ns)
                    if partial:
                        (folder / ("build.log" if member == "checks.json" else "checks.json")).unlink()
                    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
                    self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                    self.assertEqual((outside.read_bytes(), outside.stat().st_mtime_ns), outside_before)
                    self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}, before)
                    with self.assertRaises(BuildError):
                        read_record(root, "1")
                    rows = list_records(root)
                    self.assertEqual(rows[0], {"build": "1", "available": False,
                                               "reason": "Build record is missing or damaged."})
                    self.assertEqual(rows[1]["status"], "building")

    def _assert_recovery_preserves_outside_inodes_linked_after_validation(self):
        from mycel_build._registry import _materialize

        for member in ("build.json", "checks.json", "build.log", "run.lock"):
            with self.subTest(hardlink="after-validation", member=member), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "registry"
                allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                folder = root / "1"
                (folder / ("build.log" if member == "checks.json" else "checks.json")).unlink()
                outside = base / "outside"
                outside.write_bytes(b"Outside bytes must never be overwritten.\n")
                os.utime(outside, ns=(1_234_567_890_000_000_000, 1_234_567_890_000_000_000))
                outside_before = (outside.read_bytes(), outside.stat().st_mtime_ns)

                def replace_member(*args, **kwargs):
                    if kwargs.get("recovered"):
                        (folder / member).unlink(missing_ok=True)
                        os.link(outside, folder / member)
                    return _materialize(*args, **kwargs)

                with patch("mycel_build._registry._materialize", side_effect=replace_member):
                    self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                self.assertEqual((outside.read_bytes(), outside.stat().st_mtime_ns), outside_before)
                if member == "run.lock":
                    self.assertEqual(list_records(root)[0].get("available"), False)
                else:
                    self.assertEqual(read_record(root, "1")["status"], "failed")
                    self.assertEqual((folder / member).stat().st_nlink, 1)
                self.assertEqual(list_records(root)[1]["status"], "building")


# Archived complete imports; restore needed names in their original scope, not at this file tail.
