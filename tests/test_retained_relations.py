# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured acceptance for deleted-source relation retention and withdrawal.

Initial links are seeded with the real guarded evidence writer. Future relate,
verification and declaration producers retain ownership of their public flows.
"""
from hashlib import sha256
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._evidence import (CaptureLocation, EvidenceError, EvidenceStore, PinInputs,
    capture_baseline, checked_transaction_input_guard)

import unittest
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import (
    CaptureLocation,
    EvidenceStore,
    PinInputs,
    capture_baseline,
    checked_transaction_input_guard,
)
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver
from mycel._retained_relations import RetainedRelationStore

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class RetainedRelationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.fixture.answer.write_bytes(b'---\nrole: authored\n---\n# Answer\nUnchanged dependant.\n')
        self.ref = 'fixture:@artifact/source.md#Source'

    def endpoint(self, connection):
        return connection.execute("""SELECT l.id,c.chunk_version
            FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk' AND c.metadata->>'name'='Answer'""").fetchone()

    def relation(self, connection, identifier):
        return connection.execute("""SELECT id,repository,left_version,right_place,state,baseline_owner
            FROM public.mycel_relations WHERE id=%s""", (identifier,)).fetchone()

    def state(self, connection):
        return (self.fixture.state(connection), connection.execute("""SELECT to_jsonb(r),xmin::text
            FROM public.mycel_relations r ORDER BY id""").fetchall())

    def seed(self, connection, *, ownership='declared'):
        self.fixture.prepare(connection)
        identifier = str(uuid4())
        location, version = self.endpoint(connection)
        catalog = SourceResolver.from_store(connection, self.base.settings)
        endpoint = catalog.resolve('downstream:@artifact/answer.md#Answer', purpose='endpoint').selection
        resolution = catalog.resolve(self.ref)
        selection = resolution.selection
        inputs = PinInputs(self.base.settings, endpoint.members[0], endpoint.file, selection,
            CaptureLocation('disk'), resolution, catalog)
        checks = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        reread = checks.rereader(LocationId('disk', None, 'disk'), 'downstream', None)
        # The production rereader expects the complete retained resolver shape.
        from dataclasses import replace

        from mycel._dependency_application import RetainedDependencyResolver
        inputs = replace(inputs, catalog=RetainedDependencyResolver(catalog, {}),
            guards={'dependencyApplication': {'sourcePlaces': {self.ref: selection.place.address}}})
        capture = capture_baseline('downstream', endpoint.members[0], endpoint.file, selection,
            kind='related', declaration=self.ref, captured_at='2026-10-09T11:00:00Z', location=CaptureLocation('disk'))
        state = {'rawRef': self.ref, 'baselineRef': self.ref, 'ownership': ownership,
            'everResolved': True, 'anchor': selection.file.identifier if selection.kind == 'file'
                else selection.members[0].chunk.identifier,
            'declarationLocation': {'file': str(location), 'kind': 'disk', 'location': 'disk'}}
        with self.fixture.guards(connection), atomic_transaction(connection):
            with checked_transaction_input_guard(connection, inputs, lambda: reread(inputs)) as token:
                owner = EvidenceStore(connection)._write(token, capture, f'{identifier}:{capture.manifest.identifier}')
                connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,%s,%s)',
                    (identifier, 'downstream', version, selection.place.address, Jsonb(state), owner))
            checks.verify()
        self.apply(connection, identifier)
        return identifier, capture.manifest.identifier

    def apply(self, connection, identifier, **kwargs):
        location, version = self.endpoint(connection)
        checks = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            reply = RetainedRelationStore(connection).apply_in_transaction(self.base.settings, str(location), version,
                identifier, captured_at='2026-10-09T12:00:00Z',
                reread=checks.rereader(LocationId('disk', None, 'disk'), 'downstream', None), **kwargs)
            checks.verify()
        return reply


# Archived complete imports; restore needed names in their original scope, not at this file tail.
