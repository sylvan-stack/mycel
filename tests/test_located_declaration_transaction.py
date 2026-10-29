# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Prospective declaration/evidence adapters join complete capture publication.

These fixture producers do not claim the complete dependency executor. Pinned
declaration replacement intentionally refuses until identity policy is wired.
"""
import unittest
from contextlib import ExitStack

from mycel._capture import capture_repository
from mycel._declared_refs import DeclaredRefStore
from mycel._evidence import (
    CaptureLocation,
    EvidenceError,
    EvidenceStore,
    PinInputs,
    checked_transaction_input_guard,
)
from mycel._located_reconciliation import LocatedCaptureStore, location_key
from mycel._locks import operation_guard
from mycel._markdown import split_markdown
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._source_refs import read_document_declarations
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class LocatedDeclarationTransactionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedReconciliationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def prepare(self):
        self.fixture.initialize(b'---\nsources: ["fixture:@artifact/source.md#Source"]\n---\n# Guide\nPlain body.\n')
        (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nOld source.\n# Other\nOther body.\n')
        self.fixture.commit()

    def guards(self, connection):
        stack = ExitStack()
        stack.enter_context(checked_store(connection))
        for repository in sorted(self.fixture.settings.values['repos']):
            stack.enter_context(operation_guard(connection, repository, 'pass'))
        return stack

    def input(self, connection, located, ref, *, fresh=False):
        settings = self.fixture.settings
        if fresh:
            settings = load_settings(path=settings.file, home=self.fixture.base)
        catalog = SourceResolver.from_transaction(connection, settings, kind=located.location.kind,
                                                   location=location_key(located.location))
        file = next(file for file in catalog.files if file.identifier == located.binding.identifier)
        dependant = next(member for member in catalog._members(file, file.chunks) if member.chunk.version == ref.version)
        resolution = catalog.resolve(ref.declaration)
        if fresh:
            captured = capture_repository(settings, 'fixture')
            observed = next(location for location in captured.locations if location.id == located.location)
            if observed.commit != located.commit:
                raise EvidenceError('changed_since_ingest')
            for selected in (file, resolution.selection.file):
                candidates = [item for item in observed.files if any(
                    alias.root == selected.primary.root and alias.path == selected.primary.path for alias in item.aliases)]
                if len(candidates) != 1 or candidates[0].source != selected.source:
                    raise EvidenceError('changed_since_ingest')
        return PinInputs(settings, dependant, file, resolution.selection,
            CaptureLocation(located.location.kind, located.commit if located.location.kind != 'disk' else None),
            resolution, catalog)

    def producer(self, connection, result, *, before_pin=None, after=None):
        refs = DeclaredRefStore(connection)
        for located in result.files:
            catalog = SourceResolver.from_transaction(connection, self.fixture.settings,
                kind=located.location.kind, location=location_key(located.location))
            file = next(file for file in catalog.files if file.identifier == located.binding.identifier)
            if any(chunk.kind == 'document' for chunk in file.chunks):
                refs.retain_in_transaction(self.fixture.settings, located.binding.location,
                    read_document_declarations(split_markdown(file.source), file=file.primary.address))
        reply = refs.recheck_in_transaction(self.fixture.settings, repository='fixture')
        pinned = 0
        for ref in reply.refs:
            if ref.state != 'resolved':
                continue
            owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
                                       (ref.identifier,)).fetchone()[0]
            if owner is not None:
                continue
            located = next(file for file in result.files if file.binding.location == ref.location)
            expected = self.input(connection, located, ref)
            if before_pin:
                before_pin()
            with checked_transaction_input_guard(connection, expected,
                    lambda: self.input(connection, located, ref, fresh=True)) as token:
                EvidenceStore(connection).pin_in_transaction(token, dependency_id=ref.identifier, kind='declared',
                    declaration=ref.declaration, captured_at='2026-10-09T09:30:00Z', authorization='initial_resolution')
                pinned += 1
        final = refs.recheck_in_transaction(self.fixture.settings, repository='fixture')
        result.counts.update({'refsChecked': reply.checked + final.checked,
                             'refsChanged': reply.changed + final.changed,
                             'refFaults': len(final.faults), 'pinsCaptured': pinned})
        if after:
            after()

    def publish(self, connection, **kwargs):
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.fixture.settings,
                capture_repository(self.fixture.settings, 'fixture'), **kwargs)

    def rows(self, connection):
        return connection.execute('SELECT d.id,d.dependant_version,d.baseline_owner,r.manifest_hash '
            'FROM public.mycel_dependencies d JOIN public.mycel_evidence_references r '
            'ON r.owner=d.baseline_owner AND r.ordinal=0 ORDER BY d.id').fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
