"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_activity_completion as _support
from test_activity_completion import (MycelError ,activity ,locks ,patch)


class ActivityCompletionStoreTests(_support.ActivityCompletionStoreTests):


# TEST-TIER-BEGIN tests/test_activity_completion.py::ActivityCompletionStoreTests.test_final_replies_validate_before_write_and_late_native_close_rolls_back_all_scopes
    def test_final_replies_validate_before_write_and_late_native_close_rolls_back_all_scopes(self):
        with self.connect() as connection, self.connect() as observer:
            self.seed(connection)
            with activity.MutationActivity(connection, build=37).session() as audit:
                audit.apply('fixture', 'embed', self.write({'embedded': 1}))
                audit.apply('fixture', 'confirm', self.write({'confirmed': 1}))
                before = self.rows(observer)
                for counts in ([], 1, {('fixture', 'embed'): {'embedded': float('nan')}},
                               {('fixture', 'embed'): {'embedded': 2}, ('fixture', 'confirm'): []}):
                    with self.assertRaises(MycelError) as invalid:
                        audit.finish('done', counts=counts)
                    self.assertEqual(invalid.exception.code, 'invalid_input')
                    self.assertEqual(self.rows(observer), before)
                original = activity._execute
                attempted = []

                def fail_second_close(current, sql, parameters=None):
                    if sql == activity._CLOSE_SQL:
                        attempted.append(parameters[-1])
                        if len(attempted) == 2:
                            sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
                    return original(current, sql, parameters)

                final = {('fixture', 'embed'): {'embedded': 1, 'checked': 3},
                         ('fixture', 'confirm'): {'confirmed': 1, 'checked': 2}}
                with patch('mycel._activity._execute', side_effect=fail_second_close):
                    with self.assertRaises(MycelError) as failure:
                        audit.finish('done', counts=final)
                self.assertEqual(failure.exception.code, 'internal')
                self.assertEqual(set(attempted), {row[0] for row in before})
                self.assertNotIn('mycel_missing_activity', str(failure.exception))
                self.assertEqual(self.rows(observer), before)
                self.assertTrue(locks.invocation_is_live(observer, audit.invocation))
                # A caught close failure may safely retry within the same
                # live invocation; no partial final reply was published.
                audit.finish('done', counts=final)
            for row in self.rows(observer):
                self.assertEqual(row[3:], ('done', final[(row[1], row[2])]))
# TEST-TIER-END tests/test_activity_completion.py::ActivityCompletionStoreTests.test_final_replies_validate_before_write_and_late_native_close_rolls_back_all_scopes
