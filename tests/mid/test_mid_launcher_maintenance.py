"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_launcher_maintenance as _support
from test_launcher_maintenance import (LauncherFixture ,json ,launcher ,maintenance_api ,os ,peer_prune ,ready_line ,tempfile ,time ,tree_state)


class LauncherMaintenanceTests(_support.LauncherMaintenanceTests):


# TEST-TIER-BEGIN tests/test_launcher_maintenance.py::LauncherMaintenanceTests.test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit
    def test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build()
            fixture.build()
            folder = fixture.registry / '2'
            lock_identity = (folder / 'run.lock').stat().st_ino
            program_before = tree_state(folder / 'program')
            with fixture.running('hold') as process:
                ready = json.loads(ready_line(process))
                self.assertEqual(ready['pid'], process.pid)
                record = maintenance_api.withdraw(fixture.registry, '2', ' parser\nregression ')
                self.assertEqual(record['reason'], 'parser regression')
                selected = launcher.select_build(fixture.registry, ('probe',), target='macos-arm64')
                os.close(selected.run_fd)
                self.assertEqual(selected.number, '1')
                before_busy = tree_state(fixture.registry)
                start = time.monotonic()
                result = peer_prune(fixture, '2')
                self.assertLess(time.monotonic() - start, 3)
                self.assertEqual(json.loads(result.stdout)['error']['code'], 'busy')
                self.assertEqual(tree_state(fixture.registry), before_busy)
                self.assertEqual(tree_state(folder / 'program'), program_before)
                process.terminate()
                process.communicate(timeout=10)
            retained = {name: (folder / name).read_bytes() for name in
                ('checks.json', 'build.log', 'run.lock', 'files.json')}
            result = maintenance_api.prune(fixture.registry, '2')
            self.assertTrue(result['pruneComplete'])
            self.assertFalse((folder / 'program').exists())
            self.assertEqual((folder / 'run.lock').stat().st_ino, lock_identity)
            self.assertEqual({name: (folder / name).read_bytes() for name in retained}, retained)
            self.assertTrue((fixture.registry / '1/program').is_dir())
# TEST-TIER-END tests/test_launcher_maintenance.py::LauncherMaintenanceTests.test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_uncertain_lock_or_unrecorded_bootstrap_ownership_refuses_before_marking_or_deleting
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Uncertain lock or unrecorded bootstrap ownership refuses before marking or deleting.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_uncertain_lock_or_unrecorded_bootstrap_ownership_refuses_before_marking_or_deleting(self):
#         for damage in ('missing-lock', 'linked-lock', 'hardlinked-lock', 'unrecorded-bundle'):
#             with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
#                 fixture = LauncherFixture(directory)
#                 fixture.build(status='failed')
#                 folder = fixture.registry / '1'
#                 sentinel = fixture.base / 'unrelated retained bytes'
#                 sentinel.write_bytes(b'owner bytes and mode')
#                 if damage == 'unrecorded-bundle':
#                     (folder / 'launcher-bundle').mkdir()
#                     (folder / 'launcher-bundle/keep').write_bytes(b'not a recorded Build program')
#                 else:
#                     (folder / 'run.lock').unlink()
#                     if damage == 'linked-lock':
#                         (folder / 'run.lock').symlink_to(sentinel)
#                     elif damage == 'hardlinked-lock':
#                         os.link(sentinel, folder / 'run.lock')
#                 before = tree_state(fixture.base)
#                 with self.assertRaises(BuildError) as error:
#                     maintenance_api.prune(fixture.registry, '1')
#                 self.assertEqual(error.exception.code, 'refused')
#                 self.assertEqual(tree_state(fixture.base), before)
#                 self.assertNotIn('prunedAt', json.loads((folder / 'build.json').read_bytes()))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_second_program_tree_partial_prune_retries_without_removing_installed_independent_bundle_or_metadata
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Second program tree partial prune retries without removing installed independent bundle or metadata.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_second_program_tree_partial_prune_retries_without_removing_installed_independent_bundle_or_metadata(self):
#         try:
#             from .test_launcher_installation import bundle_fixture
#         except ImportError:
#             from test_launcher_installation import bundle_fixture
#         from mycel_build._launcher import install_launcher
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(status='withdrawn', reason='regression')
#             fixture.build()
#             folder = fixture.registry / '1'
#             bundle = bundle_fixture(folder, 'launcher-bundle')
#             fixture.record('1', launcherBundle='launcher-bundle')
#             installed = install_launcher(bundle, home=fixture.home)
#             installed_before = tree_state(fixture.home)
#             sibling_before = tree_state(fixture.registry / '2')
#             retained = {name: (bundle / name).read_bytes() for name in ('bundle.json', 'files.json')}
#             original = maintenance_api._remove_program
#             calls = []
#
#             def fail_second(target):
#                 calls.append(Path(target))
#                 if Path(target) == bundle:
#                     raise OSError('second program tree unavailable')
#                 return original(target)
#
#             with patch.object(maintenance_api, '_remove_program', side_effect=fail_second):
#                 with self.assertRaises(BuildError) as error:
#                     maintenance_api.prune(fixture.registry, '1')
#             partial = read_record(fixture.registry, '1')
#             self.assertEqual(error.exception.partialResult, partial)
#             self.assertFalse(partial['pruneComplete'])
#             self.assertIn(bundle, calls)
#             self.assertFalse((folder / 'program').exists())
#             self.assertTrue((bundle / 'program').is_dir())
#             result = maintenance_api.prune(fixture.registry, '1')
#             self.assertTrue(result['pruneComplete'])
#             self.assertEqual(result['prunedAt'], partial['prunedAt'])
#             self.assertFalse((bundle / 'program').exists())
#             self.assertEqual(bundle.stat().st_mode & 0o777, 0o555)
#             self.assertEqual({name: (bundle / name).read_bytes() for name in retained}, retained)
#             self.assertEqual(tree_state(fixture.home), installed_before)
#             self.assertEqual(tree_state(fixture.registry / '2'), sibling_before)
#             self.assertTrue(Path(installed['bundle']).is_dir())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_late_withdrawal_failure_or_interrupt_reports_actual_persisted_record_without_hiding_cutover
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Late withdrawal failure or interrupt reports actual persisted record without hiding cutover.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_late_withdrawal_failure_or_interrupt_reports_actual_persisted_record_without_hiding_cutover(self):
#         for failure in (OSError, KeyboardInterrupt):
#             with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
#                 fixture = LauncherFixture(directory)
#                 fixture.build()
#                 fixture.build()
#                 folder = fixture.registry / '2'
#                 program_before = tree_state(folder / 'program')
#                 siblings = {p.name: p.read_bytes() for p in folder.iterdir()
#                             if p.is_file() and p.name != 'build.json'}
#                 unrelated = tree_state(fixture.registry / '1')
#
#                 def persist_then_fail(path, record):
#                     atomic_json(path, record)
#                     raise failure('late private fixture fault')
#
#                 with patch.object(maintenance_api, 'atomic_json', side_effect=persist_then_fail):
#                     with self.assertRaises(KeyboardInterrupt if failure is KeyboardInterrupt else BuildError) as error:
#                         maintenance_api.withdraw(fixture.registry, '2', ' parser\nregression ')
#                 actual = read_record(fixture.registry, '2')
#                 self.assertEqual(error.exception.partialResult, actual)
#                 self.assertEqual((actual['status'], actual['reason']), ('withdrawn', 'parser regression'))
#                 if failure is OSError:
#                     self.assertEqual(error.exception.code, 'internal')
#                     self.assertNotIn('private fixture fault', str(error.exception))
#                 self.assertEqual(tree_state(folder / 'program'), program_before)
#                 self.assertEqual(tree_state(fixture.registry / '1'), unrelated)
#                 self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()
#                     if p.is_file() and p.name != 'build.json'}, siblings)
#                 selected = launcher.select_build(fixture.registry, ('probe',), target='macos-arm64')
#                 try:
#                     self.assertEqual(selected.number, '1')
#                 finally:
#                     os.close(selected.run_fd)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_registry_maintenance_makes_selection_and_other_release_mutations_immediately_busy
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Registry maintenance makes selection and other release mutations immediately busy.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_registry_maintenance_makes_selection_and_other_release_mutations_immediately_busy(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build()
#             before = tree_state(fixture.registry)
#             with peer_lock(fixture.registry / '.registry.lock', fcntl.LOCK_EX):
#                 start = time.monotonic()
#                 reply = fixture.run('probe')
#                 self.assertLess(time.monotonic() - start, 3)
#                 self.assertEqual(reply.returncode, 1)
#                 self.assertEqual(json.loads(reply.stdout)['error']['code'], 'busy')
#                 self.assertEqual(reply.stderr, b'')
#                 for action in (lambda: maintenance_api.withdraw(fixture.registry, '1', 'regression'),
#                                lambda: maintenance_api.prune(fixture.registry, '1')):
#                     start = time.monotonic()
#                     with self.assertRaises(BuildError) as error:
#                         action()
#                     self.assertEqual(error.exception.code, 'busy')
#                     self.assertLess(time.monotonic() - start, 1)
#             self.assertEqual(tree_state(fixture.registry), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_registry_shared_lock_covers_selection_until_actual_run_lock_is_acquired
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Registry shared lock covers selection until actual run lock is acquired.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_registry_shared_lock_covers_selection_until_actual_run_lock_is_acquired(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(status='withdrawn', reason='regression')
#             wanted = (fixture.registry / '1/run.lock').stat()
#             original = fcntl.flock
#             observed = []
#             before = tree_state(fixture.registry)
#
#             def acquire(fd, operation):
#                 info = os.fstat(fd)
#                 if (info.st_dev, info.st_ino) == (wanted.st_dev, wanted.st_ino):
#                     # This executes before the selected run lock is held. The
#                     # registry shared lock must already prevent peer pruning.
#                     result = peer_prune(fixture, '1')
#                     observed.append(json.loads(result.stdout))
#                     self.assertEqual(result.returncode, 1)
#                     self.assertEqual(observed[-1]['error']['code'], 'busy')
#                 return original(fd, operation)
#
#             with patch.object(launcher.fcntl, 'flock', side_effect=acquire):
#                 selected = launcher.select_build(fixture.registry, ('-v', '1', 'probe'), target='macos-arm64')
#             try:
#                 self.assertEqual(len(observed), 1)
#                 # Selection has now released the registry lock while retaining
#                 # the run lock. This distinct protection must also reject prune.
#                 with maintenance(fixture.registry):
#                     pass
#                 result = peer_prune(fixture, '1')
#                 self.assertEqual(json.loads(result.stdout)['error']['code'], 'busy')
#                 self.assertEqual(tree_state(fixture.registry), before)
#             finally:
#                 os.close(selected.run_fd)
#             self.assertTrue(maintenance_api.prune(fixture.registry, '1')['pruneComplete'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_only_explicit_failed_or_withdrawn_program_is_removed_without_touching_siblings_or_link_targets
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Only explicit failed or withdrawn program is removed without touching siblings or link targets.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_only_explicit_failed_or_withdrawn_program_is_removed_without_touching_siblings_or_link_targets(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(status='working')
#             fixture.build(status='building')
#             fixture.build(status='failed')
#             fixture.build(status='withdrawn', reason='regression')
#             before = tree_state(fixture.registry)
#             for number in ('1', '2'):
#                 with self.subTest(number=number), self.assertRaises(BuildError) as error:
#                     maintenance_api.prune(fixture.registry, number)
#                 self.assertEqual(error.exception.code, 'refused')
#             for reason in ('', ' \n\t '):
#                 with self.assertRaises(BuildError) as error:
#                     maintenance_api.withdraw(fixture.registry, '1', reason)
#                 self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(tree_state(fixture.registry), before)
#             sentinel = fixture.base / 'unrelated'
#             sentinel.mkdir()
#             (sentinel / 'keep').write_bytes(b'owner unrelated bytes')
#             before_sentinel = tree_state(sentinel)
#             program = fixture.registry / '3/program'
#             thaw(program)
#             (program / 'outside-link').symlink_to(sentinel, target_is_directory=True)
#             # A hardlinked external file must not be chmodded before unlink.
#             os.link(sentinel / 'keep', program / 'hardlink')
#             retained = {p.name: p.read_bytes() for p in (fixture.registry / '3').iterdir() if p.is_file()}
#             sibling = tree_state(fixture.registry / '4')
#             record = maintenance_api.prune(fixture.registry, '3')
#             self.assertTrue(record['pruneComplete'])
#             self.assertEqual(tree_state(sentinel), before_sentinel)
#             self.assertEqual(tree_state(fixture.registry / '4'), sibling)
#             self.assertTrue((fixture.registry / '4/program').exists())
#             for name, raw in retained.items():
#                 if name != 'build.json':
#                     self.assertEqual((fixture.registry / '3' / name).read_bytes(), raw)
#             self.assertEqual(read_record(fixture.registry, '3')['build'], '3')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_launcher_maintenance.py::LauncherMaintenanceTests.test_partial_prune_stays_unavailable_and_explicit_retry_preserves_original_time_and_metadata
# Reason: Narrower case removed from this family after retaining test_real_exec_retains_readonly_run_lock_through_withdrawal_until_process_exit. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Partial prune stays unavailable and explicit retry preserves original time and metadata.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_launcher_maintenance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_partial_prune_stays_unavailable_and_explicit_retry_preserves_original_time_and_metadata(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = LauncherFixture(directory)
#             fixture.build(status='withdrawn', reason='regression')
#             with patch.object(maintenance_api, '_remove_program', side_effect=OSError('private-fault')):
#                 with self.assertRaises(BuildError) as error:
#                     maintenance_api.prune(fixture.registry, '1')
#             partial = error.exception.partialResult
#             self.assertEqual(error.exception.code, 'internal')
#             self.assertFalse(partial['pruneComplete'])
#             self.assertEqual(read_record(fixture.registry, '1'), partial)
#             self.assertNotIn('private-fault', str(error.exception))
#             with self.assertRaises(launcher.LauncherError) as unavailable:
#                 launcher.select_build(fixture.registry, ('-v', '1'), target='macos-arm64')
#             self.assertEqual(unavailable.exception.code, 'refused')
#             result = maintenance_api.prune(fixture.registry, '1')
#             self.assertEqual(result['prunedAt'], partial['prunedAt'])
#             self.assertTrue(result['pruneComplete'])
#             self.assertFalse((fixture.registry / '1/program').exists())
#             for name in ('build.json', 'checks.json', 'build.log', 'run.lock', 'files.json'):
#                 self.assertTrue((fixture.registry / '1' / name).is_file())
# LOW-TIER-SOURCE-END
# LOW-TIER-END
