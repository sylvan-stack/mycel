"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_repository_removal as _support
from test_repository_removal import (CollectionStore ,RepositoryRemovalStore ,patch)


class RepositoryRemovalStoreTests(_support.RepositoryRemovalStoreTests):


# TEST-TIER-BEGIN tests/test_repository_removal.py::RepositoryRemovalStoreTests.test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards
    def test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards(self):
        with self.connect() as connection, self.connect() as peer:
            self.seed(connection, 'fixture', complete=True)
            before = self.state(connection)
            actual = CollectionStore.remove_repository_in_transaction
            def fail(store, *args, **kwargs):
                actual(store, *args, **kwargs)
                raise RuntimeError('Fixture failure after repository deletion.')
            with patch.object(CollectionStore, 'remove_repository_in_transaction', fail):
                with self.assertRaises(RuntimeError):
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertEqual(self.state(connection), before)
            reply = RepositoryRemovalStore(peer).remove(self.settings, 'fixture')
            self.assertEqual(reply['removed']['chunks'], 3)
# TEST-TIER-END tests/test_repository_removal.py::RepositoryRemovalStoreTests.test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards
