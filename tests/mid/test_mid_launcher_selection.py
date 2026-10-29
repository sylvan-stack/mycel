
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherSelectionTests.test_numeric_default_skips_every_unavailable_status_target_and_damaged_build_without_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Numeric default skips every unavailable status target and damaged build without writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherSelectionTests.test_only_first_selector_is_consumed_and_withdrawn_requires_explicit_selection
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Only first selector is consumed and withdrawn requires explicit selection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherSelectionTests.test_malformed_unknown_unavailable_and_empty_default_are_sanitized_structured_errors
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Malformed unknown unavailable and empty default are sanitized structured errors.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherProcessTests.test_actual_exec_preserves_pid_cwd_every_argument_and_environment_without_distribution_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Actual exec preserves pid cwd every argument and environment without distribution writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherProcessTests.test_actual_binary_streams_stdin_and_arbitrary_exit_status_pass_without_json_wrapping
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Actual binary streams stdin and arbitrary exit status pass without json wrapping.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherProcessTests.test_real_signal_default_and_selected_process_handler_receive_original_pid
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Real signal default and selected process handler receive original pid.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherProcessTests.test_info_reports_the_selected_package_identity_and_withdrawn_warning_uses_only_stderr
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Info reports the selected package identity and withdrawn warning uses only stderr.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_selection.py::LauncherProcessTests.test_real_product_grep_keeps_raw_stdin_output_error_and_status_under_invalid_settings
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Real product grep keeps raw stdin output error and status under invalid settings.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_selection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END
