"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_packaging_contract as _support
# from test_packaging_contract import (
#     PackagingContractTests,
#     unittest,
# )


# class PackagingContractTests(_support.PackagingContractTests):
# TEST-TIER-DISABLED-BEGIN tests/test_packaging_contract.py::PackagingContractTests.test_successful_stage_retains_complete_record_and_manifests_without_publication
#     def test_successful_stage_retains_complete_record_and_manifests_without_publication(self):
#         with tempfile.TemporaryDirectory() as directory:
#             base = Path(directory)
#             source, assets, registry = (base / name for name in ('source', 'assets', 'registry'))
#             assets.mkdir()
#             archive = assets / 'runtime.tar.gz'
#             with tarfile.open(archive, 'w:gz') as output:
#                 member = tarfile.TarInfo('python/bin/python3')
#                 member.size, member.mode = 1, 0o755
#                 output.addfile(member, io.BytesIO(b'x'))
#             wheel = assets / 'fixturedep-1.0-py3-none-any.whl'
#             _wheel_fixture(wheel, {'fixturedep/__init__.py': b''})
#             row = {'runtime': {'filename': archive.name, 'sha256': digest(archive.read_bytes()), 'licenses': [],
#                                'python': '3.14.7', 'distribution': 'fixture-standalone-2026-10'},
#                    'dependencies': [{'name': 'fixturedep', 'version': '1.0', 'filename': wheel.name,
#                                      'sha256': digest(wheel.read_bytes()), 'licenses': []}]}
#             lock = {'schemaVersion': 1, 'targets': {'macos-arm64': row}}
#             frozen = _frozen_fixture()
#             frozen['pyproject.toml'] = (b'[project]\nname="mycel"\nversion="2.0.0"\n'
#                 b'requires-python=">=3.13"\ndependencies=["fixturedep==1.0"]\n')
#             frozen['packaging/build-lock.json'] = json_bytes(lock)
#             frozen['tests/test_fixture.py'] = b'# retained automatic input\n'
#             for name, raw in frozen.items():
#                 path = source / name
#                 path.parent.mkdir(parents=True, exist_ok=True)
#                 path.write_bytes(raw)
#             native = {'passed': True, 'executed': True, 'relocations': 2, 'target': 'macos-arm64',
#                       'python': '3.14.7', 'isolated': True, 'dontWriteBytecode': True}
#             launcher = {'checks': dict(native)}
#             automatic = {'passed': True, 'executed': True, 'checks': [
#                 {'name': 'test_fixture.Unit.test_one', 'passed': True},
#                 {'name': 'test_fixture.Store.test_two', 'passed': True}],
#                 'required': 2, 'passedCount': 2, 'failedCount': 0, 'reason': 'Fixture automatic checks passed.'}
#             packaged = {'passed': False, 'executed': False, 'target': 'macos-arm64', 'relocations': [],
#                         'reason': 'Packaged execution is unavailable in this metadata-only unit fixture.'}
#             with patch('mycel_build._staging.platform.python_version', return_value='3.14.7'), patch(
#                     'mycel_build._staging.load_lock', return_value=(lock, row)), patch(
#                     'mycel_build._staging.probe_installed', return_value=native), patch(
#                     'mycel_build._staging.run_automatic', return_value=automatic), patch(
#                     'mycel_build._staging.probe_packaged_release', return_value=packaged) as packaged_probe, patch(
#                     'mycel_build._launcher.stage_launcher', return_value=launcher) as bundle:
#                 record = create_stage(source, source / 'packaging/build-lock.json', assets, registry, 'macos-arm64')
#             folder = registry / record['build']
#             self.assertEqual(record['build'], '1')
#             self.assertEqual(read_record(registry, '1'), record)
#             self.assertEqual(record['version'], '2.0.0')
#             self.assertEqual(record['target'], 'macos-arm64')
#             self.assertEqual(record['status'], 'failed')
#             self.assertEqual(record['phase'], 'staging')
#             self.assertFalse(record['automaticQualification'])
#             self.assertEqual(record['runtime'], row['runtime'])
#             self.assertEqual(record['dependencies'], row['dependencies'])
#             self.assertEqual(record['storeFormat'], 2)
#             self.assertEqual(record['searchReply'], 3)
#             self.assertEqual(record['productWheel']['filename'], 'mycel-2.0.0-py3-none-any.whl')
#             self.assertFalse(record['productWheel']['editable'])
#             self.assertEqual(record['lockSha256'], digest(frozen['packaging/build-lock.json']))
#             self.assertTrue(record['startedAt'])
#             self.assertTrue(record['stagedAt'])
#             self.assertEqual(record['checks'], {'required': 5, 'passed': 4, 'failed': 1, 'report': 'checks.json'})
#             self.assertEqual(record['reason'], packaged['reason'])
#             packaged_probe.assert_called_once()
#             self.assertEqual(packaged_probe.call_args.args, (folder / 'program', folder / 'launcher-bundle', 'macos-arm64'))
#             self.assertEqual(packaged_probe.call_args.kwargs['source_root'], source)
#             self.assertEqual(bundle.call_args.args[3], folder / 'launcher-bundle')
#             self.assertEqual(bundle.call_args.kwargs['frozen'], frozen)
#             self.assertEqual(record['launcherBundle'], 'launcher-bundle')
#             self.assertEqual(record['launcherBundleSha256'], digest(json_bytes(launcher)))
#             inputs = read_json(folder / 'source-inputs.json')
#             self.assertEqual({item['path']: item['sha256'] for item in inputs},
#                              {name: digest(raw) for name, raw in frozen.items()})
#             self.assertEqual(record['source']['inputsSha256'], digest(json_bytes(inputs)))
#             check_inputs = read_json(folder / 'check-inputs.json')
#             self.assertEqual(check_inputs, check_input_manifest(inputs))
#             self.assertEqual(record['checkManifestSha256'], digest(json_bytes(check_inputs)))
#             manifest = read_json(folder / record['filesManifest'])
#             validate_manifest(folder / 'program', manifest, record['filesSha256'])
#             self.assertEqual(record['dataFiles'], [item for item in manifest
#                 if '/mycel/data/' in item['path'] or item['path'].startswith('licenses/')])
#             self.assertTrue(any('voyage-code-4-tokenizer.json' in item['path'] for item in record['dataFiles']))
#             checks = read_json(folder / 'checks.json')
#             self.assertEqual(checks['results'], [
#                 {'name': 'installed_native_and_two_path_probe', **native},
#                 {'name': 'independent_launcher_bootstrap_two_path_probe', **launcher['checks']},
#                 {'name': 'installed_automatic_unit_store_gate', **automatic},
#                 {'name': 'packaged_selector_and_cli_two_path_probe', **packaged}])
#             self.assertEqual(checks['pending'], ['packaged_release', 'publication'])
# TEST-TIER-DISABLED-END tests/test_packaging_contract.py::PackagingContractTests.test_successful_stage_retains_complete_record_and_manifests_without_publication

# TEST-TIER-DISABLED-BEGIN tests/test_packaging_contract.py::PackagingContractTests.test_terminal_or_pruned_records_refuse_staging_without_changing_any_retained_byte_or_mode
#     def test_terminal_or_pruned_records_refuse_staging_without_changing_any_retained_byte_or_mode(self):
#         for status, pruned in (('working', False), ('withdrawn', False), ('failed', False),
#                                ('building', True), ('withdrawn', True)):
#             with self.subTest(status=status, pruned=pruned), tempfile.TemporaryDirectory() as directory:
#                 root = Path(directory)
#                 record = allocate(root, target='macos-arm64', version='2.0.0', source=SOURCE)
#                 folder = root / record['build']
#                 program = folder / 'program'
#                 program.mkdir()
#                 (program / 'retained').write_bytes(b'exact immutable program')
#                 seal_program(program)
#                 record.update(status=status, program='program')
#                 if pruned:
#                     record['prunedAt'] = '2026-10-15T00:00:00Z'
#                 atomic_json(folder / 'build.json', record)
#                 def snapshot():
#                     return {str(path.relative_to(root)): (path.stat().st_mode & 0o777,
#                         path.read_bytes() if path.is_file() else None) for path in root.rglob('*')}
#                 before = snapshot()
#                 try:
#                     with self.assertRaises(BuildError) as error:
#                         update_staging(root, '1', fields={'reason': 'must not be written'},
#                                        checks={'schemaVersion': 1, 'results': [], 'pending': []})
#                     self.assertEqual(error.exception.code, 'refused')
#                     self.assertEqual(snapshot(), before)
#                 finally:
#                     program.chmod(0o700)
# TEST-TIER-DISABLED-END tests/test_packaging_contract.py::PackagingContractTests.test_terminal_or_pruned_records_refuse_staging_without_changing_any_retained_byte_or_mode


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:2
# import io
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:3
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:4
# import tarfile
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:5
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:7
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:9
# from mycel_build._core import (BuildError, atomic_json, digest,
#                                json_bytes, read_json, seal_program, validate_manifest)
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:11
# from mycel_build._registry import allocate, read_record, update_staging
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:12
# from mycel_build._staging import check_input_manifest, create_stage
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:15
#     from .test_build import SOURCE, _frozen_fixture, _wheel_fixture
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:15

# TEST-TIER-IMPORTS-BEGIN tests/test_packaging_contract.py:17
#     from test_build import SOURCE, _frozen_fixture, _wheel_fixture
# TEST-TIER-IMPORTS-END tests/test_packaging_contract.py:17

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
