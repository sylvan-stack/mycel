"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_classification_guard_edges as _support
from test_classification_guard_edges import (AT ,ClassificationStore ,Jsonb ,NOW ,json ,os ,timedelta)


class ClassificationGuardEdgeStoreTests(_support.ClassificationGuardEdgeStoreTests):

# TEST-TIER-BEGIN tests/test_classification_guard_edges.py::ClassificationGuardEdgeStoreTests.test_removed_section_keeps_live_file_and_tombstone_timers_and_outside_edit_restarts_file
    def test_removed_section_keeps_live_file_and_tombstone_timers_and_outside_edit_restarts_file(self):
        with self.base.connect() as connection:
            initial = self.prepare(connection)
            dependency = self.fixture.reason(self.fixture.one(connection))['dependency']
            path = self.fixture.fixture.source
            path.write_bytes(b'# Other\nA surviving source section.\n')
            self.fixture.fixture.publish(connection)
            state = connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s',
                                       (dependency,)).fetchone()[0]
            deleted_at = NOW + timedelta(seconds=1)
            state['sourceAbsence']['observedAt'] = deleted_at.isoformat()
            connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',
                               (Jsonb(state), dependency))
            self.fixture.sync(connection)
            self.old_files()
            drift = self.fixture.one(connection)
            writer = ClassificationStore(connection)
            removed = writer.prepare(self.base.settings, drift['id'], self.fixture.reason(drift, kind='source_removed')['id'],
                                     at=deleted_at.isoformat())
            self.assertIsNone(removed.fault, removed.as_dict())
            self.assertIn(removed.decision.payload['current']['state'], {'away', 'deleted'})
            self.assertEqual(removed.decision.payload['current']['members'], ())
            self.assertEqual(removed.decision.payload['before'], initial.decision.payload['before'])
            observed = json.loads(removed.observations_bytes)
            file_key, tombstone_key = 'fixture:@artifact/source.md', 'fixture:@artifact/source.md#Source|tombstone'
            self.assertEqual((observed[file_key]['kind'], observed[tombstone_key]['kind']), ('file', 'deleted'))
            self.assertEqual(observed[tombstone_key]['firstObservedAt'], deleted_at.isoformat(timespec='microseconds'))
            self.assertEqual(removed.eligible_at, (deleted_at + timedelta(seconds=300)).isoformat(timespec='microseconds'))
            events = {(item['place']['address'], item['event']) for item in removed.bundle.payload['guards']}
            self.assertIn((file_key, 'file_changed'), events)
            self.assertIn(('fixture:@artifact/source.md#Source', 'deleted'), events)
            stamp = path.stat().st_mtime_ns
            path.write_bytes(path.read_bytes() + b'# Elsewhere\nA later edit outside the removed selection.\n')
            os.utime(path, ns=(stamp, stamp))
            self.fixture.fixture.publish(connection)
            self.fixture.sync(connection)
            drift = self.fixture.one(connection)
            later = NOW + timedelta(seconds=101)
            changed = writer.prepare(self.base.settings, drift['id'],
                                     self.fixture.reason(drift, kind='source_removed')['id'], at=later.isoformat())
            self.assertIsNone(changed.fault, changed.as_dict())
            self.assertEqual(changed.input_hash, removed.input_hash)
            self.assertNotEqual(changed.guards_bytes, removed.guards_bytes)
            changes = json.loads(changed.observations_bytes)
            self.assertEqual(changes[tombstone_key]['firstObservedAt'], observed[tombstone_key]['firstObservedAt'])
            self.assertEqual(changes[file_key]['firstObservedAt'], later.isoformat(timespec='microseconds'))
            self.assertEqual(changes[file_key]['faults'], ['timestamp_untrusted'])
            self.assertEqual(changed.eligible_at, (later + timedelta(seconds=300)).isoformat(timespec='microseconds'))
            self.assertFalse(self.stage_check(connection, removed, at=later.isoformat())['allowed'])
            self.assertTrue(self.stage_check(connection, changed, at=changed.eligible_at)['allowed'])
# TEST-TIER-END tests/test_classification_guard_edges.py::ClassificationGuardEdgeStoreTests.test_removed_section_keeps_live_file_and_tombstone_timers_and_outside_edit_restarts_file

# TEST-TIER-BEGIN tests/test_classification_guard_edges.py::ClassificationGuardEdgeStoreTests.test_standalone_ref_fault_is_required_missing_context_without_silent_omission
    def test_standalone_ref_fault_is_required_missing_context_without_silent_omission(self):
        self.fixture.write_answer(*self.fixture.addresses, 'not a ref')
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            faults = connection.execute("SELECT id FROM public.mycel_ref_faults WHERE repository='downstream'").fetchall()
            self.assertTrue(faults)
            # The normal producer emits the declaration fault. Remove its
            # unpinned stub to exercise the supported standalone representation.
            connection.execute("DELETE FROM public.mycel_dependencies WHERE repository='downstream' AND baseline_owner IS NULL")
            self.fixture.change(connection, 1)
            self.old_files()
            links = {row[0] for row in self.fixture.fixture.dependencies(connection)}
            self.assertTrue(any(identifier not in links for identifier, in faults))
            drift = self.fixture.one(connection)
            selected = self.fixture.reason(drift, kind='source_changed')
            prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'], selected['id'], at=AT)
            self.assertEqual(prepared.fault, 'context_missing')
            self.assertIsNone(prepared.decision)
            self.assertIsNone(prepared.bundle)
            for stage in ('jev', 'review'):
                self.assertEqual(self.stage_check(connection, prepared, stage), {'allowed': False, 'reason': 'context_missing'})
            state = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (drift['id'],)).fetchone()[0]
            self.assertEqual(state.get('classificationRequests', {}), {})
# TEST-TIER-END tests/test_classification_guard_edges.py::ClassificationGuardEdgeStoreTests.test_standalone_ref_fault_is_required_missing_context_without_silent_omission
