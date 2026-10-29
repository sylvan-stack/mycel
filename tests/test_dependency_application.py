# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured proofs for the location-owned guarded dependency executor.

Complete command behavior remains separate; these producers join one checked
publication or explicit caller transaction without spending provider quota.
"""
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
from mycel._locks import operation_guard
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class RetainedResolverUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class DependencyApplicationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedReconciliationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def prepare(self, *, declared=True, file_selection=False):
        declaration = 'fixture:@artifact/source.md' + ('' if file_selection else '#Source')
        raw = ('---\nrole: authored\nsources: ["' + declaration + '"]\n---\n') if declared else '---\nrole: authored\n---\n'
        self.fixture.initialize((raw + '# Guide\nPlain body.\n').encode())
        (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nOriginal source.\n')
        self.fixture.commit()

    def guards(self, connection):
        stack = ExitStack()
        stack.enter_context(checked_store(connection))
        for repository in sorted(self.fixture.settings.values['repos']):
            stack.enter_context(operation_guard(connection, repository, 'pass'))
        return stack

    def publish(self, connection):
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.fixture.settings,
                capture_repository(self.fixture.settings, 'fixture'),
                batch_handoff=LocatedDependencyProducer(self.fixture.settings,
                    captured_at='2026-10-09T10:00:00Z', settings_home=self.fixture.base))

    def guide(self, connection):
        return connection.execute("SELECT l.id,cl.chunk_version FROM public.mycel_file_locations l "
            "JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id "
            "JOIN public.mycel_locations cl ON cl.file_location=l.id WHERE l.kind='disk' "
            "AND l.metadata->>'path'='guide.md'").fetchone()

    def reread(self, connection, expected):
        settings = load_settings(path=self.fixture.settings.file, home=self.fixture.base)
        scope = expected.guards['dependencyApplication']
        base = SourceResolver.from_transaction(connection, settings, kind=scope['kind'], location=scope['locationKey'])
        catalog = RetainedDependencyResolver(base, expected.catalog.anchors, expected.catalog.syntax_faults)
        endpoint = catalog.resolve(expected.dependant.place.address, purpose='endpoint')
        resolution = catalog.resolve(expected.resolution.declaration)
        if endpoint.state != 'resolved':
            raise EvidenceError('changed_since_ingest')
        manifest = capture_repository(settings, 'fixture')
        places = [item for item in manifest.locations if item.id.kind == scope['kind']]
        indexed_files = (endpoint.selection.file,) + ((resolution.selection.file,) if resolution.selection else ())
        for file in indexed_files:
            current = [item for place in places for item in place.files if any(
                alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
            if len(current) != 1 or current[0].source != file.source:
                raise EvidenceError('changed_since_ingest')
        values = dict(settings=settings, dependant=endpoint.selection.members[0], dependant_file=endpoint.selection.file,
                      resolution=resolution, catalog=catalog)
        if isinstance(expected, PinInputs):
            if resolution.state != 'resolved':
                raise EvidenceError('changed_since_ingest')
            values['selection'] = resolution.selection
        return replace(expected, **values)

    def apply(self, connection, **kwargs):
        location, version = self.guide(connection)
        return DependencyApplicationStore(connection).apply_in_transaction(self.fixture.settings, str(location), version,
            captured_at='2026-10-09T10:30:00Z', reread=lambda expected: self.reread(connection, expected), **kwargs)

    def rows(self, connection):
        return connection.execute('SELECT id,dependant_version,declaration,source_place,state,baseline_owner '
            'FROM public.mycel_dependencies ORDER BY id').fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
