"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_classification_store as _support
from test_classification_store import (
    AT,
    ClassificationEvidenceStoreTests,
    ClassificationStore,
    ClassificationStoreFixture,
    DriftStore,
    EvidenceStore,
    Jsonb,
    MycelError,
    NOW,
    Path,
    datetime,
    fixtures,
    json,
    load_settings,
    operation_guard,
    os,
    patch,
    removal_guard,
    sha256,
    timedelta,
    timezone,
    unittest,
)


class ClassificationEvidenceStoreTests(_support.ClassificationEvidenceStoreTests):
# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_newest_live_file_quiet_period_is_persisted_and_repeated_reads_do_not_restart
    def test_newest_live_file_quiet_period_is_persisted_and_repeated_reads_do_not_restart(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.fixture.change(connection, 1)
            self.old_files()
            stamp = (NOW - timedelta(seconds=20)).timestamp()
            os.utime(self.fixture.extra[0], (stamp, stamp))
            drift = self.fixture.one(connection)
            source = self.fixture.reason(drift)
            prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'], source['id'], at=AT)
            self.assertEqual(prepared.status, 'pending_debounce')
            self.assertEqual(prepared.eligible_at, (NOW + timedelta(seconds=280)).isoformat(timespec='microseconds'))
            self.assertFalse(self.stage_check(connection, prepared)['allowed'])
            later = (NOW + timedelta(seconds=100)).isoformat()
            again = ClassificationStore(connection).prepare(self.base.settings, drift['id'], source['id'], at=later)
            self.assertEqual(again.eligible_at, prepared.eligible_at)
            self.assertEqual(again.input_hash, prepared.input_hash)
            self.assertEqual(again.status, 'pending_debounce')
            self.assertTrue(self.stage_check(connection, again, at=(NOW + timedelta(seconds=280)).isoformat())['allowed'])
            persisted = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (drift['id'],)).fetchone()[0]
            self.assertEqual(persisted['classificationObservations']['fixture:@artifact/source2.md']['changedAt'],
                             (NOW - timedelta(seconds=20)).isoformat(timespec='microseconds'))
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_newest_live_file_quiet_period_is_persisted_and_repeated_reads_do_not_restart

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_whole_file_edit_outside_selection_changes_only_guards_and_preserved_time_uses_observation
    def test_whole_file_edit_outside_selection_changes_only_guards_and_preserved_time_uses_observation(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            stamp = self.fixture.fixture.source.stat().st_mtime_ns
            self.fixture.fixture.source.write_bytes(self.fixture.fixture.source.read_bytes() + b'# Elsewhere\nUnrelated edit.\n')
            os.utime(self.fixture.fixture.source, ns=(stamp, stamp))
            self.fixture.fixture.publish(connection)
            self.fixture.sync(connection)
            drift = self.fixture.one(connection)
            later = NOW + timedelta(seconds=400)
            changed = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
                self.fixture.reason(drift)['id'], at=later.isoformat())
            self.assertIsNone(changed.fault, changed.as_dict())
            self.assertEqual(changed.input_hash, prepared.input_hash)
            self.assertNotEqual(changed.guards_bytes, prepared.guards_bytes)
            self.assertEqual(changed.status, 'pending_debounce')
            self.assertEqual(changed.eligible_at, (later + timedelta(seconds=300)).isoformat(timespec='microseconds'))
            observations = json.loads(changed.observations_bytes)
            observation = observations['fixture:@artifact/source.md']
            self.assertEqual(observation['faults'], ['timestamp_untrusted'])
            self.assertEqual(observation['firstObservedAt'], later.isoformat(timespec='microseconds'))
            self.assertFalse(self.stage_check(connection, prepared, at=later.isoformat())['allowed'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_whole_file_edit_outside_selection_changes_only_guards_and_preserved_time_uses_observation

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_future_timestamp_falls_back_to_first_read_and_cannot_delay_forever
    def test_future_timestamp_falls_back_to_first_read_and_cannot_delay_forever(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.fixture.change(connection, 1)
            self.old_files()
            stamp = (NOW + timedelta(days=100)).timestamp()
            os.utime(self.fixture.fixture.source, (stamp, stamp))
            drift = self.fixture.one(connection)
            prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
                self.fixture.reason(drift)['id'], at=AT)
            self.assertEqual(prepared.status, 'pending_debounce')
            self.assertEqual(prepared.eligible_at, (NOW + timedelta(seconds=300)).isoformat(timespec='microseconds'))
            self.assertEqual(json.loads(prepared.observations_bytes)['fixture:@artifact/source.md']['faults'],
                             ['timestamp_untrusted'])
            self.assertTrue(self.stage_check(connection, prepared, at=(NOW + timedelta(seconds=300)).isoformat())['allowed'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_future_timestamp_falls_back_to_first_read_and_cannot_delay_forever

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_deleted_source_uses_first_tombstone_and_complete_retained_before_text
    def test_deleted_source_uses_first_tombstone_and_complete_retained_before_text(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.fixture.fixture.source.unlink()
            self.base.commit()
            self.fixture.fixture.publish(connection)
            dependency = self.fixture.reason(self.fixture.one(connection), kind='source_removed')['dependency']
            state = connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s', (dependency,)).fetchone()[0]
            state['sourceAbsence']['observedAt'] = (NOW + timedelta(seconds=1)).isoformat()
            connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s', (Jsonb(state), dependency))
            self.fixture.sync(connection)
            drift = self.fixture.one(connection)
            tombstone = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
                self.fixture.reason(drift, kind='source_removed')['id'], at=(NOW + timedelta(seconds=1)).isoformat())
            self.assertIsNone(tombstone.fault, tombstone.as_dict())
            self.assertEqual(tombstone.decision.payload['current']['state'], 'deleted')
            self.assertEqual(tombstone.decision.payload['current']['members'], ())
            self.assertIn('Original governing source.', tombstone.decision.payload['before'][0]['text'])
            self.assertEqual(tombstone.status, 'pending_debounce')
            self.assertEqual(tombstone.eligible_at, (NOW + timedelta(seconds=301)).isoformat(timespec='microseconds'))
            self.assertEqual(json.loads(tombstone.observations_bytes)['fixture:@artifact/source.md']['kind'], 'deleted')
            self.assertTrue(self.stage_check(connection, tombstone, at=(NOW + timedelta(seconds=301)).isoformat())['allowed'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_deleted_source_uses_first_tombstone_and_complete_retained_before_text

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_complete_pinned_current_dependant_governors_and_canonical_bytes_are_owned
    def test_complete_pinned_current_dependant_governors_and_canonical_bytes_are_owned(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            self.assertEqual(prepared.status, 'pending_jev')
            decision = prepared.decision.as_dict()
            self.assertIn('Original governing source.', decision['before'][0]['text'])
            self.assertIn('Changed governing source.', decision['current']['members'][0]['text'])
            self.assertIn('Unchanged dependant.', decision['dependant']['text'])
            self.assertEqual(len(decision['context']), 2)
            self.assertEqual([item['current']['place']['address'] for item in decision['context']],
                             list(self.fixture.addresses[1:]))
            self.assertTrue(all(item['role'] == 'governor' and item['freshness'] == 'fresh'
                                for item in decision['context']))
            self.assertEqual(sha256(prepared.decision.canonical_bytes).hexdigest(), prepared.input_hash)
            stored = connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                ('downstream', prepared.input_hash)).fetchone()
            self.assertEqual(bytes(stored[0]), prepared.decision.canonical_bytes)
            row = connection.execute('SELECT evidence_owner,state FROM public.mycel_drifts WHERE id=%s',
                (prepared.drift_id,)).fetchone()
            self.assertEqual(row[1]['classificationRequests'][prepared.input_hash]['payloadSnapshot'],
                             'snapshot:' + prepared.input_hash)
            for evidence in prepared.bundle.payload['evidence']:
                self.assertTrue(connection.execute('SELECT 1 FROM public.mycel_evidence_references '
                    'WHERE owner=%s AND snapshot_hash=%s', (row[0], evidence['hash'])).fetchone())
            self.assertNotIn('fileHash', decision['baseline']['dependant'])
            self.assertNotIn('span', decision['baseline']['dependant'])
            self.assertTrue(self.stage_check(connection, prepared)['allowed'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_complete_pinned_current_dependant_governors_and_canonical_bytes_are_owned

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_direct_document_ancestors_are_complete_and_address_ordered
    def test_direct_document_ancestors_are_complete_and_address_ordered(self):
        self.fixture.fixture.answer.write_bytes(b'# Parent\nComplete parent claim.\n## Child\nComplete child claim.\n'
            b'### Answer\n<!-- sources:\nfixture:@artifact/source.md#Source\n-->\nUnchanged dependant.\n')
        self.fixture.ref = 'downstream:@artifact/answer.md#Parent > Child > Answer'
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            context = prepared.decision.as_dict()['context']
            self.assertEqual([item['evidence']['text'] for item in context],
                ['# Parent\nComplete parent claim.\n', '## Child\nComplete child claim.\n'])
            self.assertEqual([item['role'] for item in context], ['ancestor', 'ancestor'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_direct_document_ancestors_are_complete_and_address_ordered

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_missing_governor_blocks_both_stages_instead_of_silent_context_omission
    def test_missing_governor_blocks_both_stages_instead_of_silent_context_omission(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.fixture.change(connection, 1)
            self.old_files()
            dependency = next(row[0] for row in self.fixture.fixture.dependencies(connection)
                if row[4] == self.fixture.addresses[1])
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
                (dependency,)).fetchone()[0]
            connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s', (owner,))
            drift = self.fixture.one(connection)
            prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
                self.fixture.reason(drift)['id'], at=AT)
            self.assertEqual(prepared.fault, 'context_missing')
            self.assertIsNone(prepared.decision)
            for stage in ('jev', 'review'):
                self.assertFalse(self.stage_check(connection, prepared, stage)['allowed'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_missing_governor_blocks_both_stages_instead_of_silent_context_omission

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_corrupt_pinned_snapshot_and_request_metadata_never_pass_stage_guards
    def test_corrupt_pinned_snapshot_and_request_metadata_never_pass_stage_guards(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                (Jsonb({'schema': 9}), 'downstream', prepared.input_hash))
            self.assertEqual(self.stage_check(connection, prepared)['reason'], 'snapshot_corrupt')
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_corrupt_pinned_snapshot_and_request_metadata_never_pass_stage_guards

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_missing_retained_current_text_and_bundle_never_start_a_stage
    def test_missing_retained_current_text_and_bundle_never_start_a_stage(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            current_hash = prepared.decision.payload['current']['members'][0]['snapshot']['hash']
            owner = connection.execute('SELECT evidence_owner FROM public.mycel_drifts WHERE id=%s',
                (prepared.drift_id,)).fetchone()[0]
            connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND snapshot_hash=%s',
                (owner, current_hash))
            self.assertEqual(self.stage_check(connection, prepared)['reason'], 'baseline_missing')
            baseline = prepared.bundle.payload['baseline']
            capture = EvidenceStore(connection).read_baseline('downstream', baseline)
            source_hash = capture.manifest.payload['members'][0]['evidence']['hash']
            connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                (Jsonb({'schema': 9}), 'downstream', source_hash))
            self.assertEqual(self.stage_check(connection, prepared)['reason'], 'snapshot_corrupt')
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_missing_retained_current_text_and_bundle_never_start_a_stage

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_support_application_preserves_pins_stale_and_confirmations_and_guarded_cache_reuse
    def test_support_application_preserves_pins_stale_and_confirmations_and_guarded_cache_reuse(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            immutable, stale = self.fixture.immutable(connection), self.fixture.stale(connection)
            applied = ClassificationStore(connection).apply(self.base.settings, prepared,
                judgement='needs_review', evidence={'stage': 'fixture'}, at=AT)
            self.assertTrue(applied['applied'], applied)
            cached = ClassificationStore(connection).reuse(self.base.settings, prepared, at=AT)
            self.assertEqual(cached['judgement'], 'needs_review')
            self.assertEqual(cached['inputHash'], prepared.input_hash)
            repeated = ClassificationStore(connection).prepare(self.base.settings,
                prepared.drift_id, prepared.reason_id, at=AT)
            self.assertEqual(repeated.input_hash, prepared.input_hash)
            self.assertEqual(ClassificationStore(connection).reuse(self.base.settings, repeated, at=AT), cached)
            supported = ClassificationStore(connection).apply(self.base.settings, prepared,
                judgement='still_supported', at=AT)
            self.assertTrue(supported['applied'], supported)
            self.assertEqual(self.fixture.immutable(connection), immutable)
            self.assertEqual([(row[:3], {key:value for key,value in row[3].items() if key != 'classification'})
                for row in self.fixture.stale(connection)],
                [(row[:3], {key:value for key,value in row[3].items() if key != 'classification'}) for row in stale])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_support_application_preserves_pins_stale_and_confirmations_and_guarded_cache_reuse

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_file_edit_after_preparation_makes_both_stages_and_result_obsolete
    def test_context_file_edit_after_preparation_makes_both_stages_and_result_obsolete(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            original = self.fixture.immutable(connection)
            self.fixture.extra[0].write_bytes(b'# Source2\nNew required governor.\n')
            for stage in ('jev', 'review'):
                self.assertFalse(self.stage_check(connection, prepared, stage)['allowed'])
            result = ClassificationStore(connection).apply(self.base.settings, prepared,
                judgement='still_supported', at=AT)
            self.assertFalse(result['applied'])
            self.assertTrue(result['obsolete'])
            self.assertTrue(self.fixture.reason(result['drift'])['active'])
            self.assertTrue(result['drift']['history'][-1]['obsolete'])
            self.assertEqual(self.fixture.immutable(connection), original)
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_file_edit_after_preparation_makes_both_stages_and_result_obsolete

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_after_tentative_result_is_retained_only_as_obsolete_attempt
    def test_context_race_after_tentative_result_is_retained_only_as_obsolete_attempt(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            original = DriftStore._write
            calls = []
            def write(store, *args):
                original(store, *args)
                if not calls:
                    calls.append(True)
                    self.fixture.extra[0].write_bytes(b'# Source2\nContext edited during application.\n')
            with patch.object(DriftStore, '_write', write):
                result = ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='still_supported', at=AT)
            self.assertFalse(result['applied'])
            self.assertTrue(result['obsolete'])
            self.assertTrue(self.fixture.reason(result['drift'])['active'])
            self.assertTrue(result['drift']['history'][-1]['obsolete'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_after_tentative_result_is_retained_only_as_obsolete_attempt

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_during_final_annotation_rolls_back_every_store_effect
    def test_context_race_during_final_annotation_rolls_back_every_store_effect(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            before = self.fixture.state(connection)
            original = DriftStore._publish_classification
            def write(store, *args, **kwargs):
                original(store, *args, **kwargs)
                self.fixture.extra[0].write_bytes(b'# Source2\nContext edited during publication.\n')
            with patch.object(DriftStore, '_publish_classification', write), self.assertRaises(MycelError):
                ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='still_supported', at=AT)
            self.assertEqual(self.fixture.state(connection), before)
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_during_final_annotation_rolls_back_every_store_effect

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound
    def test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound(self):
        executable = self.write_reviewer()
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            guards = json.loads(prepared.guards_bytes)
            identity = guards['command']
            self.assertEqual(identity['argv'], [str(executable.resolve()), '--literal', '$HOME/*.json'])
            self.assertEqual(identity['adapterRevision'], 'fixture-adapter-v1')
            self.assertEqual(identity['executableSha256'], sha256(executable.read_bytes()).hexdigest())
            self.assertEqual((identity['protocol'], identity['instructionVersion'], identity['environmentVersion']),
                             (1, 'mycel-review-v1', 'mycel-review-env-v1'))
            self.assertTrue(self.stage_check(connection, prepared, 'review')['allowed'])
            executable.write_bytes(b'#!/bin/sh\nexit 1\n')
            for stage in ('jev', 'review', 'application', 'reuse'):
                self.assertFalse(self.stage_check(connection, prepared, stage)['allowed'])
            result = ClassificationStore(connection).apply(self.base.settings, prepared,
                judgement='still_supported', at=AT)
            self.assertTrue(result['obsolete'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_unavailable_reviewer_has_null_digest_and_jev_remains_independently_eligible
    def test_unavailable_reviewer_has_null_digest_and_jev_remains_independently_eligible(self):
        executable = self.write_reviewer()
        executable.unlink()
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            self.assertIsNone(json.loads(prepared.guards_bytes)['command']['executableSha256'])
            self.assertTrue(self.stage_check(connection, prepared)['allowed'])
            self.assertEqual(self.stage_check(connection, prepared, 'review')['reason'], 'review_command_unavailable')
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_unavailable_reviewer_has_null_digest_and_jev_remains_independently_eligible

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_frozen_settings_enablement_model_revision_and_transport_changes_refuse_old_results
    def test_frozen_settings_enablement_model_revision_and_transport_changes_refuse_old_results(self):
        self.write_reviewer()
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            original = self.base.config.read_text()
            changes = [original.replace('fixture-adapter-v1', 'fixture-adapter-v2'),
                       original.replace('[drifts]', '[drifts]\nmodel="jev-1.14.0"'),
                       original.replace('[drifts]', '[drifts]\nreview_timeout_seconds=30'),
                       original.replace('[repos.downstream]\nenabled=true', '[repos.downstream]\nenabled=false')]
            for changed in changes:
                self.base.config.write_text(changed)
                self.assertFalse(self.stage_check(connection, prepared)['allowed'])
                result = ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='still_supported', at=AT)
                self.assertTrue(result['obsolete'])
                self.assertFalse(result['applied'])
                self.base.config.write_text(original)
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_frozen_settings_enablement_model_revision_and_transport_changes_refuse_old_results

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_stage_lease_protects_every_request_blob_and_holds_no_pass_lock_during_io
    def test_stage_lease_protects_every_request_blob_and_holds_no_pass_lock_during_io(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            with ClassificationStore(connection).stage(self.base.settings, prepared, stage='jev', at=AT) as checked:
                self.assertTrue(checked['allowed'], checked)
                lease = connection.execute("SELECT id,invocation FROM public.mycel_evidence_owners "
                    "WHERE repository='downstream' AND kind='classification_lease'").fetchone()
                self.assertIsNotNone(lease)
                self.assertTrue(connection.execute('SELECT 1 FROM public.mycel_evidence_references '
                    'WHERE owner=%s AND snapshot_hash=%s', (lease[0], prepared.input_hash)).fetchone())
                with self.base.connect() as other:
                    with operation_guard(other, 'downstream', 'pass'):
                        pass
                    with self.assertRaises(MycelError), removal_guard(other, 'downstream'):
                        pass
            self.assertIsNone(connection.execute("SELECT id FROM public.mycel_evidence_owners "
                "WHERE kind='classification_lease'").fetchone())
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_stage_lease_protects_every_request_blob_and_holds_no_pass_lock_during_io
