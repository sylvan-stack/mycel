"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_disk_reconciliation as _support
from test_disk_reconciliation import (DiskCaptureStore ,Jsonb ,MutationActivity ,MycelError ,SourceResolver ,capture_repository ,uuid4)


class DiskReconciliationStoreTests(_support.DiskReconciliationStoreTests):

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication
    def test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication(self):
        path = self.artifact / 'guide.md'
        original = b'# Guide\nComplete body.\n'
        path.write_bytes(original)
        captured = capture_repository(self.settings, 'fixture')
        with self.connect() as connection:
            before = self.state(connection)
            for stage in ('handoff', 'reply_counts'):
                with self.subTest(stage=stage):
                    def change_file():
                        path.write_bytes(b'# Guide\nChanged after the last guarded source observation.\n')

                    def handoff(conn, file):
                        change_file()

                    def reply_counts(repository, counts):
                        change_file()
                        return counts

                    try:
                        with MutationActivity(connection, build=1).session() as activity:
                            with self.assertRaises(MycelError) as error:
                                DiskCaptureStore(connection).apply(self.settings, captured, activity=activity,
                                    file_handoff=handoff if stage == 'handoff' else None,
                                    reply_counts=reply_counts if stage == 'reply_counts' else None)
                            self.assertEqual(error.exception.code, 'invalid_input')
                            self.assertEqual(self.state(connection), before)
                            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                            activity.finish('failed', error={'code': 'invalid_input', 'message': 'Source changed.'})
                    finally:
                        path.write_bytes(original)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication


# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_root_retarget_creates_new_identity_and_retains_branch_binding
    def test_root_retarget_creates_new_identity_and_retains_branch_binding(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nSame body.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            branch_location = uuid4()
            connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                (branch_location, original.binding.version, 'branch', 'retained-main', Jsonb({})))
            for identifier, version in original.chunk_versions:
                connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                    (uuid4(), version, branch_location, 'branch', 'retained-main', Jsonb({})))
            other_code = self.base / 'other-code'
            other_artifact = other_code / 'docs'
            other_artifact.mkdir(parents=True)
            (other_artifact / 'guide.md').write_bytes(b'# Guide\nSame body.\n')
            settings = self.configure(code=other_code, artifact=other_artifact)
            current = self.apply(connection, settings).files[0]
            self.assertNotEqual(current.binding.identifier, original.binding.identifier)
            self.assertNotEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertEqual(self.disk(connection, settings=settings).file.identifier, current.binding.identifier)
            retained = SourceResolver.from_store(connection, settings, kind='branch', location='retained-main')
            self.assertEqual(retained.resolve('fixture:@artifact/guide.md#Guide').selection.file.identifier,
                             original.binding.identifier)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 2)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_root_retarget_creates_new_identity_and_retains_branch_binding
