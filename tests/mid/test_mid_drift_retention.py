"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_drift_retention as _support
from test_drift_retention import (AT ,ClassificationStore ,ConfirmationStore ,DriftHistoryStore ,EvidenceStore ,Jsonb ,NOW ,UUID ,atomic_transaction ,timedelta)


class DriftRetentionStoreTests(_support.DriftRetentionStoreTests):


# TEST-TIER-BEGIN tests/test_drift_retention.py::DriftRetentionStoreTests.test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners
    def test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            ConfirmationStore(connection).apply(self.base.settings, self.fixture.ref, by='owner', captured_at=AT)
            self.fixture.change(connection, 1)
            self.old_files()
            drift = self.fixture.one(connection)
            prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
                self.fixture.reason(drift)['id'], at=AT)
            dependency = self.fixture.fixture.dependencies(connection)[0]
            baseline = EvidenceStore(connection).read_baseline('downstream', dependency[7])
            verification = connection.execute('SELECT evidence_owner FROM public.mycel_verifications').fetchone()[0]
            with self.guarded(connection), atomic_transaction(connection):
                histories = self.seed_history(connection, prepared, 1001,
                    first_id=UUID('00000000-0000-0000-0000-000000000001'))
                result = DriftHistoryStore(connection).prune_in_transaction('downstream')
            self.assertEqual(result['records'], 1)
            self.assertGreaterEqual(result['snapshots'], 2)
            ids = {str(row[0]) for row in connection.execute('SELECT id FROM public.mycel_drifts WHERE closed_at IS NOT NULL')}
            self.assertEqual(ids, {item[0] for item in histories[1:]})
            for digest in histories[0][1:]:
                self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                                                    ('downstream', digest)).fetchone())
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', dependency[7]), baseline)
            self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_evidence_owners WHERE id=%s',
                                                   (verification,)).fetchone())
            self.assertEqual(self.fixture.one(connection)['state'], 'open')
            # Closure time wins over UUID; an older high ID falls outside the bound.
            oldest = histories[-1][0]
            with self.guarded(connection), atomic_transaction(connection):
                older = (NOW - timedelta(days=2)).isoformat()
                state = self.row(connection, oldest)[5]
                state['closed']['at'] = older
                state['sources'][0]['closed']['at'] = older
                connection.execute('UPDATE public.mycel_drifts SET closed_at=%s,state=%s WHERE id=%s',
                                    (older, Jsonb(state), oldest))
                self.seed_history(connection, prepared, 1, at=(NOW + timedelta(days=1)).isoformat())
                removed = DriftHistoryStore(connection).prune_in_transaction('downstream')
            self.assertEqual(removed['records'], 1)
            self.assertIsNone(self.row(connection, oldest))
# TEST-TIER-END tests/test_drift_retention.py::DriftRetentionStoreTests.test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners

# TEST-TIER-BEGIN tests/test_drift_retention.py::DriftRetentionStoreTests.test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends
    def test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends(self):
        with self.base.connect() as connection, self.base.connect() as writer:
            prepared = self.prepare(connection)
            with ClassificationStore(connection).stage(self.base.settings, prepared, stage='jev', at=AT) as checked:
                self.assertTrue(checked['allowed'])
                self.fixture.fixture.source.write_bytes(b'# Source\nA newer changed source.\n')
                self.fixture.fixture.publish(writer)
                self.fixture.sync(writer)
                archived = writer.execute("SELECT id FROM public.mycel_drifts WHERE dependant_version IS NULL "
                    "AND state->'classificationRequests' ? %s", (prepared.input_hash,)).fetchone()[0]
                current = self.fixture.one(writer)
                newer = ClassificationStore(writer).prepare(self.base.settings, current['id'],
                    self.fixture.reason(current)['id'], at=(NOW + timedelta(minutes=10)).isoformat())
                with self.guarded(writer), atomic_transaction(writer):
                    self.seed_history(writer, newer, 1000, at=(NOW + timedelta(days=1)).isoformat())
                    result = DriftHistoryStore(writer).prune_in_transaction('downstream')
                self.assertEqual(result['records'], 0)
                self.assertIsNotNone(self.row(writer, archived))
                returned = ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='needs_review', evidence={'stage': 'late-result'}, at=AT)
                self.assertTrue(returned['obsolete'])
                saved = self.row(writer, archived)[5]
                self.assertTrue(any(item.get('evidence') == {'stage': 'late-result'} and item['obsolete']
                                    for item in saved['history']))
                self.assertIsNotNone(writer.execute('SELECT 1 FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                                                    ('downstream', prepared.input_hash)).fetchone())
            self.assertIsNone(self.row(writer, archived))
            self.assertIsNone(writer.execute('SELECT 1 FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                                            ('downstream', prepared.input_hash)).fetchone())
            self.assertEqual(writer.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='classification_lease'").fetchone(), (0,))
# TEST-TIER-END tests/test_drift_retention.py::DriftRetentionStoreTests.test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends
