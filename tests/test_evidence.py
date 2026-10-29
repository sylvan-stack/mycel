# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Pure comparison checks, SQL seams, and separate native fixture checks.

The native methods are acceptance candidates. Declaring a store requirement
does not claim it in the Build; exploratory probes remain separate evidence.
"""
from dataclasses import replace
from hashlib import sha256

from mycel._errors import MycelError
from mycel._markdown import split_markdown, COMPARISON_REVISION, UNICODE_VERSION


import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg import pq
from psycopg.types.json import Jsonb

from mycel import _evidence as evidence
from mycel._markdown import split_markdown
from mycel._resolver import ResolvedChunk, ResolvedFile, SelectionMember, SourceResolver
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress


def settings(*, enabled=True):
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({
        'repos': {'owner': {'enabled': enabled}, 'source': {'enabled': True}}, 'store': {}}), True, True)


def document(repository, path, text, *, version=1, identifier=None):
    parsed = split_markdown(text)
    primary = SourceAddress(repository, 'artifact', path)
    chunks = tuple(ResolvedChunk(identifier or str(uuid5(NAMESPACE_URL, f'{repository}:{path}:{chunk.name}')),
                   version + number, chunk.name, 'document', chunk.text.encode(), chunk.snapshot_hash,
                   (chunk.span.byte_start, chunk.span.byte_end), chunk.title, None,
                   evidence.document_comparisons(chunk.body, chunk.title or ''), chunk.body.encode(),
                   (len(chunk.text.encode()) - len(chunk.body.encode()), len(chunk.text.encode())))
                   for number, chunk in enumerate(parsed.chunks))
    return ResolvedFile(str(uuid5(NAMESPACE_URL, f'file:{repository}:{path}')), repository, primary, (primary,),
                        parsed.source, parsed.file_hash, chunks)


def member(file, number=0):
    return SelectionMember(SourceAddress(file.repository, file.primary.root, file.primary.path,
                                         file.chunks[number].name), file.chunks[number])


def inputs(*, source='# Source\nExact source.\n', dependant='# Answer\nExact answer.\n',
           whole=False, source_version=11, dependant_version=1, location=None, enabled=True):
    dep = document('owner', 'answer.md', dependant, version=dependant_version)
    src = document('source', 'source.md', source, version=source_version)
    snapshot = settings(enabled=enabled)
    resolver = SourceResolver(snapshot, (dep, src))
    resolution = resolver.resolve('source:source.md' if whole else 'source:source.md#Source')
    return evidence.PinInputs(snapshot, member(dep), dep, resolution.selection,
                              location or evidence.CaptureLocation('disk'), resolution, resolver,
                              _freeze({'locationIdentity': 'disk'}))


def capture(observation, **kwargs):
    return evidence.capture_baseline('owner', observation.dependant, observation.dependant_file,
            observation.selection, kind='declared', declaration=observation.resolution.declaration,
            captured_at='2026-10-09T00:00:00Z', location=observation.location, **kwargs)


class EvidenceUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class EvidenceConnection:
    """Transactional SQL seam, never a substitute for native store acceptance."""
    def __init__(self, observed):
        self.autocommit = True
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)
        self.snapshots, self.manifests, self.owners, self.refs, self.dependencies = {}, {}, {}, {}, {}
        self.versions, self.files = {}, {}
        self.sql, self.guards, self.events = [], [], []
        self.seed(observed)

    def seed(self, observed):
        for file in (observed.dependant_file, observed.selection.file):
            self.files[(file.identifier, file.snapshot_hash)] = (file.repository, file.source)
            for chunk in file.chunks:
                self.versions[chunk.version] = (chunk.version, UUID(chunk.identifier), file.repository,
                                               UUID(file.identifier), chunk.snapshot_hash, chunk.source, dict(chunk.comparison))

    @contextmanager
    def transaction(self):
        saved = deepcopy((self.snapshots, self.manifests, self.owners, self.refs, self.dependencies))
        self.info.transaction_status = pq.TransactionStatus.INTRANS
        self.events.append('begin')
        try:
            yield
        except BaseException:
            self.snapshots, self.manifests, self.owners, self.refs, self.dependencies = saved
            self.events.append('rollback')
            raise
        else:
            self.events.append('commit')
        finally:
            self.info.transaction_status = pq.TransactionStatus.IDLE

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        args = tuple(json.loads(evidence.canonical_json(value.obj)) if isinstance(value, Jsonb) else value for value in params)
        if sql.startswith('SET '):
            return Rows()
        if sql == evidence._VERSIONS_SQL:
            return Rows(self.versions[key] for key in args[0] if key in self.versions)
        if sql in {evidence._INHERITANCE_VERSION_READ_SQL, evidence._INHERITANCE_VERSION_SQL}:
            return Rows([self.versions[args[0]]] if args[0] in self.versions else [])
        if sql == evidence._FILE_VERSION_SQL:
            return Rows([self.files[args]] if args in self.files else [])
        if sql == evidence._INSERT_SNAPSHOT_SQL:
            self.snapshots.setdefault(args[:2], args[2:])
            return Rows()
        if sql in {evidence._SNAPSHOT_SQL, evidence._SNAPSHOT_LOCK_SQL}:
            return Rows([self.snapshots[args]] if args in self.snapshots else [])
        if sql == evidence._INSERT_MANIFEST_SQL:
            self.manifests.setdefault(args[:2], args[2:])
            return Rows()
        if sql in {evidence._MANIFEST_SQL, evidence._MANIFEST_LOCK_SQL}:
            return Rows([self.manifests[args]] if args in self.manifests else [])
        if sql == evidence._INSERT_OWNER_SQL:
            self.owners.setdefault(args[1:], args[0])
            return Rows()
        if sql == evidence._OWNER_ID_SQL:
            return Rows([(self.owners[args],)])
        if sql in {evidence._INHERITANCE_OWNER_READ_SQL, evidence._INHERITANCE_OWNER_SQL}:
            return Rows(key for key, identifier in self.owners.items() if identifier == args[0])
        if sql in {evidence._REFERENCES_SQL, evidence._INHERITANCE_REFERENCES_SQL}:
            return Rows(sorted(self.refs.get(args, [])))
        if sql == evidence._INSERT_REFERENCE_SQL:
            self.refs.setdefault(args[:2], []).append((args[4], args[2], args[3]))
            return Rows()
        if sql in {evidence._DEPENDENCY_SQL, evidence._DEPENDENCY_READ_SQL}:
            return Rows([self.dependencies[args[0]]] if args[0] in self.dependencies else [])
        if sql == evidence._INSERT_DEPENDENCY_SQL:
            self.dependencies[args[0]] = args[1:6] + (args[7],)
            return Rows()
        if sql == evidence._UPDATE_DEPENDENCY_SQL:
            self.dependencies[args[1]] = self.dependencies[args[1]][:5] + (args[0],)
            return Rows()
        if sql == evidence._RELEASE_OWNER_SQL:
            owner, repository = args
            if not any(row[-1] == owner for row in self.dependencies.values()):
                for key, identifier in list(self.owners.items()):
                    if identifier == owner and key[0] == repository:
                        del self.owners[key]
                self.refs.pop((owner, repository), None)
            return Rows()
        if sql in {evidence._COLLECT_SNAPSHOTS_SQL, evidence._COLLECT_MANIFESTS_SQL}:
            blobs = self.snapshots if sql == evidence._COLLECT_SNAPSHOTS_SQL else self.manifests
            position = 1 if blobs is self.snapshots else 2
            for key in list(blobs):
                if key[0] == args[0] and not any(ref_key[1] == key[0] and any(row[position] == key[1] for row in rows)
                                                for ref_key, rows in self.refs.items()):
                    del blobs[key]
            return Rows()
        if sql == evidence._OWNED_SNAPSHOT_SQL:
            return Rows([(1,)] if any(key[1] == args[0] and any(row[1] == args[1] for row in rows)
                                      for key, rows in self.refs.items()) else [])
        raise AssertionError(sql)


class EvidenceSQLTests(unittest.TestCase):
    def setUp(self):
        self.observed = inputs()
        self.connection = EvidenceConnection(self.observed)
        self.store = evidence.EvidenceStore(self.connection)
        self.patchers = [patch.object(evidence, 'checked_store', self.checked),
                         patch.object(evidence, 'operation_guard', self.operation),
                         patch.object(evidence, 'read_snapshot', self.read)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)


    @contextmanager
    def checked(self, connection):
        connection.events.append('checked')
        yield

    @contextmanager
    def operation(self, connection, repository, operation):
        connection.guards.append(repository)
        try:
            yield
        finally:
            connection.guards.remove(repository)

    @contextmanager
    def read(self, connection):
        yield

    def pin(self, *, reread=None, identifier=None, **kwargs):
        return self.store.pin(self.observed, reread or (lambda: self.observed), dependency_id=identifier or uuid4(),
               kind='declared', declaration=kwargs.pop('declaration', self.observed.resolution.declaration),
               captured_at=kwargs.pop('captured_at', '2026-10-09T00:00:00Z'),
               authorization=kwargs.pop('authorization', 'initial_resolution'), **kwargs)


class EvidenceStoreTests(unittest.TestCase):
    check_kind = "store"

    def seed(self, connection, observed):
        for file in (observed.dependant_file, observed.selection.file):
            connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                               (file.repository, Jsonb([])))
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                               (UUID(file.identifier), file.repository, file.primary.root, file.primary.path, 'documents'))
            file_version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
                    'ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
                    (uuid4(), UUID(file.identifier), file.snapshot_hash, file.source, Jsonb({}))).fetchone()[0]
            location = observed.location.kind
            identity = observed.location.commit or 'disk'
            file_location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
                    (uuid4(), file_version, location, identity, Jsonb({}))).fetchone()[0]
            for chunk in file.chunks:
                connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                        (UUID(chunk.identifier), file.repository, UUID(file.identifier), chunk.kind, Jsonb({})))
                body_start = len(chunk.source) - len(chunk.body)
                metadata = {'name':chunk.name,'kind':chunk.kind,'title':chunk.title,'span':{'start':chunk.span[0],'end':chunk.span[1]},
                            'bodySpan': {'start':body_start,'end':len(chunk.source)}}
                number = connection.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
                        'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (chunk_id,snapshot_hash) '
                        'DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
                        (UUID(chunk.identifier),chunk.snapshot_hash,chunk.source,chunk.source.decode().replace('\0','\ufffd'),
                         Jsonb(json.loads(evidence.canonical_json(chunk.comparison))),Jsonb(metadata))).fetchone()[0]
                connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                        (uuid4(),number,file_location,location,identity,Jsonb({})))
        return self.observe(connection, observed)

    def observe(self, connection, previous):
        location = previous.location
        resolver = SourceResolver.from_store(connection, previous.settings, kind=location.kind, location=location.commit)
        dependant_selection = resolver.resolve(previous.dependant.place.address, purpose='endpoint').selection
        resolution = resolver.resolve(previous.resolution.declaration)
        return evidence.PinInputs(previous.settings, dependant_selection.members[0], dependant_selection.file,
                                  resolution.selection, location, resolution, resolver, previous.guards)

    def pin(self, writer, observed, *, dependency=None, reread=None):
        return writer.pin(observed, reread or (lambda: observed), dependency_id=dependency or uuid4(),
                          kind='declared', declaration=observed.resolution.declaration, captured_at='2026-10-09T00:00:00Z',
                          authorization='initial_resolution')


# Archived complete imports; restore needed names in their original scope, not at this file tail.
