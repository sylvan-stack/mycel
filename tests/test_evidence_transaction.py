"""Evidence applies within a caller's complete native file/activity change."""

import json
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4
import unittest

from psycopg.types.json import Jsonb

from mycel import _evidence as evidence
from mycel._activity import AppliedMutation, MutationActivity
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver

try:
    from . import test_evidence as fixtures
except ImportError:
    import test_evidence as fixtures


class EvidenceTransactionStoreTests(unittest.TestCase):
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

    @proves('MYC-16.5', 'MYC-16.13', kind='store')
    def test_new_file_versions_exact_evidence_and_activity_publish_in_one_transaction(self):
        with self.connect() as connection, self.connect() as reader:
            _, observed, writer = self.prepare(connection)
            rows = self.reserve_rows(connection)
            dependency = uuid4()
            with MutationActivity(connection, build=7).session() as activity, evidence.checked_input_guard(
                    connection, observed, lambda: observed) as token:
                def apply(current):
                    self.insert_rows(current, rows)
                    baseline = self.pin(writer, token, dependency=dependency)
                    self.assertEqual(self.counts(reader), (0,) * 8)
                    self.assertEqual(json.loads(current.execute(
                        'SELECT bytes FROM public.mycel_manifests WHERE hash=%s', (baseline,)).fetchone()[0])['dependantVersion'],
                        str(observed.dependant.chunk.version))
                    return AppliedMutation(True, {'pinned': 1})
                activity.apply('owner', 'ingest', apply)
                activity.finish('done', counts={('owner', 'ingest'): {'pinned': 1}})
            self.assertEqual(self.counts(reader), (2, 2, 2, 1, 1, 3, 1, 1))
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (dependency,)).fetchone()[0]
            self.assertIsNotNone(owner)

    @proves('MYC-16.5', 'MYC-16.13', kind='store')
    def test_evidence_or_activity_failure_rolls_back_new_file_rows_and_all_owners(self):
        with self.connect() as connection:
            _, observed, writer = self.prepare(connection)
            rows = self.reserve_rows(connection)
            for fault in ('evidence', 'activity'):
                with self.subTest(fault=fault), MutationActivity(connection, build=7).session() as activity, evidence.checked_input_guard(
                        connection, observed, lambda: observed) as token:
                    def apply(current):
                        self.insert_rows(current, rows)
                        self.pin(writer, token)
                        if fault == 'evidence':
                            raise RuntimeError('public fixture caller failed after writing its baseline')
                        return AppliedMutation(True, {'pinned': 1})
                    if fault == 'activity':
                        with patch.object(activity, '_details', side_effect=MycelError('internal', 'public fixture audit failure')):
                            with self.assertRaises(MycelError):
                                activity.apply('owner', 'ingest', apply)
                    else:
                        with self.assertRaises(RuntimeError):
                            activity.apply('owner', 'ingest', apply)
                    self.assertEqual(self.counts(connection), (0,) * 8)
                    activity.finish('failed', error={'code': 'internal', 'message': 'public fixture outcome'})

    @proves('MYC-16.5', 'MYC-16.13', kind='store')
    def test_idle_expired_foreign_and_aborted_transaction_tokens_refuse_before_writes(self):
        with self.connect() as connection, self.connect() as other:
            helper, observed, writer = self.prepare(connection)
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with self.assertRaises(evidence.EvidenceError):
                    self.pin(writer, token)
                with atomic_transaction(other), self.assertRaises(evidence.EvidenceError):
                    self.pin(evidence.EvidenceStore(other), token)
                with self.assertRaises(MycelError), atomic_transaction(connection):
                    try:
                        connection.execute('SELECT 1/0')
                    except Exception:
                        with self.assertRaises(evidence.EvidenceError):
                            self.pin(writer, token)
                        raise
            with atomic_transaction(connection), self.assertRaises(evidence.EvidenceError):
                self.pin(writer, token)
            self.assertEqual(self.counts(connection), before)

    @proves('MYC-16.5', 'MYC-16.13', kind='store')
    def test_capture_rechecks_new_version_bytes_and_existing_baseline_owner(self):
        with self.connect() as connection:
            helper, observed, writer = self.prepare(connection)
            dependency = uuid4()
            original = helper.pin(writer, observed, dependency=dependency)
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    self.pin(writer, token, dependency=dependency)
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    connection.execute('UPDATE public.mycel_chunk_versions SET source_bytes=%s,snapshot_hash=%s,text=%s WHERE id=%s',
                        (b'changed exact bytes', sha256(b'changed exact bytes').hexdigest(), 'changed exact bytes',
                         observed.dependant.chunk.version))
                    self.pin(writer, token)
            self.assertEqual(self.counts(connection), before)
            self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)

    @proves('MYC-2.26', 'MYC-16.5', 'MYC-16.6', kind='store')
    def test_inheritance_copies_selected_old_evidence_without_current_source_in_caller_transaction(self):
        with self.connect() as connection:
            helper, observed, writer = self.prepare(connection)
            previous = uuid4()
            original_id = helper.pin(writer, observed, dependency=previous)
            original = writer.read_baseline('owner', original_id)
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            catalog = SourceResolver.from_store(connection, observed.settings)
            selection = catalog.resolve(observed.dependant.place.address, purpose='endpoint').selection
            inputs = evidence.InheritanceInputs(observed.settings, selection.members[0], selection.file,
                evidence.CaptureLocation('disk'), catalog.resolve(observed.resolution.declaration), catalog)
            before = self.counts(connection)
            dependency = uuid4()
            with evidence.checked_input_guard(connection, inputs, lambda: inputs) as token:
                with atomic_transaction(connection):
                    inherited_id = writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=dependency, authorization='normalized_equivalent_edit')
                with self.assertRaises(RuntimeError), atomic_transaction(connection):
                    writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=uuid4(), authorization='normalized_equivalent_edit')
                    raise RuntimeError('public fixture graph failure')
            inherited = writer.read_baseline('owner', inherited_id)
            self.assertEqual(inherited.manifest.payload['members'], original.manifest.payload['members'])
            self.assertEqual(inherited.manifest.payload['pinnedHash'], original.manifest.payload['pinnedHash'])
            self.assertEqual(self.counts(connection)[-2], before[-2] + 1)
            self.assertEqual(writer.read_baseline('owner', original_id), original)

    @proves('MYC-16.5', 'MYC-16.6', kind='store')
    def test_inheritance_locks_and_validates_complete_prior_owning_graph(self):
        with self.connect() as connection, self.connect() as blocker:
            helper, observed, writer = self.prepare(connection)
            previous = uuid4()
            original_id = helper.pin(writer, observed, dependency=previous)
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone()[0]
            before = self.counts(connection)
            with evidence.checked_input_guard(connection, observed, lambda: helper.observe(connection, observed)) as token:
                with blocker.transaction():
                    blocker.execute('SELECT hash FROM public.mycel_manifests WHERE hash=%s FOR UPDATE', (original_id,))
                    with self.assertRaises(MycelError) as error, atomic_transaction(connection):
                        writer.inherit_in_transaction(token, previous_dependency=previous,
                            dependency_id=uuid4(), authorization='normalized_equivalent_edit')
                    self.assertEqual(error.exception.code.value, 'busy')
                with self.assertRaises(evidence.EvidenceError), atomic_transaction(connection):
                    connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND ordinal>0', (owner,))
                    writer.inherit_in_transaction(token, previous_dependency=previous,
                        dependency_id=uuid4(), authorization='normalized_equivalent_edit')
            self.assertEqual(self.counts(connection), before)
