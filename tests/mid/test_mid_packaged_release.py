"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_packaged_release as _support
from test_packaged_release import (BuildError ,Path ,os ,packaged ,sys ,tempfile)


class PackagedReleaseTests(_support.PackagedReleaseTests):


# TEST-TIER-BEGIN tests/test_packaged_release.py::PackagedReleaseTests.test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution
    def test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'unexpected-write'
            with self.assertRaises(BuildError) as error:
                packaged._case('fixture_write', [sys.executable, '-I', '-B', '-c',
                    'import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("actual write")', str(target)],
                    cwd=root, env=os.environ.copy(), before_root=root, timeout=10)
            self.assertEqual(error.exception.code, 'refused')
            self.assertEqual(target.read_text(), 'actual write')
# TEST-TIER-END tests/test_packaged_release.py::PackagedReleaseTests.test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_packaged_release.py::PackagedReleaseTests.test_fixture_group_disappearing_before_signal_is_already_cleaned_up
# Reason: Narrower case removed from this family after retaining test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Fixture group disappearing before signal is already cleaned up.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_packaged_release.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fixture_group_disappearing_before_signal_is_already_cleaned_up(self):
#         with patch.object(packaged, '_gone', return_value=False), \
#                 patch.object(packaged.os, 'killpg', side_effect=ProcessLookupError) as send:
#             self.assertIsNone(packaged._stop_fixture_group(12345))
#         send.assert_called_once_with(12345, signal.SIGTERM)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_packaged_release.py::PackagedReleaseTests.test_real_selected_product_pid_stop_continue_interrupt_and_termination_leave_inputs_unchanged
# Reason: Narrower case removed from this family after retaining test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real selected product pid stop continue interrupt and termination leave inputs unchanged.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_packaged_release.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_selected_product_pid_stop_continue_interrupt_and_termination_leave_inputs_unchanged(self):
#         # A real exec chain, selector and Mycel grep run on the test interpreter.
#         # It deliberately does not purport to qualify a synthetic runtime pin.
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(product=True)
#             environment = fixture.environment(MYCEL_GREP_PLAIN='1')
#             before = tree_state(fixture.base)
#             for stop in (signal.SIGINT, signal.SIGTERM):
#                 with self.subTest(signal=stop):
#                     result = packaged.signal_case(fixture.command('grep', '--line-buffered', '-F', '-e', 'packaged readiness'),
#                         cwd=fixture.cwd, env=environment, interpreter=Path(sys.executable),
#                         grep=Path(shutil.which('grep', path=environment['PATH'])), stop_signal=stop, timeout=15)
#                     self.assertEqual(result['exitStatus'], 128 + stop)
#                     for field in ('pidPreserved', 'selectedBundledInterpreter', 'stopContinueObserved', 'grepGroupReaped'):
#                         self.assertTrue(result[field])
#                     self.assertEqual(tree_state(fixture.base), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_packaged_release.py::PackagedReleaseTests.test_unavailable_native_host_never_fabricates_or_starts_packaged_checks
# Reason: Narrower case removed from this family after retaining test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unavailable native host never fabricates or starts packaged checks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_packaged_release.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unavailable_native_host_never_fabricates_or_starts_packaged_checks(self):
#         with patch.object(packaged.platform, 'system', return_value='Linux'), \
#                 patch.object(packaged, '_relocation') as relocation, \
#                 patch.object(packaged, 'file_manifest') as manifest:
#             result = packaged.probe_packaged_release(Path('/unread/program'), Path('/unread/bundle'),
#                 'macos-arm64', source_root=Path('/unread/source'), record={})
#         self.assertFalse(result['passed'])
#         self.assertFalse(result['executed'])
#         self.assertEqual(result['relocations'], [])
#         relocation.assert_not_called()
#         manifest.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_packaged_release.py::PackagedReleaseTests.test_two_native_relocation_orchestration_retains_first_actual_case_when_second_fails
# Reason: Narrower case removed from this family after retaining test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Two native relocation orchestration retains first actual case when second fails.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_packaged_release.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_two_native_relocation_orchestration_retains_first_actual_case_when_second_fails(self):
#         # This tests orchestration with a finite executor, not distribution
#         # qualification. Each executor still starts a real isolated process.
#         for fail_second in (False, True):
#             with self.subTest(fail_second=fail_second), tempfile.TemporaryDirectory() as directory:
#                 root = Path(directory)
#                 program, bundle = root / 'program', root / 'bundle'
#                 program.mkdir(); bundle.mkdir()
#                 (program / 'retained').write_bytes(b'unchanged program')
#                 (bundle / 'retained').write_bytes(b'unchanged bootstrap')
#                 seal_program(program); seal_program(bundle)
#                 before = (tree_state(program), tree_state(bundle))
#                 record = {'filesSha256': digest(json_bytes(packaged.file_manifest(program))), 'runtime': {'python': '3.14.7'}}
#                 seen = []
#                 def execute(_program, _bundle, _record, target, destination, **options):
#                     seen.append(destination.name)
#                     options['progress']['activeCase'] = 'finite_actual_process'
#                     self.assertNotEqual(destination, root)
#                     reply = run_group([sys.executable, '-I', '-B', '-c', 'import os;print(os.getcwd())'],
#                         cwd=destination, timeout=10)
#                     self.assertEqual(reply.returncode, 0)
#                     self.assertEqual(reply.stdout.decode().strip(), str(destination.resolve()))
#                     if fail_second and len(seen) == 2:
#                         raise ValueError('private failure detail must not escape')
#                     return {'label': destination.name, 'passed': True, 'executed': True,
#                         'cases': [{'name': 'finite_actual_process', 'passed': True}], 'privateWorkingRecordFixtureOnly': True}
#                 actual = Path.is_file
#                 with patch.object(packaged.platform, 'system', return_value='Darwin'), \
#                         patch.object(packaged.platform, 'machine', return_value='arm64'), \
#                         patch.object(Path, 'is_file', lambda p: p == Path('/usr/bin/sandbox-exec') or actual(p)), \
#                         patch.object(packaged, '_relocation', side_effect=execute):
#                     result = packaged.probe_packaged_release(program, bundle, 'macos-arm64', source_root=root / 'source', record=record)
#                 self.assertEqual(seen, ['first installation', 'second relocated installation'])
#                 self.assertEqual(result['passed'], not fail_second)
#                 self.assertTrue(result['executed'])
#                 self.assertEqual(len(result['relocations']), 2)
#                 self.assertEqual(result['relocations'][0]['label'], 'first installation')
#                 self.assertEqual(result['relocations'][1]['passed'], not fail_second)
#                 if fail_second:
#                     self.assertEqual(result['relocations'][1]['activeCase'], 'finite_actual_process')
#                 self.assertNotIn('private failure detail', json.dumps(result))
#                 self.assertEqual((tree_state(program), tree_state(bundle)), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_packaged_release.py::PackagedReleaseTests.test_last_packaged_failure_blocks_qualification_and_retains_all_prior_results_without_publication
# Reason: Narrower case removed from this family after retaining test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Last packaged failure blocks qualification and retains all prior results without publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_packaged_release.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_last_packaged_failure_blocks_qualification_and_retains_all_prior_results_without_publication(self):
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
#             row = {'runtime': {'filename': archive.name, 'sha256': digest(archive.read_bytes()), 'licenses': []},
#                 'dependencies': [{'name': 'fixturedep', 'version': '1.0', 'filename': wheel.name,
#                     'sha256': digest(wheel.read_bytes()), 'licenses': []}]}
#             lock = {'schemaVersion': 1, 'targets': {'macos-arm64': row}}
#             frozen = _frozen_fixture()
#             frozen['pyproject.toml'] = b'[project]\nname="mycel"\nversion="2.0.0"\nrequires-python=">=3.13"\ndependencies=["fixturedep==1.0"]\n'
#             frozen['packaging/build-lock.json'] = json_bytes(lock)
#             for name, raw in frozen.items():
#                 path = source / name
#                 path.parent.mkdir(parents=True, exist_ok=True)
#                 path.write_bytes(raw)
#             automatic = _sanitize_report(json_bytes(report()), 10, contract=contract_fixture())
#             automatic.update(build=1, required=1, passedCount=1, failedCount=0, reason='Finite runner fixture.',
#                 sourceInputsSha256=digest(json_bytes([{'path': name, 'sha256': digest(raw), 'size': len(raw)}
#                     for name, raw in sorted(frozen.items())])))
#             native = {'passed': True, 'executed': True}
#             failure = {'passed': False, 'executed': True, 'reason': 'A packaged fixture case failed.',
#                 'relocations': [{'label': 'first installation', 'passed': True, 'executed': True}]}
#             with patch('mycel_build._staging.platform.python_version', return_value='3.14.7'), \
#                     patch('mycel_build._staging.load_lock', return_value=(lock, row)), \
#                     patch('mycel_build._staging.probe_installed', return_value=native), \
#                     patch('mycel_build._launcher.stage_launcher', return_value={'checks': native}), \
#                     patch('mycel_build._staging.run_automatic', return_value=automatic), \
#                     patch('mycel_build._staging.probe_packaged_release', return_value=failure) as probe:
#                 record = create_stage(source, source / 'packaging/build-lock.json', assets, registry, 'macos-arm64')
#             self.assertEqual(record['status'], 'failed')
#             self.assertFalse(record['automaticQualification'])
#             self.assertNotIn('qualification', record)
#             self.assertEqual(record['checks'], {'required': 4, 'passed': 3, 'failed': 1, 'report': 'checks.json'})
#             results = read_json(registry / '1/checks.json')['results']
#             self.assertEqual(results[2], {'name': 'installed_automatic_unit_store_gate', **automatic})
#             self.assertEqual(results[3], {'name': 'packaged_selector_and_cli_two_path_probe', **failure})
#             self.assertEqual(probe.call_args.kwargs['record']['status'], 'building')
#             self.assertEqual(len(list(registry.glob('*/build.json'))), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
