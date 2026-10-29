"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_check_store as _support
from test_check_store import (NativePostgresBackend ,Path ,json ,os ,patch ,tempfile)


class NativeCheckRunnerTests(_support.NativeCheckRunnerTests):


# TEST-TIER-BEGIN tests/test_check_store.py::NativeCheckRunnerTests.test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission
    def test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory)
            address = "postgresql://fixture@localhost/owner"
            worker = NativePostgresBackend(address, _ownership_journal=journal)
            name = "mycel_check_atomic"
            original_replace = os.replace
            def replace(source, destination):
                self.assertEqual(json.loads(Path(source).read_text())["database"], name)
                self.assertEqual(Path(source).stat().st_mode & 0o777, 0o600)
                self.assertFalse(Path(destination).exists())
                original_replace(source, destination)
            worker._begin_creation(name)
            with patch("mycel._check_store.os.replace", side_effect=replace) as publish:
                worker._acknowledge_creation(name)
                publish.assert_called_once()
            with patch.object(worker, "_execute", return_value=""):
                worker.drop_database(name)
            worker._begin_creation(name)
            with patch("mycel._check_store.json.dump", side_effect=OSError("private-file-sentinel")):
                with self.assertRaisesRegex(RuntimeError, "ownership record failed"):
                    worker._acknowledge_creation(name)
            self.assertEqual(list(journal.iterdir()), [])
            parent = NativePostgresBackend(address, _ownership_journal=journal)
            with patch.object(parent, "_execute") as boundary:
                self.assertEqual(parent.recover_owned_databases(), ())
                boundary.assert_not_called()
# TEST-TIER-END tests/test_check_store.py::NativeCheckRunnerTests.test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission
