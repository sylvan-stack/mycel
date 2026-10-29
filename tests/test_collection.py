# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Partial configured-store proofs for guarded collection, without claims."""
import unittest
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel import _evidence as evidence
from mycel._capture import capture_repository
from mycel._collection import CollectionStore
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._resolver import SourceResolver

try:
    from . import test_located_reconciliation as located_fixtures
except ImportError:
    import test_located_reconciliation as located_fixtures


class CollectionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        helper = located_fixtures.LocatedReconciliationStoreTests()
        helper.store_fixture = self.store_fixture
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper
        self.code, self.artifact, self.settings = helper.code, helper.artifact, helper.settings

    def connect(self):
        return self.helper.connect()

    def state(self, connection):
        tables = ('mycel_files', 'mycel_file_versions', 'mycel_file_locations', 'mycel_chunks',
            'mycel_chunk_versions', 'mycel_locations', 'mycel_dependencies', 'mycel_edges',
            'mycel_snapshots', 'mycel_manifests', 'mycel_evidence_owners', 'mycel_evidence_references',
            'mycel_verifications', 'mycel_drifts', 'mycel_classification_work', 'mycel_embedding_plans', 'mycel_vectors')
        return {name: connection.execute(f'SELECT to_jsonb(t) FROM public.{name} t ORDER BY to_jsonb(t)::text').fetchall()
                for name in tables}

    def apply(self, connection, *, collect=True, confirm_empty=False):
        manifest = capture_repository(self.settings, 'fixture')
        collected = []
        callback = None if not collect else lambda current, result: collected.append(
            CollectionStore(current).collect_in_transaction(self.settings, manifest))
        result = LocatedCaptureStore(connection).apply(self.settings, manifest,
            batch_handoff=callback, confirm_empty=confirm_empty)
        return result, collected

    def pin(self, connection, *, dependant='fixture:@artifact/answer.md#Answer', source='fixture:@artifact/source.md#Source'):
        catalog = SourceResolver.from_store(connection, self.settings)
        selected = catalog.resolve(dependant, purpose='endpoint').selection
        resolution = catalog.resolve(source)
        observed = evidence.PinInputs(self.settings, selected.members[0], selected.file, resolution.selection,
            evidence.CaptureLocation('disk'), resolution, catalog)
        identifier = uuid4()
        baseline = evidence.EvidenceStore(connection).pin(observed, lambda: observed, dependency_id=identifier,
            kind='asserted', declaration=source, captured_at='2026-10-09T12:00:00Z', authorization='initial_resolution')
        owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0]
        return identifier, baseline, owner, observed

    def docs(self):
        (self.artifact / 'answer.md').write_bytes(b'# Answer\nAn answer.\n')
        (self.artifact / 'source.md').write_bytes(b'# Source\nOriginal source.\n')


    def classification(self, connection, dependency, *, baseline=None):
        owner, work = uuid4(), uuid4()
        raw = b'Exact independent classification evidence.'
        digest = sha256(raw).hexdigest()
        connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
            ('fixture', digest, raw, Jsonb({})))
        connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
            (owner, 'fixture', 'classification', str(work)))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
            (owner, 'fixture', digest))
        if baseline is not None:
            connection.execute('INSERT INTO public.mycel_evidence_references '
                'SELECT %s,repository,snapshot_hash,manifest_hash,ordinal+1 FROM public.mycel_evidence_references WHERE owner=%s',
                (owner, baseline))
        connection.execute('INSERT INTO public.mycel_classification_work VALUES (%s,%s,%s,NULL,%s,%s)',
            (work, 'fixture', dependency, Jsonb({}), owner))
        return owner, work, digest



# Archived complete imports; restore needed names in their original scope, not at this file tail.
