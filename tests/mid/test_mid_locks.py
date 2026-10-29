"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_locks as _support
from test_locks import (Path ,UUID ,json ,locks ,selectors ,sha256 ,subprocess ,sys ,time)


class LockStoreTests(_support.LockStoreTests):


# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_killed_owning_process_releases_every_lock_without_cleanup_files
    def test_killed_owning_process_releases_every_lock_without_cleanup_files(self):
        fixture = self.store_fixture
        def files():
            return {str(path.relative_to(fixture.root)): sha256(path.read_bytes()).hexdigest()
                    for path in fixture.root.rglob("*") if path.is_file()}
        before = files()
        # Only the disposable settings filename is passed. The child reads it
        # itself; argv/environment contain no store URI or credential value.
        program = """
import json, time
from urllib.parse import unquote, urlsplit
from mycel._coverage import require_check_database
from mycel._settings import load_settings
from mycel._credentials import Credentials
from mycel._database import store_connection
from mycel._locks import invocation_guard, operation_guard
from mycel._safeguards import InvocationPolicy
settings = load_settings()
settings.require_valid()
database = require_check_database(unquote(urlsplit(settings.values['store']['address']).path[1:]))
with store_connection(Credentials(settings, InvocationPolicy('init'))) as connection:
    assert connection.execute('SELECT pg_catalog.current_database()').fetchone()[0] == database
    with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'pass'):
        print(json.dumps({'invocation': str(invocation.id)}), flush=True)
        time.sleep(60)
"""
        process = subprocess.Popen((sys.executable, "-c", program), cwd=fixture.root,
                                   env={"HOME": str(Path.home()), "MYCEL_CONFIG": str(fixture.settings_file),
                                        "PATH": "/usr/bin:/bin", "LC_ALL": "C",
                                        "PYTHONDONTWRITEBYTECODE": "1",
                                        "PYTHONPATH": str(Path(locks._support.__file__).parent.parent)},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(5), "Fictional lock holder did not become ready.")
            payload = json.loads(process.stdout.readline())
            identifier = UUID(payload["invocation"])
            with self.connect() as other:
                self.assertTrue(locks.invocation_is_live(other, identifier))
                self.busy(locks.operation_guard(other, "fixture", "pass"))
                process.kill()
                process.wait(timeout=5)
                until = time.monotonic() + 2
                while locks.invocation_is_live(other, identifier) and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertFalse(locks.invocation_is_live(other, identifier))
                with locks.operation_guard(other, "fixture", "pass"):
                    pass
                with locks.removal_guard(other, "fixture"):
                    pass
                with locks.structure_guard(other, exclusive=True):
                    pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        self.assertEqual(files(), before)
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_killed_owning_process_releases_every_lock_without_cleanup_files
