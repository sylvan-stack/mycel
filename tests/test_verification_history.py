# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Native read-only reporting, logical lifetime and exact legacy migration."""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch

from psycopg.types.json import Jsonb
from mycel._errors import MycelError
from mycel._evidence import EvidenceError
from mycel._verification_reader import VerificationReader, validate_verification_record

import unittest

from mycel import _store as store
from mycel._capture import capture_repository
from mycel._collection import CollectionStore
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import snapshot_transaction
from mycel._verification import ConfirmationStore
from mycel._verification_reader import VerificationReader

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class VerificationHistoryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        helper = fixtures.LocatedReconciliationStoreTests()
        helper.store_fixture = self.store_fixture
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper
        self.settings, self.artifact = helper.settings, helper.artifact
        self.path = self.artifact / 'guide.md'
        self.path.write_bytes(b'# Guide\nOriginal text.\n')
        self.ref = 'fixture:@artifact/guide.md#Guide'

    def publish(self, connection, *, fail=False):
        capture = capture_repository(self.settings, 'fixture')
        def collect(current, result):
            CollectionStore(current).collect_in_transaction(self.settings, capture)
            if fail:
                raise RuntimeError('deliberate collection audit failure')
        return LocatedCaptureStore(connection).apply(self.settings, capture, batch_handoff=collect, confirm_empty=True)

    def confirm(self, connection, *, ref=None, at='2026-10-11T12:00:00Z'):
        return ConfirmationStore(connection).apply(self.settings, ref or self.ref, by='owner',
                                                   captured_at=at, settings_home=self.helper.base)

    def report(self, connection, *, history=False):
        with store.checked_store(connection), snapshot_transaction(connection):
            # PostgreSQL itself rejects writes during this complete reader.
            return VerificationReader(connection, self.settings).list_in_transaction('fixture', history=history)

    def records(self, connection):
        return connection.execute('SELECT id,repository,chunk_id,recorded_at,record,evidence_owner '
                                  'FROM public.mycel_verifications ORDER BY id').fetchall()

    def state(self, connection):
        tables = ('mycel_store', 'mycel_chunk_versions', 'mycel_chunks', 'mycel_verifications',
                  'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_snapshots',
                  'mycel_manifests', 'mycel_dependencies', 'mycel_relations', 'mycel_locations')
        return {table: connection.execute(f'SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
                for table in tables}

    def predecessor(self, connection):
        """Restore the precisely known format-1 shape, retaining valid data."""
        connection.execute('ALTER TABLE public.mycel_verifications ADD COLUMN chunk_version bigint')
        connection.execute("UPDATE public.mycel_verifications SET chunk_version=(record->'dependant'->>'versionId')::bigint")
        connection.execute('ALTER TABLE public.mycel_verifications ALTER COLUMN chunk_version SET NOT NULL')
        connection.execute('ALTER TABLE public.mycel_verifications ADD FOREIGN KEY (chunk_version) '
                           'REFERENCES public.mycel_chunk_versions(id) ON DELETE CASCADE')
        connection.execute('ALTER TABLE public.mycel_verifications DROP COLUMN chunk_id')
        connection.execute('ALTER TABLE public.mycel_repository_state DROP COLUMN pass_progress')
        connection.execute('DROP TABLE public.mycel_judgements')
        connection.execute('UPDATE public.mycel_store SET format=1')


# Archived complete imports; restore needed names in their original scope, not at this file tail.
