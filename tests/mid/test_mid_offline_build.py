"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_offline_build as _support
from test_offline_build import (
    BuildError,
    InstalledAutomaticTests,
    Path,
    _sanitize_report,
    automatic_contract,
    contract_fixture,
    create_stage,
    digest,
    frozen_contract_fixture,
    io,
    json,
    json_bytes,
    patch,
    relocation_results,
    report,
    required_packaged_cases,
    run_automatic,
    store_address,
    subprocess,
    tarfile,
    tempfile,
    unittest,
)


class InstalledAutomaticTests(_support.InstalledAutomaticTests):
# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_gate_protocol_retains_only_closed_sanitized_named_results
    def test_gate_protocol_retains_only_closed_sanitized_named_results(self):
        result = _sanitize_report(json.dumps(report(passed=False, errors=1)).encode(), 10, contract=contract_fixture())
        self.assertFalse(result["passed"])
        self.assertNotIn("private-password", json.dumps(result))
        self.assertEqual(result["checks"][0]["name"], "test_fixture.AutomaticTests.test_one")
        extra = report()
        extra["providerBody"] = "private-password-provider-body"
        clean = _sanitize_report(json.dumps(extra).encode(), 10, contract=contract_fixture())
        self.assertNotIn("providerBody", clean)
        self.assertNotIn("private-password", json.dumps(clean))
        for mutation in (lambda value: value.update(build=11),
                         lambda value: value.update(isolated=False),
                         lambda value: value.update(machine="x86_64"),
                         lambda value: value.update(machine="riscv64"),
                         lambda value: value.pop("machine"),
                         lambda value: value.update(checks=[]),
                         lambda value: value["checks"][0].update(kind="live"),
                         lambda value: value["checks"][0].update(requirements=["MYC-13.15"]),
                         lambda value: value["checks"].append(dict(value["checks"][0])),
                         lambda value: value.update(passed=False)):
            value = report()
            mutation(value)
            with self.assertRaises(BuildError):
                _sanitize_report(json.dumps(value).encode(), 10, contract=contract_fixture())
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_gate_protocol_retains_only_closed_sanitized_named_results

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_cross_target_automatic_gate_never_executes_or_claims_target_checks
    def test_cross_target_automatic_gate_never_executes_or_claims_target_checks(self):
        for target, system, machine in (("macos-x86_64", "Darwin", "arm64"),
                                        ("linux-arm64", "Darwin", "arm64"),
                                        ("macos-arm64", "Darwin", "x86_64"),
                                        ("macos-arm64", "Darwin", "unknown"),
                                        ("macos-arm64", "Linux", "arm64")):
            with self.subTest(target=target, system=system, machine=machine), patch(
                    "mycel_build._automatic.platform.system", return_value=system), patch(
                    "mycel_build._automatic.platform.machine", return_value=machine), patch(
                    "mycel_build._automatic.run_group") as run, patch(
                    "mycel_build._automatic.tempfile.TemporaryDirectory") as workspace:
                result = run_automatic(Path("/unused"), target, {}, source_root=Path("/source"), number="a")
            run.assert_not_called()
            workspace.assert_not_called()
            self.assertFalse(result["passed"])
            self.assertFalse(result["executed"])
            self.assertEqual(result["target"], target)
            self.assertEqual(result["checks"], [])
            self.assertEqual(result["required"], 1)
            self.assertEqual(result["passedCount"], 0)
            self.assertEqual(result["failedCount"], 1)
            self.assertFalse(result["automaticQualification"])
            self.assertIn("unavailable" if target == "macos-arm64" else "unsupported", result["reason"])
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_cross_target_automatic_gate_never_executes_or_claims_target_checks

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_remote_store_refuses_an_unrestrictable_network_boundary_before_execution
    def test_remote_store_refuses_an_unrestrictable_network_boundary_before_execution(self):
        with patch("mycel_build._automatic.platform.system", return_value="Darwin"), patch(
                "mycel_build._automatic.platform.machine", return_value="arm64"), patch(
                "mycel_build._automatic.run_group") as run:
            result = run_automatic(Path("/unused"), "macos-arm64", {}, source_root=Path("/source"),
                                   number="a", address="postgresql://user@server.invalid/owner")
        run.assert_not_called()
        self.assertFalse(result["executed"])
        self.assertFalse(result["passed"])
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_remote_store_refuses_an_unrestrictable_network_boundary_before_execution

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_frozen_check_workspace_imports_installed_product_and_records_exact_inputs
    def test_frozen_check_workspace_imports_installed_product_and_records_exact_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            program = base / "program"
            product = program / "runtime/lib/python3.14/site-packages/mycel"
            product.mkdir(parents=True)
            (product / "__init__.py").write_bytes(b"# sealed product\n")
            frozen = {"src/mycel/__init__.py": b"# source copy must not be importable\n",
                      "src/mycel_build/__init__.py": b"# frozen builder\n",
                      "tests/test_fixture.py": b"# frozen tests\n"}
            frozen.update(frozen_contract_fixture())
            original = dict(frozen)
            def execute(command, **options):
                workspace = Path(command[-2])
                linked = workspace / "src/mycel"
                self.assertTrue(linked.is_symlink())
                relocated_program = Path(command[-1])
                self.assertEqual(linked.resolve(), relocated_program / "runtime/lib/python3.14/site-packages/mycel")
                self.assertNotEqual(relocated_program, program)
                self.assertEqual((linked / "__init__.py").read_bytes(), b"# sealed product\n")
                self.assertEqual((workspace / "tests/test_fixture.py").read_bytes(), frozen["tests/test_fixture.py"])
                self.assertEqual(command[command.index("-I"):command.index("-I") + 2], ["-I", "-B"])
                self.assertIn('(deny network*)', command[2])
                self.assertIn('(allow network-bind (local tcp "localhost:*"))', command[2])
                self.assertNotIn('(allow network-inbound', command[2])
                self.assertNotIn('(allow network-outbound', command[2])
                self.assertIn('(deny file-read* file-write* (subpath "/source-checkout"))', command[2])
                self.assertEqual(options["env"]["MYCEL_CONFIG"], str(workspace.parent / "private-home/missing.toml"))
                self.assertNotIn("PYTHONPATH", options["env"])
                return subprocess.CompletedProcess(command, 0, json.dumps(report()).encode(), b"")
            with patch("mycel_build._automatic.platform.system", return_value="Darwin"), patch(
                    "mycel_build._automatic.platform.machine", return_value="arm64"), patch(
                    "mycel_build._automatic.run_group", side_effect=execute):
                result = run_automatic(program, "macos-arm64", frozen, source_root=Path("/source-checkout"), number="a")
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["sourceInputsSha256"], digest(json_bytes([
                {"path": name, "sha256": digest(raw), "size": len(raw)} for name, raw in sorted(frozen.items())])))
            self.assertEqual(frozen, original)
            self.assertFalse(result["automaticQualification"])
            self.assertTrue(result["verifiedPrivateRelocation"])
            self.assertEqual(result["required"], 1)
            self.assertEqual((product / "__init__.py").read_bytes(), b"# sealed product\n")
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_frozen_check_workspace_imports_installed_product_and_records_exact_inputs

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_failed_or_incomplete_process_retains_no_raw_stdout_or_stderr
    def test_failed_or_incomplete_process_retains_no_raw_stdout_or_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "program"
            program.mkdir()
            for reply in (subprocess.CompletedProcess([], 1, b"private-password", b"private-key"),
                          subprocess.CompletedProcess([], 0, b"private-password", b"")):
                with patch("mycel_build._automatic.platform.system", return_value="Darwin"), patch(
                        "mycel_build._automatic.platform.machine", return_value="arm64"), patch(
                        "mycel_build._automatic.automatic_contract", return_value=contract_fixture()), patch(
                        "mycel_build._automatic.run_group", return_value=reply):
                    result = run_automatic(program, "macos-arm64", {}, source_root=Path("/source"), number="a")
                self.assertFalse(result["passed"])
                self.assertTrue(result["executed"])
                self.assertNotIn("private-", json.dumps(result))
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_failed_or_incomplete_process_retains_no_raw_stdout_or_stderr

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_only_explicit_password_free_store_address_is_read
    def test_only_explicit_password_free_store_address_is_read(self):
        self.assertIsNone(store_address(None))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.toml"
            for value in ('[store]\naddress="postgresql://user:private-password@localhost/owner"\n',
                          '[store]\naddress="https://localhost/owner"\n', '[store]\naddress=false\n',
                          '[store]\naddress=17\n', '[store]\naddress=true\n', '[store]\naddress=[]\n'):
                path.write_text(value)
                with self.assertRaises(BuildError) as caught:
                    store_address(path)
                self.assertNotIn("private-password", str(caught.exception))
            path.write_text('[store]\naddress="postgresql://user@127.0.0.1:55432/owner"\n[unrelated]\nsecret="unused"\n')
            self.assertEqual(store_address(path), "postgresql://user@127.0.0.1:55432/owner")
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_only_explicit_password_free_store_address_is_read

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_staging_retains_all_named_automatic_failures_and_never_publishes_working
    def test_staging_retains_all_named_automatic_failures_and_never_publishes_working(self):
        from test_build import _frozen_fixture, _wheel_fixture
        from mycel_build._core import read_json
        for passed, launcher_passed in ((True, True), (True, False), (False, True), (False, False)):
            with self.subTest(passed=passed, launcher_passed=launcher_passed), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                source, assets, registry = (base / name for name in ("source", "assets", "registry"))
                assets.mkdir()
                archive = assets / "runtime.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    member = tarfile.TarInfo("python/bin/python3")
                    member.size, member.mode = 1, 0o755
                    output.addfile(member, io.BytesIO(b"x"))
                wheel = assets / "fixturedep-1.0-py3-none-any.whl"
                _wheel_fixture(wheel, {"fixturedep/__init__.py": b""})
                row = {"runtime": {"filename": archive.name, "sha256": digest(archive.read_bytes()), "licenses": []},
                       "dependencies": [{"name": "fixturedep", "version": "1.0", "filename": wheel.name,
                                         "sha256": digest(wheel.read_bytes()), "licenses": []}]}
                lock = {"schemaVersion": 1, "targets": {"macos-arm64": row}}
                frozen = _frozen_fixture()
                frozen["pyproject.toml"] = b'[project]\nname="mycel"\nversion="2.0.0"\nrequires-python=">=3.13"\ndependencies=["fixturedep==1.0"]\n'
                frozen["packaging/build-lock.json"] = json_bytes(lock)
                for name, raw in frozen.items():
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                gate = {"passed": passed, "executed": True, "checks": [{"name": "test_fixture.Unit.test_one", "passed": True},
                         {"name": "test_fixture.Store.test_two", "passed": passed}], "required": 2,
                        "passedCount": 1 + int(passed), "failedCount": int(not passed), "reason": "Fixed gate result."}
                gate.update(completeFrozenInventory=True,
                            inventorySha256=contract_fixture()['inventorySha256'], gateErrorCount=0, build=1,
                            sourceInputsSha256=digest(json_bytes([{'path': name, 'sha256': digest(raw), 'size': len(raw)}
                                for name, raw in sorted(frozen.items())])))
                native_probe, bootstrap_probe, packaged_probe = relocation_results(1)
                launcher = {"checks": {**bootstrap_probe, "passed": launcher_passed,
                                       "reason": "Fixed launcher check result."}}
                with patch("mycel_build._staging.platform.python_version", return_value="3.14.7"), patch(
                        "mycel_build._staging.load_lock", return_value=(lock, row)), patch(
                        "mycel_build._staging.probe_installed", return_value=native_probe), patch(
                        "mycel_build._staging.run_automatic", return_value=gate), patch(
                        "mycel_build._staging.probe_packaged_release", return_value=packaged_probe), patch(
                        "mycel_build._launcher.stage_launcher", return_value=launcher) as bundle:
                    record = create_stage(source, source / "packaging/build-lock.json", assets, registry, "macos-arm64")
                # The pinned runtime of this fixture names no Python version,
                # so no certificate is issued even when every group passes.
                all_groups_passed = passed and launcher_passed
                self.assertEqual(record["status"], "failed")
                self.assertFalse(record["automaticQualification"])
                self.assertEqual(record["checks"], {"required": 5,
                    "passed": 2 + int(passed) + int(launcher_passed) + int(all_groups_passed),
                    "failed": int(not passed) + int(not launcher_passed) + int(not all_groups_passed), "report": "checks.json"})
                self.assertEqual(bundle.call_args.args[3], registry / "1/launcher-bundle")
                self.assertEqual(bundle.call_args.kwargs["frozen"], frozen)
                checks = read_json(registry / "1/checks.json")
                self.assertEqual(checks["results"][1], {"name": "independent_launcher_bootstrap_two_path_probe", **launcher["checks"]})
                self.assertEqual(checks["results"][2], {"name": "installed_automatic_unit_store_gate", **gate})
                self.assertEqual(checks["pending"], ["packaged_release", "publication"])
                self.assertEqual(len(checks['results']), 4)
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_staging_retains_all_named_automatic_failures_and_never_publishes_working

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_spawned_workers_deserialize_installed_backend_and_keep_unit_network_denied
    def test_spawned_workers_deserialize_installed_backend_and_keep_unit_network_denied(self):
        import sys
        from mycel._coverage import discover_checks, run_checks
        from mycel_build._automatic_backend import InstalledFixtureBackend
        source = b'\n'.join((
            b'import os,socket,tempfile,time,unittest', b'from pathlib import Path',
            b'class Workers(unittest.TestCase):',
            b' def check_worker(self):',
            b'  Path(__file__).with_name(str(os.getpid())+".pid").write_text("ready")',
            b'  until=time.monotonic()+10',
            b'  while len(list(Path(__file__).parent.glob("*.pid")))<2:',
            b'   self.assertLess(time.monotonic(),until);time.sleep(0.01)',
            b'  with self.assertRaisesRegex(RuntimeError,"network access is forbidden"):',
            b'   socket.create_connection(("127.0.0.1",1))',
            b' def test_one(self): self.check_worker()',
            b' def test_two(self): self.check_worker()', b''))
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                journal = root / 'owned'
                journal.mkdir(mode=0o700)
                (root / 'test_installed_worker_fixture.py').write_bytes(source)
                backend = InstalledFixtureBackend('postgresql://fixture@localhost/owner',
                                                   _ownership_journal=journal)
                report = run_checks(discover_checks(root), store_backend=backend,
                                    workers=2, tests_directory=root)
                self.assertTrue(report.passed, report.errors)
                self.assertEqual(len(report.checks), 2)
                self.assertEqual(len(list(root.glob('*.pid'))), 2)
                self.assertEqual(list(journal.iterdir()), [])
        finally:
            sys.modules.pop('test_installed_worker_fixture', None)
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_spawned_workers_deserialize_installed_backend_and_keep_unit_network_denied

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_unknown_child_lifetime_retains_its_private_workspace_without_database_recovery
    def test_unknown_child_lifetime_retains_its_private_workspace_without_database_recovery(self):
        from mycel_build import _automatic
        from mycel_build._staging import _delete_tree
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'program'
            product = program / 'runtime/lib/python3.14/site-packages/mycel'
            product.mkdir(parents=True)
            (product / '__init__.py').write_bytes(b'# diagnostic fixture\n')
            for process_state in (
                    {'spawnConfirmed': False, 'spawnOutcomeUnconfirmed': True, 'processGroupAbsent': None},
                    {'spawnConfirmed': True, 'spawnOutcomeUnconfirmed': False, 'processGroupAbsent': False}):
                error = BuildError('refused', 'Fixture child lifetime is unconfirmed.')
                error.process_state = process_state
                with patch.object(_automatic.platform, 'system', return_value='Darwin'), \
                        patch.object(_automatic.platform, 'machine', return_value='arm64'), \
                        patch.object(_automatic, 'run_group', side_effect=error), \
                        patch.object(_automatic, '_recover_automatic') as recovery:
                    result = run_automatic(program, 'macos-arm64', frozen_contract_fixture(),
                                           source_root=Path('/source'), number='a')
                retained = Path(result['retainedCheckWorkspace'])
                try:
                    self.assertFalse(result['passed'])
                    self.assertEqual(result['processState'], process_state)
                    self.assertTrue(retained.is_dir())
                    self.assertEqual(retained.stat().st_mode & 0o777, 0o700)
                    recovery.assert_not_called()
                finally:
                    # No actual process was launched by this lifecycle fixture.
                    _delete_tree(retained)
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_unknown_child_lifetime_retains_its_private_workspace_without_database_recovery

# TEST-TIER-BEGIN tests/test_offline_build.py::InstalledAutomaticTests.test_incomplete_recovery_keeps_acknowledged_records_and_does_not_follow_external_links
    def test_incomplete_recovery_keeps_acknowledged_records_and_does_not_follow_external_links(self):
        from mycel_build import _automatic
        from mycel_build._staging import _delete_tree
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / 'outside'
            outside.mkdir()
            sentinel = outside / 'sentinel'
            sentinel.write_bytes(b'unchanged outside evidence')
            with _automatic._automatic_workspace() as state:
                base = state['path']
                (base / 'alias').symlink_to(outside, target_is_directory=True)
                journal = base / 'owned-databases'
                journal.mkdir(mode=0o700)
                record = journal / 'mycel_check_fixture.json'
                record.write_text('retained permission fixture')
                with patch.object(_automatic, 'run_group', return_value=
                        subprocess.CompletedProcess([], 0, b'{"remaining":1}', b'')), \
                        self.assertRaises(BuildError):
                    _automatic._recover_automatic(journal, ['fixture', 'runner', 'workspace', 'program'], {}, state)
            try:
                self.assertTrue(base.is_dir())
                self.assertEqual(record.read_text(), 'retained permission fixture')
                self.assertEqual(sentinel.read_bytes(), b'unchanged outside evidence')
            finally:
                _delete_tree(base)
            self.assertEqual(sentinel.read_bytes(), b'unchanged outside evidence')
# TEST-TIER-END tests/test_offline_build.py::InstalledAutomaticTests.test_incomplete_recovery_keeps_acknowledged_records_and_does_not_follow_external_links
