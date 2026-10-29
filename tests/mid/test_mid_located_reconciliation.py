"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_located_reconciliation as _support
from test_located_reconciliation import (LocationId)


class LocatedReconciliationStoreTests(_support.LocatedReconciliationStoreTests):

# TEST-TIER-BEGIN tests/test_located_reconciliation.py::LocatedReconciliationStoreTests.test_publish_disk_branches_and_untracked_stash_without_changing_checkout
    def test_publish_disk_branches_and_untracked_stash_without_changing_checkout(self):
        self.initialize()
        self.git('branch', 'feature')
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nStashed body.\n')
        (self.artifact / 'untracked.md').write_bytes(b'# Extra\nUntracked stash document.\n')
        self.git('stash', 'push', '--include-untracked', '--message', 'Saved')
        stash = self.git('rev-parse', 'refs/stash')
        head, status = self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')
        before_bytes = (self.artifact / 'guide.md').read_bytes()
        with self.connect() as connection:
            result = self.apply(connection)
            disk = self.resolve(connection).selection
            for ref in ('refs/heads/fixture-main', 'refs/heads/feature'):
                branch = self.resolve(connection, identifier=LocationId('branch', 'code', ref)).selection
                self.assertEqual(branch.file.identifier, disk.file.identifier)
                self.assertEqual(branch.members[0].chunk.identifier, disk.members[0].chunk.identifier)
                self.assertEqual(branch.members[0].chunk.version, disk.members[0].chunk.version)
            saved = self.resolve(connection, identifier=LocationId('stash', 'code', stash)).selection
            self.assertEqual(saved.members[0].chunk.identifier, disk.members[0].chunk.identifier)
            self.assertNotEqual(saved.members[0].chunk.version, disk.members[0].chunk.version)
            self.assertEqual(saved.members[0].chunk.source, b'# Guide\nStashed body.\n')
            self.assertIsNotNone(self.resolve(connection, 'fixture:@artifact/untracked.md#Extra',
                                              identifier=LocationId('stash', 'code', stash)).selection)
            self.assertEqual(self.resolve(connection, 'fixture:@artifact/untracked.md').fault, 'missing_file')
            self.assertEqual([file.location.kind for file in result.files],
                             ['disk', 'branch', 'branch', 'stash', 'stash'])
        self.assertEqual((self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1'),
                          (self.artifact / 'guide.md').read_bytes()), (head, status, before_bytes))
# TEST-TIER-END tests/test_located_reconciliation.py::LocatedReconciliationStoreTests.test_publish_disk_branches_and_untracked_stash_without_changing_checkout
