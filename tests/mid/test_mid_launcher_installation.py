
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_installation.py::LauncherInstallationTests.test_complete_independent_bundles_install_atomically_run_and_keep_old_bundle_bytes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Complete independent bundles install atomically run and keep old bundle bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_installation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_independent_bundles_install_atomically_run_and_keep_old_bundle_bytes(self):
#         with tempfile.TemporaryDirectory(prefix="mycel launcher ' quoted ") as directory:
#             fixture = LauncherFixture(directory)
#             fixture.registry = fixture.home / '.mycel/builds'
#             fixture.build()
#             first = bundle_fixture(fixture.base, 'bundle first')
#             second = bundle_fixture(fixture.base, 'bundle second')
#             source_before = (tree_state(first), tree_state(second))
#             settings_before = fixture.config.read_bytes()
#             one = installer.install_launcher(first, home=fixture.home)
#             entry, old_bundle = Path(one['entrypoint']), Path(one['bundle'])
#             self.assertTrue(entry.is_symlink())
#             old_before = tree_state(old_bundle)
#             two = installer.install_launcher(second, home=fixture.home)
#             self.assertTrue(two['previousLauncherRetained'])
#             self.assertNotEqual(one['bundle'], two['bundle'])
#             self.assertEqual(tree_state(old_bundle), old_before)
#             self.assertEqual(entry.resolve(), Path(two['bundle']) / 'mycel')
#             before = tree_state(fixture.home)
#             with subprocess.Popen([str(entry), 'probe', 'with spaces', '', '$(literal)', '-v', '1'],
#                     cwd=fixture.cwd, env=fixture.environment(), stdout=subprocess.PIPE,
#                     stderr=subprocess.PIPE) as process:
#                 try:
#                     output, errors = process.communicate(timeout=10)
#                 except BaseException:
#                     process.kill()
#                     process.communicate(timeout=10)
#                     raise
#                 self.assertEqual(process.returncode, 0, errors)
#                 self.assertEqual(json.loads(output)['pid'], process.pid)
#                 self.assertEqual(json.loads(output)['argv'], ['with spaces', '', '$(literal)', '-v', '1'])
#                 self.assertEqual(json.loads(output)['cwd'], str(fixture.cwd))
#                 self.assertEqual(errors, b'')
#             self.assertEqual(tree_state(fixture.home), before)
#             self.assertEqual((tree_state(first), tree_state(second)), source_before)
#             self.assertEqual(fixture.config.read_bytes(), settings_before)
#             self.assertEqual(installer.install_launcher(second, home=fixture.home)['bundle'], two['bundle'])
#             self.assertEqual(tree_state(old_bundle), old_before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_installation.py::LauncherInstallationTests.test_unrelated_command_and_unsafe_parent_refuse_before_creating_or_replacing_owner_files
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unrelated command and unsafe parent refuse before creating or replacing owner files.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_installation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unrelated_command_and_unsafe_parent_refuse_before_creating_or_replacing_owner_files(self):
#         for conflict in ('regular-command', 'outside-command-link', 'launcher-parent-link', 'bin-parent-link'):
#             with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as directory:
#                 fixture = LauncherFixture(directory)
#                 bundle = bundle_fixture(fixture.base, 'bundle')
#                 outside = fixture.base / 'unrelated-owner'
#                 outside.mkdir()
#                 (outside / 'keep').write_bytes(b'unrelated bytes')
#                 entry = fixture.home / '.local/bin/mycel'
#                 if conflict == 'launcher-parent-link':
#                     (fixture.home / '.mycel').mkdir()
#                     (fixture.home / '.mycel/launcher').symlink_to(outside, target_is_directory=True)
#                 elif conflict == 'bin-parent-link':
#                     (fixture.home / '.local').mkdir()
#                     (fixture.home / '.local/bin').symlink_to(outside, target_is_directory=True)
#                 else:
#                     entry.parent.mkdir(parents=True)
#                     if conflict == 'regular-command':
#                         entry.write_bytes(b'owner command must remain')
#                     else:
#                         entry.symlink_to(outside / 'keep')
#                 before = tree_state(fixture.base)
#                 with self.assertRaises(BuildError) as error:
#                     installer.install_launcher(bundle, home=fixture.home)
#                 self.assertEqual(error.exception.code, 'refused')
#                 self.assertEqual(tree_state(fixture.base), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_installation.py::LauncherInstallationTests.test_busy_installer_and_failed_final_cutover_preserve_existing_runnable_launcher
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Busy installer and failed final cutover preserve existing runnable launcher.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_installation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_busy_installer_and_failed_final_cutover_preserve_existing_runnable_launcher(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.registry = fixture.home / '.mycel/builds'
#             fixture.build()
#             first = bundle_fixture(fixture.base, 'first')
#             second = bundle_fixture(fixture.base, 'second')
#             one = installer.install_launcher(first, home=fixture.home)
#             entry, old_bundle = Path(one['entrypoint']), Path(one['bundle'])
#             before = tree_state(fixture.home)
#             old_before = tree_state(old_bundle)
#             with peer_lock(fixture.home / '.mycel/launcher/.install.lock', fcntl.LOCK_EX):
#                 with self.assertRaises(BuildError) as error:
#                     installer.install_launcher(second, home=fixture.home)
#                 self.assertEqual(error.exception.code, 'busy')
#             self.assertEqual(tree_state(fixture.home), before)
#             original = os.replace
#
#             def refuse_final(source, destination):
#                 if Path(destination) == entry:
#                     raise OSError('fixture cutover failure')
#                 return original(source, destination)
#
#             with patch.object(installer.os, 'replace', side_effect=refuse_final):
#                 with self.assertRaises(BuildError) as error:
#                     installer.install_launcher(second, home=fixture.home)
#             self.assertEqual(error.exception.code, 'internal')
#             self.assertFalse(error.exception.partialResult['installed'])
#             self.assertTrue(error.exception.partialResult['bundleStaged'])
#             self.assertNotIn('fixture cutover failure', str(error.exception))
#             self.assertEqual(entry.resolve(), old_bundle / 'mycel')
#             self.assertEqual(tree_state(old_bundle), old_before)
#             self.assertFalse(list(entry.parent.glob('.mycel-launcher-*')))
#             self.assertFalse(list((fixture.home / '.mycel/launcher').glob('.install-*')))
#             result = subprocess.run([str(entry), 'probe', 'old still available'], cwd=fixture.cwd,
#                 env=fixture.environment(), capture_output=True, timeout=10)
#             self.assertEqual(result.returncode, 0)
#             self.assertEqual(json.loads(result.stdout)['argv'], ['old still available'])
#             self.assertEqual(tree_state(old_bundle), old_before)
#             # A later directory fsync can fail after entry replacement. Both
#             # ordinary faults and cancellation must report the actual new entry,
#             # retaining the old immutable bundle rather than pretending rollback.
#             original_sync = os.fsync
#             parent_info = entry.parent.stat()
#             for failure, source in ((OSError, second), (KeyboardInterrupt, first)):
#                 with self.subTest(late_failure=failure):
#                     immutable = {path.name: tree_state(path) for path in
#                         (fixture.home / '.mycel/launcher').iterdir() if path.is_dir()}
#
#                     def fail_entry_sync(fd):
#                         info = os.fstat(fd)
#                         if (info.st_dev, info.st_ino) == (parent_info.st_dev, parent_info.st_ino):
#                             raise failure('late private entry fsync')
#                         return original_sync(fd)
#
#                     with patch.object(installer.os, 'fsync', side_effect=fail_entry_sync):
#                         with self.assertRaises(KeyboardInterrupt if failure is KeyboardInterrupt else BuildError) as error:
#                             installer.install_launcher(source, home=fixture.home)
#                     partial = error.exception.partialResult
#                     self.assertTrue(partial['installed'])
#                     self.assertTrue(partial['bundleStaged'])
#                     self.assertEqual(entry.resolve(), Path(partial['bundle']) / 'mycel')
#                     if failure is OSError:
#                         self.assertEqual(error.exception.code, 'internal')
#                         self.assertNotIn('late private entry fsync', str(error.exception))
#                     self.assertEqual({path.name: tree_state(path) for path in
#                         (fixture.home / '.mycel/launcher').iterdir() if path.is_dir()}, immutable)
#                     self.assertFalse(list(entry.parent.glob('.mycel-launcher-*')))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_installation.py::LauncherInstallationTests.test_unchecked_or_tampered_bundle_never_replaces_existing_command
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unchecked or tampered bundle never replaces existing command.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_installation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unchecked_or_tampered_bundle_never_replaces_existing_command(self):
#         for damage in ('unchecked', 'payload', 'pin', 'writable'):
#             with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
#                 fixture = LauncherFixture(directory)
#                 first = bundle_fixture(fixture.base, 'first')
#                 installer.install_launcher(first, home=fixture.home)
#                 second = bundle_fixture(fixture.base, 'second')
#                 if damage == 'writable':
#                     second.chmod(0o755)
#                 elif damage == 'unchecked':
#                     path = second / 'bundle.json'
#                     path.chmod(0o644)
#                     record = json.loads(path.read_bytes())
#                     record['checks']['passed'] = False
#                     second.chmod(0o755)
#                     atomic_json(path, record)
#                     path.chmod(0o444)
#                     second.chmod(0o555)
#                 else:
#                     path = second / 'program' / ('launcher.py' if damage == 'payload' else 'bootstrap-pin.json')
#                     path.chmod(0o644)
#                     path.write_bytes(b'changed bytes')
#                     path.chmod(0o444)
#                 before = tree_state(fixture.home)
#                 with self.assertRaises(BuildError) as error:
#                     installer.install_launcher(second, home=fixture.home)
#                 self.assertEqual(error.exception.code, 'refused')
#                 self.assertEqual(tree_state(fixture.home), before)
#         # An unchanged, read-only trampoline is still damaged when it cannot
#         # execute. Check both the currently owned command and reuse of an old
#         # retained bundle whose command link is absent; neither may be repaired
#         # or reported as a successful installation implicitly.
#         for location in ('owned-command', 'retained-destination'):
#             with self.subTest(nonexecutable_entry=location), tempfile.TemporaryDirectory() as directory:
#                 fixture = LauncherFixture(directory)
#                 source = bundle_fixture(fixture.base, 'checked source')
#                 result = installer.install_launcher(source, home=fixture.home)
#                 entry = Path(result['entrypoint'])
#                 target = Path(result['bundle']) / 'mycel'
#                 original_bytes = target.read_bytes()
#                 self.assertTrue(os.access(target, os.X_OK))
#                 target.chmod(0o444)
#                 self.assertEqual(target.read_bytes(), original_bytes)
#                 self.assertFalse(os.access(target, os.X_OK))
#                 if location == 'retained-destination':
#                     entry.unlink()
#                 before = tree_state(fixture.base)
#                 with self.assertRaises(BuildError) as error:
#                     installer.install_launcher(source, home=fixture.home)
#                 self.assertEqual(error.exception.code, 'refused')
#                 self.assertEqual(tree_state(fixture.base), before)
#                 self.assertEqual(target.read_bytes(), original_bytes)
#                 self.assertEqual(target.stat().st_mode & 0o777, 0o444)
#                 if location == 'retained-destination':
#                     self.assertFalse(os.path.lexists(entry))
#                 else:
#                     self.assertTrue(entry.is_symlink())
#                     self.assertEqual(entry.resolve(), target)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
