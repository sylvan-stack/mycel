"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_rebuild_generation as _support
from test_rebuild_generation import (DriftStore ,EvidenceStore ,inspect_store ,sha256)


class RebuildGenerationStoreTests(_support.RebuildGenerationStoreTests):

# TEST-TIER-BEGIN tests/test_rebuild_generation.py::RebuildGenerationStoreTests.test_exact_store_backup_restores_generation_pins_verification_and_classifier_bytes
    def test_exact_store_backup_restores_generation_pins_verification_and_classifier_bytes(self):
        generation, baseline, verification, prepared = self.history()
        with self.base.connect() as connection:
            backup = self.backup(connection)
            original = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.erase_store(connection)
        self.assertNotEqual(self.invoke('init')['indexGeneration'], generation)
        with self.base.connect() as connection:
            self.restore(connection, backup)
            self.assertEqual(inspect_store(connection).index_generation, generation)
            self.assertEqual(self.backup(connection), backup)
            restored = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.assertEqual(restored, original)
            self.assertIn(self.fixture.fixture.source_bytes, [blob.source for blob in restored.snapshots])
            record = connection.execute('SELECT record FROM public.mycel_verifications WHERE id=%s',
                                        (verification['id'],)).fetchone()[0]
            self.assertEqual(record['textHash'], verification['textHash'])
            drift, = DriftStore(connection).list('downstream', closed=True, all_versions=True)['drifts']
            self.assertEqual((drift['state'], drift['history'][-1]['inputHash']), ('closed', prepared.input_hash))
            raw = bytes(connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                ('downstream', prepared.input_hash)).fetchone()[0])
            self.assertEqual((raw, sha256(raw).hexdigest()), (prepared.decision.canonical_bytes, prepared.input_hash))
            entries = connection.execute('SELECT id FROM public.mycel_activity ORDER BY id').fetchall()
        self.assertEqual(self.generation(), generation)
        self.assertFalse(self.invoke('init')['changed'])
        for entry, in entries:
            self.assertEqual(self.invoke('activity', '--entry', str(entry))['entries'][0]['indexGeneration'], generation)
        with self.base.connect() as connection:
            self.assertEqual(self.backup(connection), backup)
# TEST-TIER-END tests/test_rebuild_generation.py::RebuildGenerationStoreTests.test_exact_store_backup_restores_generation_pins_verification_and_classifier_bytes

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_rebuild_generation.py::RebuildGenerationStoreTests.test_lost_store_cli_rebuild_reports_new_generation_and_only_new_current_baselines
# Reason: Narrower case removed from this family after retaining test_exact_store_backup_restores_generation_pins_verification_and_classifier_bytes. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Lost store cli rebuild reports new generation and only new current baselines.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_rebuild_generation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_lost_store_cli_rebuild_reports_new_generation_and_only_new_current_baselines(self):
#         old_generation, old_baseline, verification, prepared = self.history()
#         with self.base.connect() as connection:
#             self.erase_store(connection)
#         self.assertIsNone(self.generation())
#         initialized = self.invoke('init')
#         generation = initialized['indexGeneration']
#         self.assertNotEqual(generation, old_generation)
#         self.assertEqual(self.generation(), generation)
#         with self.base.connect() as connection:
#             entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
#         detail = self.invoke('activity', '--entry', str(entry))['entries'][0]
#         self.assertEqual((detail['kind'], detail['indexGeneration'], detail['counts']),
#                          ('init', generation, initialized))
#         self.ingest_files()
#         with self.base.connect() as connection:
#             dependencies = self.fixture.fixture.dependencies(connection)
#             self.assertEqual({row[2] for row in dependencies}, {'declared'})
#             self.assertEqual(len(dependencies), 3)
#             baseline = next(row[7] for row in dependencies if row[4] == self.fixture.addresses[0])
#             self.assertNotEqual(baseline, old_baseline)
#             captured = EvidenceStore(connection).read_baseline('downstream', baseline)
#             self.assertIn(self.fixture.fixture.source.read_bytes(), [blob.source for blob in captured.snapshots])
#             self.assertNotIn(self.fixture.fixture.source_bytes, [blob.source for blob in captured.snapshots])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_relations').fetchone()[0], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_classification_work').fetchone()[0], 0)
#             self.assertEqual(DriftStore(connection).list('downstream', closed=True, all_versions=True)['drifts'], [])
#             for digest in (old_baseline, prepared.input_hash, sha256(self.fixture.fixture.source_bytes).hexdigest()):
#                 self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_manifests '
#                     'WHERE repository=%s AND hash=%s', ('downstream', digest)).fetchone())
#                 self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
#                     'WHERE repository=%s AND hash=%s', ('downstream', digest)).fetchone())
#             entries = connection.execute('SELECT id,kind,index_generation FROM public.mycel_activity ORDER BY id').fetchall()
#             self.assertEqual({row[1] for row in entries}, {'init', 'ingest'})
#             self.assertEqual({str(row[2]) for row in entries}, {generation})
#         for entry, _, _ in entries:
#             self.assertEqual(self.invoke('activity', '--entry', str(entry))['entries'][0]['indexGeneration'], generation)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
