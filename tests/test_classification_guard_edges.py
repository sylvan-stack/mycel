"""Additional exact request and timer edges through disposable native stores."""

from datetime import timedelta
from hashlib import sha256
import json
import os
import unittest

from psycopg.types.json import Jsonb

from mycel._classification_store import ClassificationStore
from mycel._coverage import proves
from mycel._relate import RelateStore
from mycel._resolver import SourceResolver

try:
    from .test_classification_store import ClassificationStoreFixture, AT, NOW
except ImportError:
    from test_classification_store import ClassificationStoreFixture, AT, NOW


class ClassificationGuardEdgeStoreTests(ClassificationStoreFixture):
    check_kind = "store"

    @proves('MYC-14.2', 'MYC-14.14', 'MYC-14.15', 'MYC-16.8', kind='store')
    def test_two_related_inputs_retain_independent_evidence_and_observation_maps(self):
        self.fixture.write_answer()
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            for address in self.fixture.addresses[:2]:
                RelateStore(connection).apply(self.base.settings, self.fixture.ref, address,
                    captured_at=AT, settings_home=self.base.base)
            self.fixture.change(connection, 1, 2)
            self.old_files()
            paths = (self.fixture.fixture.source, self.fixture.extra[0])
            for path, seconds in zip(paths, (20, 40), strict=True):
                stamp = (NOW - timedelta(seconds=seconds)).timestamp()
                os.utime(path, (stamp, stamp))
            drift = self.fixture.one(connection)
            reasons = [self.fixture.reason(drift, number, kind='related_changed') for number in (1, 2)]
            writer = ClassificationStore(connection)
            first = writer.prepare(self.base.settings, drift['id'], reasons[0]['id'], at=AT)
            second = writer.prepare(self.base.settings, drift['id'], reasons[1]['id'], at=AT)
            for prepared in (first, second):
                self.assertIsNone(prepared.fault, prepared.as_dict())
                self.assertEqual(prepared.decision.payload['baseline']['kind'], 'related')
                self.assertEqual(prepared.decision.payload['context'], ())
                self.assertEqual(prepared.status, 'pending_debounce')
                self.assertIn('Original', prepared.decision.payload['before'][0]['text'])
                self.assertIn('Changed', prepared.decision.payload['current']['members'][0]['text'])
            self.assertNotEqual(first.input_hash, second.input_hash)
            self.assertEqual(first.eligible_at, (NOW + timedelta(seconds=280)).isoformat(timespec='microseconds'))
            self.assertEqual(second.eligible_at, (NOW + timedelta(seconds=260)).isoformat(timespec='microseconds'))
            state = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (drift['id'],)).fetchone()[0]
            observations = state['classificationObservations']
            self.assertTrue({'fixture:@artifact/source.md', 'fixture:@artifact/source2.md'} <= set(observations))
            self.assertTrue({first.input_hash, second.input_hash} <= set(state['classificationRequests']))
            repeated = writer.prepare(self.base.settings, drift['id'], reasons[0]['id'],
                                      at=(NOW + timedelta(seconds=60)).isoformat())
            self.assertEqual(repeated.input_hash, first.input_hash)
            self.assertEqual(repeated.eligible_at, first.eligible_at)
            retained = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (drift['id'],)).fetchone()[0]
            self.assertEqual(retained['classificationObservations']['fixture:@artifact/source2.md'],
                             observations['fixture:@artifact/source2.md'])
            self.assertTrue(self.stage_check(connection, repeated, at=first.eligible_at)['allowed'])
            self.assertTrue(self.stage_check(connection, second, at=second.eligible_at)['allowed'])

    @proves('MYC-14.2', 'MYC-14.14', 'MYC-14.15', 'MYC-16.8', kind='store')
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

    @proves('MYC-14.2', 'MYC-14.15', kind='store')
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

    @proves('MYC-14.2', 'MYC-14.15', 'MYC-16.8', kind='store')
    def test_code_family_and_whole_file_preserve_complete_exact_membership_and_bytes(self):
        code = self.base.code / 'policy.py'
        original = (b'# exact file preface\nclass Policy:\n    def apply(self):\n        return 1\n'
                    b'    def keep(self):\n        return 2\n# exact file footer\n')
        code.write_bytes(original)
        self.fixture.write_answer('fixture:@code/policy.py#Policy', 'fixture:@code/policy.py')
        self.base.commit()
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            current = original.replace(b'return 1', b'return 3').replace(b'# exact file footer',
                b'    def zed(self):\n        return 4\n# exact file footer')
            code.write_bytes(current)
            self.fixture.fixture.publish(connection)
            self.fixture.sync(connection)
            self.old_files()
            stamp = (NOW - timedelta(days=1)).timestamp()
            os.utime(code, (stamp, stamp))
            drift = self.fixture.one(connection)
            dependency_by_ref = {row[3]: str(row[0]) for row in self.fixture.fixture.dependencies(connection)}
            requests = {}
            for ref in ('fixture:@code/policy.py#Policy', 'fixture:@code/policy.py'):
                reason = next(item for item in drift['sources'] if item['dependency'] == dependency_by_ref[ref]
                              and item['kind'] == 'source_changed')
                prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'], reason['id'], at=AT)
                self.assertIsNone(prepared.fault, prepared.as_dict())
                self.assertTrue(self.stage_check(connection, prepared)['allowed'])
                requests[ref] = prepared
            family = requests['fixture:@code/policy.py#Policy'].decision.payload
            whole = requests['fixture:@code/policy.py'].decision.payload
            self.assertEqual(family['baseline']['selection'], 'family')
            self.assertEqual([item['snapshot']['place']['name'] for item in family['before']],
                             ['Policy', 'Policy.apply', 'Policy.keep'])
            self.assertEqual([item['snapshot']['place']['name'] for item in family['current']['members']],
                             ['Policy', 'Policy.apply', 'Policy.keep', 'Policy.zed'])
            resolved = SourceResolver.from_store(connection, self.base.settings).resolve('fixture:@code/policy.py#Policy').selection
            self.assertEqual([(item['snapshot']['place']['address'], item['text'].encode()) for item in family['current']['members']],
                             [(member.place.address, member.chunk.source) for member in resolved.members])
            self.assertEqual(whole['baseline']['selection'], 'file')
            self.assertEqual(whole['before'][0]['text'].encode(), original)
            self.assertEqual(whole['current']['members'][0]['text'].encode(), current)
            self.assertEqual(whole['current']['members'][0]['snapshot']['hash'], sha256(current).hexdigest())
            for prepared in requests.values():
                retained = connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                    ('downstream', prepared.input_hash)).fetchone()[0]
                self.assertEqual(bytes(retained), prepared.decision.canonical_bytes)

    @proves('MYC-14.14', 'MYC-14.15', 'MYC-16.8', kind='store')
    def test_unchanged_preparation_sixty_seconds_later_preserves_request_bundle_and_cache(self):
        with self.base.connect() as connection:
            first = self.prepare(connection)
            writer = ClassificationStore(connection)
            self.assertTrue(writer.apply(self.base.settings, first, judgement='needs_review', at=AT)['applied'])
            cached = writer.reuse(self.base.settings, first, at=AT)
            before = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (first.drift_id,)).fetchone()[0]
            snapshot_count = connection.execute("SELECT count(*) FROM public.mycel_snapshots WHERE repository='downstream'").fetchone()[0]
            later = (NOW + timedelta(seconds=60)).isoformat()
            repeated = writer.prepare(self.base.settings, first.drift_id, first.reason_id, at=later)
            self.assertIsNone(repeated.fault, repeated.as_dict())
            self.assertEqual((repeated.input_hash, repeated.recorded_at, repeated.guards_bytes),
                             (first.input_hash, first.recorded_at, first.guards_bytes))
            self.assertEqual(repeated.bundle.evidence_hash, first.bundle.evidence_hash)
            self.assertEqual(repeated.eligible_at, first.eligible_at)
            self.assertEqual(writer.reuse(self.base.settings, repeated, at=later), cached)
            self.assertTrue(self.stage_check(connection, first, at=later)['allowed'])
            after = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (first.drift_id,)).fetchone()[0]
            self.assertEqual(after['classificationRequests'], before['classificationRequests'])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_snapshots WHERE repository='downstream'")
                             .fetchone()[0], snapshot_count)


if __name__ == '__main__':
    unittest.main()
