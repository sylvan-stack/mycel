"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_collection as _support
from test_collection import (CollectionStore ,ExitStack ,LocatedCaptureStore ,MutationActivity ,MycelError ,SourceResolver ,atomic_transaction ,capture_repository ,evidence ,json ,load_settings ,operation_guard ,sha256 ,uuid4)


class CollectionStoreTests(_support.CollectionStoreTests):


# TEST-TIER-BEGIN tests/test_collection.py::CollectionStoreTests.test_collection_and_owner_release_roll_back_with_complete_publication_on_failure
    def test_collection_and_owner_release_roll_back_with_complete_publication_on_failure(self):
        self.docs()
        with self.connect() as connection:
            self.apply(connection)
            self.pin(connection)
            before = self.state(connection)
            (self.artifact / 'answer.md').unlink()
            manifest = capture_repository(self.settings, 'fixture')
            def failed(current, result):
                collected = CollectionStore(current).collect_in_transaction(self.settings, manifest)
                self.assertEqual((collected.versions, collected.owners), (1, 1))
                raise RuntimeError('Public fixture audit failed after collection')
            with self.assertRaises(RuntimeError):
                LocatedCaptureStore(connection).apply(self.settings, manifest, batch_handoff=failed)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_collection.py::CollectionStoreTests.test_collection_and_owner_release_roll_back_with_complete_publication_on_failure

# TEST-TIER-BEGIN tests/test_collection.py::CollectionStoreTests.test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename
    def test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename(self):
        (self.code / 'answer.py').write_bytes(b'# prefix\ndef old(x):\n    return x\n\ndef other():\n    return 1\n')
        (self.artifact / 'source.md').write_bytes(b'# Source\nOriginal source.\n')
        with self.connect() as connection:
            self.apply(connection)
            dependency, baseline, owner, observed = self.pin(connection, dependant='fixture:@code/answer.py#old')
            original_pin = evidence.EvidenceStore(connection).read_baseline('fixture', baseline).manifest.payload['pinnedHash']
            original_hash = observed.dependant_file.snapshot_hash
            (self.code / 'answer.py').write_bytes(b'# prefix\ndef old(x):\n    return x\n\ndef other():\n    return 2\n')
            self.apply(connection)
            self.assertIsNotNone(connection.execute('SELECT id FROM public.mycel_file_versions WHERE snapshot_hash=%s',
                (original_hash,)).fetchone())
            (self.code / 'answer.py').write_bytes(b'# prefix\ndef new(x):\n    return x\n\ndef other():\n    return 2\n')
            manifest = capture_repository(self.settings, 'fixture')
            inherited = []
            def inherit(current, result):
                catalog = SourceResolver.from_transaction(current, self.settings)
                selected = catalog.resolve('fixture:@code/answer.py#new', purpose='endpoint').selection
                inputs = evidence.InheritanceInputs(self.settings, selected.members[0], selected.file,
                    evidence.CaptureLocation('disk'), catalog.resolve('fixture:@artifact/source.md#Source'), catalog)
                with evidence.checked_transaction_input_guard(current, inputs, lambda: inputs) as token:
                    inherited.append(evidence.EvidenceStore(current).inherit_in_transaction(token,
                        previous_dependency=dependency, dependency_id=uuid4(), authorization='recognized_rename'))
                CollectionStore(current).collect_in_transaction(self.settings, manifest)
            LocatedCaptureStore(connection).apply(self.settings, manifest, batch_handoff=inherit)
            retained = evidence.EvidenceStore(connection).read_baseline('fixture', inherited[0])
            self.assertEqual(retained.manifest.payload['pinnedHash'], original_pin)
            self.assertEqual(retained.manifest.payload['dependant']['comparison']['kind'], 'code_text')
# TEST-TIER-END tests/test_collection.py::CollectionStoreTests.test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename

# TEST-TIER-BEGIN tests/test_collection.py::CollectionStoreTests.test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy
    def test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy(self):
        self.docs()
        downstream = self.helper.base / 'downstream'
        downstream.mkdir()
        (downstream / 'answer.md').write_bytes(b'# Answer\nDownstream answer.\n')
        self.helper.config.write_text('[store]\naddress=' + json.dumps(self.store_fixture.backend.address(self.store_fixture.database))
            + '\n[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(self.code))
            + '\nartifact_root=' + json.dumps(str(self.artifact)) + '\n[repos.downstream]\nenabled=true\nartifact_root='
            + json.dumps(str(downstream)) + '\n')
        self.settings = load_settings(path=self.helper.config, home=self.helper.base)
        with self.connect() as connection:
            self.apply(connection)
            LocatedCaptureStore(connection).apply(self.settings, capture_repository(self.settings, 'downstream'))
            dependency, baseline, owner, observed = self.pin(connection, dependant='downstream:@artifact/answer.md#Answer')
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)',
                (dependency, observed.selection.members[0].chunk.version))
            before = self.state(connection)
            (self.artifact / 'source.md').unlink()
            with self.assertRaises(MycelError):
                self.apply(connection)
            self.assertEqual(self.state(connection), before)
            with ExitStack() as held:
                for repository in ('downstream', 'fixture'):
                    held.enter_context(operation_guard(connection, repository, 'pass'))
                _, collected = self.apply(connection)
            self.assertEqual(collected[0].versions, 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
            retained = evidence.EvidenceStore(connection).read_baseline('downstream', baseline)
            self.assertIn(b'# Source\nOriginal source.\n', [blob.source for blob in retained.snapshots])
            self.assertEqual(connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
                (dependency,)).fetchone(), (owner,))
# TEST-TIER-END tests/test_collection.py::CollectionStoreTests.test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy

# TEST-TIER-BEGIN tests/test_collection.py::CollectionStoreTests.test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release
    def test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release(self):
        self.docs()
        with self.connect() as connection:
            self.apply(connection)
            dependency, baseline, owner, observed = self.pin(connection)
            raw = observed.selection.members[0].chunk.source
            digest = sha256(raw).hexdigest()
            lease = uuid4()
            # The real activity session registers and owns this invocation.
            with MutationActivity(connection, build=7).session() as activity:
                invocation = connection.execute('SELECT id FROM public.mycel_invocations').fetchone()[0]
                connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
                    (lease, 'fixture', 'lease', str(lease), invocation))
                connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
                    (lease, 'fixture', digest))
                with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection):
                    connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (dependency,))
                    store = CollectionStore(connection)
                    self.assertTrue(store.release_baseline_owner_in_transaction(owner, 'fixture'))
                    self.assertEqual(store.collect_evidence_in_transaction('fixture'), (1, 1))
                    self.assertEqual(connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE hash=%s',
                        (digest,)).fetchone(), (raw,))
                activity.finish('done')
# TEST-TIER-END tests/test_collection.py::CollectionStoreTests.test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release


# TEST-TIER-BEGIN tests/test_collection.py::CollectionStoreTests.test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection
    def test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection(self):
        self.docs()
        with self.connect() as connection:
            self.apply(connection)
            manifest = capture_repository(self.settings, 'fixture')
            before = self.state(connection)
            path = self.artifact / 'answer.md'
            replacement = self.artifact / 'replacement.tmp'
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
            with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection), self.assertRaises(MycelError):
                CollectionStore(connection).collect_in_transaction(self.settings, manifest)
            self.assertEqual(self.state(connection), before)
            # The identity producer checks and publishes atomic-save continuity.
            self.apply(connection)
# TEST-TIER-END tests/test_collection.py::CollectionStoreTests.test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_unlocated_versions_vectors_and_dead_chunks_collect_but_branch_stash_versions_survive
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unlocated versions vectors and dead chunks collect but branch stash versions survive.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unlocated_versions_vectors_and_dead_chunks_collect_but_branch_stash_versions_survive(self):
#         self.helper.initialize()
#         self.helper.git('branch', 'retained')
#         path = self.artifact / 'guide.md'
#         path.write_bytes(b'# Guide\nStashed version.\n')
#         self.helper.git('stash', 'push', '--message', 'Saved')
#         path.write_bytes(b'# Guide\nOld disk version.\n')
#         with self.connect() as connection:
#             first, _ = self.apply(connection)
#             old = first.files[0].chunk_versions[0][1]
#             initial_versions = {file.chunk_versions[0][1] for file in first.files}
#             owners = {version: self.helper.own_pin(connection, version, f'pin-{version}') for version in initial_versions}
#             plan = uuid4()
#             connection.execute('INSERT INTO public.mycel_embedding_plans VALUES (%s,%s,%s,1024,%s,%s,%s,NULL)',
#                 (plan, old, 'voyage-code-4', 'fixture-plan', 'Guide', Jsonb({})))
#             raw = b'# Guide\nOld disk version.\n'
#             connection.execute('INSERT INTO public.mycel_embedding_parts VALUES (%s,0,0,%s,%s,1,1,NULL)', (plan, len(raw), raw))
#             connection.execute('INSERT INTO public.mycel_vectors VALUES (%s,0,%s,1024,%s::vector)',
#                 (plan, 'voyage-code-4', '[' + ','.join(['1'] + ['0'] * 1023) + ']'))
#             path.write_bytes(b'# Guide\nNew disk version.\n')
#             result, collected = self.apply(connection)
#             self.assertEqual(collected[0].versions, 1)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_embedding_plans').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions').fetchone(), (3,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone(), (1,))
#             self.assertEqual({file.location.kind for file in result.files}, {'disk', 'branch', 'stash'})
#             self.assertEqual({row[0] for row in connection.execute('SELECT dependant_version FROM public.mycel_dependencies').fetchall()},
#                 initial_versions - {old})
#             self.assertEqual({str(row[0]) for row in connection.execute('SELECT id FROM public.mycel_evidence_owners').fetchall()},
#                 {owner for version, (owner, _) in owners.items() if version != old})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_source_deletion_removes_search_rows_but_preserves_dependant_record_and_owned_exact_bytes
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Source deletion removes search rows but preserves dependant record and owned exact bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_deletion_removes_search_rows_but_preserves_dependant_record_and_owned_exact_bytes(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             source_version = observed.selection.members[0].chunk.version
#             connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (dependency, source_version))
#             (self.artifact / 'source.md').unlink()
#             _, collected = self.apply(connection)
#             self.assertEqual(collected[0].versions, 1)
#             self.assertEqual(collected[0].chunks, 1)
#             self.assertEqual(collected[0].files, 1)
#             self.assertEqual(connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
#                 (dependency,)).fetchone(), (owner,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
#             retained = evidence.EvidenceStore(connection).read_baseline('fixture', baseline)
#             self.assertIn(b'# Source\nOriginal source.\n', [blob.source for blob in retained.snapshots])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone(), (1,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_selected_withdrawal_keeps_history_owners_then_collects_after_final_release
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Selected withdrawal keeps history owners then collects after final release.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_selected_withdrawal_keeps_history_owners_then_collects_after_final_release(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             history = uuid4()
#             connection.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,%s,clock_timestamp(),'
#                 'clock_timestamp(),%s,%s)', (history, 'fixture', observed.dependant.chunk.version, Jsonb({}), owner))
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection):
#                 connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (dependency,))
#                 store = CollectionStore(connection)
#                 self.assertFalse(store.release_baseline_owner_in_transaction(owner, 'fixture'))
#                 self.assertEqual(store.collect_evidence_in_transaction('fixture'), (0, 0))
#             self.assertEqual(evidence.EvidenceStore(connection).read_baseline('fixture', baseline).manifest.identifier, baseline)
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection):
#                 connection.execute('DELETE FROM public.mycel_drifts WHERE id=%s', (history,))
#                 self.assertTrue(store.release_baseline_owner_in_transaction(owner, 'fixture'))
#                 self.assertEqual(store.collect_evidence_in_transaction('fixture'), (2, 1))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_dead_dependant_releases_its_owners_without_collecting_surviving_history
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Dead dependant releases its owners without collecting surviving history.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dead_dependant_releases_its_owners_without_collecting_surviving_history(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             drift = uuid4()
#             connection.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,%s,clock_timestamp(),'
#                 'clock_timestamp(),%s,%s)', (drift, 'fixture', observed.dependant.chunk.version, Jsonb({}), owner))
#             (self.artifact / 'answer.md').unlink()
#             _, collected = self.apply(connection)
#             self.assertEqual(collected[0].versions, 1)
#             self.assertEqual(collected[0].owners, 0)
#             self.assertEqual(connection.execute('SELECT dependant_version,evidence_owner FROM public.mycel_drifts '
#                 'WHERE id=%s', (drift,)).fetchone(), (None, owner))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone(), (0,))
#             self.assertEqual(evidence.EvidenceStore(connection).read_baseline('fixture', baseline).manifest.identifier, baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_incomplete_unpublished_changed_and_unguarded_collection_refuse_without_mutation
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Incomplete unpublished changed and unguarded collection refuse without mutation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_incomplete_unpublished_changed_and_unguarded_collection_refuse_without_mutation(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             manifest = capture_repository(self.settings, 'fixture')
#             store = CollectionStore(connection)
#             before = self.state(connection)
#             with self.assertRaises(MycelError):
#                 store.collect_in_transaction(self.settings, manifest)
#             with atomic_transaction(connection), self.assertRaises(MycelError):
#                 store.collect_in_transaction(self.settings, manifest)
#             for incomplete in (replace(manifest, complete=False), replace(manifest, locations=tuple(
#                     replace(item, complete=False) for item in manifest.locations))):
#                 with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection), self.assertRaises(MycelError):
#                     store.collect_in_transaction(self.settings, incomplete)
#             (self.artifact / 'answer.md').write_bytes(b'# Answer\nChanged answer.\n')
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection), self.assertRaises(MycelError):
#                 store.collect_in_transaction(self.settings, manifest)
#             unpublished = capture_repository(self.settings, 'fixture')
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection), self.assertRaises(MycelError):
#                 store.collect_in_transaction(self.settings, unpublished)
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_row_lock_conflict_refuses_without_waiting_or_partial_collection
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Row lock conflict refuses without waiting or partial collection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_row_lock_conflict_refuses_without_waiting_or_partial_collection(self):
#         self.docs()
#         with self.connect() as connection, self.connect() as blocker:
#             self.apply(connection)
#             selected = SourceResolver.from_store(connection, self.settings).resolve('fixture:@artifact/answer.md#Answer').selection
#             version = selected.members[0].chunk.version
#             before = self.state(connection)
#             (self.artifact / 'answer.md').unlink()
#             with blocker.transaction():
#                 blocker.execute('SELECT id FROM public.mycel_chunk_versions WHERE id=%s FOR UPDATE', (version,))
#                 with self.assertRaises(MycelError) as error:
#                     self.apply(connection)
#                 self.assertEqual(error.exception.code.value, 'busy')
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_dependency_release_collects_independent_classification_owner_and_only_selected_owners
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Dependency release collects independent classification owner and only selected owners.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dependency_release_collects_independent_classification_owner_and_only_selected_owners(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             classification, work, digest = self.classification(connection, dependency)
#             orphan = uuid4()
#             orphan_raw = b'Unrelated exact diagnostic evidence.'
#             orphan_hash = sha256(orphan_raw).hexdigest()
#             connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s)',
#                 ('fixture', orphan_hash, orphan_raw, Jsonb({})))
#             connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
#                 (orphan, 'fixture', 'classification', 'Unrelated diagnostic owner'))
#             connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
#                 (orphan, 'fixture', orphan_hash))
#             connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,%s,%s)',
#                 (dependency, 'fixture', observed.dependant.chunk.version, observed.resolution.declaration, Jsonb({'fault': 'source_removed'})))
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection):
#                 released = CollectionStore(connection).release_dependency_in_transaction(dependency, 'fixture')
#                 self.assertEqual(released, 2)
#             self.assertEqual(connection.execute('SELECT id FROM public.mycel_evidence_owners').fetchall(), [(orphan,)])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_classification_work').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_ref_faults').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT hash FROM public.mycel_snapshots').fetchall(), [(orphan_hash,)])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_dependency_release_preserves_independent_classification_history_and_exact_baseline
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Dependency release preserves independent classification history and exact baseline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dependency_release_preserves_independent_classification_history_and_exact_baseline(self):
#         self.docs()
#         with self.connect() as connection:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             classification, work, digest = self.classification(connection, dependency, baseline=owner)
#             history = uuid4()
#             connection.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,%s,clock_timestamp(),'
#                 'clock_timestamp(),%s,%s)', (history, 'fixture', observed.dependant.chunk.version, Jsonb({}), classification))
#             original = evidence.EvidenceStore(connection).read_baseline('fixture', baseline)
#             with operation_guard(connection, 'fixture', 'pass'), atomic_transaction(connection):
#                 self.assertEqual(CollectionStore(connection).release_dependency_in_transaction(dependency, 'fixture'), 1)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_classification_work').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT id FROM public.mycel_evidence_owners').fetchall(), [(classification,)])
#             self.assertEqual(evidence.EvidenceStore(connection).read_baseline('fixture', baseline), original)
#             self.assertIsNotNone(connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE hash=%s', (digest,)).fetchone())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_collection.py::CollectionStoreTests.test_dependency_release_work_lock_conflict_and_later_failure_roll_back_selected_owners
# Reason: Narrower case removed from this family after retaining test_collection_and_owner_release_roll_back_with_complete_publication_on_failure, test_original_code_file_survives_other_chunk_edit_and_can_verify_later_rename, test_unlocated_source_cross_repository_edges_require_downstream_guard_and_keep_owned_copy, test_live_invocation_and_independent_snapshot_owner_protect_bytes_after_baseline_release, test_same_bytes_at_replaced_physical_file_need_new_publication_before_collection. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Dependency release work lock conflict and later failure roll back selected owners.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_collection.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dependency_release_work_lock_conflict_and_later_failure_roll_back_selected_owners(self):
#         self.docs()
#         with self.connect() as connection, self.connect() as blocker:
#             self.apply(connection)
#             dependency, baseline, owner, observed = self.pin(connection)
#             classification, work, digest = self.classification(connection, dependency)
#             before = self.state(connection)
#             with operation_guard(connection, 'fixture', 'pass'):
#                 with blocker.transaction():
#                     blocker.execute('SELECT id FROM public.mycel_classification_work WHERE id=%s FOR UPDATE', (work,))
#                     with self.assertRaises(MycelError) as error, atomic_transaction(connection):
#                         CollectionStore(connection).release_dependency_in_transaction(dependency, 'fixture')
#                     self.assertEqual(error.exception.code.value, 'busy')
#                 self.assertEqual(self.state(connection), before)
#                 with self.assertRaises(RuntimeError), atomic_transaction(connection):
#                     self.assertEqual(CollectionStore(connection).release_dependency_in_transaction(dependency, 'fixture'), 2)
#                     raise RuntimeError('Public fixture activity failure after release')
#                 self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
