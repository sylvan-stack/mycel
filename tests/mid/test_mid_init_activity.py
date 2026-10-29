"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_init_activity as _support
from test_init_activity import (activity ,patch ,store)


class InitActivityStoreTests(_support.InitActivityStoreTests):


# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks
    def test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks(self):
        original = activity._execute
        def fail(connection, sql, parameters=None):
            if sql == activity._OPEN_SQL:
                sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
            return original(connection, sql, parameters)
        with self.package(), patch('mycel._activity._execute', side_effect=fail):
            status, reply = self.invoke()
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.inspect_store(connection).state, 'empty')
            self.assertEqual(connection.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
                "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())").fetchone()[0], 0)
        with self.package():
            self.assertEqual(self.invoke()[0], 0)
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks
