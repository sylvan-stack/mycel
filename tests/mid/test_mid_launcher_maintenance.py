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
