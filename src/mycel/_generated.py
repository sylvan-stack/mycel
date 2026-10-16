"""Composable successful-text publication and retained generated pin evidence.

This is the store hook for the later summary tree publisher. The caller owns
the checked store, repository guards and transaction, and can add vectors or
other levels before committing. No command, model or embedding is started here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from ._capture import capture_repository
from ._errors import MycelError
from ._evidence import ComparisonRecord, EvidenceError, canonical_json, chunk_comparison
from ._locks import require_transaction_guards
from ._resolver import Resolution, SelectionMember, SourceResolver, SourceSelection
from ._source_refs import SourceAddress, parse_source_address
from ._store import exact_bytes
from ._summary_evidence import (GenerationEvidenceStore, GenerationLease, _KIND, _OWNER_SQL,
    _REFERENCES_SQL)
from ._summary_store import PublishedSummaryState, SummaryMemberPin, SummarySetMetadata

PIN_SCHEMA = 'mycel-generated-pin-v1'
OWNER_KIND = 'generated'
_NAME = re.compile(r'([1-5])/([1-9][0-9]*)\Z')


def _fail(status='snapshot_corrupt'):
    raise EvidenceError(status)


def generated_resolution(catalog, row):
    """Keep logical identity across moves; rejoin a deleted source at its place."""
    raw, identifier = row[4], row[6].get('memberId')
    current = [member for file in catalog.files for member in catalog._members(file, file.chunks)]
    current.extend(SelectionMember(place, chunk) for place, chunk in catalog.index)
    selected = [member for member in current if member.chunk.identifier == identifier]
    if len(selected) == 1:
        member = selected[0]
        file = next((file for file in catalog.files if member.chunk in file.chunks), None)
        return Resolution(raw, 'resolved', SourceSelection('index' if file is None else 'chunk',
            member.place, file, (member,)))
    return catalog.resolve(raw, purpose='read')


def generated_capture(connection, row):
    """Validate the complete permanent owner and its exact successful response."""
    identifier, repository, version, raw, natural, kind, state, owner, digest = row
    if (kind != 'generated' or not isinstance(state, dict) or set(state) != {
            'schema', 'manifest', 'requestManifest', 'memberId', 'memberOrdinal', 'dependantId'}
            or state['schema'] != PIN_SCHEMA or state['manifest'] != digest
            or type(state['memberOrdinal']) is not int or state['memberOrdinal'] < 0):
        _fail()
    lease_store = GenerationEvidenceStore(connection)
    capture = lease_store._read(repository, digest)
    request = lease_store._read(repository, state['requestManifest'])
    payload = json.loads(capture.manifest.canonical_bytes)
    if 'response' not in payload:
        _fail()
    original = dict(payload)
    original.pop('response')
    if canonical_json(original) != request.manifest.canonical_bytes:
        _fail()
    ordinal = state['memberOrdinal']
    if ordinal >= len(payload['members']):
        _fail()
    member = payload['members'][ordinal]
    if member['id'] != state['memberId'] or raw != member['place']['address'] or natural != raw:
        _fail()
    owned = connection.execute('SELECT repository,kind,identity,invocation FROM public.mycel_evidence_owners '
        'WHERE id=%s', (owner,)).fetchone()
    if owned != (repository, OWNER_KIND, str(owner), None):
        _fail()
    refs = connection.execute(_REFERENCES_SQL, (owner, repository)).fetchall()
    expected = [(None, digest), (None, state['requestManifest'])]
    expected += [(blob.evidence.hash, None) for blob in capture.snapshots]
    if refs != [(number, *ref) for number, ref in enumerate(expected)]:
        _fail()
    dependant = connection.execute('SELECT c.id,c.kind,c.file_id,v.snapshot_hash,v.source_bytes,v.metadata '
        'FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE v.id=%s',
        (version,)).fetchone()
    response = next(blob.source for blob in capture.snapshots if blob.evidence.hash == payload['response']['hash'])
    if (dependant is None or str(dependant[0]) != state['dependantId'] or dependant[1:3] != ('summary', None)
            or dependant[3] != payload['response']['hash'] or exact_bytes(dependant[4]) != response):
        _fail()
    current_locations = connection.execute("SELECT location,metadata,file_location FROM public.mycel_locations "
        "WHERE chunk_version=%s AND kind='index'", (version,)).fetchall()
    if current_locations:
        published = connection.execute('SELECT kind,state FROM public.mycel_generated_state WHERE chunk_id=%s',
            (dependant[0],)).fetchone()
        if published is None or published[0] != 'summary':
            _fail()
        try:
            summary = PublishedSummaryState.from_dict(published[1], repository=repository)
        except MycelError:
            _fail()
        expected_pins = tuple(SummaryMemberPin(item['id'], item['version'], item['source']['hash'],
            parse_source_address(item['place']['address'])) for item in payload['members'])
        if summary.chunk_version != version or summary.members != expected_pins:
            _fail()
        if len(current_locations) != 1:
            _fail()
        address, located, file_location = current_locations[0]
        if not isinstance(located, dict) or set(located) != {'name', 'path', 'level'}:
            _fail()
        name = located['name']
        if (not isinstance(name, str) or not _NAME.fullmatch(name) or located['path'] != 'summaries'
                or located['level'] != summary.level or int(name.split('/')[0]) != summary.level
                or file_location is not None or address != SourceAddress(repository, 'index', 'summaries', name).address):
            _fail()
        if dependant[5] != {'kind': 'summary', **located}:
            _fail()
    # Every request member must have exactly one generated pin with this owner.
    siblings = connection.execute('SELECT declaration,state FROM public.mycel_dependencies '
        "WHERE dependant_version=%s AND kind='generated' AND baseline_owner=%s ORDER BY state->>'memberOrdinal'",
        (version, owner)).fetchall()
    expected_states = [(item['place']['address'], {**state, 'memberId': item['id'], 'memberOrdinal': number})
                       for number, item in enumerate(payload['members'])]
    if sorted(canonical_json(item) for item in siblings) != sorted(canonical_json(item) for item in expected_states):
        _fail()
    return capture, member


def compare_generated(member, resolution):
    """Generation retains exact bytes; document detection compares its body."""
    from ._staleness import StaleReason
    natural = parse_source_address(member['place']['address'])
    if resolution.selection is None:
        if resolution.fault in {'missing_file', 'missing_name'}:
            return (StaleReason('source_removed', natural, 'generated'),)
        _fail('ref_fault')
    if len(resolution.selection.members) != 1:
        _fail('ref_fault')
    current = resolution.selection.members[0]
    if current.chunk.kind != member['kind']:
        _fail('ref_fault')
    if member['kind'] == 'document':
        old = ComparisonRecord.from_record(member['comparison']['body'])
        old.require_supported()
        changed = old != chunk_comparison(current.chunk)
    else:
        changed = member['source']['hash'] != current.chunk.snapshot_hash
    return (StaleReason('source_changed', current.place, 'generated'),) if changed else ()


@dataclass(frozen=True)
class GeneratedPublication:
    chunk_id: str
    chunk_version: int
    place: SourceAddress
    evidence_owner: UUID
    manifest_hash: str


class GeneratedPublicationStore:
    def __init__(self, connection):
        self.connection = connection
        self._checks = []
        self._detector = None

    def _current(self, settings, capture, guarded):
        settings.require_current()
        require_transaction_guards(self.connection, guarded)
        evidence = GenerationEvidenceStore(self.connection)
        evidence._inputs(capture)
        catalog = SourceResolver.from_transaction(self.connection, settings, guarded_repositories=guarded)
        generated_members = {item['id'] for item in capture.manifest.payload['members'] if item['kind'] == 'summary'}
        if generated_members:
            from ._summary_store import _published
            repository = capture.manifest.payload['ownerRepository']
            scoped = SourceResolver(settings, tuple(file for file in catalog.files if file.repository == repository),
                index=tuple((place, chunk) for place, chunk in catalog.index if place.repository == repository))
            current = {member.chunk.identifier: member for file in scoped.files for member in scoped._members(file, file.chunks)}
            current.update((chunk.identifier, SelectionMember(place, chunk)) for place, chunk in scoped.index)
            _, stale = _published(self.connection, scoped, current, repository)
            if generated_members & stale:
                _fail('stale_member')
        physical = []
        for item in capture.manifest.payload['members']:
            resolution = catalog.resolve(item['place']['address'], purpose='read')
            if resolution.selection is None or len(resolution.selection.members) != 1:
                _fail('inputs_changed')
            member = resolution.selection.members[0]
            if (member.chunk.identifier != item['id'] or member.chunk.version != item['version']
                    or member.chunk.snapshot_hash != item['source']['hash']):
                _fail('inputs_changed')
            if resolution.selection.file is not None:
                file = resolution.selection.file
                observed = capture_repository(settings, file.repository)
                actual = [source for source in observed.disk.files if any(
                    alias.root == file.primary.root and alias.path == file.primary.path for alias in source.aliases)]
                if (not observed.deletion_safe or len(actual) != 1 or actual[0].source != file.source
                        or sorted((alias.root, alias.path) for alias in actual[0].aliases) !=
                           sorted((alias.root, alias.path) for alias in file.aliases)):
                    _fail('inputs_changed')
                physical.append((file.identifier, file.source))
            elif self.connection.execute('SELECT EXISTS(SELECT 1 FROM public.mycel_stale_reasons '
                    'WHERE chunk_version=%s)', (member.chunk.version,)).fetchone() != (False,):
                _fail('stale_member')
        return tuple(physical)

    def publish_in_transaction(self, settings, invocation, lease: GenerationLease, *,
                               chunk_id: UUID, place: SourceAddress, level: int,
                               metadata: SummarySetMetadata, guarded_repositories: tuple[str, ...],
                               reserved_version: int | None = None):
        """Publish one produced response with complete request-owned pins.

        Requires exact active invocation, checked_store and all involved pass
        guards in the caller's transaction. The caller must call verify before
        committing after any vectors, other nodes, or audit callback are added.
        """
        if (not isinstance(lease, GenerationLease) or invocation != lease.invocation
                or not isinstance(chunk_id, UUID) or not isinstance(place, SourceAddress)
                or place.repository != lease.repository or place.root != 'index'
                or place.path != 'summaries' or not isinstance(place.name, str) or not _NAME.fullmatch(place.name)
                or type(level) is not int or int(place.name.split('/')[0]) != level
                or not isinstance(metadata, SummarySetMetadata)
                or (reserved_version is not None and (type(reserved_version) is not int or reserved_version < 1))
                or type(guarded_repositories) is not tuple or any(not isinstance(owner, str) for owner in guarded_repositories)):
            _fail('invalid_input')
        store = GenerationEvidenceStore(self.connection)
        store._invocation(invocation)
        identity = lease.identity
        if self.connection.execute(_OWNER_SQL, (lease.repository, _KIND, identity)).fetchone() != (
                lease.owner_id, lease.repository, _KIND, identity, invocation.id):
            _fail('invalid_input')
        capture = store._read(lease.repository, lease.manifest_hash)
        if 'response' not in capture.manifest.payload:
            _fail('invalid_input')
        refs = self.connection.execute(_REFERENCES_SQL, (lease.owner_id, lease.repository)).fetchall()
        expected = {(None, lease.request_manifest), *store._refs(capture)}
        if (len(refs) != len(expected) or [number for number, _, _ in refs] != list(range(len(refs)))
                or {(snap, manifest) for _, snap, manifest in refs} != expected):
            _fail()
        repository = lease.repository
        payload = capture.manifest.payload
        needed = {repository, *(item['place']['repository'] for item in payload['members'])}
        if needed != {repository} or not needed <= set(guarded_repositories):
            _fail('invalid_input')
        physical = self._current(settings, capture, guarded_repositories)
        if any(item['id'] == str(chunk_id) or (item['kind'] == 'summary' and
                int(item['place']['name'].split('/')[0]) >= level) for item in payload['members']):
            _fail('invalid_input')
        response = next(blob.source for blob in capture.snapshots if blob.evidence.hash == payload['response']['hash'])
        collisions = self.connection.execute('SELECT c.id FROM public.mycel_locations l '
            'JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version JOIN public.mycel_chunks c ON c.id=v.chunk_id '
            "WHERE c.repository=%s AND l.kind='index' AND l.metadata->>'path'=%s AND l.metadata->>'name'=%s",
            (repository, place.path, place.name)).fetchall()
        if any(identifier != chunk_id for identifier, in collisions):
            _fail('invalid_input')
        self.connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,%s) ON CONFLICT DO NOTHING',
            (chunk_id, repository, 'summary', Jsonb({})))
        if self.connection.execute('SELECT repository,file_id,kind FROM public.mycel_chunks WHERE id=%s FOR UPDATE NOWAIT',
                (chunk_id,)).fetchone() != (repository, None, 'summary'):
            _fail('invalid_input')
        values = (chunk_id, payload['response']['hash'], response, response.decode().replace('\0', '\ufffd'), Jsonb({}),
                  Jsonb({'kind': 'summary', 'name': place.name, 'path': place.path, 'level': level}))
        if reserved_version is None:
            version = self.connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT (chunk_id,snapshot_hash) DO UPDATE SET snapshot_hash=EXCLUDED.snapshot_hash RETURNING id',
                values).fetchone()[0]
        else:
            # A tree reserves identities without publishing any searchable row.
            # Retained higher requests already name this exact future version.
            if self.connection.execute('SELECT EXISTS(SELECT 1 FROM public.mycel_chunk_versions '
                    'WHERE id=%s OR chunk_id=%s)', (reserved_version, chunk_id)).fetchone() != (False,):
                _fail('invalid_input')
            version = self.connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(id,chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) OVERRIDING SYSTEM VALUE '
                'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id', (reserved_version, *values)).fetchone()[0]
        pins = tuple(SummaryMemberPin(item['id'], item['version'], item['source']['hash'],
            parse_source_address(item['place']['address'])) for item in payload['members'])
        state = PublishedSummaryState(version, level, pins, metadata)
        PublishedSummaryState.from_dict(state.to_dict(), repository=repository)
        self.connection.execute("DELETE FROM public.mycel_locations l USING public.mycel_chunk_versions v "
            "WHERE l.chunk_version=v.id AND v.chunk_id=%s AND l.kind='index'", (chunk_id,))
        self.connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,%s,%s,%s)',
            (uuid4(), version, 'index', place.address, Jsonb({'name': place.name, 'path': place.path, 'level': level})))
        self.connection.execute('INSERT INTO public.mycel_generated_state VALUES (%s,%s,%s,%s) '
            'ON CONFLICT (chunk_id) DO UPDATE SET kind=EXCLUDED.kind,state=EXCLUDED.state',
            (chunk_id, repository, 'summary', Jsonb(state.to_dict())))
        superseded = [row[0] for row in self.connection.execute("SELECT DISTINCT baseline_owner FROM public.mycel_dependencies "
            "WHERE dependant_version=%s AND kind='generated'", (version,)).fetchall()]
        self.connection.execute("DELETE FROM public.mycel_dependencies WHERE dependant_version=%s AND kind='generated'", (version,))
        owner = uuid4()
        self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
            (owner, repository, OWNER_KIND, str(owner)))
        permanent_refs = [(None, lease.manifest_hash), (None, lease.request_manifest)] + [
            (blob.evidence.hash, None) for blob in capture.snapshots]
        for number, (snapshot_hash, manifest_hash) in enumerate(permanent_refs):
            self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                (owner, repository, snapshot_hash, manifest_hash, number))
        for number, item in enumerate(payload['members']):
            identifier = uuid5(NAMESPACE_URL, f'mycel:generated:{version}:{item["id"]}')
            pin_state = {'schema': PIN_SCHEMA, 'manifest': lease.manifest_hash, 'requestManifest': lease.request_manifest,
                'memberId': item['id'], 'memberOrdinal': number, 'dependantId': str(chunk_id)}
            self.connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (identifier, repository, version, item['place']['address'], item['place']['address'],
                 'generated', Jsonb(pin_state), owner))
            self.connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (identifier, item['version']))
        self.connection.execute('DELETE FROM public.mycel_stale_reasons WHERE chunk_version=%s', (version,))
        for prior_owner in superseded:
            self.connection.execute("DELETE FROM public.mycel_evidence_owners o WHERE o.id=%s AND o.repository=%s "
                "AND o.kind='generated' AND o.invocation IS NULL "
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_dependencies d WHERE d.baseline_owner=o.id) '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_relations r WHERE r.baseline_owner=o.id) '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_verifications v WHERE v.evidence_owner=o.id) '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_drifts d WHERE d.evidence_owner=o.id) '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_classification_work w WHERE w.evidence_owner=o.id)',
                (prior_owner, repository))
        result = GeneratedPublication(str(chunk_id), version, place, owner, lease.manifest_hash)
        self._checks.append((settings, invocation, lease, capture, guarded_repositories, physical, result, state.to_dict()))
        # Generation answers its own direct pins and immediately recomposes
        # higher levels. The later tree publisher need not run a second pass.
        from ._staleness import DetectionGuards, MechanicalStalenessStore
        guards = DetectionGuards(guarded_repositories, {})
        detector = MechanicalStalenessStore(self.connection)
        _, _, pending = detector.apply_in_transaction(settings, repository, guards)
        if pending:
            _fail('inputs_changed')
        self._detector = (detector, settings, guards)
        self.verify_in_transaction()
        return result

    def verify_in_transaction(self):
        """Final exact guard after every caller-owned write and audit callback."""
        if self._detector is not None:
            detector, settings, guards = self._detector
            detector.verify_in_transaction(settings, guards)
        for settings, invocation, lease, capture, guarded, physical, result, state in self._checks:
            lease_store = GenerationEvidenceStore(self.connection)
            lease_store._invocation(invocation)
            identity = lease.identity
            if self.connection.execute(_OWNER_SQL, (lease.repository, _KIND, identity)).fetchone() != (
                    lease.owner_id, lease.repository, _KIND, identity, invocation.id):
                _fail('invalid_input')
            if self._current(settings, capture, guarded) != physical:
                _fail('inputs_changed')
            if self.connection.execute('SELECT kind,state FROM public.mycel_generated_state WHERE chunk_id=%s',
                    (result.chunk_id,)).fetchone() != ('summary', state):
                _fail()
            locations = self.connection.execute('SELECT l.chunk_version,l.file_location,l.kind,l.location,l.metadata '
                'FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version '
                "WHERE v.chunk_id=%s AND l.kind='index' ORDER BY l.id", (result.chunk_id,)).fetchall()
            if locations != [(result.chunk_version, None, 'index', result.place.address,
                    {'name': result.place.name, 'path': result.place.path, 'level': state['level']})]:
                _fail()
            colliding = self.connection.execute('SELECT c.id FROM public.mycel_locations l '
                'JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version JOIN public.mycel_chunks c ON c.id=v.chunk_id '
                "WHERE c.repository=%s AND l.kind='index' AND l.metadata->>'path'=%s AND l.metadata->>'name'=%s",
                (lease.repository, result.place.path, result.place.name)).fetchall()
            if colliding != [(UUID(result.chunk_id),)]:
                _fail()
            rows = self.connection.execute('SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,'
                'd.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d '
                'JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 '
                "WHERE d.dependant_version=%s AND d.kind='generated' ORDER BY d.id", (result.chunk_version,)).fetchall()
            if len(rows) != len(capture.manifest.payload['members']):
                _fail()
            for row in rows:
                observed, _ = generated_capture(self.connection, row)
                if observed != capture or row[7] != result.evidence_owner:
                    _fail()
                expected_version = capture.manifest.payload['members'][row[6]['memberOrdinal']]['version']
                if self.connection.execute('SELECT source_version FROM public.mycel_edges WHERE dependency=%s',
                        (row[0],)).fetchall() != [(expected_version,)]:
                    _fail()
