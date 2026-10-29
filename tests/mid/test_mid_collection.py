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
