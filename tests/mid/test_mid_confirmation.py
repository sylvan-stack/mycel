"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_confirmation as _support
from test_confirmation import (MutationActivity ,MycelError ,patch)


class ConfirmationStoreTests(_support.ConfirmationStoreTests):


# TEST-TIER-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_source_change_rolls_back_pins_record_and_activity
    def test_final_audit_callback_source_change_rolls_back_pins_record_and_activity(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            before = self.state(connection)
            original = MutationActivity.record_in_transaction
            def change_after_audit(activity, *args, **kwargs):
                result = original(activity, *args, **kwargs)
                self.fixture.source.write_bytes(b'# Source\nChanged during audit callback.\n')
                return result
            with patch.object(MutationActivity, 'record_in_transaction', change_after_audit):
                with self.assertRaises(MycelError) as error:
                    self.confirm(connection, build=1)
            self.assertIn('changed_since_ingest', error.exception.message)
            after = self.state(connection)
            # The failed audit session may retain invocation liveness, but no
            # feature or per-repository mutation activity row can survive.
            self.assertEqual(after, before)
# TEST-TIER-END tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_source_change_rolls_back_pins_record_and_activity
