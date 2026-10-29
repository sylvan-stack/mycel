# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Real-store checks for source passes observing surviving foreign dependants."""
from hashlib import sha256
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._evidence import EvidenceError, EvidenceStore, PinInputs
from mycel._reconciliation import AssertedRemoval
from mycel._source_refs import SourceAddress

import json
import unittest
from contextlib import ExitStack
from dataclasses import replace

from mycel._capture import capture_repository
from mycel._dependency_application import (
    DependencyApplicationStore,
    RetainedDependencyResolver,
)
from mycel._evidence import EvidenceError, PinInputs
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import atomic_transaction, operation_guard
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class DependencySourceRefreshStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize(b'# Guide\nSource repository guide.\n')
        self.source = self.base.artifact / 'source.md'
        self.source_bytes = b'# Source\nOriginal governing source.\n'
        self.source.write_bytes(self.source_bytes)
        self.base.commit()
        self.downstream = self.base.base / 'downstream'
        self.downstream.mkdir()
        self.answer = self.downstream / 'answer.md'
        self.answer.write_bytes(b'---\nrole: authored\nsources: ["fixture:@artifact/source.md#Source"]\n---\n'
                                b'# Answer\nUnchanged dependant.\n')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.downstream]\nenabled=true\n'
                                    + 'artifact_root=' + json.dumps(str(self.downstream)) + '\n')
        self.reload()

    def reload(self):
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)

    def guards(self, connection):
        held = ExitStack()
        held.enter_context(checked_store(connection))
        for repository in sorted(self.base.settings.values['repos']):
            held.enter_context(operation_guard(connection, repository, 'pass'))
        return held

    def publish(self, connection, repository='fixture', *, collect=True, activity=None, reply_counts=None):
        manifest = capture_repository(self.base.settings, repository)
        producer = LocatedDependencyProducer(self.base.settings, captured_at='2026-10-09T11:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest if collect else None, activity=activity)
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.base.settings, manifest,
                batch_handoff=producer, activity=activity, reply_counts=reply_counts)

    def prepare(self, connection):
        self.publish(connection)
        self.publish(connection, 'downstream')
        return self.dependencies(connection)

    def dependencies(self, connection):
        return connection.execute("""SELECT d.id,d.dependant_version,d.kind,d.declaration,d.source_place,d.state,
            d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d
            LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
            WHERE d.repository='downstream' ORDER BY d.kind,d.id""").fetchall()

    def edges(self, connection):
        return connection.execute("""SELECT e.dependency,e.source_version FROM public.mycel_edges e
            JOIN public.mycel_dependencies d ON d.id=e.dependency WHERE d.repository='downstream'
            ORDER BY e.dependency,e.source_version""").fetchall()

    def role(self, connection):
        return connection.execute("""SELECT l.metadata->>'role' FROM public.mycel_locations l
            JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
            JOIN public.mycel_chunks c ON c.id=v.chunk_id
            WHERE c.repository='downstream' AND l.kind='disk'""").fetchone()[0]

    def pins(self, rows):
        return [(row[0], row[1], row[2], row[3], row[6], row[7]) for row in rows]

    def state(self, connection):
        tables = ('mycel_repository_state', 'mycel_files', 'mycel_file_aliases', 'mycel_file_versions',
                  'mycel_file_locations', 'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations',
                  'mycel_dependencies', 'mycel_edges', 'mycel_ref_faults', 'mycel_evidence_owners',
                  'mycel_evidence_references', 'mycel_snapshots', 'mycel_manifests', 'mycel_activity',
                  'mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
                                          'ORDER BY to_jsonb(t)::text').fetchall() for table in tables}


    def reread(self, connection, expected):
        settings = load_settings(path=self.base.config, home=self.base.base)
        scope = expected.guards['dependencyApplication']
        base = SourceResolver.from_transaction(connection, settings, kind=scope['kind'], location=scope['locationKey'])
        catalog = RetainedDependencyResolver(base, expected.catalog.anchors, expected.catalog.syntax_faults)
        endpoint = catalog.resolve(expected.dependant.place.address, purpose='endpoint')
        resolution = catalog.resolve(expected.resolution.declaration)
        if endpoint.state != 'resolved':
            raise EvidenceError('changed_since_ingest')
        for file in (endpoint.selection.file,) + ((resolution.selection.file,) if resolution.selection else ()):
            captured = capture_repository(settings, file.repository)
            matches = [item for place in captured.locations if place.id.kind == 'disk' for item in place.files
                       if any(alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
            if len(matches) != 1 or matches[0].source != file.source:
                raise EvidenceError('changed_since_ingest')
        values = dict(settings=settings, dependant=endpoint.selection.members[0], dependant_file=endpoint.selection.file,
                      resolution=resolution, catalog=catalog)
        if isinstance(expected, PinInputs):
            values['selection'] = resolution.selection
        return replace(expected, **values)

    def apply_assertions(self, connection, **kwargs):
        located = connection.execute("""SELECT l.id,cl.chunk_version FROM public.mycel_file_locations l
            JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations cl ON cl.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk'""").fetchone()
        with self.guards(connection), atomic_transaction(connection):
            return DependencyApplicationStore(connection).apply_in_transaction(self.base.settings, str(located[0]), located[1],
                captured_at='2026-10-09T11:00:00Z', reread=lambda expected: self.reread(connection, expected), **kwargs)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
