"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_generated as _support
from test_generated import (Jsonb ,MycelError ,invocation_guard ,patch)


class GeneratedStoreTests(_support.GeneratedStoreTests):


# TEST-TIER-BEGIN tests/test_generated.py::GeneratedStoreTests.test_final_secondary_request_evidence_change_rolls_back_detection_and_source_publication
    def test_final_secondary_request_evidence_change_rolls_back_detection_and_source_publication(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, self.capture(connection, 'fixture:@artifact/source.md#Source'))
                self.publish(connection, invocation, lease)
            self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
            before = self.state(connection)
            from mycel._staleness import MechanicalStalenessStore
            verify = MechanicalStalenessStore.verify_in_transaction
            def changed_request(detector, settings, guards):
                connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 99}), 'fixture', lease.request_manifest))
                verify(detector, settings, guards)
            with patch.object(MechanicalStalenessStore, 'verify_in_transaction', changed_request), self.assertRaises(MycelError):
                self.fixture.publish(connection)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_generated.py::GeneratedStoreTests.test_final_secondary_request_evidence_change_rolls_back_detection_and_source_publication
