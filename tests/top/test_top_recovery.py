"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_recovery as _support
from test_recovery import (
    JevFailure,
    StringIO,
    json,
    patch,
)


class RecoveryStoreTests(_support.RecoveryStoreTests):
    def test_edit_during_final_audit_rolls_back_the_origin_claim_and_edge(self):
        source=self.source
        class EditingAudit:
            def record_in_transaction(self,*args):
                source.write_text('def value():\n    return 3\n')
        reply=self.run_recovery(k=1,dependencies=self.dependencies(),activity=EditingAudit())
        self.assertEqual(reply['status'],1,reply)
        self.assertEqual(reply['jevCalls'],1)
        self.assertEqual(self.origins(),[])
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='origin'").fetchone(),(0,))

    def test_a_pair_in_error_keeps_the_step_reply_and_closes_its_activity_failed(self):
        # Regression (SYL-289): the step closed its activity `refused` without an
        # error, the record of work refused that, and the reply was lost.
        from mycel._cli import run
        def fail_second(request):
            if len(self.calls)==2:raise JevFailure('provider_result_invalid')
        output,diagnostic=StringIO(),StringIO()
        with patch('mycel._cli.load_settings',return_value=self.settings), \
             patch('mycel._recovery.ClassifyDependencies',return_value=self.dependencies(changed=fail_second)), \
             patch('mycel._build_identity.current_build',return_value=1):
            status=run(('recovery',self.ref),stdout=output,stderr=diagnostic)
        reply=json.loads(output.getvalue())
        self.assertEqual((status,reply['status'],reply['errors'],reply['completed']),(1,1,1,3),reply)
        with self.base.connect() as connection:
            counts,outcome,error=connection.execute("SELECT counts,outcome,error FROM public.mycel_activity WHERE kind='recovery'").fetchone()
        self.assertEqual((outcome,error['code'],counts['completed']),('failed','refused',3))
