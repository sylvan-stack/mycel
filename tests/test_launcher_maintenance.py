"""Real OS lock handoff, explicit maintenance and interrupted pruning proofs."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel_build import _launcher_runtime as launcher
from mycel_build import _maintenance as maintenance_api
from mycel_build._core import BuildError, atomic_json
from mycel_build._registry import maintenance, read_record, run_guard

try:
    from .test_launcher_selection import LauncherFixture, ROOT, ready_line, thaw, tree_state
except ImportError:
    from test_launcher_selection import LauncherFixture, ROOT, ready_line, thaw, tree_state


@contextmanager
def peer_lock(path, operation):
    code = ('import fcntl,os,sys\n'
        'fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW)\n'
        'fcntl.flock(fd,int(sys.argv[2])|fcntl.LOCK_NB)\n'
        'print("locked",flush=True)\n'
        'sys.stdin.buffer.read()\n')
    process = subprocess.Popen([sys.executable, '-I', '-B', '-c', code, str(path), str(operation)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert ready_line(process) == b'locked\n'
        yield process
    finally:
        process.communicate(timeout=10)
        if process.returncode:
            raise AssertionError('fixture lock peer failed')


def peer_prune(fixture, number):
    code = ('import json,sys\nfrom pathlib import Path\n'
        f'sys.path.insert(0,{str(ROOT / "src")!r})\n'
        'from mycel_build._maintenance import prune\n'
        'from mycel_build._core import BuildError\n'
        'try:\n'
        '    result=prune(Path(sys.argv[1]),sys.argv[2])\n'
        '    print(json.dumps({"result":result}))\n'
        'except BuildError as error:\n'
        '    print(json.dumps({"error":{"code":error.code}}))\n'
        '    raise SystemExit(1)\n')
    return subprocess.run([sys.executable, '-I', '-B', '-c', code, str(fixture.registry), number],
        env=fixture.environment(), capture_output=True, timeout=5)


class LauncherMaintenanceTests(unittest.TestCase):
    @proves('MYC-15.9', kind='unit')
    def test_uncertain_lock_or_unrecorded_bootstrap_ownership_refuses_before_marking_or_deleting(self):
        for damage in ('missing-lock', 'linked-lock', 'hardlinked-lock', 'unrecorded-bundle'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
                fixture = LauncherFixture(directory)
                fixture.build(status='failed')
                folder = fixture.registry / '1'
                sentinel = fixture.base / 'unrelated retained bytes'
                sentinel.write_bytes(b'owner bytes and mode')
                if damage == 'unrecorded-bundle':
                    (folder / 'launcher-bundle').mkdir()
                    (folder / 'launcher-bundle/keep').write_bytes(b'not a recorded Build program')
                else:
                    (folder / 'run.lock').unlink()
                    if damage == 'linked-lock':
                        (folder / 'run.lock').symlink_to(sentinel)
                    elif damage == 'hardlinked-lock':
                        os.link(sentinel, folder / 'run.lock')
                before = tree_state(fixture.base)
                with self.assertRaises(BuildError) as error:
                    maintenance_api.prune(fixture.registry, '1')
                self.assertEqual(error.exception.code, 'refused')
                self.assertEqual(tree_state(fixture.base), before)
                self.assertNotIn('prunedAt', json.loads((folder / 'build.json').read_bytes()))

    @proves('MYC-15.9', kind='unit')
    def test_second_program_tree_partial_prune_retries_without_removing_installed_independent_bundle_or_metadata(self):
        try:
            from .test_launcher_installation import bundle_fixture
        except ImportError:
            from test_launcher_installation import bundle_fixture
        from mycel_build._launcher import install_launcher
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build(status='withdrawn', reason='regression')
            fixture.build()
            folder = fixture.registry / '1'
            bundle = bundle_fixture(folder, 'launcher-bundle')
            fixture.record('1', launcherBundle='launcher-bundle')
            installed = install_launcher(bundle, home=fixture.home)
            installed_before = tree_state(fixture.home)
            sibling_before = tree_state(fixture.registry / '2')
            retained = {name: (bundle / name).read_bytes() for name in ('bundle.json', 'files.json')}
            original = maintenance_api._remove_program
            calls = []

            def fail_second(target):
                calls.append(Path(target))
                if Path(target) == bundle:
                    raise OSError('second program tree unavailable')
                return original(target)

            with patch.object(maintenance_api, '_remove_program', side_effect=fail_second):
                with self.assertRaises(BuildError) as error:
                    maintenance_api.prune(fixture.registry, '1')
            partial = read_record(fixture.registry, '1')
            self.assertEqual(error.exception.partialResult, partial)
            self.assertFalse(partial['pruneComplete'])
            self.assertIn(bundle, calls)
            self.assertFalse((folder / 'program').exists())
            self.assertTrue((bundle / 'program').is_dir())
            result = maintenance_api.prune(fixture.registry, '1')
            self.assertTrue(result['pruneComplete'])
            self.assertEqual(result['prunedAt'], partial['prunedAt'])
            self.assertFalse((bundle / 'program').exists())
            self.assertEqual(bundle.stat().st_mode & 0o777, 0o555)
            self.assertEqual({name: (bundle / name).read_bytes() for name in retained}, retained)
            self.assertEqual(tree_state(fixture.home), installed_before)
            self.assertEqual(tree_state(fixture.registry / '2'), sibling_before)
            self.assertTrue(Path(installed['bundle']).is_dir())

    @proves('MYC-15.9', kind='unit')
    def test_late_withdrawal_failure_or_interrupt_reports_actual_persisted_record_without_hiding_cutover(self):
        for failure in (OSError, KeyboardInterrupt):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                fixture = LauncherFixture(directory)
                fixture.build()
                fixture.build()
                folder = fixture.registry / '2'
                program_before = tree_state(folder / 'program')
                siblings = {p.name: p.read_bytes() for p in folder.iterdir()
                            if p.is_file() and p.name != 'build.json'}
                unrelated = tree_state(fixture.registry / '1')

                def persist_then_fail(path, record):
                    atomic_json(path, record)
                    raise failure('late private fixture fault')

                with patch.object(maintenance_api, 'atomic_json', side_effect=persist_then_fail):
                    with self.assertRaises(KeyboardInterrupt if failure is KeyboardInterrupt else BuildError) as error:
                        maintenance_api.withdraw(fixture.registry, '2', ' parser\nregression ')
                actual = read_record(fixture.registry, '2')
                self.assertEqual(error.exception.partialResult, actual)
                self.assertEqual((actual['status'], actual['reason']), ('withdrawn', 'parser regression'))
                if failure is OSError:
                    self.assertEqual(error.exception.code, 'internal')
                    self.assertNotIn('private fixture fault', str(error.exception))
                self.assertEqual(tree_state(folder / 'program'), program_before)
                self.assertEqual(tree_state(fixture.registry / '1'), unrelated)
                self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()
                    if p.is_file() and p.name != 'build.json'}, siblings)
                selected = launcher.select_build(fixture.registry, ('probe',), target='macos-arm64')
                try:
                    self.assertEqual(selected.number, '1')
                finally:
                    os.close(selected.run_fd)

    @proves('MYC-15.6', 'MYC-15.9', kind='unit')
    def test_registry_maintenance_makes_selection_and_other_release_mutations_immediately_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build()
            before = tree_state(fixture.registry)
            with peer_lock(fixture.registry / '.registry.lock', fcntl.LOCK_EX):
                start = time.monotonic()
                reply = fixture.run('probe')
                self.assertLess(time.monotonic() - start, 3)
                self.assertEqual(reply.returncode, 1)
                self.assertEqual(json.loads(reply.stdout)['error']['code'], 'busy')
                self.assertEqual(reply.stderr, b'')
                for action in (lambda: maintenance_api.withdraw(fixture.registry, '1', 'regression'),
                               lambda: maintenance_api.prune(fixture.registry, '1')):
                    start = time.monotonic()
                    with self.assertRaises(BuildError) as error:
                        action()
                    self.assertEqual(error.exception.code, 'busy')
                    self.assertLess(time.monotonic() - start, 1)
            self.assertEqual(tree_state(fixture.registry), before)

    @proves('MYC-15.6', 'MYC-15.9', kind='unit')
    def test_registry_shared_lock_covers_selection_until_actual_run_lock_is_acquired(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build(status='withdrawn', reason='regression')
            wanted = (fixture.registry / '1/run.lock').stat()
            original = fcntl.flock
            observed = []
            before = tree_state(fixture.registry)

            def acquire(fd, operation):
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) == (wanted.st_dev, wanted.st_ino):
                    # This executes before the selected run lock is held. The
                    # registry shared lock must already prevent peer pruning.
                    result = peer_prune(fixture, '1')
                    observed.append(json.loads(result.stdout))
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(observed[-1]['error']['code'], 'busy')
                return original(fd, operation)

            with patch.object(launcher.fcntl, 'flock', side_effect=acquire):
                selected = launcher.select_build(fixture.registry, ('-v', '1', 'probe'), target='macos-arm64')
            try:
                self.assertEqual(len(observed), 1)
                # Selection has now released the registry lock while retaining
                # the run lock. This distinct protection must also reject prune.
                with maintenance(fixture.registry):
                    pass
                result = peer_prune(fixture, '1')
                self.assertEqual(json.loads(result.stdout)['error']['code'], 'busy')
                self.assertEqual(tree_state(fixture.registry), before)
            finally:
                os.close(selected.run_fd)
            self.assertTrue(maintenance_api.prune(fixture.registry, '1')['pruneComplete'])

    @proves('MYC-15.7', 'MYC-15.9', kind='unit')
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

    @proves('MYC-15.9', kind='unit')
    def test_only_explicit_failed_or_withdrawn_program_is_removed_without_touching_siblings_or_link_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build(status='working')
            fixture.build(status='building')
            fixture.build(status='failed')
            fixture.build(status='withdrawn', reason='regression')
            before = tree_state(fixture.registry)
            for number in ('1', '2'):
                with self.subTest(number=number), self.assertRaises(BuildError) as error:
                    maintenance_api.prune(fixture.registry, number)
                self.assertEqual(error.exception.code, 'refused')
            for reason in ('', ' \n\t '):
                with self.assertRaises(BuildError) as error:
                    maintenance_api.withdraw(fixture.registry, '1', reason)
                self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(tree_state(fixture.registry), before)
            sentinel = fixture.base / 'unrelated'
            sentinel.mkdir()
            (sentinel / 'keep').write_bytes(b'owner unrelated bytes')
            before_sentinel = tree_state(sentinel)
            program = fixture.registry / '3/program'
            thaw(program)
            (program / 'outside-link').symlink_to(sentinel, target_is_directory=True)
            # A hardlinked external file must not be chmodded before unlink.
            os.link(sentinel / 'keep', program / 'hardlink')
            retained = {p.name: p.read_bytes() for p in (fixture.registry / '3').iterdir() if p.is_file()}
            sibling = tree_state(fixture.registry / '4')
            record = maintenance_api.prune(fixture.registry, '3')
            self.assertTrue(record['pruneComplete'])
            self.assertEqual(tree_state(sentinel), before_sentinel)
            self.assertEqual(tree_state(fixture.registry / '4'), sibling)
            self.assertTrue((fixture.registry / '4/program').exists())
            for name, raw in retained.items():
                if name != 'build.json':
                    self.assertEqual((fixture.registry / '3' / name).read_bytes(), raw)
            self.assertEqual(read_record(fixture.registry, '3')['build'], '3')

    @proves('MYC-15.6', 'MYC-15.9', kind='unit')
    def test_partial_prune_stays_unavailable_and_explicit_retry_preserves_original_time_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build(status='withdrawn', reason='regression')
            with patch.object(maintenance_api, '_remove_program', side_effect=OSError('private-fault')):
                with self.assertRaises(BuildError) as error:
                    maintenance_api.prune(fixture.registry, '1')
            partial = error.exception.partialResult
            self.assertEqual(error.exception.code, 'internal')
            self.assertFalse(partial['pruneComplete'])
            self.assertEqual(read_record(fixture.registry, '1'), partial)
            self.assertNotIn('private-fault', str(error.exception))
            with self.assertRaises(launcher.LauncherError) as unavailable:
                launcher.select_build(fixture.registry, ('-v', '1'), target='macos-arm64')
            self.assertEqual(unavailable.exception.code, 'refused')
            result = maintenance_api.prune(fixture.registry, '1')
            self.assertEqual(result['prunedAt'], partial['prunedAt'])
            self.assertTrue(result['pruneComplete'])
            self.assertFalse((fixture.registry / '1/program').exists())
            for name in ('build.json', 'checks.json', 'build.log', 'run.lock', 'files.json'):
                self.assertTrue((fixture.registry / '1' / name).is_file())
