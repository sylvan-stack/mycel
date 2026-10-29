"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_launcher_selection as _support
# from test_launcher_selection import (
#     LauncherFixture,
#     LauncherProcessTests,
#     LauncherSelectionTests,
#     PROBE,
#     Path,
#     ROOT,
#     SOURCE,
#     STORE_FORMAT,
#     allocate,
#     atomic_json,
#     contextmanager,
#     digest,
#     file_manifest,
#     json,
#     json_bytes,
#     os,
#     ready_line,
#     seal_program,
#     selectors,
#     shlex,
#     shutil,
#     subprocess,
#     sys,
#     thaw,
#     time,
#     tree_state,
#     unittest,
# )


# class LauncherSelectionTests(_support.LauncherSelectionTests):
# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherSelectionTests.test_numeric_default_skips_every_unavailable_status_target_and_damaged_build_without_writes
#     def test_numeric_default_skips_every_unavailable_status_target_and_damaged_build_without_writes(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build('f')
#             fixture.build('10')
#             fixture.build('11', status='withdrawn', reason='regression')
#             fixture.build('12', status='building')
#             fixture.build('13', status='failed')
#             fixture.build('14')
#             fixture.record('14', prunedAt='2026-01-01T00:00:00Z')
#             fixture.build('15')
#             fixture.record('15', target='linux-arm64')
#             fixture.build('16')
#             damaged = fixture.registry / '16/program/probe.py'
#             damaged.chmod(0o644)
#             damaged.write_text('damaged installed file\n')
#             damaged.chmod(0o444)
#             before = tree_state(fixture.base)
#             selected = launcher.select_build(fixture.registry, ('probe',), target='macos-arm64')
#             try:
#                 self.assertEqual(selected.number, '10')
#                 self.assertEqual(selected.arguments, ('probe',))
#                 self.assertIsNone(selected.warning)
#                 self.assertTrue(os.get_inheritable(selected.run_fd))
#             finally:
#                 os.close(selected.run_fd)
#             for number in ('12', '13', '14', '15', '16'):
#                 with self.subTest(unavailable=number), self.assertRaises(launcher.LauncherError) as error:
#                     launcher.select_build(fixture.registry, ('-v', number, 'probe'), target='macos-arm64')
#                 self.assertEqual(error.exception.code, 'refused')
#             self.assertEqual(tree_state(fixture.base), before)
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherSelectionTests.test_numeric_default_skips_every_unavailable_status_target_and_damaged_build_without_writes

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherSelectionTests.test_only_first_selector_is_consumed_and_withdrawn_requires_explicit_selection
#     def test_only_first_selector_is_consumed_and_withdrawn_requires_explicit_selection(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build('f')
#             fixture.build('10', status='withdrawn', reason='known parser regression')
#             for arguments, number, forwarded in (
#                 (('probe', '-v', '10'), 'f', ('probe', '-v', '10')),
#                 (('-v', 'f', 'grep', '-v', 'needle'), 'f', ('grep', '-v', 'needle')),
#                 (('-v', '10', 'probe', ''), '10', ('probe', ''))):
#                 with self.subTest(arguments=arguments):
#                     selected = launcher.select_build(fixture.registry, arguments, target='macos-arm64')
#                     try:
#                         self.assertEqual((selected.number, selected.arguments), (number, forwarded))
#                         if number == '10':
#                             self.assertIn('known parser regression', selected.warning)
#                     finally:
#                         os.close(selected.run_fd)
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherSelectionTests.test_only_first_selector_is_consumed_and_withdrawn_requires_explicit_selection

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherSelectionTests.test_malformed_unknown_unavailable_and_empty_default_are_sanitized_structured_errors
#     def test_malformed_unknown_unavailable_and_empty_default_are_sanitized_structured_errors(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build('f')
#             fixture.build('10', status='failed')
#             for arguments, code in ((('-v',), 'invalid_input'), (('-v', '01'), 'invalid_input'),
#                 (('-v', 'F'), 'invalid_input'), (('-v', '0'), 'invalid_input'),
#                 (('-v', '0x10'), 'invalid_input'), (('-v', '17'), 'invalid_input'),
#                 (('-v', '../private-secret'), 'invalid_input'), (('-v', '10'), 'refused')):
#                 output, errors = io.StringIO(), io.StringIO()
#                 with self.subTest(arguments=arguments):
#                     status = launcher.main(arguments, registry=fixture.registry, target='macos-arm64',
#                         stdout=output, stderr=errors, execute=lambda *args: self.fail('unavailable exec'))
#                     self.assertEqual(status, 1)
#                     reply = json.loads(output.getvalue())
#                     self.assertEqual(reply['error']['code'], code)
#                     self.assertNotIn('private-secret', output.getvalue())
#                     self.assertEqual(errors.getvalue(), '')
#                     self.assertEqual(reply['runnable'], ['f'])
#             output, errors = io.StringIO(), io.StringIO()
#
#             def failed_exec(*arguments):
#                 raise OSError('private executable path must not escape')
#
#             self.assertEqual(launcher.main(('probe',), registry=fixture.registry, target='macos-arm64',
#                 stdout=output, stderr=errors, execute=failed_exec), 1)
#             self.assertEqual(json.loads(output.getvalue())['error']['code'], 'refused')
#             self.assertEqual(json.loads(output.getvalue())['runnable'], ['f'])
#             self.assertNotIn('private executable', output.getvalue())
#             self.assertEqual(errors.getvalue(), '')
#             fixture.record('f', status='withdrawn', reason='regression')
#             result = fixture.run('probe')
#             self.assertEqual(result.returncode, 1)
#             self.assertEqual(json.loads(result.stdout)['error']['code'], 'refused')
#             self.assertEqual(result.stderr, b'')
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherSelectionTests.test_malformed_unknown_unavailable_and_empty_default_are_sanitized_structured_errors



# class LauncherProcessTests(_support.LauncherProcessTests):
# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherProcessTests.test_actual_exec_preserves_pid_cwd_every_argument_and_environment_without_distribution_writes
#     def test_actual_exec_preserves_pid_cwd_every_argument_and_environment_without_distribution_writes(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build('f')
#             fixture.build('10')
#             before = tree_state(fixture.base)
#             arguments = ('spaces inside', '', 'éλ', '--literal', '-v', 'f', '$(literal)')
#             with fixture.running('-v', 'f', 'probe', *arguments) as process:
#                 output, errors = process.communicate(timeout=10)
#                 reply = json.loads(output)
#                 self.assertEqual(process.returncode, 0)
#                 self.assertEqual(reply['pid'], process.pid)
#                 self.assertEqual(reply['cwd'], str(fixture.cwd))
#                 self.assertEqual(reply['argv'], list(arguments))
#                 self.assertEqual((reply['isolated'], reply['noBytecode']), (1, True))
#                 self.assertEqual(reply['config'], str(fixture.config))
#                 self.assertEqual(errors, b'')
#             self.assertEqual(tree_state(fixture.base), before)
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherProcessTests.test_actual_exec_preserves_pid_cwd_every_argument_and_environment_without_distribution_writes

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherProcessTests.test_actual_binary_streams_stdin_and_arbitrary_exit_status_pass_without_json_wrapping
#     def test_actual_binary_streams_stdin_and_arbitrary_exit_status_pass_without_json_wrapping(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build()
#             for status in (0, 1, 2, 37):
#                 with self.subTest(status=status):
#                     reply = fixture.run('binary', str(status), input=b'input\x00\xff\n')
#                     self.assertEqual(reply.returncode, status)
#                     self.assertEqual(reply.stdout, b'out\x00input\x00\xff\n')
#                     self.assertEqual(reply.stderr, b'err\xff\n')
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherProcessTests.test_actual_binary_streams_stdin_and_arbitrary_exit_status_pass_without_json_wrapping

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherProcessTests.test_real_signal_default_and_selected_process_handler_receive_original_pid
#     def test_real_signal_default_and_selected_process_handler_receive_original_pid(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build()
#             for mode, expected, error in (((), -signal.SIGTERM, b''), (('handle',), 73, b'handled SIGTERM\n')):
#                 with self.subTest(mode=mode), fixture.running('hold', *mode) as process:
#                     ready = json.loads(ready_line(process))
#                     self.assertEqual(ready['pid'], process.pid)
#                     process.send_signal(signal.SIGTERM)
#                     output, errors = process.communicate(timeout=10)
#                     self.assertEqual((process.returncode, output, errors), (expected, b'', error))
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherProcessTests.test_real_signal_default_and_selected_process_handler_receive_original_pid

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherProcessTests.test_info_reports_the_selected_package_identity_and_withdrawn_warning_uses_only_stderr
#     def test_info_reports_the_selected_package_identity_and_withdrawn_warning_uses_only_stderr(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build('f', product=True)
#             fixture.build('10', status='withdrawn', product=True, reason='known parser regression')
#             before = tree_state(fixture.base)
#             default, explicit = fixture.run('info'), fixture.run('-v', '10', 'info')
#             self.assertEqual(default.returncode, 0)
#             self.assertEqual(explicit.returncode, 0)
#             self.assertEqual(json.loads(default.stdout)['build'], 'f')
#             self.assertEqual(json.loads(explicit.stdout)['build'], '10')
#             self.assertEqual(default.stderr, b'')
#             self.assertIn(b'known parser regression', explicit.stderr)
#             self.assertNotIn(b'known parser regression', explicit.stdout)
#             self.assertEqual(tree_state(fixture.base), before)
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherProcessTests.test_info_reports_the_selected_package_identity_and_withdrawn_warning_uses_only_stderr

# TEST-TIER-DISABLED-BEGIN tests/test_launcher_selection.py::LauncherProcessTests.test_real_product_grep_keeps_raw_stdin_output_error_and_status_under_invalid_settings
#     def test_real_product_grep_keeps_raw_stdin_output_error_and_status_under_invalid_settings(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(product=True)
#             executable = shutil.which('grep', path=os.defpath)
#             self.assertIsNotNone(executable)
#             for arguments, data in ((('needle',), b'needle\x00bytes\n'),
#                 (('absent',), b'ordinary line\n'), (('[',), b'any\n')):
#                 with self.subTest(arguments=arguments):
#                     expected = subprocess.run([executable, *arguments], input=data, capture_output=True,
#                         cwd=fixture.cwd, env=fixture.environment(), timeout=10)
#                     actual = fixture.run('grep', *arguments, input=data)
#                     self.assertEqual(actual.returncode, expected.returncode)
#                     self.assertEqual(actual.stdout, expected.stdout)
#                     self.assertTrue(actual.stderr.startswith(expected.stderr))
#                     self.assertNotIn(b'"error"', actual.stdout)
# TEST-TIER-DISABLED-END tests/test_launcher_selection.py::LauncherProcessTests.test_real_product_grep_keeps_raw_stdin_output_error_and_status_under_invalid_settings


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_selection.py:9
# import io
# TEST-TIER-IMPORTS-END tests/test_launcher_selection.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_selection.py:16
# import signal
# TEST-TIER-IMPORTS-END tests/test_launcher_selection.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_selection.py:19
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_launcher_selection.py:19

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_selection.py:22
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_launcher_selection.py:22

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_selection.py:24
# from mycel_build import _launcher_runtime as launcher
# TEST-TIER-IMPORTS-END tests/test_launcher_selection.py:24

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
