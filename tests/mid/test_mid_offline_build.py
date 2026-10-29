"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_offline_build as _support
from test_offline_build import (Path ,report ,tempfile)


class InstalledAutomaticTests(_support.InstalledAutomaticTests):


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
