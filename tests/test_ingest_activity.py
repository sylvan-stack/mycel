# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public subprocess audit checks with an explicitly fictional numbered package.

Only the immutable package-local Build identity is a fixture. CLI dispatch,
publication, PostgreSQL writes and both activity readers run without patches.
This is not installed-runtime or working-Build qualification.
"""


import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import mycel

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class PublicIngestActivityStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()
        self.package_root = self.base.base / 'fictional-numbered-package'
        package = self.package_root / 'mycel'
        shutil.copytree(Path(mycel.__file__).parent, package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # Installed inputs are sealed. Only this independent fictional copy
        # may replace its identity; the source package stays untouched.
        data = package / 'data'
        data.chmod(data.stat().st_mode | 0o200)
        (package / 'data/development-identity.json').unlink(missing_ok=True)
        self.identity = package / 'data/build-identity.json'
        self.identity.unlink(missing_ok=True)
        self.identity.write_bytes(b'{"schemaVersion":1,"build":26}\n')

    def invoke(self, *arguments, status=0):
        completed = subprocess.run([sys.executable, '-B', '-P', '-m', 'mycel', *arguments],
            env={**os.environ, 'MYCEL_CONFIG': str(self.base.config),
                 'PYTHONPATH': str(self.package_root)}, cwd=self.base.base,
            capture_output=True, text=True, timeout=180)
        self.assertEqual(completed.stderr, '')
        reply = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, status, reply)
        return reply

    def history(self):
        return self.invoke('activity', '--repo', 'fixture', '--kind', 'ingest')['entries']
