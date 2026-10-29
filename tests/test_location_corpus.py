# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Strict location corpus ownership and actual mixed disk/Git publication."""
import unittest
from hashlib import sha256

from mycel._capture import (
    CapturedFile,
    CapturedLocation,
    CaptureManifest,
    FileAlias,
    LocationId,
    capture_repository,
    parse_history_record,
)
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._markdown import split_markdown
from mycel._store import TABLES

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class LocationCorpusUnitTests(unittest.TestCase):
    def document(self):
        raw = b'# Guide\nExact retained body.\n'
        alias = FileAlias('artifact', 'guide.md')
        captured = CapturedFile(alias, (alias,), 'documents', raw, sha256(raw).hexdigest(), split_markdown(raw))
        policy = 'a' * 64
        metadata = {'root': alias.root, 'path': alias.path,
            'aliases': [{'root': alias.root, 'path': alias.path}],
            'parseHistory': parse_history_record(captured, policy)}
        row = ('file', alias.root, alias.path, 'code', 'location', 'version', raw, metadata)
        manifest = CaptureManifest('fixture', policy, (CapturedLocation(
            LocationId('disk', None, 'disk'), None, (captured,), True),), True)
        return captured, row, manifest


class LocationCorpusStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.raw = b'---\ngenerated: true\n---\n# Historical\nOriginal generated text.\n'
        self.generated = self.base.artifact / 'generated.md'
        self.generated.write_bytes(self.raw)
        (self.base.artifact / 'keeper.md').write_bytes(b'# Keeper\nIndependent document.\n')
        (self.base.code / 'keeper.py').write_bytes(b'def keeper():\n    return 1\n')
        self.source = self.base.artifact / 'source.md'
        self.source.write_bytes(b'# Source\nOriginal source.\n')
        self.base.git('init', '--initial-branch=fixture-main')
        self.commit = self.base.commit()

    def publish(self, connection, *, activity=None, **kwargs):
        manifest = capture_repository(self.base.settings, 'fixture')
        producer = LocatedDependencyProducer(self.base.settings, captured_at='2026-10-11T12:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest)
        return LocatedCaptureStore(connection).apply(self.base.settings, manifest,
            batch_handoff=producer, activity=activity, **kwargs)

    def state(self, connection):
        # Quiet repeats/failures preserve every feature and activity row,
        # including location metadata and xmin. Invocation liveness records
        # have their own lifecycle and are created by each activity session.
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                    'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
                if table.name not in ('mycel_invocations', 'mycel_lock_keys')}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
