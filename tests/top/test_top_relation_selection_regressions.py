"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_relation_selection_regressions as _support
from test_relation_selection_regressions import (
    MycelError,
)


class RelationSelectionRegressionStoreTests(_support.RelationSelectionRegressionStoreTests):
    def test_same_literal_short_method_ref_cannot_redirect_existing_pin_to_unrelated_place(self):
        self.declare(source='fixture:@code/policy.py#apply')
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            original = self.current(connection)
            self.assertEqual(original[2], 'fixture:@code/policy.py#Policy.apply')
            before = self.harness.state(connection)
            self.fixture.code.write_bytes(b'class Other:\n    """Unrelated replacement."""\n'
                b'    def apply(self):\n        return "entirely different behaviour"\n')
            with self.assertRaises(MycelError) as error:
                self.fixture.publish(connection)
            self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(error.exception.message, 'An existing relation cannot bind another source selection.')
            self.assertEqual(self.harness.state(connection), before)
            self.assertEqual(self.current(connection), original)
