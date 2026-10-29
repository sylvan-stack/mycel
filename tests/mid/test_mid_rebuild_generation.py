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
