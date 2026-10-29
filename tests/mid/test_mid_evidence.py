"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evidence as _support
from test_evidence import (MycelError ,evidence ,inputs ,patch)


class EvidenceStoreTests(_support.EvidenceStoreTests):

# TEST-TIER-BEGIN tests/test_evidence.py::EvidenceStoreTests.test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable
    def test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            observed = self.seed(connection, inputs(source='---\nrole: authored\n---\n# Source\r\nComplete source.\r\n', whole=True))
            writer = evidence.EvidenceStore(connection)
            identifier = self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
            baseline = writer.read_baseline('owner', identifier)
            self.assertEqual(baseline.manifest.payload['ownerRepository'], 'owner')
            self.assertEqual(baseline.manifest.payload['members'][0]['evidence']['hash'], observed.selection.file.snapshot_hash)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots WHERE repository=%s', ('source',)).fetchone()[0], 0)
            counts = connection.execute('SELECT (SELECT count(*) FROM public.mycel_chunks),'
                                        '(SELECT count(*) FROM public.mycel_locations),(SELECT count(*) FROM public.mycel_vectors)').fetchone()
            self.assertEqual(counts, (2, 2, 0))
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            self.assertEqual(writer.read_baseline('owner', identifier), baseline)
            self.assertIsNone(connection.execute('SELECT id FROM public.mycel_chunks WHERE repository=%s', ('source',)).fetchone())
# TEST-TIER-END tests/test_evidence.py::EvidenceStoreTests.test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable

# TEST-TIER-BEGIN tests/test_evidence.py::EvidenceStoreTests.test_real_callback_and_mid_transaction_failure_write_no_partial_baseline
    def test_real_callback_and_mid_transaction_failure_write_no_partial_baseline(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            observed = self.seed(connection, inputs())
            writer = evidence.EvidenceStore(connection)
            changed = inputs(source='# Source\nChanged current source\n')
            with self.assertRaises(evidence.EvidenceError) as error:
                self.pin(writer, observed, reread=lambda: changed)
            self.assertEqual(error.exception.status, 'changed_since_ingest')
            original = writer._write
            def fail_after_write(*args):
                original(*args)
                connection.execute('SELECT 1/0')
            with patch.object(writer, '_write', fail_after_write), self.assertRaises(MycelError):
                self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
            counts = connection.execute('SELECT (SELECT count(*) FROM public.mycel_snapshots),'
                    '(SELECT count(*) FROM public.mycel_manifests),(SELECT count(*) FROM public.mycel_evidence_owners),'
                    '(SELECT count(*) FROM public.mycel_evidence_references),(SELECT count(*) FROM public.mycel_dependencies)').fetchone()
            self.assertEqual(counts, (0, 0, 0, 0, 0))
# TEST-TIER-END tests/test_evidence.py::EvidenceStoreTests.test_real_callback_and_mid_transaction_failure_write_no_partial_baseline
