"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evidence_transaction as _support
from test_evidence_transaction import (
    AppliedMutation,
    EvidenceTransactionStoreTests,
    Jsonb,
    MutationActivity,
    MycelError,
    SourceResolver,
    atomic_transaction,
    evidence,
    fixtures,
    json,
    patch,
    sha256,
    unittest,
    uuid4,
)


class EvidenceTransactionStoreTests(_support.EvidenceTransactionStoreTests):
# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_new_file_versions_exact_evidence_and_activity_publish_in_one_transaction
    def test_new_file_versions_exact_evidence_and_activity_publish_in_one_transaction(self):
        with self.connect() as connection, self.connect() as reader:
            _, observed, writer = self.prepare(connection)
            rows = self.reserve_rows(connection)
            dependency = uuid4()
            with MutationActivity(connection, build=7).session() as activity, evidence.checked_input_guard(
                    connection, observed, lambda: observed) as token:
                def apply(current):
                    self.insert_rows(current, rows)
                    baseline = self.pin(writer, token, dependency=dependency)
                    self.assertEqual(self.counts(reader), (0,) * 8)
                    self.assertEqual(json.loads(current.execute(
                        'SELECT bytes FROM public.mycel_manifests WHERE hash=%s', (baseline,)).fetchone()[0])['dependantVersion'],
                        str(observed.dependant.chunk.version))
                    return AppliedMutation(True, {'pinned': 1})
                activity.apply('owner', 'ingest', apply)
                activity.finish('done', counts={('owner', 'ingest'): {'pinned': 1}})
            self.assertEqual(self.counts(reader), (2, 2, 2, 1, 1, 3, 1, 1))
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (dependency,)).fetchone()[0]
            self.assertIsNotNone(owner)
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_new_file_versions_exact_evidence_and_activity_publish_in_one_transaction

# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_evidence_or_activity_failure_rolls_back_new_file_rows_and_all_owners
    def test_evidence_or_activity_failure_rolls_back_new_file_rows_and_all_owners(self):
        with self.connect() as connection:
            _, observed, writer = self.prepare(connection)
            rows = self.reserve_rows(connection)
            for fault in ('evidence', 'activity'):
                with self.subTest(fault=fault), MutationActivity(connection, build=7).session() as activity, evidence.checked_input_guard(
                        connection, observed, lambda: observed) as token:
                    def apply(current):
                        self.insert_rows(current, rows)
                        self.pin(writer, token)
                        if fault == 'evidence':
                            raise RuntimeError('public fixture caller failed after writing its baseline')
                        return AppliedMutation(True, {'pinned': 1})
                    if fault == 'activity':
                        with patch.object(activity, '_details', side_effect=MycelError('internal', 'public fixture audit failure')):
                            with self.assertRaises(MycelError):
                                activity.apply('owner', 'ingest', apply)
                    else:
                        with self.assertRaises(RuntimeError):
                            activity.apply('owner', 'ingest', apply)
                    self.assertEqual(self.counts(connection), (0,) * 8)
                    activity.finish('failed', error={'code': 'internal', 'message': 'public fixture outcome'})
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_evidence_or_activity_failure_rolls_back_new_file_rows_and_all_owners

# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_idle_expired_foreign_and_aborted_transaction_tokens_refuse_before_writes
    def test_idle_expired_foreign_and_aborted_transaction_tokens_refuse_before_writes(self):
        with self.connect() as connection, self.connect() as other:
            helper, observed, writer = self.prepare(connection)
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with self.assertRaises(evidence.EvidenceError):
                    self.pin(writer, token)
                with atomic_transaction(other), self.assertRaises(evidence.EvidenceError):
                    self.pin(evidence.EvidenceStore(other), token)
                with self.assertRaises(MycelError), atomic_transaction(connection):
                    try:
                        connection.execute('SELECT 1/0')
                    except Exception:
                        with self.assertRaises(evidence.EvidenceError):
                            self.pin(writer, token)
                        raise
            with atomic_transaction(connection), self.assertRaises(evidence.EvidenceError):
                self.pin(writer, token)
            self.assertEqual(self.counts(connection), before)
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_idle_expired_foreign_and_aborted_transaction_tokens_refuse_before_writes

# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_capture_rechecks_new_version_bytes_and_existing_baseline_owner
    def test_capture_rechecks_new_version_bytes_and_existing_baseline_owner(self):
        with self.connect() as connection:
            helper, observed, writer = self.prepare(connection)
            dependency = uuid4()
            original = helper.pin(writer, observed, dependency=dependency)
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    self.pin(writer, token, dependency=dependency)
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    connection.execute('UPDATE public.mycel_chunk_versions SET source_bytes=%s,snapshot_hash=%s,text=%s WHERE id=%s',
                        (b'changed exact bytes', sha256(b'changed exact bytes').hexdigest(), 'changed exact bytes',
                         observed.dependant.chunk.version))
                    self.pin(writer, token)
            self.assertEqual(self.counts(connection), before)
            self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_capture_rechecks_new_version_bytes_and_existing_baseline_owner

# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_inheritance_copies_selected_old_evidence_without_current_source_in_caller_transaction
    def test_inheritance_copies_selected_old_evidence_without_current_source_in_caller_transaction(self):
        with self.connect() as connection:
            helper, observed, writer = self.prepare(connection)
            previous = uuid4()
            original_id = helper.pin(writer, observed, dependency=previous)
            original = writer.read_baseline('owner', original_id)
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            catalog = SourceResolver.from_store(connection, observed.settings)
            selection = catalog.resolve(observed.dependant.place.address, purpose='endpoint').selection
            inputs = evidence.InheritanceInputs(observed.settings, selection.members[0], selection.file,
                evidence.CaptureLocation('disk'), catalog.resolve(observed.resolution.declaration), catalog)
            before = self.counts(connection)
            dependency = uuid4()
            with evidence.checked_input_guard(connection, inputs, lambda: inputs) as token:
                with atomic_transaction(connection):
                    inherited_id = writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=dependency, authorization='normalized_equivalent_edit')
                with self.assertRaises(RuntimeError), atomic_transaction(connection):
                    writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=uuid4(), authorization='normalized_equivalent_edit')
                    raise RuntimeError('public fixture graph failure')
            inherited = writer.read_baseline('owner', inherited_id)
            self.assertEqual(inherited.manifest.payload['members'], original.manifest.payload['members'])
            self.assertEqual(inherited.manifest.payload['pinnedHash'], original.manifest.payload['pinnedHash'])
            self.assertEqual(self.counts(connection)[-2], before[-2] + 1)
            self.assertEqual(writer.read_baseline('owner', original_id), original)
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_inheritance_copies_selected_old_evidence_without_current_source_in_caller_transaction

# TEST-TIER-BEGIN tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_inheritance_locks_and_validates_complete_prior_owning_graph
    def test_inheritance_locks_and_validates_complete_prior_owning_graph(self):
        with self.connect() as connection, self.connect() as blocker:
            helper, observed, writer = self.prepare(connection)
            previous = uuid4()
            original_id = helper.pin(writer, observed, dependency=previous)
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone()[0]
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with blocker.transaction():
                    blocker.execute('SELECT hash FROM public.mycel_manifests WHERE hash=%s FOR UPDATE', (original_id,))
                    with self.assertRaises(MycelError) as error, atomic_transaction(connection):
                        writer.inherit_in_transaction(token, previous_dependency=previous,
                            dependency_id=uuid4(), authorization='normalized_equivalent_edit')
                    self.assertEqual(error.exception.code.value, 'busy')
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND ordinal>0', (owner,))
                    writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=uuid4(), authorization='normalized_equivalent_edit')
            self.assertEqual(self.counts(connection), before)
# TEST-TIER-END tests/test_evidence_transaction.py::EvidenceTransactionStoreTests.test_inheritance_locks_and_validates_complete_prior_owning_graph
