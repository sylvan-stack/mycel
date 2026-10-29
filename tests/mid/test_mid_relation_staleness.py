"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_relation_staleness as _support
from test_relation_staleness import (EvidenceStore ,MycelError ,checked_store ,operation_guard ,patch)


class RelationStalenessStoreTests(_support.RelationStalenessStoreTests):


# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication
    def test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            identifier, _ = self.seed(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged before late relation race.\n')
            def mutate(owner, counts):
                if owner == 'fixture':
                    peer.execute("""UPDATE public.mycel_relations SET state=state || '{"peerObservation":true}'::jsonb
                        WHERE id=%s""", (identifier,))
                return counts
            with checked_store(peer), operation_guard(peer, 'downstream', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, reply_counts=mutate)
            self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), [])
            original = self.fixture.answer.read_bytes()
            native = EvidenceStore._read_baseline
            def read(store, owner, baseline_id, **kwargs):
                value = native(store, owner, baseline_id, **kwargs)
                if owner == 'downstream':
                    self.fixture.answer.write_bytes(original + b'Late foreign mutation.\n')
                return value
            with patch.object(EvidenceStore, '_read_baseline', read):
                with self.assertRaises(MycelError):
                    self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication
