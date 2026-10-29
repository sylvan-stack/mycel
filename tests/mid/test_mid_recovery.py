"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_recovery as _support
from test_recovery import (os)


class RecoveryStoreTests(_support.RecoveryStoreTests):


# TEST-TIER-BEGIN tests/test_recovery.py::RecoveryStoreTests.test_an_edit_with_restored_mtime_during_a_step_is_still_caught
    def test_an_edit_with_restored_mtime_during_a_step_is_still_caught(self):
        before=self.source.stat()
        def changed(request):
            self.source.write_text('def value():\n    return 3\n')
            os.utime(self.source,ns=(before.st_atime_ns,before.st_mtime_ns))
        reply=self.run_recovery(k=2,dependencies=self.dependencies(changed=changed))
        self.assertEqual(reply['completed'],0,reply)
        self.assertEqual(self.origins(),[])
        self.assertIn(reply['pairs'][0]['reason'],{'obsolete','changed_since_ingest'})
# TEST-TIER-END tests/test_recovery.py::RecoveryStoreTests.test_an_edit_with_restored_mtime_during_a_step_is_still_caught


# TEST-TIER-BEGIN tests/test_recovery.py::RecoveryStoreTests.test_interrupt_preserves_completed_prefix_and_releases_evidence_leases
    def test_interrupt_preserves_completed_prefix_and_releases_evidence_leases(self):
        def interrupt(request):
            if len(self.calls)==2:raise KeyboardInterrupt()
        result=self.run_recovery(dependencies=self.dependencies(changed=interrupt))
        self.assertEqual(result['status'],2,result)
        self.assertEqual(result['completed'],1,result)
        self.assertEqual(result['jevCalls'],2)
        self.assertEqual(len(self.origins()),1)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='origin_recovery' AND invocation IS NOT NULL").fetchone(),(0,))
# TEST-TIER-END tests/test_recovery.py::RecoveryStoreTests.test_interrupt_preserves_completed_prefix_and_releases_evidence_leases
