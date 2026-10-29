# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Complete local dependency contracts through guarded configured-store callers.

These acceptance callers use the reusable publication/confirmation boundary;
they do not dispatch future ingest, confirmation, relation or detection commands.
"""
from hashlib import sha256

from mycel._reconciliation import ReconciliationError

import unittest

from mycel._capture import LocationId
from mycel._dependency_application import DependencyApplicationStore
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import EvidenceStore
from mycel._locks import atomic_transaction

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class DependencyContractStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def baseline(self, connection, row):
        return EvidenceStore(connection).read_baseline('downstream', row[7]).manifest.payload

    def confirm(self, connection):
        location, version = connection.execute("""SELECT l.id,c.chunk_version
            FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk'
            AND l.metadata->>'path'='answer.md' AND c.metadata->>'name'='Answer'""").fetchone()
        inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            reply = DependencyApplicationStore(connection).apply_in_transaction(self.base.settings,
                str(location), version, mode='confirm', captured_at='2026-10-09T12:00:00Z',
                reread=inputs.rereader(LocationId('disk', None, 'disk'), 'downstream', None))
            inputs.verify()
        return reply


# Archived complete imports; restore needed names in their original scope, not at this file tail.
