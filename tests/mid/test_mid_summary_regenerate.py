"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_regenerate as _support


class SummaryRegenerationStoreTests(_support.SummaryRegenerationStoreTests):


# TEST-TIER-BEGIN tests/test_summary_regenerate.py::SummaryRegenerationStoreTests.test_member_restored_during_memberless_deletion_preserves_stale_original
    def test_member_restored_during_memberless_deletion_preserves_stale_original(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summary = self.snapshot(connection)[0][0]
            sources = [(self.base.artifact / pin.place.path, (self.base.artifact / pin.place.path).read_bytes())
                       for pin in summary.state.members]
            for path, _ in sources:
                path.unlink()
            self.base.commit()
            self.base.apply(connection)
            old = self.current(connection)
            result = self.regenerate(connection, before_publish=lambda: sources[0][0].write_bytes(sources[0][1]))
            self.assertEqual((result.status, result.value["deleted"], result.value["written"]), (1, 0, 0))
            self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
            self.assertEqual(self.current(connection), old)
            self.no_leases(connection)
# TEST-TIER-END tests/test_summary_regenerate.py::SummaryRegenerationStoreTests.test_member_restored_during_memberless_deletion_preserves_stale_original
