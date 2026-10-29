"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_verification_history as _support
from test_verification_history import (MycelError ,patch ,store)


class VerificationHistoryStoreTests(_support.VerificationHistoryStoreTests):


# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration
    def test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            self.predecessor(connection)
            before = self.state(connection)
            migration = store.MIGRATIONS[1]
            def failed(current):
                migration.apply(current)
                raise RuntimeError('deliberate migration validation failure')
            with patch.object(store, 'MIGRATIONS', {1: store.Migration(failed, migration.validate),
                                                    **{number: step for number, step in store.MIGRATIONS.items() if number > 1}}):
                with self.assertRaises(RuntimeError):
                    store.initialize_store(connection, dimensions=1024)
            self.assertEqual(self.state(connection), before)
            with patch('mycel._activity.record_initialization', side_effect=MycelError('internal', 'deliberate audit failure')):
                with self.assertRaises(MycelError):
                    store.initialize_store(connection, dimensions=1024, build=1,
                                           address=self.store_fixture.backend.address(self.store_fixture.database))
            self.assertEqual(self.state(connection), before)
            store.initialize_store(connection, dimensions=1024)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration
