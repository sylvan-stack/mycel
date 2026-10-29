"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_derive as _support
from test_derive import (MutationActivity ,MycelError ,patch)


class DeriveStoreTests(_support.DeriveStoreTests):


# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_audit_failure_and_late_capture_change_roll_back_feature_and_activity
    def test_audit_failure_and_late_capture_change_roll_back_feature_and_activity(self):
        with self.base.connect() as connection:
            self.publish(connection)
            before = self.state(connection)
            with patch.object(MutationActivity, 'record_in_transaction', side_effect=MycelError('internal', 'Audit failed.')):
                with self.assertRaises(MycelError):
                    self.derive(connection)
            self.assertEqual(self.state(connection), before)
            record = MutationActivity.record_in_transaction
            def late_change(activity, repository, kind, result):
                record(activity, repository, kind, result)
                self.source.write_bytes(b'# Source\nChanged during audit.\n')
            with patch.object(MutationActivity, 'record_in_transaction', late_change):
                with self.assertRaises(MycelError) as error:
                    self.derive(connection)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            self.source.write_bytes(self.source_bytes)
            original_settings = self.base.config.read_text()
            def late_settings(activity, repository, kind, result):
                record(activity, repository, kind, result)
                self.base.config.write_text(original_settings.replace('enabled=true', 'enabled=false'))
            with patch.object(MutationActivity, 'record_in_transaction', late_settings):
                with self.assertRaises(MycelError) as error:
                    self.derive(connection)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            self.base.config.write_text(original_settings)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_audit_failure_and_late_capture_change_roll_back_feature_and_activity
