"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_relation_occurrence_regressions as _support
from test_relation_occurrence_regressions import (
    SOURCE,
    store_state,
)


class RelationOccurrenceRegressionStoreTests(_support.RelationOccurrenceRegressionStoreTests):
    def test_mixed_closed_and_unclosed_same_ref_pins_valid_occurrence_and_reports_only_invalid_fault(self):
        self.guide.write_bytes(self.mixed())
        self.base.commit()
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            pins = self.current_pins(connection)
            self.assertEqual(set(pins), {'declared'})
            baseline = self.baseline(connection, pins['declared'])
            self.assertEqual((baseline.manifest.payload['selection'], baseline.manifest.payload['source']['address']),
                             ('chunk', SOURCE))
            self.assertEqual(len(baseline.manifest.payload['members']), 1)
            self.assertIn(self.fixture.source_bytes, [blob.source for blob in baseline.snapshots])
            before = store_state(connection)
            self.assert_mixed_reports()
            self.assertEqual(store_state(connection), before)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
