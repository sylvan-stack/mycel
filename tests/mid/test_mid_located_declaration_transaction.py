"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_located_declaration_transaction as _support
from test_located_declaration_transaction import (MycelError)


class LocatedDeclarationTransactionStoreTests(_support.LocatedDeclarationTransactionStoreTests):


# TEST-TIER-BEGIN tests/test_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_git_ref_change_after_last_pin_refuses_complete_publication
    def test_git_ref_change_after_last_pin_refuses_complete_publication(self):
        self.prepare()
        with self.fixture.connect() as connection:
            before = self.fixture.state(connection)
            def change():
                self.fixture.git('branch', 'added-during-publication')
            with self.assertRaises(MycelError) as error:
                self.publish(connection,
                    batch_handoff=lambda conn, result: self.producer(conn, result, after=change))
            self.assertEqual(error.exception.code.value, 'invalid_input')
            self.assertEqual(self.fixture.state(connection), before)
# TEST-TIER-END tests/test_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_git_ref_change_after_last_pin_refuses_complete_publication
