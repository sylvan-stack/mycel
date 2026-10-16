"""Offline fixture proofs for staging; full MYC-15 acceptance stays unclaimed."""

import contextlib
import base64
import csv
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from mycel._coverage import proves
from mycel_build.__main__ import main
from mycel_build._core import (BuildError, atomic_json, digest, extract_runtime,
                              file_manifest, install_wheel, json_bytes, load_lock,
                              read_json, seal_program, snapshot_asset, validate_manifest, verify_asset)
from mycel_build._registry import (allocate, build_number, list_records, maintenance,
                                  read_record, update_staging)
from mycel_build._staging import (check_input_manifest, create_stage, exec_installed, input_manifest,
                                 install_build_identity, installed_command, probe_installed,
                                 product_wheel, source_inputs, verify_source)


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
    @proves('MYC-15.1')
    def test_creation_refuses_free_threaded_and_non_cpython_before_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "unused-registry"
            for implementation, free_threaded in (("CPython", 1), ("PyPy", 0)):
                with self.subTest(implementation=implementation), patch(
                        "mycel_build._staging.platform.python_version", return_value="3.14.7"), patch(
                        "mycel_build._staging.platform.python_implementation", return_value=implementation), patch(
                        "mycel_build._staging.sysconfig.get_config_var", return_value=free_threaded):
                    with self.assertRaises(BuildError):
                        create_stage(ROOT, ROOT / "packaging/build-lock.json", Path(directory), registry, "macos-arm64")
                self.assertFalse(registry.exists())
            for target in ("macos-x86_64", "linux-arm64"):
                with self.subTest(target=target), patch(
                        "mycel_build._staging.platform.python_version", return_value="3.14.7"), patch(
                        "mycel_build._staging.platform.python_implementation", return_value="CPython"), patch(
                        "mycel_build._staging.sysconfig.get_config_var", return_value=0), patch(
                        "mycel_build._staging.source_inputs") as capture, patch(
                        "mycel_build._staging.allocate") as allocate_build:
                    with self.assertRaises(BuildError) as caught:
                        create_stage(ROOT, ROOT / "packaging/build-lock.json", Path(directory), registry, target)
                self.assertEqual(caught.exception.code, "invalid_input")
                capture.assert_not_called()
                allocate_build.assert_not_called()
                self.assertFalse(registry.exists())

    @proves('MYC-15.1', 'MYC-15.2')
    def test_checked_in_target_pins_and_licence_digests(self):
        lock_path = ROOT / "packaging/build-lock.json"
        lock, row = load_lock(lock_path, "macos-arm64")
        self.assertEqual(set(lock["targets"]), {"macos-arm64"})
        self.assertEqual(lock["python"], "3.14.7")
        self.assertEqual(len(row["dependencies"]), 29)
        dependencies = {d["name"]: d for d in row["dependencies"]}
        numerical_pins = {"numpy": "2.5.4", "scipy": "1.18.1", "scikit-learn": "1.9.1",
                          "joblib": "1.6.0", "narwhals": "2.27.1", "threadpoolctl": "3.7.0",
                          "cloudpickle": "3.1.2"}
        self.assertEqual({name: dependencies[name]["version"] for name in numerical_pins}, numerical_pins)
        for name in ("numpy", "scipy"):
            self.assertTrue(dependencies[name]["filename"].endswith(
                "-cp314-cp314-macosx_14_0_arm64.whl"))
        self.assertTrue(dependencies["scikit-learn"]["filename"].endswith(
            "-cp314-cp314-macosx_12_0_arm64.whl"))
        self.assertTrue(all(dependencies[name]["filename"].endswith("-py3-none-any.whl")
                            for name in ("joblib", "narwhals", "threadpoolctl", "cloudpickle")))
        self.assertTrue(all(d["filename"].endswith(".whl") for d in row["dependencies"]))
        self.assertEqual(row["runtime"]["python"], "3.14.7")
        for target in ("macos-x86_64", "linux-arm64"):
            with self.subTest(target=target), patch("mycel_build._core.read_json") as read:
                with self.assertRaises(BuildError) as caught:
                    load_lock(lock_path, target)
                self.assertEqual(caught.exception.code, "invalid_input")
                read.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            copied_lock = Path(directory) / "build-lock.json"
            for asset in (row["runtime"], *row["dependencies"]):
                for licence in asset["licenses"]:
                    destination = copied_lock.parent / licence["path"]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(lock_path.parent / licence["path"], destination)
            atomic_json(copied_lock, lock)
            self.assertEqual(load_lock(copied_lock, "macos-arm64"), (lock, row))
            for target in ("macos-x86_64", "linux-arm64"):
                with self.subTest(declared_target=target):
                    altered = json.loads(json.dumps(lock))
                    altered["targets"][target] = row
                    atomic_json(copied_lock, altered)
                    with self.assertRaises(BuildError) as caught:
                        load_lock(copied_lock, "macos-arm64")
                    self.assertEqual(caught.exception.code, "refused")

    @proves('MYC-15.1', 'MYC-15.2')
    def test_runtime_pin_validation_is_not_disabled_by_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = {"schemaVersion": 1, "python": "3.14.7", "targets": {"macos-arm64": {
                "runtime": {"python": "3.14.8", "sha256": "0" * 64,
                            "distribution": "python-build-standalone/20260901/install_only_stripped"}, "dependencies": []}}}
            atomic_json(root / "lock.json", lock)
            code = "from pathlib import Path; from mycel_build._core import load_lock; load_lock(Path(__import__('sys').argv[1]), 'macos-arm64')"
            env = {"PATH": os.defpath, "PYTHONPATH": str(ROOT / "src")}
            result = subprocess.run([sys.executable, "-O", "-B", "-c", code, str(root / "lock.json")],
                                    env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"release lock", result.stderr)

    @proves('MYC-15.2', 'MYC-15.4')
    def test_json_duplicate_keys_and_nonfinite_numbers_are_damaged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            for raw in (b'{"status":"building","status":"working"}', b'{"value":NaN}', b'{"value":Infinity}'):
                path.write_bytes(raw)
                with self.assertRaises(BuildError):
                    read_json(path)

    @proves('MYC-15.2')
    def test_source_inputs_include_dirty_untracked_and_gate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/mycel").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "pyproject.toml").write_bytes(_frozen_fixture()["pyproject.toml"])
            (root / "src/mycel/cli.py").write_text("pass\n")
            (root / "scripts/checkpoint.py").write_text("pass\n")
            (root / "README.md").write_text("guide\n")
            (root / "Makefile").write_text("check:\n")
            first, frozen = source_inputs(root)
            self.assertTrue(first["dirty"])
            self.assertIn("scripts/checkpoint.py", frozen)
            self.assertIn("README.md", frozen)
            self.assertIn("Makefile", frozen)
            (root / "src/mycel/untracked.py").write_text("new\n")
            second, _ = source_inputs(root)
            self.assertNotEqual(first["inputsSha256"], second["inputsSha256"])

    @proves('MYC-15.2')
    def test_source_identity_ignores_generated_egg_info_and_tool_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/mycel").mkdir(parents=True)
            (root / "src/mycel/cli.py").write_bytes(b"pass\n")
            (root / "pyproject.toml").write_bytes(_frozen_fixture()["pyproject.toml"])
            before, frozen = source_inputs(root)
            for name in ("src/mycel.egg-info/PKG-INFO", "tests/.pytest_cache/state",
                         "src/mycel/__pycache__/cli.pyc", "docs/.DS_Store"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"generated metadata\n")
            after, captured = source_inputs(root)
            self.assertEqual(after["inputsSha256"], before["inputsSha256"])
            self.assertEqual(captured, frozen)

    @proves('MYC-15.1', 'MYC-15.2')
    def test_source_capture_refuses_directory_and_dangling_links_without_reading_external_inputs(self):
        for kind in ("root-directory", "nested-directory", "dangling-file", "metadata"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "source"
                (root / "src/mycel").mkdir(parents=True)
                (root / "pyproject.toml").write_bytes(_frozen_fixture()["pyproject.toml"])
                (root / "src/mycel/cli.py").write_bytes(b"pass\n")
                outside = base / "outside"
                outside.mkdir()
                (outside / "secret.py").write_bytes(b"external source must not be captured\n")
                if kind == "root-directory":
                    (root / "src").rename(root / "retained-src")
                    (root / "src").symlink_to(outside, target_is_directory=True)
                elif kind == "nested-directory":
                    (root / "src/mycel/linked").symlink_to(outside, target_is_directory=True)
                elif kind == "dangling-file":
                    (root / "src/mycel/absent.py").symlink_to(outside / "absent.py")
                else:
                    (root / "pyproject.toml").unlink()
                    (root / "pyproject.toml").symlink_to(outside / "secret.py")
                with self.assertRaises(BuildError) as caught:
                    source_inputs(root)
                self.assertEqual(caught.exception.code, "refused")

    @proves('MYC-15.1', 'MYC-15.2')
    def test_verified_asset_refuses_wrong_hash_and_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.whl"
            path.write_bytes(b"wheel")
            asset = {"filename": path.name, "sha256": digest(b"wheel")}
            self.assertEqual(verify_asset(asset, root), path)
            path.write_bytes(b"damaged")
            with self.assertRaises(BuildError):
                verify_asset(asset, root)
            path.unlink()
            path.symlink_to(root / "absent")
            with self.assertRaises(BuildError):
                verify_asset(asset, root)

    @proves('MYC-15.1', 'MYC-15.2')
    def test_private_asset_snapshot_keeps_exact_bytes_and_refuses_cache_races(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.whl"
            source.write_bytes(b"locked wheel")
            asset = {"filename": source.name, "sha256": digest(source.read_bytes())}
            copied = snapshot_asset(asset, root, root / "private")
            self.assertEqual(copied.read_bytes(), b"locked wheel")
            self.assertFalse(copied.stat().st_mode & 0o222)
            source.write_bytes(b"later cache mutation")
            self.assertEqual(copied.read_bytes(), b"locked wheel")
            source.write_bytes(b"locked wheel")

            def verify_then_change(value, directory):
                verified = verify_asset(value, directory)
                verified.write_bytes(b"changed after verification")
                return verified

            with patch("mycel_build._core.verify_asset", side_effect=verify_then_change):
                with self.assertRaises(BuildError) as caught:
                    snapshot_asset(asset, root, root / "raced")
            self.assertEqual(caught.exception.code, "busy")
            self.assertFalse((root / "raced/fixture.whl").exists())


class BuildSourceBindingTests(unittest.TestCase):
    def stage_fixture(self, base):
        source = base / "source"
        for name, raw in {**_frozen_fixture(), "packaging/build-lock.json": b"{}\n",
                          "tests/test_fixture.py": b"pass\n", "checks/claims.json": b"{}\n",
                          "scripts/check_coverage.py": b"pass\n", "Makefile": b"check:\n",
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

    @proves('MYC-15.2')
    def test_gate_input_identity_covers_runner_imports_scripts_metadata_and_entrypoint(self):
        frozen = {name: b"input" for name in ("src/mycel/_coverage.py", "src/mycel_build/_staging.py",
                  "tests/test_fixture.py", "checks/claims.json", "scripts/check_coverage.py",
                  "pyproject.toml", "Makefile", "docs/builds.md", "packaging/build-lock.json")}
        captured = check_input_manifest(input_manifest(frozen))
        self.assertEqual({row["path"] for row in captured}, set(frozen) - {
            "docs/builds.md", "packaging/build-lock.json"})

    @proves('MYC-15.2')
    def test_source_binding_distinguishes_exact_current_inputs_from_historical_evidence_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, registry, _ = self.stage_fixture(Path(directory))
            before = file_manifest(registry)
            match = verify_source(source, registry, "1")
            self.assertTrue(match["matches"])
            self.assertFalse(match["automaticQualification"])
            for name in ("docs/builds.md", "src/mycel/cli.py", "scripts/check_coverage.py"):
                with self.subTest(name=name):
                    path = source / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"Changed\n")
                    stale = verify_source(source, registry, "1")
                    self.assertFalse(stale["matches"])
                    self.assertEqual(stale["differences"]["changed"], [name])
                    path.write_bytes(original)
            added = source / "src/mycel/added.py"
            added.write_bytes(b"Added\n")
            removed = source / "docs/builds.md"
            removed.unlink()
            stale = verify_source(source, registry, "1")
            self.assertEqual(stale["differences"]["added"], ["src/mycel/added.py"])
            self.assertEqual(stale["differences"]["removed"], ["docs/builds.md"])
            self.assertEqual(file_manifest(registry), before)

    @proves('MYC-15.2')
    def test_source_binding_refuses_damaged_manifests_and_reports_legacy_gate_scope_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            source, registry, rows = self.stage_fixture(Path(directory))
            checks = [row for row in rows if row["path"].startswith(("checks/", "tests/"))]
            atomic_json(registry / "1/check-inputs.json", checks)
            update_staging(registry, "1", fields={"checkManifestSha256": digest(json_bytes(checks))})
            stale = verify_source(source, registry, "1")
            self.assertTrue(stale["sameSourceBytes"])
            self.assertFalse(stale["completeCheckInputs"])
            self.assertFalse(stale["matches"])
            for malformed in (rows + [rows[0]], [{**rows[0], "path": "../escape"}],
                              [{**rows[0], "size": True}], [{**rows[0], "sha256": "0" * 64}]):
                with self.subTest(malformed=malformed):
                    atomic_json(registry / "1/source-inputs.json", malformed)
                    before = file_manifest(registry)
                    with self.assertRaises(BuildError):
                        verify_source(source, registry, "1")
                    self.assertEqual(file_manifest(registry), before)

    @proves('MYC-15.2', 'MYC-15.4')
    def test_source_binding_cli_has_json_status_and_nonwaiting_read_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            source, registry, _ = self.stage_fixture(Path(directory))
            arguments = ["verify-source", "1", "--source", str(source), "--registry", str(registry)]
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(arguments), 0)
            self.assertTrue(json.loads(output.getvalue())["matches"])
            (source / "Makefile").write_bytes(b"Changed\n")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(arguments), 1)
            self.assertFalse(json.loads(output.getvalue())["matches"])
            before = file_manifest(registry)
            with maintenance(registry), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(arguments), 1)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "busy")
            self.assertEqual(file_manifest(registry), before)


class BuildWheelTests(unittest.TestCase):
    @proves('MYC-15.1', 'MYC-15.2', 'MYC-15.4')
    def test_installed_identity_is_allocated_numeric_sealed_data_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen = _frozen_fixture()
            frozen["src/mycel/data/development-identity.json"] = b'{"schemaVersion":1,"development":true}\n'
            frozen["src/mycel/data/build-identity.json"] = b'{"schemaVersion":1,"build":999}\n'
            with self.assertRaises(BuildError):
                product_wheel(frozen, root / "poisoned")
            frozen.pop("src/mycel/data/build-identity.json")
            wheel, _ = product_wheel(frozen, root / "wheels")
            site = root / "program/site"
            install_wheel(wheel, site)
            identity = site / "mycel/data/build-identity.json"
            self.assertFalse(identity.exists())
            self.assertFalse((site / "mycel/data/development-identity.json").exists())
            install_build_identity(site, "a3")
            self.assertEqual(read_json(identity), {"schemaVersion": 1, "build": 163})
            with self.assertRaises(BuildError):
                install_build_identity(site, "a4")
            seal_program(root / "program")
            manifest = file_manifest(root / "program")
            row = next(row for row in manifest if row["path"] == "site/mycel/data/build-identity.json")
            self.assertEqual(row["sha256"], digest(identity.read_bytes()))
            self.assertEqual(row["mode"], 0o444)
            validate_manifest(root / "program", manifest, digest(json_bytes(manifest)))
            # Restore fixture permissions for portable temporary-directory disposal.
            for path in (root / "program").rglob("*"):
                if path.is_dir():
                    path.chmod(0o700)
            (root / "program").chmod(0o700)

    @proves('MYC-15.1')
    def test_wheel_full_record_preflight_rejects_without_partial_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "extra-record.whl"
            _wheel_fixture(wheel, {"first.py": b"valid\n"}, extra_record=("absent.py", "sha256=invalid", "3"))
            site = root / "existing-site"
            site.mkdir()
            (site / "retained.py").write_bytes(b"already installed\n")
            before = file_manifest(site)
            with self.assertRaises(BuildError):
                install_wheel(wheel, site)
            self.assertEqual(file_manifest(site), before)

    @proves('MYC-15.1')
    def test_wheel_special_files_bytecode_and_portable_collisions_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [({"first.py": b"safe", "module.pyo": b"bytecode"}, None),
                     ({"first.py": b"safe", "fifo": b"special"}, {"fifo": stat.S_IFIFO | 0o644}),
                     ({"Package.py": b"a", "package.py": b"b"}, None),
                     ({"caf\u00e9.py": b"a", "cafe\u0301.py": b"b"}, None),
                     ({"package": b"file", "package/module.py": b"child"}, None),
                     ({"fixture.data/purelib/first.py": b"a", "first.py": b"b"}, None)]
            for index, (members, modes) in enumerate(cases):
                with self.subTest(index=index):
                    wheel = root / f"unsafe-{index}.whl"
                    _wheel_fixture(wheel, members, modes=modes)
                    site = root / f"site-{index}"
                    with self.assertRaises(BuildError):
                        install_wheel(wheel, site)
                    self.assertFalse(site.exists())

    @proves('MYC-15.1')
    def test_product_only_noneditable_wheel_installs_exact_recorded_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, metadata = product_wheel(_frozen_fixture(), root / "wheels")
            with zipfile.ZipFile(wheel) as archive:
                self.assertFalse(any("mycel_build" in p for p in archive.namelist()))
                self.assertIn("mycel/cli.py", archive.namelist())
                self.assertIn(metadata["version"].encode(), archive.read(f"mycel-{metadata['version']}.dist-info/METADATA"))
            install_wheel(wheel, root / "site")
            self.assertEqual((root / "site/mycel/cli.py").read_bytes(), _frozen_fixture()["src/mycel/cli.py"])
            self.assertFalse((root / "site/mycel_build").exists())

    @proves('MYC-15.1', 'MYC-15.2')
    def test_wheel_record_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, _ = product_wheel(_frozen_fixture(), root / "wheels")
            tampered = root / "tampered.whl"
            with zipfile.ZipFile(wheel) as original, zipfile.ZipFile(tampered, "w") as output:
                for name in original.namelist():
                    output.writestr(name, b"changed\n" if name == "mycel/cli.py" else original.read(name))
            with self.assertRaises(BuildError):
                install_wheel(tampered, root / "site")

    @proves('MYC-15.1')
    def test_wheel_escape_editable_hooks_and_collisions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, _ = product_wheel(_frozen_fixture(), root / "wheels")
            install_wheel(wheel, root / "site")
            with self.assertRaises(BuildError):
                install_wheel(wheel, root / "site")
            poisoned = _frozen_fixture()
            poisoned["src/mycel/override.pth"] = b"/developer/path\n"
            with self.assertRaises(BuildError):
                product_wheel(poisoned, root / "other")
            escaping = root / "escaping.whl"
            with zipfile.ZipFile(escaping, "w") as output:
                output.writestr("../outside", b"unsafe")
                output.writestr("x.dist-info/RECORD", "../outside,,\nx.dist-info/RECORD,,\n")
            with self.assertRaises(BuildError):
                install_wheel(escaping, root / "second-site")
            self.assertFalse((root / "outside").exists())

    @proves('MYC-15.1')
    def test_runtime_tar_rejects_escaping_and_special_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number, member in enumerate(("python/../outside", "/python/file", "python/dev")):
                archive = root / f"bad-{number}.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    info = tarfile.TarInfo(member)
                    info.type = tarfile.CHRTYPE if number == 2 else tarfile.REGTYPE
                    info.size = 1 if number != 2 else 0
                    output.addfile(info, io.BytesIO(b"x") if info.size else None)
                with self.assertRaises(BuildError):
                    extract_runtime(archive, root / f"runtime-{number}")

    @proves('MYC-15.1')
    def test_runtime_preflight_refuses_late_bad_member_links_and_collisions_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [("python/bad", tarfile.FIFOTYPE, ""),
                     ("python", tarfile.SYMTYPE, "bin/python3"),
                     ("python/bin/escape", tarfile.SYMTYPE, "../../outside"),
                     ("python/bin/cycle", tarfile.SYMTYPE, "cycle"),
                     ("python/bin/absent", tarfile.SYMTYPE, "missing"),
                     ("python/BIN/python3", tarfile.REGTYPE, "")]
            for index, (name, kind, target) in enumerate(cases):
                with self.subTest(index=index):
                    archive = root / f"bad-{index}.tar.gz"
                    with tarfile.open(archive, "w:gz") as output:
                        valid = tarfile.TarInfo("python/bin/python3")
                        valid.size, valid.mode = 1, 0o755
                        output.addfile(valid, io.BytesIO(b"x"))
                        invalid = tarfile.TarInfo(name)
                        invalid.type, invalid.linkname = kind, target
                        invalid.size = 1 if kind == tarfile.REGTYPE else 0
                        output.addfile(invalid, io.BytesIO(b"x") if invalid.size else None)
                    destination = root / f"runtime-{index}"
                    with self.assertRaises(BuildError):
                        extract_runtime(archive, destination)
                    self.assertFalse(destination.exists())

    @proves('MYC-15.1')
    def test_runtime_directory_ancestors_refuse_case_and_unicode_file_collisions_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (file_name, directory_name) in enumerate((
                    ("A", "a/child"), ("caf\u00e9", "cafe\u0301/child"))):
                with self.subTest(file=file_name):
                    archive = root / f"ambiguous-{index}.tar.gz"
                    with tarfile.open(archive, "w:gz") as output:
                        regular = tarfile.TarInfo("python/" + file_name)
                        regular.size = 1
                        output.addfile(regular, io.BytesIO(b"x"))
                        nested = tarfile.TarInfo("python/" + directory_name)
                        nested.type = tarfile.DIRTYPE
                        output.addfile(nested)
                    destination = root / f"runtime-{index}"
                    with self.assertRaises(BuildError):
                        extract_runtime(archive, destination)
                    self.assertFalse(destination.exists())

    @proves('MYC-15.1', 'MYC-15.3')
    def test_runtime_relative_interpreter_link_remains_inside_relocated_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.tar.gz"
            (root / "program").mkdir()
            with tarfile.open(archive, "w:gz") as output:
                info = tarfile.TarInfo("python/bin/python3.14")
                info.mode = 0o755
                info.size = 1
                output.addfile(info, io.BytesIO(b"x"))
                link = tarfile.TarInfo("python/bin/python3")
                link.type, link.linkname = tarfile.SYMTYPE, "python3.14"
                output.addfile(link)
            extract_runtime(archive, root / "program/runtime")
            shutil.copytree(root / "program", root / "relocated", symlinks=True)
            command = installed_command(root / "relocated", ["--help"])
            self.assertEqual(command[1:], ["-I", "-B", "-m", "mycel.cli", "--help"])
            self.assertTrue(Path(command[0]).resolve().is_relative_to((root / "relocated").resolve()))


class BuildManifestTests(unittest.TestCase):
    @proves('MYC-15.1', 'MYC-15.2')
    def test_failed_native_probe_returns_sanitized_executed_result(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "program"
            (program / "runtime/bin").mkdir(parents=True)
            (program / "runtime/bin/python3").write_bytes(b"private fixture interpreter")
            real_is_file = Path.is_file
            with patch("mycel_build._staging.platform.system", return_value="Darwin"), patch(
                    "mycel_build._staging.platform.machine", return_value="arm64"), patch.object(
                    Path, "is_file", lambda path: path == Path("/usr/bin/sandbox-exec") or real_is_file(path)), patch(
                    "mycel_build._staging.subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 1, b"private-output-sentinel", b"private-error-sentinel")):
                result = probe_installed(program, "macos-arm64", [])
            self.assertFalse(result["passed"])
            self.assertTrue(result["executed"])
            self.assertIn("native/data/dependency probe failed", result["reason"])
            self.assertNotIn("private-", json.dumps(result))

    @proves('MYC-15.2', 'MYC-15.4')
    def test_stage_retains_named_native_failure_results_and_exact_source_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            assets = base / "assets"
            assets.mkdir()
            archive = assets / "runtime.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                interpreter = tarfile.TarInfo("python/bin/python3")
                interpreter.size, interpreter.mode = 1, 0o755
                output.addfile(interpreter, io.BytesIO(b"x"))
            wheel = assets / "fixturedep-1.0-py3-none-any.whl"
            _wheel_fixture(wheel, {"fixturedep/__init__.py": b""})
            row = {"runtime": {"filename": archive.name, "sha256": digest(archive.read_bytes()), "licenses": []},
                   "dependencies": [{"name": "fixturedep", "version": "1.0", "filename": wheel.name,
                                     "sha256": digest(wheel.read_bytes()), "licenses": []}]}
            lock = {"schemaVersion": 1, "targets": {"macos-arm64": row}}
            frozen = _frozen_fixture()
            frozen["src/mycel/_store.py"] = b"STORE_FORMAT = 37\n"
            frozen["pyproject.toml"] = b'[project]\nname="mycel"\nversion="2.0.0"\nrequires-python=">=3.13"\ndependencies=["fixturedep==1.0"]\n'
            frozen["packaging/build-lock.json"] = json_bytes(lock)
            for name, raw in frozen.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            failure = {"passed": False, "executed": True, "target": "macos-arm64", "reason": "Fixture native check failed."}
            launcher = {"checks": {"passed": True, "executed": True, "target": "macos-arm64"}}
            registry = base / "registry"
            with patch("mycel_build._staging.platform.python_version", return_value="3.14.7"), patch(
                    "mycel_build._staging.load_lock", return_value=(lock, row)), patch(
                    "mycel_build._staging.probe_installed", return_value=failure), patch(
                    "mycel_build._launcher.stage_launcher", return_value=launcher) as bundle:
                record = create_stage(source, source / "packaging/build-lock.json", assets, registry, "macos-arm64")
            folder = registry / record["build"]
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["storeFormat"], 37)
            self.assertEqual(record["checks"], {"required": 3, "passed": 1, "failed": 2, "report": "checks.json"})
            self.assertEqual(bundle.call_args.args[3], folder / "launcher-bundle")
            self.assertEqual(bundle.call_args.kwargs["frozen"], frozen)
            self.assertEqual(record["launcherBundleSha256"], digest(json_bytes(launcher)))
            checks = read_json(folder / "checks.json")
            self.assertEqual(checks["results"], [
                {"name": "installed_native_and_two_path_probe", **failure},
                {"name": "independent_launcher_bootstrap_two_path_probe", **launcher["checks"]},
                {"name": "packaged_selector_and_cli_two_path_probe", "passed": False,
                 "executed": False, "target": "macos-arm64", "relocations": [],
                 "reason": "Packaged execution requires passing native, bootstrap and complete automatic checks."}])
            rows = read_json(folder / "source-inputs.json")
            self.assertEqual({row["path"]: row["sha256"] for row in rows}, {name: digest(raw) for name, raw in frozen.items()})
            self.assertEqual(read_record(registry, record["build"])["source"]["inputsSha256"], digest(json_bytes(rows)))

    @proves('MYC-15.2', 'MYC-15.4')
    def test_sealed_file_directory_root_and_link_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "program"
            (root / "nested").mkdir(parents=True)
            (root / "nested/file").write_bytes(b"immutable")
            (root / "link").symlink_to("nested/file")
            seal_program(root)
            manifest = file_manifest(root)
            fingerprint = digest(json_bytes(manifest))
            validate_manifest(root, manifest, fingerprint)
            for node in (root, root / "nested", root / "nested/file"):
                old = node.stat().st_mode & 0o777
                node.chmod(old | 0o200)
                with self.assertRaises(BuildError):
                    validate_manifest(root, manifest, fingerprint)
                node.chmod(old)
            (root / "nested/file").chmod(0o644)
            (root / "nested/file").write_bytes(b"changed")
            (root / "nested/file").chmod(0o444)
            with self.assertRaises(BuildError):
                validate_manifest(root, manifest, fingerprint)
            root.chmod(0o700)
            (root / "nested").chmod(0o700)

    @proves('MYC-15.2', 'MYC-15.4')
    def test_manifest_refuses_external_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "program"
            root.mkdir()
            (root / "link").symlink_to(Path(directory) / "external")
            with self.assertRaises(BuildError):
                file_manifest(root)

    @proves('MYC-15.1', 'MYC-15.2', 'MYC-15.4')
    def test_manifest_refuses_contained_absolute_links_and_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "program"
            root.mkdir()
            (root / "file").write_bytes(b"installed")
            link = root / "link"
            link.symlink_to(root / "file")
            with self.assertRaises(BuildError):
                file_manifest(root)
            link.unlink()
            link.symlink_to("link")
            with self.assertRaises(BuildError):
                file_manifest(root)

    @proves('MYC-15.3')
    def test_exec_uses_bundled_isolated_python_and_preserves_arguments_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "program"
            (program / "runtime/bin").mkdir(parents=True)
            (program / "runtime/bin/python3").write_text("fixture")
            before = Path.cwd()
            with patch("mycel_build._staging.os.execv") as execute:
                exec_installed(program, ["grep", "-rn", "literal spaces", "."])
            self.assertEqual(Path.cwd(), before)
            self.assertEqual(execute.call_args.args[1][1:], ["-I", "-B", "-m", "mycel.cli", "grep", "-rn", "literal spaces", "."])

    @proves('MYC-15.1', 'MYC-15.3')
    def test_cross_target_probe_is_an_explicit_failure(self):
        for target, system, machine in (("macos-x86_64", "Darwin", "arm64"),
                                        ("linux-arm64", "Darwin", "arm64"),
                                        ("macos-arm64", "Darwin", "x86_64"),
                                        ("macos-arm64", "Darwin", "unknown"),
                                        ("macos-arm64", "Linux", "arm64")):
            with self.subTest(target=target, system=system, machine=machine), patch(
                    "mycel_build._staging.platform.system", return_value=system), patch(
                    "mycel_build._staging.platform.machine", return_value=machine), patch(
                    "mycel_build._staging.subprocess.run") as run, patch(
                    "mycel_build._staging.tempfile.TemporaryDirectory") as workspace:
                result = probe_installed(Path("/unused"), target, [])
            run.assert_not_called()
            workspace.assert_not_called()
            self.assertFalse(result["passed"])
            self.assertFalse(result["executed"])
            self.assertEqual(result["target"], target)
            self.assertIn("unavailable" if target == "macos-arm64" else "unsupported", result["reason"])


class BuildRegistryTests(unittest.TestCase):
    @proves('MYC-15.4')
    def test_canonical_numeric_allocation_retains_failed_and_pruned_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(1, 18):
                record = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                self.assertEqual(record["build"], format(number, "x"))
            update_staging(root, "1", fields={"reason": "fixture failure"}, failed=True)
            retained = read_record(root, "1")
            retained["prunedAt"] = "2026-10-09T00:00:00+00:00"
            atomic_json(root / "1/build.json", retained)
            self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "12")
            rows = list_records(root)
            self.assertEqual([row["build"] for row in rows][-3:], ["10", "11", "12"])
            self.assertEqual(rows[0]["status"], "failed")
            self.assertIn("prunedAt", rows[0])
            for invalid in ("0", "00", "01", "A", "0xa", "../a", "a/"):
                with self.assertRaises(BuildError):
                    build_number(invalid)
        for target in ("macos-x86_64", "linux-riscv64"):
            with self.subTest(retired_target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                retained = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                retained.update(target=target, program="program")
                (root / "1/program").mkdir()
                (root / "1/program/retained").write_bytes(b"historical program bytes")
                atomic_json(root / "1/build.json", retained)
                ledger = read_json(root / ".allocations.json")
                ledger["allocations"]["1"]["target"] = target
                atomic_json(root / ".allocations.json", ledger)
                before = file_manifest(root)
                self.assertEqual(list_records(root), [{**retained, "targetSupported": False}])
                self.assertEqual(file_manifest(root), before)
                for operation in (lambda: read_record(root, "1"),
                                  lambda: update_staging(root, "1", fields={"reason": "must not update"}),
                                  lambda: allocate(root, target=target, version="2.0.0", source=SOURCE)):
                    with self.assertRaises(BuildError):
                        operation()
                    self.assertEqual(file_manifest(root), before)
                for malformed in ("../outside", "macos-x86_64/escape", "MacOS-x86_64", "",
                                  "m" * 17 + "-arm64", "macos-" + "x" * 33, None, 7, [], {}):
                    with self.subTest(malformed=malformed):
                        atomic_json(root / "1/build.json", {**retained, "target": malformed})
                        damaged = file_manifest(root)
                        self.assertEqual(list_records(root), [{"build": "1", "available": False,
                                                              "reason": "Build record is missing or damaged."}])
                        self.assertEqual(file_manifest(root), damaged)

    @proves('MYC-15.4')
    def test_busy_registry_refuses_without_waiting_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            before = (root / ".allocations.json").read_bytes()
            with maintenance(root):
                for operation in (lambda: allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE), lambda: list_records(root)):
                    with self.assertRaises(BuildError) as caught:
                        operation()
                    self.assertEqual(caught.exception.code, "busy")
            self.assertEqual((root / ".allocations.json").read_bytes(), before)

    @proves('MYC-15.4')
    def test_concurrent_process_allocations_are_unique_and_monotonic(self):
        with tempfile.TemporaryDirectory() as directory:
            context = multiprocessing.get_context("spawn")
            output = context.Queue()
            workers = [context.Process(target=_race, args=(directory, output)) for _ in range(6)]
            for worker in workers:
                worker.start()
            numbers = [output.get(timeout=15) for _ in workers]
            for worker in workers:
                worker.join(15)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(sorted(build_number(n) for n in numbers), list(range(1, 7)))

    @proves('MYC-15.4')
    def test_interruption_after_journal_reserves_and_recovers_failed_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("mycel_build._registry._materialize", side_effect=OSError("injected boundary")):
                with self.assertRaises(OSError):
                    allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            record = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            self.assertEqual(record["build"], "2")
            self.assertEqual(read_record(root, "1")["status"], "failed")

    @proves('MYC-15.4')
    def test_partial_record_boundaries_recover_as_failed_without_reuse(self):
        for member in ("build.json", "checks.json", "build.log", "run.lock"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                (root / "1" / member).unlink()
                with self.assertRaises(BuildError):
                    read_record(root, "1")
                self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                self.assertEqual(read_record(root, "1")["status"], "failed")

    @proves('MYC-15.4')
    def test_damaged_partial_record_does_not_block_or_change_later_allocation(self):
        for damage in (b"damaged", b"[]", b"null", b"{}", "boolean-schema", "changed-source"):
            for missing in ("checks.json", "build.log", "run.lock"):
                with self.subTest(damage=damage, missing=missing), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    record = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                    folder = root / "1"
                    if isinstance(damage, bytes):
                        (folder / "build.json").write_bytes(damage)
                    else:
                        record = json.loads(json.dumps(record))
                        if damage == "boolean-schema":
                            record["schemaVersion"] = True
                        else:
                            record["source"]["dirty"] = 1
                        atomic_json(folder / "build.json", record)
                    (folder / missing).unlink()
                    before = {p.name: p.read_bytes() for p in folder.iterdir()}
                    self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                    self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)
                    rows = list_records(root)
                    self.assertFalse(rows[0]["available"])
                    self.assertEqual(rows[1]["status"], "building")

    @proves('MYC-15.4')
    def test_partial_terminal_or_staged_record_is_preserved_without_recovery(self):
        for state in ("failed", "working", "withdrawn", "pruned", "staged", "missing-staged-record"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                record = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                folder = root / "1"
                if state in {"failed", "working", "withdrawn"}:
                    record["status"] = state
                elif state == "pruned":
                    record["prunedAt"] = "2026-10-09T00:00:00+00:00"
                else:
                    record["phase"] = "staging"
                atomic_json(folder / "build.json", record)
                if state == "missing-staged-record":
                    (folder / "program").mkdir()
                    (folder / "program" / "retained").write_bytes(b"staged immutable bytes")
                    (folder / "build.json").unlink()
                else:
                    (folder / "checks.json").unlink()
                before = {p.relative_to(folder).as_posix(): p.read_bytes()
                          for p in folder.rglob("*") if p.is_file()}
                self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                self.assertEqual({p.relative_to(folder).as_posix(): p.read_bytes()
                                  for p in folder.rglob("*") if p.is_file()}, before)
                self.assertFalse(list_records(root)[0]["available"])

    @proves('MYC-15.4')
    def test_unsafe_partial_metadata_and_folder_stay_local_without_following_links(self):
        for unsafe in ("build.json", "checks.json", "build.log", "run.lock", "folder-link", "folder-file"):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "registry"
                allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
                folder = root / "1"
                sentinel = base / "outside"
                sentinel.write_bytes(b"outside bytes must remain unchanged")
                if unsafe.startswith("folder-"):
                    folder.rename(base / "retained-folder")
                    if unsafe == "folder-link":
                        folder.symlink_to(base / "retained-folder", target_is_directory=True)
                    else:
                        folder.write_bytes(b"conflicting folder bytes")
                    before = file_manifest(base / "retained-folder")
                else:
                    (folder / unsafe).unlink()
                    (folder / unsafe).symlink_to(sentinel)
                    (folder / ("build.log" if unsafe == "checks.json" else "checks.json")).unlink()
                    before = {p.name: ("link", os.readlink(p)) if p.is_symlink() else p.read_bytes()
                              for p in folder.iterdir()}
                self.assertEqual(allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)["build"], "2")
                self.assertEqual(sentinel.read_bytes(), b"outside bytes must remain unchanged")
                if unsafe.startswith("folder-"):
                    self.assertEqual(file_manifest(base / "retained-folder"), before)
                    if unsafe == "folder-link":
                        self.assertTrue(folder.is_symlink())
                    else:
                        self.assertEqual(folder.read_bytes(), b"conflicting folder bytes")
                else:
                    self.assertEqual({p.name: ("link", os.readlink(p)) if p.is_symlink() else p.read_bytes()
                                      for p in folder.iterdir()}, before)
                rows = list_records(root)
                self.assertFalse(rows[0]["available"])
                self.assertEqual(rows[1]["status"], "building")

    @proves('MYC-15.2', 'MYC-15.4')
    def test_damage_is_local_and_staging_cannot_publish_or_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            (root / "1/build.json").write_text("damaged")
            rows = list_records(root)
            self.assertFalse(rows[0]["available"])
            self.assertEqual(rows[1]["status"], "building")
            for fields in ({"status": "working"}, {"program": "../outside"}, {"source": SOURCE}, {"filesManifest": "../outside"}):
                with self.assertRaises(BuildError):
                    update_staging(root, "2", fields=fields)
            self.assertEqual(read_record(root, "2")["status"], "building")

    @proves('MYC-15.4')
    def test_development_errors_are_one_sanitized_json_and_help_is_json(self):
        for arguments, expected in (([], 1), (["create", "--target", "private-sentinel"], 1), (["--help"], 0)):
            with self.subTest(arguments=arguments), contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(arguments), expected)
            self.assertEqual(errors.getvalue(), "")
            reply = json.loads(output.getvalue())
            self.assertNotIn("private-sentinel", output.getvalue())
            self.assertIn("error" if expected else "commands", reply)
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "unused-registry"
            for target in ("macos-x86_64", "linux-arm64"):
                arguments = ["create", "--target", target, "--assets", directory, "--registry", str(registry)]
                with self.subTest(target=target), contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(
                        io.StringIO()) as errors, patch("mycel_build.__main__.create_stage") as create:
                    self.assertEqual(main(arguments), 1)
                create.assert_not_called()
                self.assertEqual(errors.getvalue(), "")
                self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
                self.assertFalse(registry.exists())
