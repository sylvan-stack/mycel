# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured proofs for exact public assertion and withdrawal commands."""
from hashlib import sha256
import io
import json
from unittest.mock import patch

from psycopg.types.json import Jsonb
from mycel._activity import MutationActivity, activity_state
from mycel._cli import Invocation, parse, run
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._locks import atomic_transaction, operation_guard
from mycel._settings import load_settings

import unittest
from contextlib import ExitStack

from mycel._capture import capture_repository
from mycel._derive import DeriveStore
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import operation_guard
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class DeriveCliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class DeriveStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize(b'---\nrole: authored\n---\n# Guide\nOriginal dependant.\n\n## Other\nOther body.\n')
        self.source = self.base.artifact / 'source.md'
        self.source_bytes = b'# Source\nOriginal source.\n'
        self.source.write_bytes(self.source_bytes)
        self.other = self.base.artifact / 'other.md'
        self.other.write_bytes(b'# Other source\nIndependent source.\n')
        self.code = self.base.code / 'policy.py'
        self.code.write_bytes(b'class Policy:\n    """Governing policy."""\n    def apply(self):\n        return 1\n')
        self.base.commit()
        self.dependant = 'fixture:@artifact/guide.md#Guide'
        self.ref = 'fixture:@artifact/source.md#Source'

    def guards(self, connection):
        stack = ExitStack()
        stack.enter_context(checked_store(connection))
        for repository in sorted(self.base.settings.values['repos']):
            stack.enter_context(operation_guard(connection, repository, 'pass'))
        return stack

    def publish(self, connection, repository='fixture'):
        manifest = capture_repository(self.base.settings, repository)
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.base.settings, manifest,
                batch_handoff=LocatedDependencyProducer(self.base.settings, captured_at='2026-10-09T11:00:00Z',
                    settings_home=self.base.base, collection_manifest=manifest))

    def derive(self, connection, source=None, **kwargs):
        return DeriveStore(connection).apply(self.base.settings, self.dependant, source or self.ref,
            captured_at='2026-10-09T11:30:00Z', settings_home=self.base.base, build=0xDA, **kwargs)

    def dependencies(self, connection):
        return connection.execute("""SELECT d.id,d.dependant_version,d.kind,d.declaration,d.source_place,d.state,
            d.baseline_owner,r.manifest_hash,d.xmin::text FROM public.mycel_dependencies d
            LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
            ORDER BY d.kind,d.id""").fetchall()

    def state(self, connection):
        tables = ('mycel_file_versions', 'mycel_file_locations', 'mycel_chunks', 'mycel_chunk_versions',
                  'mycel_locations', 'mycel_dependencies', 'mycel_edges', 'mycel_ref_faults',
                  'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_snapshots',
                  'mycel_manifests', 'mycel_activity')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in tables}

    def role(self, connection):
        return connection.execute("""SELECT l.metadata->>'role' FROM public.mycel_locations l
            JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
            WHERE l.kind='disk' AND l.metadata->>'name'='Guide'""").fetchone()[0]


# Archived complete imports; restore needed names in their original scope, not at this file tail.
