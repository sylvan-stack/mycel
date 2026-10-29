# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Evidence applies within a caller's complete native file/activity change."""
import json
from hashlib import sha256
from unittest.mock import patch

from mycel._activity import AppliedMutation, MutationActivity
from mycel._errors import MycelError
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver


import unittest
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel import _evidence as evidence

try:
    from . import test_evidence as fixtures
except ImportError:
    import test_evidence as fixtures


class EvidenceTransactionStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def prepare(self, connection):
        helper = fixtures.EvidenceStoreTests()
        observed = helper.seed(connection, fixtures.inputs())
        return helper, observed, evidence.EvidenceStore(connection)

    def pin(self, writer, token, *, dependency=None, **kwargs):
        return writer.pin_in_transaction(token, dependency_id=dependency or uuid4(), kind='declared',
            declaration=token.inputs.resolution.declaration, captured_at='2026-10-09T08:45:00Z',
            authorization='initial_resolution', **kwargs)

    def counts(self, connection):
        tables = ('mycel_files', 'mycel_chunk_versions', 'mycel_snapshots', 'mycel_manifests',
                  'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_dependencies', 'mycel_activity')
        return tuple(connection.execute(f'SELECT count(*) FROM public.{table}').fetchone()[0] for table in tables)

    def reserve_rows(self, connection):
        # Retain the fixture's prospective identifier map; real ingest allocates
        # the map before evidence binding. Recreate these exact new rows inside
        # the checked caller transaction rather than committing them first.
        tables = ('mycel_files', 'mycel_file_versions', 'mycel_file_locations',
                  'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations')
        rows = {table: connection.execute(f'SELECT * FROM public.{table}').fetchall() for table in tables}
        connection.execute('DELETE FROM public.mycel_files')
        return rows

    def insert_rows(self, connection, rows):
        for table, records in rows.items():
            for record in records:
                values = tuple(Jsonb(value) if isinstance(value, (dict, list)) else value for value in record)
                override = ' OVERRIDING SYSTEM VALUE' if table == 'mycel_chunk_versions' else ''
                connection.execute(f'INSERT INTO public.{table}{override} VALUES (' + ','.join(['%s'] * len(values)) + ')', values)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
