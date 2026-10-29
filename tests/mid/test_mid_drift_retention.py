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

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_public_writers_deduplicate_returning_inputs_and_remove_collected_metadata
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Public writers deduplicate returning inputs and remove collected metadata.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_writers_deduplicate_returning_inputs_and_remove_collected_metadata(self):
#         with self.base.connect() as connection:
#             prepared = self.prepare(connection)
#             original = self.fixture.fixture.source.read_bytes()
#             ClassificationStore(connection).apply(self.base.settings, prepared, judgement='still_supported', at=AT)
#             hashes = [prepared.input_hash]
#             for number, raw in enumerate((b'# Source\nChanged B.\n', original, b'# Source\nChanged C.\n'), 1):
#                 self.fixture.fixture.source.write_bytes(raw)
#                 self.old_files()
#                 self.fixture.fixture.publish(connection)
#                 DriftStore(connection).reconcile(self.base.settings, 'downstream',
#                     at=(NOW + timedelta(days=number)).isoformat())
#                 drift = self.fixture.one(connection)
#                 ready = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
#                     self.fixture.reason(drift)['id'], at=(NOW + timedelta(days=number)).isoformat())
#                 hashes.append(ready.input_hash)
#             self.assertEqual(hashes[0], hashes[2])
#             archived = connection.execute("SELECT id,state FROM public.mycel_drifts WHERE dependant_version IS NULL "
#                 "AND state->'classificationRequests' ? %s", (prepared.input_hash,)).fetchall()
#             self.assertEqual(len(archived), 1)
#             self.assertEqual(archived[0][1]['closureProvenance']['source']['because'], 'still_supported')
#             self.assertIsNotNone(archived[0][1]['closureProvenance']['drift'])
#             self.fixture.fixture.source.write_bytes(b'# Source\nChanged D.\n')
#             self.old_files()
#             self.fixture.fixture.publish(connection)
#             with patch('mycel._drift_retention.HISTORY_LIMIT', 2):
#                 DriftStore(connection).reconcile(self.base.settings, 'downstream',
#                     at=(NOW + timedelta(days=4)).isoformat())
#             survivors = {str(row[0]) for row in connection.execute('SELECT id FROM public.mycel_drifts '
#                 'WHERE dependant_version IS NULL').fetchall()}
#             self.assertEqual(len(survivors), 2)
#             current = self.row(connection, prepared.drift_id)[5]
#             self.assertTrue(all(item.get('bundle') in survivors for item in current['history']
#                                 if item.get('bundle')))
#             self.assertFalse(any(item.get('inputHash') == hashes[1] for item in current['history']))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_restored_reason_reappearance_reuses_its_complete_owning_archive
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Restored reason reappearance reuses its complete owning archive.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_restored_reason_reappearance_reuses_its_complete_owning_archive(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             changed = self.fixture.fixture.source.read_bytes()
#             self.fixture.change(connection, 2)
#             self.old_files()
#             drift = self.fixture.one(connection)
#             prepared = ClassificationStore(connection).prepare(self.base.settings, drift['id'],
#                 self.fixture.reason(drift)['id'], at=AT)
#             self.fixture.fixture.source.write_bytes(self.fixture.originals[self.fixture.fixture.source])
#             self.fixture.fixture.publish(connection)
#             self.fixture.sync(connection)
#             ended = self.fixture.reason(self.fixture.one(connection))
#             self.assertEqual(ended['closed']['because'], 'source_restored')
#             owner_bundle = ended['historyBundle']
#             archived = self.row(connection, owner_bundle)
#             self.assertIn(prepared.input_hash, archived[5]['classificationRequests'])
#             payload_refs = connection.execute('SELECT snapshot_hash FROM public.mycel_evidence_references '
#                 'WHERE owner=%s AND snapshot_hash=%s', (archived[6], prepared.input_hash)).fetchall()
#             self.assertEqual(payload_refs, [(prepared.input_hash,)])
#             self.fixture.fixture.source.write_bytes(changed)
#             self.fixture.fixture.publish(connection)
#             self.fixture.sync(connection)
#             active = self.fixture.reason(self.fixture.one(connection))
#             self.assertTrue(active['active'])
#             retained = connection.execute("SELECT id FROM public.mycel_drifts WHERE dependant_version IS NULL "
#                 "AND state->'classificationRequests' ? %s", (prepared.input_hash,)).fetchall()
#             self.assertEqual(retained, [(UUID(owner_bundle),)])
#             self.assertIsNotNone(EvidenceStore(connection).read_snapshot('downstream',
#                 snapshot(prepared.decision.canonical_bytes).evidence))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_located_ended_work_without_live_suppression_obeys_closed_history_bound
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Located ended work without live suppression obeys closed history bound.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_located_ended_work_without_live_suppression_obeys_closed_history_bound(self):
#         with self.base.connect() as connection:
#             prepared = self.prepare(connection)
#             baseline_id = self.fixture.fixture.dependencies(connection)[0][7]
#             baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
#             self.fixture.fixture.source.write_bytes(self.fixture.originals[self.fixture.fixture.source])
#             self.fixture.fixture.publish(connection)
#             self.fixture.sync(connection)
#             ended = self.row(connection, prepared.drift_id)
#             self.assertIsNotNone(ended[4])
#             self.assertEqual(ended[5]['closed']['because'], 'source_restored')
#             self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_locations '
#                 'WHERE chunk_version=%s', (ended[2],)).fetchone())
#             with self.guarded(connection), atomic_transaction(connection):
#                 self.seed_history(connection, prepared, 3, at=(NOW + timedelta(days=1)).isoformat())
#                 with patch('mycel._drift_retention.HISTORY_LIMIT', 1):
#                     result = DriftHistoryStore(connection).prune_in_transaction('downstream')
#             self.assertEqual(result['records'], 3)
#             self.assertIsNone(self.row(connection, prepared.drift_id))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_drifts WHERE closed_at IS NOT NULL').fetchone(), (1,))
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_owner_withdrawal_retires_supported_pair_and_bounds_open_work_history
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Owner withdrawal retires supported pair and bounds open work history.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_owner_withdrawal_retires_supported_pair_and_bounds_open_work_history(self):
#         paths = [self.base.artifact / ('asserted-' + name + '.md') for name in ('a', 'b')]
#         refs = ['fixture:@artifact/' + path.name + '#Asserted' for path in paths]
#         for path in paths:
#             path.write_bytes(b'# Asserted\nOriginal assertion source.\n')
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             for ref in refs:
#                 DeriveStore(connection).apply(self.base.settings, self.fixture.ref, ref,
#                     captured_at=AT, settings_home=self.base.base)
#             for path in paths:
#                 path.write_bytes(b'# Asserted\nChanged assertion source.\n')
#             self.fixture.fixture.publish(connection)
#             self.old_files()
#             prepared = []
#             for number, ref in enumerate(refs):
#                 drift = self.fixture.one(connection)
#                 source = next(source for source in drift['sources']
#                               if source['source']['address'] == ref and source['link'] == 'asserted')
#                 observed_at = NOW + timedelta(minutes=20 * number)
#                 ready_at = observed_at + timedelta(minutes=10)
#                 current = ClassificationStore(connection).prepare(self.base.settings, drift['id'], source['id'],
#                     at=observed_at.isoformat())
#                 # A guarded re-observation resolves any preserved-mtime quiet period.
#                 current = ClassificationStore(connection).prepare(self.base.settings, drift['id'], source['id'],
#                     at=ready_at.isoformat())
#                 applied = ClassificationStore(connection).apply(self.base.settings, current,
#                     judgement='still_supported', at=ready_at.isoformat())
#                 self.assertTrue(applied['applied'], applied)
#                 prepared.append(current)
#             version = self.row(connection, prepared[0].drift_id)[2]
#             removed = DeriveStore(connection).apply(self.base.settings, self.fixture.ref, refs[0], remove=True,
#                 captured_at=(NOW + timedelta(minutes=41)).isoformat(), settings_home=self.base.base)
#             self.assertTrue(removed['changed'])
#             row = self.row(connection, prepared[0].drift_id)
#             self.assertEqual(row[2], version)
#             self.assertIsNone(row[4])
#             retired = next(source for source in row[5]['sources'] if source['id'] == prepared[0].reason_id)
#             desired = next(source for source in row[5]['sources'] if source['id'] == prepared[1].reason_id)
#             self.assertEqual(retired['closed']['because'], 'ref_removed')
#             archived = self.row(connection, retired['historyBundle'])
#             self.assertEqual(archived[5]['closureProvenance']['source']['because'], 'still_supported')
#             self.assertIn(prepared[0].input_hash, archived[5]['classificationRequests'])
#             self.assertNotIn(prepared[0].input_hash, row[5]['classificationRequests'])
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_evidence_references '
#                 'WHERE owner=%s AND snapshot_hash=%s', (row[6], prepared[0].input_hash)).fetchone())
#             self.assertFalse(desired['active'])
#             self.assertEqual(desired['closed']['because'], 'still_supported')
#             self.assertNotIn('historyBundle', desired)
#             self.assertIn(prepared[1].input_hash, row[5]['classificationRequests'])
#             main = self.fixture.reason(self.fixture.one(connection))
#             current = ClassificationStore(connection).prepare(self.base.settings, str(row[0]), main['id'],
#                 at=(NOW + timedelta(minutes=42)).isoformat())
#             with self.guarded(connection), atomic_transaction(connection):
#                 self.seed_history(connection, current, 3, at=(NOW + timedelta(days=1)).isoformat())
#                 with patch('mycel._drift_retention.HISTORY_LIMIT', 1):
#                     DriftHistoryStore(connection).prune_in_transaction('downstream')
#             retained = self.row(connection, prepared[0].drift_id)[5]
#             self.assertFalse(any(source['id'] == prepared[0].reason_id for source in retained['sources']))
#             self.assertFalse(any(item.get('inputHash') == prepared[0].input_hash for item in retained['history']))
#             self.assertNotIn(prepared[0].input_hash, retained['classificationRequests'])
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
#                                                 ('downstream', prepared[0].input_hash)).fetchone())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_current_closed_suppression_report_and_activity_pruning_preserve_evidence
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Current closed suppression report and activity pruning preserve evidence.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_current_closed_suppression_report_and_activity_pruning_preserve_evidence(self):
#         with self.base.connect() as connection:
#             prepared = self.prepare(connection)
#             with MutationActivity(connection, build=1).session() as audit:
#                 def recorded(result):
#                     audit.record_in_transaction('downstream', 'classify', AppliedMutation(True,
#                         {'classified': 1}, classifications=(ClassificationReference(
#                             'snapshot:' + prepared.input_hash, parse_source_address(self.fixture.ref), 'still_supported'),)))
#                 ClassificationStore(connection).apply(self.base.settings, prepared,
#                     judgement='still_supported', at=AT, _audit=recorded)
#                 audit.finish('done')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity_classifications').fetchone(), (1,))
#             with self.guarded(connection), atomic_transaction(connection):
#                 self.seed_history(connection, prepared, 1000, at=(NOW + timedelta(days=1)).isoformat())
#                 result = DriftHistoryStore(connection).prune_in_transaction('downstream')
#             self.assertEqual(result['records'], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_drifts WHERE closed_at IS NOT NULL').fetchone(), (1001,))
#             before = self.fixture.state(connection)
#             DriftStore(connection).list('downstream', closed=True, all_versions=True)
#             DriftStore(connection).list('downstream')
#             self.assertEqual(self.fixture.state(connection), before)
#             with atomic_transaction(connection):
#                 connection.execute('DELETE FROM public.mycel_activity')
#             retained = self.row(connection, prepared.drift_id)
#             self.assertEqual(retained[5]['sources'][0]['classification']['judgement'], 'still_supported')
#             self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
#                                                    ('downstream', prepared.input_hash)).fetchone())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_archive_prune_release_and_collection_are_guarded_and_roll_back_together
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Archive prune release and collection are guarded and roll back together.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_archive_prune_release_and_collection_are_guarded_and_roll_back_together(self):
#         with self.base.connect() as connection:
#             prepared = self.prepare(connection)
#             row = self.row(connection, prepared.drift_id)
#             store = DriftHistoryStore(connection)
#             before = self.fixture.state(connection)
#             with self.assertRaises(MycelError), atomic_transaction(connection):
#                 store.prune_in_transaction('downstream')
#             with self.assertRaises(RuntimeError), self.guarded(connection), atomic_transaction(connection):
#                 self.seed_history(connection, prepared, 1001)
#                 self.assertEqual(store.prune_in_transaction('downstream')['records'], 1)
#                 raise RuntimeError('Fixture transaction failed after evidence collection.')
#             self.assertEqual(self.fixture.state(connection), before)
#             self.assertEqual(self.row(connection, row[0]), row)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_drift_retention.py::DriftRetentionStoreTests.test_repository_removal_requires_ended_mutations_and_preserves_foreign_dependant_bytes
# Reason: Narrower case removed from this family after retaining test_1001_closed_bundles_use_closure_time_full_id_and_keep_live_owners, test_live_stage_protects_old_bundle_late_result_and_collects_after_lease_ends. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Repository removal requires ended mutations and preserves foreign dependant bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_drift_retention.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repository_removal_requires_ended_mutations_and_preserves_foreign_dependant_bytes(self):
#         with self.base.connect() as connection, self.base.connect() as peer:
#             prepared = self.prepare(connection)
#             baseline_id = self.fixture.fixture.dependencies(connection)[0][7]
#             retained = EvidenceStore(connection).read_baseline('downstream', baseline_id)
#             before = self.fixture.state(connection)
#             with operation_guard(peer, 'fixture', 'pass'):
#                 with self.assertRaises(MycelError) as failure:
#                     with removal_guard(connection, 'fixture'):
#                         self.fail('An active mutation must prevent removal.')
#                 self.assertEqual(failure.exception.code.value, 'busy')
#             with invocation_guard(peer) as invocation:
#                 lease = uuid4()
#                 with operation_guard(peer, 'fixture', 'pass'), atomic_transaction(peer):
#                     peer.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
#                                  (lease, 'fixture', 'classification_lease', str(lease), invocation.id))
#                 with removal_guard(connection, 'fixture'), self.guarded(connection):
#                     with self.assertRaises(MycelError) as failure, atomic_transaction(connection):
#                         CollectionStore(connection).remove_repository_in_transaction('fixture',
#                             guarded_repositories=('downstream', 'fixture'))
#                 self.assertEqual(failure.exception.code.value, 'busy')
#             with removal_guard(connection, 'fixture'), self.guarded(connection), atomic_transaction(connection):
#                 result = CollectionStore(connection).remove_repository_in_transaction('fixture',
#                     guarded_repositories=('downstream', 'fixture'))
#             self.assertEqual(result['repositories'], 1)
#             self.assertEqual(result['affectedRepositories'], ('downstream',))
#             self.assertIsNone(connection.execute("SELECT 1 FROM public.mycel_repository_state WHERE repository='fixture'").fetchone())
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), retained)
#             self.assertIsNotNone(self.row(connection, prepared.drift_id))
#             with removal_guard(connection, 'downstream'), operation_guard(connection, 'downstream', 'pass'), atomic_transaction(connection):
#                 result = CollectionStore(connection).remove_repository_in_transaction('downstream',
#                     guarded_repositories=('downstream',))
#             self.assertEqual(result['repositories'], 1)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
