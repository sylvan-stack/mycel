"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_dependency_source_refresh as _support
from test_dependency_source_refresh import (DependencyApplicationStore ,EvidenceError ,MutationActivity ,patch)


class DependencySourceRefreshStoreTests(_support.DependencySourceRefreshStoreTests):


# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner
    def test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.state(connection)
            original_answer = self.answer.read_bytes()
            self.source.write_bytes(b'# Source\nChanged source requiring observation.\n')
            actual = DependencyApplicationStore.apply_in_transaction

            def mutate_after_foreign_application(store, *args, **kwargs):
                reply = actual(store, *args, **kwargs)
                owner = store.connection.execute("""SELECT f.repository FROM public.mycel_file_locations l
                    JOIN public.mycel_file_versions v ON v.id=l.file_version
                    JOIN public.mycel_files f ON f.id=v.file_id WHERE l.id=%s""", (args[1],)).fetchone()[0]
                if owner == 'downstream':
                    self.answer.write_bytes(original_answer.replace(b'Unchanged dependant.', b'Changed during pass.'))
                return reply

            with patch.object(DependencyApplicationStore, 'apply_in_transaction', mutate_after_foreign_application):
                with self.assertRaises(EvidenceError) as caught:
                    self.publish(connection)
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
            self.answer.write_bytes(original_answer)
            with MutationActivity(connection, build=1).session() as activity:
                with patch.object(activity, '_details', side_effect=RuntimeError('late audit failure')):
                    with self.assertRaises(RuntimeError):
                        self.publish(connection, activity=activity)
                self.assertEqual(self.state(connection), before)
                activity.finish('failed', error={'code': 'internal', 'message': 'fixture failed'})
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner
