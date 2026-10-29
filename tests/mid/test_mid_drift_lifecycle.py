"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_drift_lifecycle as _support
from test_drift_lifecycle import (DriftStore ,MycelError ,_FailAfterWrite ,operation_guard ,patch)


class DriftLifecycleStoreTests(_support.DriftLifecycleStoreTests):


# TEST-TIER-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason
    def test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason(self):
        guide = self.base.artifact / 'guide.md'
        self.fixture.source.write_bytes(b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n'
                                       + self.fixture.source_bytes)
        self.write_answer(*self.addresses, 'absent:@artifact/missing.md#Missing')
        self.base.commit()
        with self.base.connect() as connection:
            self.prepare(connection)
            guide.write_bytes(b'# Guide\nChanged upstream authority.\n')
            self.extra[0].write_bytes(b'# Source2\nChanged direct source.\n')
            self.fixture.publish(connection)
            self.sync(connection)
            drift = self.one(connection)
            self.assertIn('upstream_stale', {reason['kind'] for reason in drift['sources']})
            self.assertIn('ref_fault', {reason['kind'] for reason in drift['sources']})
            direct = self.reason(drift, 2, 'source_changed')
            drift = self.support(connection, drift, direct)
            protected = [reason for reason in drift['sources'] if reason['kind'] in {'ref_fault', 'upstream_stale'}]
            self.assertTrue(protected)
            for reason in protected:
                result = self.record(connection, drift, reason, judgement='still_supported')
                saved = next(value for value in result['drift']['sources'] if value['id'] == reason['id'])
                self.assertTrue(saved['active'])
                self.assertEqual(saved['classification']['status'], 'error')
                self.assertNotIn('judgement', saved['classification'])
            self.assertEqual(self.one(connection)['state'], 'open')
# TEST-TIER-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason


# TEST-TIER-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification
    def test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            self.change(connection, 1)
            opened = self.one(connection)
            with operation_guard(peer, 'downstream', 'pass'):
                with self.assertRaises(MycelError) as error:
                    self.sync(connection)
                self.assertEqual(error.exception.code, 'busy')
            self.sync(connection)
            self.assertEqual(self.one(connection), opened)
            before = self.state(connection)
            failing = _FailAfterWrite(connection)
            with self.assertRaises((RuntimeError, MycelError)):
                self.record(failing, opened, self.reason(opened), judgement='still_supported')
            self.assertTrue(failing.failed)
            self.assertEqual(self.state(connection), before)

            def annotations():
                return connection.execute("SELECT id,reason,xmin::text FROM public.mycel_stale_reasons "
                    "WHERE repository='downstream' ORDER BY id").fetchall()

            source_bytes = self.fixture.source.read_bytes()
            native_write = DriftStore._write

            def obsolete_support(drift, evidence):
                edited = False
                def late_write(store, *args, **kwargs):
                    nonlocal edited
                    value = native_write(store, *args, **kwargs)
                    if not edited:
                        edited = True
                        self.fixture.source.write_bytes(source_bytes + b'Late physical input change.\n')
                    return value
                previous = annotations()
                with patch.object(DriftStore, '_write', late_write):
                    result = self.record(connection, drift, self.reason(drift),
                        judgement='still_supported', evidence=evidence)
                self.assertTrue(edited)
                self.assertFalse(result['applied'], result)
                self.assertTrue(result['obsolete'], result)
                self.assertEqual(annotations(), previous)
                latest = self.one(connection)
                self.assertTrue(self.reason(latest)['active'])
                attempts = [item for item in latest['history'] if item.get('evidence') == evidence]
                self.assertEqual(len(attempts), 1)
                self.assertTrue(attempts[0]['obsolete'])
                archived = [item['source'] for item in latest['history'] if item.get('because') == 'input_changed'
                    and item['source']['pairHash'] == self.reason(drift)['pairHash']]
                self.assertTrue(archived)
                self.assertEqual(archived[-1]['classification'], self.reason(drift)['classification'])

            # An obsolete attempt may not create an annotation, or replace one
            # that an earlier exact-input answer already committed.
            self.assertTrue(all('classification' not in row[1] for row in annotations()))
            obsolete_support(opened, {'jev': {'case': 'late-first-answer'}})
            self.fixture.source.write_bytes(source_bytes)
            self.sync(connection)
            current = self.one(connection)
            committed = self.record(connection, current, self.reason(current), judgement='insufficient_evidence',
                evidence={'jev': {'case': 'committed-earlier-answer'}})
            self.assertTrue(committed['applied'], committed)
            self.assertEqual(annotations()[0][1]['classification']['evidence'],
                             {'jev': {'case': 'committed-earlier-answer'}})
            obsolete_support(committed['drift'], {'jev': {'case': 'late-replacement-answer'}})

            self.fixture.source.write_bytes(source_bytes)
            self.sync(connection)
            current = self.one(connection)
            before = self.state(connection)
            native_publish = DriftStore._publish_classification
            def late_publish(store, *args, **kwargs):
                value = native_publish(store, *args, **kwargs)
                self.fixture.source.write_bytes(source_bytes + b'Publication-time physical input change.\n')
                return value
            with patch.object(DriftStore, '_publish_classification', late_publish):
                with self.assertRaises(MycelError) as error:
                    self.record(connection, current, self.reason(current), judgement='still_supported',
                        evidence={'jev': {'case': 'publication-time-answer'}})
            self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification
