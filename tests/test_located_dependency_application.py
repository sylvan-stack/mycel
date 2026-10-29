# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured proofs for identity-selected complete located policy production."""
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._declared_refs import _text
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._reconciliation import ReconciliationError
from mycel._settings import load_settings

import unittest

from mycel._capture import capture_repository
from mycel._evidence import EvidenceStore
from mycel._located_dependencies import LocatedDependencyProducer

try:
    from . import test_located_declaration_transaction as fixtures
except ImportError:
    import test_located_declaration_transaction as fixtures


class LocatedDependencyApplicationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedDeclarationTransactionStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.base = self.fixture.fixture

    def publish(self, connection, *, collect=False, **kwargs):
        producer = LocatedDependencyProducer(self.base.settings, captured_at='2026-10-09T10:00:00Z',
            settings_home=self.base.base, collection_manifest=(capture_repository(self.base.settings, 'fixture')
                                                              if collect else None))
        return self.fixture.publish(connection, batch_handoff=producer, **kwargs)

    def current(self, connection):
        rows = connection.execute("""SELECT d.id,d.dependant_version,d.declaration,d.state,d.baseline_owner,
            f.kind,r.manifest_hash FROM public.mycel_dependencies d
            JOIN public.mycel_file_locations f ON f.id=(d.state->'declarationLocation'->>'file')::uuid
            JOIN public.mycel_locations l ON l.file_location=f.id AND l.chunk_version=d.dependant_version
            LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
            WHERE d.kind='declared' ORDER BY f.kind,d.id""").fetchall()
        return {row[5]: row for row in rows}

    def manifest(self, connection, row):
        return EvidenceStore(connection).read_baseline('fixture', row[6]).manifest.payload


# Archived complete imports; restore needed names in their original scope, not at this file tail.
