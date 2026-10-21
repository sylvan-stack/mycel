"""Offline mechanical detection after complete located publication.

Current disk and generated index versions participate. Immutable
pins are read, never renewed. The authority graph retains every distinct
reason/path; relations supply direct reasons only. The publication caller owns
the transaction, exact source checks and activity.
"""
from __future__ import annotations

from collections import defaultdict, deque
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import json
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from ._dependency_application import RetainedDependencyResolver
from ._capture import FileAlias, capture_repository, file_from_parse_history
from ._declared_refs import _text
from ._errors import MycelError
from ._evidence import (ComparisonRecord, EvidenceError, EvidenceStore,
    _inheritance_version, _validate_inheritance, canonical_json)
from ._locks import operation_guard, read_snapshot, require_transaction_guards
from ._reconciliation import _comparison, _place_payload
from ._resolver import SourceResolver
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address, read_document_declarations


@dataclass(frozen=True)
class StaleNode:
    identifier: str
    version: int
    place: SourceAddress
    exempt: bool = False


@dataclass(frozen=True)
class StaleEdge:
    source: str
    dependant: str
    dependency: str
    kind: str


@dataclass(frozen=True)
class StaleReason:
    kind: str
    source: SourceAddress
    edge: str
    via: tuple[SourceAddress, ...] = ()

    def record(self):
        value = {'kind': self.kind, 'source': _place_payload(self.source), 'edge': self.edge}
        if self.via:
            value['via'] = [_place_payload(place) for place in self.via]
        return value


def _ordered(reasons):
    return tuple(sorted(set(reasons), key=lambda item:
        (item[1].kind == 'upstream_stale', item[1].source.address,
         tuple(place.address for place in item[1].via), item[1].kind, item[1].edge, item[0])))


def _stored_link(dependency, reason):
    # The store's dependency FK belongs to authoritative dependencies. A
    # relation remains identified in its reason without entering that graph.
    return str(dependency) if dependency is not None else reason.get('relation')


def compare_dependency(baseline: dict, resolution, natural: SourceAddress, kind: str):
    """Compare a validated immutable baseline with one current typed selection."""
    pinned = ComparisonRecord.from_record(baseline['selectionComparison'])
    pinned.require_supported()
    selection = resolution.selection
    reasons = []
    if selection is not None:
        if pinned != _comparison(selection):
            reasons.append(StaleReason('related_changed' if kind == 'related' else 'source_changed',
                                       selection.place, kind))
        if baseline['selection'] == 'family':
            ids = {member.chunk.identifier for member in selection.members}
            places = {member.place.address for member in selection.members}
            reasons.extend(StaleReason('source_removed', parse_source_address(member['place']['address']), kind)
                for member in baseline['members']
                if member.get('id') not in ids and member['place']['address'] not in places)
    elif resolution.fault in {'missing_file', 'missing_name'}:
        reasons.append(StaleReason('source_removed', natural, kind))
    return tuple(reasons)


def plan_staleness(nodes: tuple[StaleNode, ...], edges: tuple[StaleEdge, ...],
                   direct: dict[str, tuple[tuple[str, StaleReason], ...]]):
    """Return every direct/indirect reason without I/O or model work.

    Distinct dependency kinds and diamond paths survive. An exempt node has no
    reasons and passes none onward, while its own changed bytes may still be a
    direct comparison reason of a dependant. Related reasons stay on their own
    node. Corrupt authority cycles are refused; relations are absent from edges.
    """
    by_id = {node.identifier: node for node in nodes}
    if len(by_id) != len(nodes) or any(edge.source not in by_id or edge.dependant not in by_id
            or edge.kind not in {'declared', 'asserted', 'generated'} for edge in edges):
        raise MycelError('invalid_input', 'Mechanical detection requires exact authoritative current endpoints.')
    outgoing, incoming = defaultdict(list), dict.fromkeys(by_id, 0)
    for edge in sorted(set(edges), key=lambda item: (item.source, item.dependant, item.dependency, item.kind)):
        outgoing[edge.source].append(edge)
        incoming[edge.dependant] += 1
    ready = deque(sorted(identifier for identifier, count in incoming.items() if count == 0))
    reasons = {identifier: [] if node.exempt else list(direct.get(identifier, ()))
               for identifier, node in by_id.items()}
    processed = 0
    while ready:
        identifier = ready.popleft()
        processed += 1
        current = _ordered(reasons[identifier])
        reasons[identifier] = list(current)
        for edge in outgoing[identifier]:
            if not by_id[edge.dependant].exempt:
                reasons[edge.dependant].extend((edge.dependency, StaleReason('upstream_stale',
                    reason.source, edge.kind, (*reason.via, by_id[identifier].place)))
                    for _, reason in current if reason.edge != 'related')
            incoming[edge.dependant] -= 1
            if incoming[edge.dependant] == 0:
                ready.append(edge.dependant)
    if processed != len(nodes):
        raise MycelError('invalid_input', 'The current authoritative dependency graph contains a cycle.')
    return {identifier: _ordered(values) for identifier, values in reasons.items()}


_DEPENDENCIES = """SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,
    d.state,d.baseline_owner,r.manifest_hash
    FROM public.mycel_dependencies d
    JOIN public.mycel_locations c ON c.chunk_version=d.dependant_version AND c.kind='disk'
    JOIN public.mycel_file_locations l ON l.id=c.file_location AND l.kind='disk'
      AND l.id::text=d.state->'declarationLocation'->>'file'
    LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
    WHERE d.kind=ANY(ARRAY['declared','asserted']) AND d.repository=ANY(%s)
    ORDER BY d.repository,d.id"""
_RELATIONS = """SELECT r.id,r.repository,r.left_version,r.state->>'rawRef',r.right_place,'related',
    r.state,r.baseline_owner,e.manifest_hash
    FROM public.mycel_relations r
    JOIN public.mycel_locations c ON c.chunk_version=r.left_version AND c.kind='disk'
    JOIN public.mycel_file_locations l ON l.id=c.file_location AND l.kind='disk'
      AND l.id::text=r.state->'declarationLocation'->>'file'
    LEFT JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
    WHERE r.state->>'ownership'=ANY(ARRAY['declared','asserted']) AND r.repository=ANY(%s)
    ORDER BY r.repository,r.id"""
_NODES = """SELECT c.id,c.repository,v.id,l.id,l.metadata,f.metadata
    FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
    JOIN public.mycel_chunks c ON c.id=v.chunk_id
    JOIN public.mycel_file_locations f ON f.id=l.file_location AND f.kind='disk'
    WHERE l.kind='disk' AND c.repository=ANY(%s)
    UNION ALL
    SELECT c.id,c.repository,v.id,l.id,l.metadata,'{}'::jsonb
    FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
    JOIN public.mycel_chunks c ON c.id=v.chunk_id
    WHERE l.kind='index' AND c.file_id IS NULL AND c.kind<>'overview'
      AND c.repository=ANY(%s) ORDER BY 2,1,4"""


def _eligible(settings):
    return sorted(name for name, value in settings.values['repos'].items() if value['enabled'])


def _links(connection, eligible):
    generated = connection.execute('SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,'
        'd.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d '
        "JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version AND l.kind='index' "
        'LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 '
        "WHERE d.kind='generated' AND d.repository=ANY(%s) ORDER BY d.repository,d.id", (eligible,)).fetchall()
    return (tuple(connection.execute(_DEPENDENCIES, (eligible,)).fetchall()) +
            tuple(connection.execute(_RELATIONS, (eligible,)).fetchall()) + tuple(generated))


def _relation_evidence(connection, rows):
    """Observe exact related pin ownership without locking a busy owner."""
    owners = list({row[7] for row in rows if row[5] in {'related', 'generated'} and row[7] is not None})
    versions = list({row[2] for row in rows if row[5] in {'related', 'generated'}})
    return (
        tuple(connection.execute("""SELECT id,repository,kind,identity,invocation FROM public.mycel_evidence_owners
            WHERE id=ANY(%s) ORDER BY id""", (owners,)).fetchall()),
        tuple(connection.execute("""SELECT owner,repository,ordinal,snapshot_hash,manifest_hash
            FROM public.mycel_evidence_references WHERE owner=ANY(%s) ORDER BY owner,ordinal""",
            (owners,)).fetchall()),
        tuple(connection.execute("""SELECT v.id,c.id,c.repository,c.file_id,v.snapshot_hash,v.source_bytes,v.comparison,v.metadata
            FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
            WHERE v.id=ANY(%s) ORDER BY v.id""", (versions,)).fetchall()),
        tuple(connection.execute("""SELECT g.chunk_id,g.repository,g.kind,g.state FROM public.mycel_generated_state g
            JOIN public.mycel_chunk_versions v ON v.chunk_id=g.chunk_id WHERE v.id=ANY(%s) ORDER BY g.chunk_id""",
            (versions,)).fetchall()))


def _validate_relation(row, baseline, observed):
    owners, references, versions, _ = observed
    identifier, owner, version, _, natural, _, state, baseline_owner, _ = row
    owning = next((value[1:4] for value in owners if value[0] == baseline_owner), None)
    refs = tuple(value[2:] for value in references if value[:2] == (baseline_owner, owner))
    prior = next((value for value in versions if value[0] == version), None)
    _validate_inheritance(identifier, (owner, version, state.get('baselineRef', _raw(row)),
        natural, 'related', baseline_owner), baseline, owning, refs, _inheritance_version(prior))


def _raw(row):
    if row[5] == 'related':
        from ._relations import _relation_raw
        return _relation_raw(row[6])
    return _text(row[6]['rawRef']) if 'rawRef' in row[6] else row[3]


def _resolve(catalog, row):
    if row[5] == 'generated':
        from ._generated import generated_resolution
        return generated_resolution(catalog, row)
    raw = _raw(row)
    return RetainedDependencyResolver(catalog,
        {raw: row[6]['anchor']} if row[6].get('anchor') else {},
        endpoint_refs=(raw,) if row[5] == 'related' and row[6].get('endpoint') else ()).resolve(raw)


def _target(row):
    try:
        return parse_source_address(row[4] or _raw(row)).repository
    except SourceAddressError:
        return None


def _closure(seeds, edges):
    outgoing = defaultdict(set)
    for edge in edges:
        outgoing[edge.source].add(edge.dependant)
    selected, todo = set(seeds), list(seeds)
    while todo:
        for dependant in outgoing[todo.pop()]:
            if dependant not in selected:
                selected.add(dependant)
                todo.append(dependant)
    return selected


@dataclass
class DetectionGuards:
    writable: tuple[str, ...]
    pending: dict[str, str]
    original_affected: frozenset[str] = frozenset()
    original_related: frozenset[str] = frozenset()


@contextmanager
def detection_guards(connection, settings, repository):
    """Acquire only potentially affected owner locks without waiting.

    Current source rows can be replaced/deleted by the upcoming publication, so
    natural declarations also seed ownership. Exemptions are checked again in
    the prospective graph. Locks are acquired before the caller transaction.
    """
    eligible = _eligible(settings)
    catalog = SourceResolver.from_store(connection, settings)
    with read_snapshot(connection):
        rows = _links(connection, eligible)
        current = connection.execute(_NODES, (eligible, eligible)).fetchall()
        version_ids = {row[2]: str(row[0]) for row in current}
        edges = []
        for row in rows:
            selection = _resolve(catalog, row).selection
            if selection is not None and row[5] != 'related':
                edges.extend(StaleEdge(member.chunk.identifier, version_ids[row[2]], str(row[0]), row[5])
                             for member in selection.members)
    seeds = {str(row[0]) for row in current if row[1] == repository}
    seeds.update(version_ids[row[2]] for row in rows if row[5] != 'related' and _target(row) == repository)
    affected = _closure(seeds, edges)
    related = {version_ids[row[2]] for row in rows if row[5] == 'related' and _target(row) == repository}
    owners = {row[1] for row in current if str(row[0]) in affected | related} | {repository}
    pending, writable = {}, []
    with ExitStack() as held:
        for owner in sorted(owners):
            try:
                held.enter_context(operation_guard(connection, owner, 'pass'))
            except MycelError as error:
                if error.code != 'busy':
                    raise
                pending[owner] = 'busy'
            else:
                writable.append(owner)
        yield DetectionGuards(tuple(writable), pending, frozenset(affected), frozenset(related))


class MechanicalStalenessStore:
    def __init__(self, connection, snapshot=None):
        self.connection = connection
        self._signature = None
        self._physical = None
        self._scope = None
        # A complete pass publishes the capture it read (MYC-1.37): its own
        # repository is observed through that capture, every other one once.
        self._snapshot = snapshot
        self._captures = None if snapshot is None else {snapshot.repository: snapshot}

    def _read(self, settings, guards):
        eligible = _eligible(settings)
        catalog = SourceResolver.from_observation_transaction(self.connection, settings,
            guarded_repositories=guards.writable)
        rows = _links(self.connection, eligible)
        located = tuple(self.connection.execute(_NODES, (eligible, eligible)).fetchall())
        if any(value.get('code_clones') for value in settings.values['repos'].values()):
            from ._scope import RepositoryLocations
            locations = {repository.name: repository for repository in RepositoryLocations(settings).repositories}
            rows = tuple(row for row in rows if row[5] == 'generated' or
                row[6].get('declarationLocation', {}).get('location', 'disk') == locations[row[1]].disk_location)
            index_ids = {chunk.identifier for _, chunk in catalog.index}
            selected_versions = {chunk.version for file in catalog.files for chunk in file.chunks}
            selected_versions.update(chunk.version for _, chunk in catalog.index)
            located = tuple(row for row in located if row[2] in selected_versions and
                (str(row[0]) in index_ids or row[5].get('captureLocation', {}).get('clone') == locations[row[1]].location))
        # These observations can include a busy owner. Keep all exact row and
        # evidence inputs in the final CAS; no unheld peer can change a pin,
        # exemption, version or source selection unnoticed before publication.
        evidence = tuple(self.connection.execute("""SELECT m.repository,m.hash,m.kind,m.bytes,m.metadata FROM public.mycel_manifests m
            WHERE (m.repository,m.hash) IN (SELECT r.repository,r.manifest_hash
                FROM public.mycel_evidence_references r WHERE r.owner=ANY(%s)) ORDER BY m.repository,m.hash""",
            ([row[7] for row in rows if row[7] is not None],)).fetchall())
        snapshots = tuple(self.connection.execute("""SELECT s.repository,s.hash,s.bytes,s.metadata
            FROM public.mycel_snapshots s WHERE (s.repository,s.hash) IN (
                SELECT r.repository,r.snapshot_hash FROM public.mycel_evidence_references r
                WHERE r.owner=ANY(%s)) ORDER BY s.repository,s.hash""",
            ([row[7] for row in rows if row[7] is not None],)).fetchall())
        return catalog, rows, located, evidence, snapshots, _relation_evidence(self.connection, rows)

    def _signature_of(self, observed):
        catalog, rows, located, evidence, snapshots, relation_evidence = observed
        needed, affected, repository = self._scope
        version_ids = {row[2]: str(row[0]) for row in located}
        selected, files, declarations = [], set(), []
        for row in rows:
            raw = _raw(row)
            resolution = _resolve(catalog, row)
            selection = resolution.selection
            # A new downstream link is part of the affected graph even when its
            # owner was not in the initial lock discovery. Disjoint observations
            # and metadata do not invalidate this source's guarded publication.
            relevant = affected if row[5] == 'related' else needed
            if (version_ids[row[2]] not in relevant and _target(row) != repository and not
                    (row[5] != 'related' and selection is not None and
                     any(member.chunk.identifier in affected for member in selection.members))):
                continue
            selected.append(row)
            if selection is not None and selection.file is not None:
                files.add(selection.file.identifier)
            try:
                declarations.append(parse_source_address(raw))
            except SourceAddressError:
                pass
        current = tuple(row for row in located if str(row[0]) in needed
                        or row[2] in {dependency[2] for dependency in selected})
        files.update(file.identifier for file in catalog.files if any(chunk.identifier in needed for chunk in file.chunks))
        files.update(file.identifier for file in catalog.files for address in declarations
            if file.repository == address.repository and any(alias.path == address.path
                and address.root in {None, alias.root} for alias in file.aliases))
        manifests = {(row[1], row[8]) for row in selected if row[8] is not None}
        generated_owners = {row[7] for row in selected if row[5] == 'generated'}
        manifests.update((owner, digest) for identifier, owner, _, _, digest in relation_evidence[1]
                         if identifier in generated_owners and digest is not None)
        evidence = tuple(row for row in evidence if (row[0], row[1]) in manifests)
        snapshot_keys = set()
        for owner, _, _, raw, _ in evidence:
            try:
                payload = json.loads(bytes(raw))
            except (ValueError, TypeError):
                continue  # Exact malformed manifest bytes still guard pending observation.
            if not isinstance(payload, dict):
                continue
            try:
                if 'dependant' in payload:
                    snapshot_keys.add((owner, payload['dependant']['hash']))
                    snapshot_keys.update((owner, member['evidence']['hash']) for member in payload['members'])
                else:
                    snapshot_keys.update((owner, payload[key]['hash']) for key in ('request', 'instruction', 'task', 'response') if key in payload)
                    snapshot_keys.update((owner, member[key]['hash']) for member in payload['members'] for key in ('source', 'sent'))
            except (ValueError, TypeError, KeyError):
                pass  # Shape validation reports the fault; CAS retains exact manifest bytes.
        snapshots = tuple(row for row in snapshots if (row[0], row[1]) in snapshot_keys)
        owners, references, versions, states = relation_evidence
        selected_owners = {row[7] for row in selected if row[5] in {'related', 'generated'}}
        selected_versions = {row[2] for row in selected if row[5] in {'related', 'generated'}}
        related = (tuple(row for row in owners if row[0] in selected_owners),
                   tuple(row for row in references if row[0] in selected_owners),
                   tuple(row for row in versions if row[0] in selected_versions),
                   tuple(row for row in states if row[0] in {value[1] for value in versions if value[0] in selected_versions}))
        return (tuple(file for file in catalog.files if file.identifier in files),
                tuple(selected), current, evidence, snapshots, related)

    def _physical_inputs(self, settings, files, declarations, captures=None):
        from ._located_reconciliation import _catalog
        from ._disk_reconciliation import _parse_history
        if self._captures is not None:
            # A pass takes another repository's sources from the index (MYC-1.37):
            # only its own repository's disk is compared, through its capture.
            captures = self._captures
            files = [file for file in files if file.repository == self._snapshot.repository]
            declarations = [address for address in declarations if address.repository == self._snapshot.repository]
        captures = {} if captures is None else captures
        for owner in sorted({file.repository for file in files} | {address.repository for address in declarations}):
            if owner not in captures:
                rows, _, _, state, _ = _catalog(self.connection, owner)
                history = _parse_history(owner, rows, () if state is None else state[0])
                captures[owner] = capture_repository(settings, owner, previous=history)
        output = []
        for file in sorted({file.identifier: file for file in files}.values(), key=lambda item: (item.repository, item.identifier)):
            manifest = captures[file.repository]
            actual = [item for item in manifest.disk.files if any(
                alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
            expected = (tuple(sorted((alias.root, alias.path) for alias in file.aliases)), file.source)
            present = tuple((tuple(sorted((alias.root, alias.path) for alias in item.aliases)), item.source) for item in actual)
            output.append((file.repository, file.identifier, expected, present, manifest.deletion_safe))
        for address in sorted(set(declarations), key=lambda item: item.address):
            manifest = captures[address.repository]
            actual = tuple(sorted((tuple(sorted((alias.root, alias.path) for alias in item.aliases)), item.source)
                for item in manifest.disk.files if any(alias.path == address.path and address.root in {None, alias.root}
                                                       for alias in item.aliases)))
            output.append((address.repository, address.address, actual, manifest.deletion_safe))
        return tuple(output)

    def apply_in_transaction(self, settings, repository, guards: DetectionGuards, *, targeted=False):
        """Compare prospective complete corpora and apply guarded owners only.

        A busy owner keeps every existing mark; its exact pending places are
        returned. Other acquired descendants use the complete prospective graph.
        Missing/corrupt/unsupported baseline comparisons retain old marks and
        are visibly pending, never a newly invented fresh result.
        """
        if type(targeted) is not bool:
            raise MycelError('invalid_input', 'Mechanical detection requires a typed observation scope.')
        require_transaction_guards(self.connection, guards.writable)
        settings.require_current()
        observed = self._read(settings, guards)
        catalog, rows, located, _, _, relation_evidence = observed
        members = {member.chunk.identifier: member for file in catalog.files
                   for member in catalog._members(file, file.chunks)}
        from ._resolver import SelectionMember
        members.update((chunk.identifier, SelectionMember(place, chunk)) for place, chunk in catalog.index)
        nodes = []
        for identifier, owner, version, _, metadata, file_metadata in located:
            member = members.get(str(identifier))
            if member is None or member.chunk.version != version:
                raise MycelError('invalid_input', 'Mechanical detection requires one exact current disk location.')
            declarations = file_metadata.get('documentDeclarations', {}).get('metadata', {})
            if 'documentDeclarations' not in file_metadata and member.chunk.kind == 'document':
                file = next(file for file in catalog.files if member.chunk in file.chunks)
                parsed = file_from_parse_history(file.source, 'documents',
                    FileAlias(file.primary.root, file.primary.path),
                    tuple(FileAlias(alias.root, alias.path) for alias in file.aliases), file_metadata.get('parseHistory'))
                if parsed is not None:
                    declaration = read_document_declarations(parsed.parsed, file=file.primary.address)
                    declarations = declaration.metadata
            nodes.append(StaleNode(str(identifier), version, member.place,
                member.chunk.kind == 'document' and
                (declarations.get('heartwood') is True or declarations.get('generated') is True)))
        by_version = {node.version: node.identifier for node in nodes}
        stored = tuple(self.connection.execute("""SELECT id,chunk_version,dependency,reason FROM public.mycel_stale_reasons
            WHERE repository=ANY(%s) ORDER BY id""", (_eligible(settings),)).fetchall())
        direct, edges, unchecked = defaultdict(list), [], {}
        resolutions = {}
        for row in rows:
            resolution = _resolve(catalog, row)
            resolutions[str(row[0])] = resolution
            if resolution.selection is not None and row[5] != 'related':
                edges.extend(StaleEdge(member.chunk.identifier, by_version[row[2]], str(row[0]), row[5])
                             for member in resolution.selection.members)
        seeds = {node.identifier for node in nodes if node.place.repository == repository}
        seeds.update(by_version[row[2]] for row in rows if row[5] != 'related' and _target(row) == repository)
        affected = _closure(seeds | (set(guards.original_affected) & {node.identifier for node in nodes}), edges)
        affected.update(by_version[row[2]] for row in rows if row[5] == 'related' and _target(row) == repository)
        affected.update(set(guards.original_related) & {node.identifier for node in nodes})
        exemptions = {node.identifier for node in nodes if node.exempt}
        # Relevant ancestors supply the complete reasons for affected nodes.
        # An unrelated component's physical files never qualify this pass.
        reverse = [StaleEdge(edge.dependant, edge.source, edge.dependency, edge.kind)
                   for edge in edges if edge.dependant not in exemptions]
        needed = _closure(affected, reverse)
        self._scope = (needed, affected, repository)
        physical_files, physical_declarations, checked_physical, captures = [], [], {}, {}
        evidence = EvidenceStore(self.connection)
        for row in rows:
            identifier, owner, version, _, natural, kind, state, baseline_owner, manifest_hash = row
            dependant = by_version[version]
            if dependant not in (affected if kind == 'related' else needed):
                continue
            if targeted and owner != repository and _target(row) != repository:
                # A selected source pass renews only its incoming observations.
                # Other direct marks remain exact inputs to the complete graph;
                # recomputing them would read unrelated physical sources and
                # change unrelated records in this affected dependant chunk.
                for _, old_version, dependency, reason in stored:
                    if (old_version == version and _stored_link(dependency, reason) == str(identifier)
                            and reason['kind'] != 'upstream_stale'):
                        direct[dependant].append((str(identifier), StaleReason(reason['kind'],
                            parse_source_address(reason['source']['address']), reason['edge'],
                            tuple(parse_source_address(place['address']) for place in reason.get('via', ())))))
                continue
            raw = _raw(row)
            resolution = resolutions[str(identifier)]
            selection = resolution.selection
            if resolution.state == 'invalid':
                continue  # Ineligible/malformed refs supply no current authority.
            dependant_file = next((file for file in catalog.files
                                  if any(member.identifier == dependant for member in file.chunks)), None)
            required = ((dependant_file,) if dependant_file is not None else ()) + ((selection.file,)
                if selection is not None and selection.file is not None else ())
            try:
                address = parse_source_address(raw)
            except SourceAddressError:
                address = None
            addresses = (address,) if address is not None and address.root != 'index' and address.repository in _eligible(settings) else ()
            key = (tuple(file.identifier for file in required), addresses)
            if key not in checked_physical:
                checked_physical[key] = self._physical_inputs(settings, required, addresses, captures)
            physical_files.extend(required)
            physical_declarations.extend(addresses)
            physical_bad = any(len(value) == 5 and (value[3] != (value[2],) or not value[4])
                               or len(value) == 4 and not value[3] for value in checked_physical[key])
            observed_declarations = [value for value in checked_physical[key] if len(value) == 4]
            if addresses and observed_declarations:
                expected_candidates = tuple(sorted((tuple(sorted((alias.root, alias.path) for alias in file.aliases)), file.source)
                    for file in catalog.files if file.repository == address.repository and any(
                        alias.path == address.path and address.root in {None, alias.root} for alias in file.aliases)))
                physical_bad = physical_bad or observed_declarations[-1][2] != expected_candidates
            if baseline_owner is None and not state.get('everResolved') and kind != 'generated':
                continue  # A never-resolved declaration is a ref fault, not removed evidence.
            try:
                if manifest_hash is None:
                    raise EvidenceError('baseline_missing')
                if kind == 'generated':
                    from ._generated import generated_capture, compare_generated
                    if physical_bad:
                        raise EvidenceError('changed_since_ingest')
                    capture, member = generated_capture(self.connection, row)
                    direct[dependant].extend((str(identifier), reason) for reason in compare_generated(member, resolution))
                    continue
                capture = evidence._read_baseline(owner, manifest_hash)
                baseline = capture.manifest.payload
                if physical_bad:
                    raise EvidenceError('changed_since_ingest')
                if baseline['dependantId'] != dependant or baseline['dependantVersion'] != str(version):
                    raise EvidenceError('baseline_missing')
                if kind == 'related' and (baseline['kind'] != 'related'
                        or baseline.get('ref') != state.get('baselineRef', raw)):
                    raise EvidenceError('baseline_missing')
                if kind == 'related':
                    _validate_relation(row, capture, relation_evidence)
                if selection is None and resolution.fault not in {'missing_file', 'missing_name'}:
                    unchecked[str(identifier)] = 'ref_fault'
                    continue
                direct[dependant].extend((str(identifier), reason) for reason in compare_dependency(baseline,
                    resolution, parse_source_address(natural or baseline['source']['address']), kind))
            except EvidenceError as error:
                unchecked[str(identifier)] = error.status
                for _, old_version, dependency, reason in stored:
                    if old_version == version and _stored_link(dependency, reason) == str(identifier):
                        direct[dependant].append((str(identifier), StaleReason(reason['kind'],
                            parse_source_address(reason['source']['address']), reason['edge'],
                            tuple(parse_source_address(place['address']) for place in reason.get('via', ())))))
        plan = plan_staleness(tuple(nodes), tuple(edges), dict(direct))
        # Clearing an old reason after a ref withdrawal or a source restoration
        # needs the same downstream closure as adding that reason.
        uncertain_nodes = {by_version[row[2]] for row in rows if row[5] != 'related' and str(row[0]) in unchecked}
        uncertain_closure = _closure(uncertain_nodes - exemptions,
            [edge for edge in edges if edge.source not in exemptions])
        uncertain_closure.update(by_version[row[2]] for row in rows
                                 if row[5] == 'related' and str(row[0]) in unchecked)
        replies, changed_owners, pending = {}, set(), []
        for node in sorted(nodes, key=lambda node: node.place.address):
            if node.identifier not in affected:
                continue
            owner = node.place.repository
            old = [row for row in stored if row[1] == node.version]
            desired = plan[node.identifier]
            if owner not in guards.writable:
                pending.append({'chunk': _place_payload(node.place), 'reason': guards.pending.get(owner, 'not_guarded')})
                continue
            counts = replies.setdefault(owner, {'staleChecked': 0, 'staleChanged': 0, 'staleReasons': 0})
            counts['staleChecked'] += 1
            uncertain = [str(row[0]) for row in rows if row[2] == node.version and str(row[0]) in unchecked]
            if node.identifier in uncertain_closure and not node.exempt:
                counts['staleReasons'] += len(old)
                pending.extend({'chunk': _place_payload(node.place), 'dependency': dep,
                                'reason': unchecked[dep]} for dep in uncertain)
                if not uncertain:
                    pending.append({'chunk': _place_payload(node.place), 'reason': 'upstream_unchecked'})
                continue
            counts['staleReasons'] += len(desired)
            old_keys = {(_stored_link(row[2], row[3]), canonical_json({key: value for key, value in row[3].items()
                            if key != 'classification'})): row for row in old}
            wanted = {}
            for dependency, reason in desired:
                record = reason.record()
                if reason.edge == 'related':
                    record['relation'] = dependency
                wanted[(dependency, canonical_json(record))] = record
            removed, added = old_keys.keys() - wanted.keys(), wanted.keys() - old_keys.keys()
            if removed or added:
                counts['staleChanged'] += 1
                changed_owners.add(owner)
                for key in removed:
                    self.connection.execute('DELETE FROM public.mycel_stale_reasons WHERE id=%s', (old_keys[key][0],))
                for dependency, encoded in sorted(added):
                    reason_id = uuid5(NAMESPACE_URL, 'mycel:stale:' + str(node.version) + ':' + dependency + ':' + encoded.decode())
                    self.connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,%s,%s)',
                        (reason_id, owner, node.version,
                         None if wanted[(dependency, encoded)]['edge'] == 'related' else dependency,
                         Jsonb(wanted[(dependency, encoded)])))
        for owner, counts in replies.items():
            counts['stale'] = self.connection.execute("""SELECT count(DISTINCT r.chunk_version)
                FROM public.mycel_stale_reasons r JOIN public.mycel_locations l ON l.chunk_version=r.chunk_version
                WHERE r.repository=%s AND l.kind IN ('disk','index')""", (owner,)).fetchone()[0]
        from ._drift_store import DriftStore
        drift_changed = DriftStore(self.connection).sync_in_transaction(settings, guards.writable,
            versions=tuple(node.version for node in nodes if node.identifier in affected), pending=pending)
        changed_owners.update(drift_changed)
        self._signature = self._signature_of(observed)
        self._physical = (tuple(physical_files), tuple(physical_declarations),
                          self._physical_inputs(settings, physical_files, physical_declarations, captures))
        return replies, changed_owners, tuple(pending)

    def verify_in_transaction(self, settings, guards):
        settings.require_current()
        if self._signature is None or self._signature_of(self._read(settings, guards)) != self._signature:
            raise MycelError('invalid_input', 'Mechanical dependency inputs changed during publication.')
        files, declarations, expected = self._physical
        if self._physical_inputs(settings, files, declarations) != expected:
            raise MycelError('invalid_input', 'Mechanical current file inputs changed during publication.')
