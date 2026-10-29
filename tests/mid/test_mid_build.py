"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_build as _support
from test_build import (BuildError ,Path ,SOURCE ,_frozen_fixture ,_race ,_wheel_fixture ,allocate ,build_number ,digest ,extract_runtime ,file_manifest ,install_wheel ,io ,list_records ,multiprocessing ,os ,patch ,read_record ,snapshot_asset ,source_inputs ,tarfile ,tempfile ,verify_asset)


class BuildInputsTests(_support.BuildInputsTests):


# TEST-TIER-BEGIN tests/test_build.py::BuildInputsTests.test_source_capture_refuses_directory_and_dangling_links_without_reading_external_inputs
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
# TEST-TIER-END tests/test_build.py::BuildInputsTests.test_source_capture_refuses_directory_and_dangling_links_without_reading_external_inputs


# TEST-TIER-BEGIN tests/test_build.py::BuildInputsTests.test_private_asset_snapshot_keeps_exact_bytes_and_refuses_cache_races
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
# TEST-TIER-END tests/test_build.py::BuildInputsTests.test_private_asset_snapshot_keeps_exact_bytes_and_refuses_cache_races


class BuildWheelTests(_support.BuildWheelTests):

# TEST-TIER-BEGIN tests/test_build.py::BuildWheelTests.test_wheel_full_record_preflight_rejects_without_partial_installation
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
# TEST-TIER-END tests/test_build.py::BuildWheelTests.test_wheel_full_record_preflight_rejects_without_partial_installation


# TEST-TIER-BEGIN tests/test_build.py::BuildWheelTests.test_runtime_preflight_refuses_late_bad_member_links_and_collisions_before_writes
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
# TEST-TIER-END tests/test_build.py::BuildWheelTests.test_runtime_preflight_refuses_late_bad_member_links_and_collisions_before_writes


class BuildRegistryTests(_support.BuildRegistryTests):


# TEST-TIER-BEGIN tests/test_build.py::BuildRegistryTests.test_concurrent_process_allocations_are_unique_and_monotonic
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
# TEST-TIER-END tests/test_build.py::BuildRegistryTests.test_concurrent_process_allocations_are_unique_and_monotonic

# TEST-TIER-BEGIN tests/test_build.py::BuildRegistryTests.test_interruption_after_journal_reserves_and_recovers_failed_identity
    def test_interruption_after_journal_reserves_and_recovers_failed_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("mycel_build._registry._materialize", side_effect=OSError("injected boundary")):
                with self.assertRaises(OSError):
                    allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            record = allocate(root, target="macos-arm64", version="2.0.0", source=SOURCE)
            self.assertEqual(record["build"], "2")
            self.assertEqual(read_record(root, "1")["status"], "failed")
# TEST-TIER-END tests/test_build.py::BuildRegistryTests.test_interruption_after_journal_reserves_and_recovers_failed_identity


# TEST-TIER-BEGIN tests/test_build.py::BuildRegistryTests.test_unsafe_partial_metadata_and_folder_stay_local_without_following_links
    def test_unsafe_partial_metadata_and_folder_stay_local_without_following_links(self):
        self._assert_hard_linked_retained_metadata_stays_damaged()
        self._assert_recovery_preserves_outside_inodes_linked_after_validation()
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
# TEST-TIER-END tests/test_build.py::BuildRegistryTests.test_unsafe_partial_metadata_and_folder_stay_local_without_following_links
