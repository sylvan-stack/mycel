"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_activity_store as _support
from test_activity_store import (Jsonb ,MycelError ,activity ,locks ,patch ,time ,uuid4)


class ActivityStoreTests(_support.ActivityStoreTests):


# TEST-TIER-BEGIN tests/test_activity_store.py::ActivityStoreTests.test_exact_session_loss_and_recycled_pid_or_other_lock_never_protect_open_work
    def test_exact_session_loss_and_recycled_pid_or_other_lock_never_protect_open_work(self):
        with self.connect() as owner, self.connect() as observer:
            self.seed(owner)
            audit=activity.MutationActivity(owner,build=1)
            session=audit.session(); session.__enter__()
            try:
                audit.apply('fixture','ingest',self.write())
                invocation=audit.invocation
                identifier=self.entries(observer)[0][0]
                self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'running')
                observer.execute('UPDATE public.mycel_invocations SET backend_start=backend_start-interval \'1 second\' WHERE id=%s',(invocation.id,))
                self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                observer.execute('UPDATE public.mycel_invocations SET backend_start=%s WHERE id=%s',(invocation.backend_start,invocation.id))
                # Own generated sessions only; backend PID is not an owner-store target.
                self.assertTrue(observer.execute('SELECT pg_terminate_backend(%s)',(invocation.backend_pid,)).fetchone()[0])
                until=time.monotonic()+2
                while locks.invocation_is_live(observer,invocation) and time.monotonic()<until: time.sleep(.01)
                with locks.operation_guard(observer,'fixture','pass'):
                    self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                with locks._session_guard(observer,invocation.liveness_key,shared=False,message='fixture'):
                    self.assertEqual(activity.activity_state(observer,identifier)['outcome'],'unfinished')
                self.assertIsNone(observer.execute('SELECT ended_at FROM public.mycel_activity WHERE id=%s',(identifier,)).fetchone()[0])
            finally:
                try: session.__exit__(RuntimeError,RuntimeError('ended session'),None)
                except MycelError: pass
# TEST-TIER-END tests/test_activity_store.py::ActivityStoreTests.test_exact_session_loss_and_recycled_pid_or_other_lock_never_protect_open_work


# TEST-TIER-BEGIN tests/test_activity_store.py::ActivityStoreTests.test_caller_transaction_late_audit_failure_rolls_back_all_scopes_and_retry
    def test_caller_transaction_late_audit_failure_rolls_back_all_scopes_and_retry(self):
        with self.connect() as c:
            self.seed(c)
            files = (activity.FileChange('code', 'worker.py', 'disk', 'changed'),)
            decisions = (activity.IdentityChange('code', 'worker.py', 'disk', uuid4(), 'unchanged', 'work'),)
            original = activity._execute

            def fail_downstream(connection, statement, parameters=None):
                if statement == activity._OPEN_SQL and parameters[0] == 'downstream':
                    statement = statement.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(connection, statement, parameters)

            with activity.MutationActivity(c, build=17).session() as audit:
                with locks.mutation_guard(c, 'fixture'), locks.mutation_guard(c, 'downstream'):
                    with patch('mycel._activity._execute', side_effect=fail_downstream):
                        with self.assertRaises(MycelError) as error:
                            with locks.atomic_transaction(c):
                                audit.record_in_transaction('fixture', 'ingest',
                                                            self.write(files=files, decisions=decisions)(c))
                                c.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='downstream'",
                                          (Jsonb({'refsChanged': 1}),))
                                audit.record_in_transaction('downstream', 'ingest',
                                                            activity.AppliedMutation(True, {'refsChanged': 1}))
                    self.assertEqual(error.exception.code, 'internal')
                    self.assertNotIn('mycel_missing_activity', str(error.exception))
                    self.assertEqual(self.entries(c), [])
                    self.assertEqual(c.execute('SELECT read_locations FROM public.mycel_repository_state '
                                               'ORDER BY repository').fetchall(), [({},), ({},)])
                    self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_identity_decisions').fetchone()[0], 0)
                    with locks.atomic_transaction(c):
                        audit.record_in_transaction('fixture', 'ingest', self.write(files=files, decisions=decisions)(c))
                        c.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='downstream'",
                                  (Jsonb({'refsChanged': 1}),))
                        audit.record_in_transaction('downstream', 'ingest',
                                                    activity.AppliedMutation(True, {'refsChanged': 1}))
            self.assertEqual([row[1:4] for row in self.entries(c)],
                             [('fixture', 'ingest', 'done'), ('downstream', 'ingest', 'done')])
            self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_identity_decisions').fetchone()[0], 1)
# TEST-TIER-END tests/test_activity_store.py::ActivityStoreTests.test_caller_transaction_late_audit_failure_rolls_back_all_scopes_and_retry
