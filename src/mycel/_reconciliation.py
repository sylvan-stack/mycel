"""Pure dependency plans; persistence, guarded evidence capture and detection follow.

The caller supplies one complete current catalog, one dependant version's own
baseline records (or the identity-selected reference version), and the complete
existing dependency graph. No source row, baseline, pin or role is written here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from ._evidence import (BaselineManifest, ComparisonRecord, EvidenceError,
                        FAMILY_REVISION, canonical_json, chunk_comparison,
                        exact_comparison)
from ._resolver import Resolution, SelectionMember, SourceResolver, SourceSelection
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address


class ReconciliationError(ValueError):
    def __init__(self, status: str, *, dependencies: tuple[str, ...] = (), cycle: tuple[str, ...] = ()):
        self.status = status
        self.dependencies = tuple(sorted(set(dependencies)))
        self.cycle = cycle
        super().__init__(status)


def _invalid() -> None:
    raise ReconciliationError('invalid_input')


def _label(value: object) -> None:
    if not isinstance(value, str) or not value or '\0' in value:
        _invalid()
    try:
        value.encode('utf-8')
    except UnicodeError:
        _invalid()


@dataclass(frozen=True)
class DependencyRecord:
    identifier: str
    baseline: BaselineManifest
    retained_place: SourceAddress | None = None
    current_anchor: str | None = None
    current_declaration: str | None = None

    def __post_init__(self):
        _label(self.identifier)
        if not isinstance(self.baseline, BaselineManifest) or self.baseline.payload['kind'] not in {'declared', 'asserted'}:
            _invalid()
        if self.retained_place is not None:
            if not isinstance(self.retained_place, SourceAddress) or self.retained_place.root not in {'code', 'artifact'}:
                _invalid()
            self.retained_place.address
            if (self.retained_place.repository != self.baseline.payload['source']['repository']
                    or (self.baseline.payload['selection'] == 'file') != (self.retained_place.name is None)):
                _invalid()
        if self.current_anchor is not None:
            _label(self.current_anchor)
        if self.current_declaration is not None:
            _label(self.current_declaration)

    @property
    def kind(self) -> str:
        return self.baseline.payload['kind']

    @property
    def natural_place(self) -> SourceAddress:
        return self.retained_place or parse_source_address(self.baseline.payload['source']['address'])


@dataclass(frozen=True)
class BaselineFault:
    identifier: str
    status: Literal['baseline_missing', 'snapshot_corrupt', 'unsupported_comparison']

    def __post_init__(self):
        _label(self.identifier)
        if self.status not in {'baseline_missing', 'snapshot_corrupt', 'unsupported_comparison'}:
            _invalid()


@dataclass(frozen=True)
class DependencyRequest:
    """Opaque matching ID, separate from raw declaration and resolved place.

    Ingest matches declared records before invoking this planner. A changed
    spelling/qualified alias of the same dependency retains its existing ID.
    """
    identifier: str
    kind: Literal['declared', 'asserted']
    declaration: str
    absent_state: Literal['away', 'deleted'] | None = None

    def __post_init__(self):
        _label(self.identifier)
        if self.kind not in {'declared', 'asserted'} or not isinstance(self.declaration, str):
            _invalid()
        try:
            self.declaration.encode('utf-8')
        except UnicodeError:
            _invalid()
        if self.absent_state not in {None, 'away', 'deleted'}:
            _invalid()


@dataclass(frozen=True)
class AssertedRemoval:
    place: SourceAddress
    selection: Literal['file', 'chunk', 'family']

    def __post_init__(self):
        if not isinstance(self.place, SourceAddress) or self.place.root not in {'code', 'artifact'}:
            _invalid()
        self.place.address
        if self.selection not in {'file', 'chunk', 'family'}:
            _invalid()
        if (self.selection == 'file') != (self.place.name is None):
            _invalid()


@dataclass(frozen=True)
class GraphEdge:
    source: str
    dependant: str
    dependency: str

    def __post_init__(self):
        for value in (self.source, self.dependant, self.dependency):
            _label(value)


@dataclass(frozen=True)
class ResolvedBinding:
    place: SourceAddress
    anchor: str
    declaration: str

    def __post_init__(self):
        if not isinstance(self.place, SourceAddress) or self.place.root not in {'code', 'artifact'}:
            _invalid()
        self.place.address
        _label(self.anchor)
        _label(self.declaration)


@dataclass(frozen=True)
class DependencyDecision:
    identifier: str
    kind: str
    declaration: str
    action: Literal['keep', 'inherit', 'capture', 'withdraw', 'release', 'unresolved']
    baseline: BaselineManifest | None
    natural_place: SourceAddress | None
    current_selection: SourceSelection | None
    source_state: Literal['present', 'away', 'deleted', 'ineligible', 'unresolved']
    active_sources: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    fault: str | None = None
    resolution: Resolution | None = None
    binding: ResolvedBinding | None = None


@dataclass(frozen=True)
class DependencyPlan:
    decisions: tuple[DependencyDecision, ...]
    role: Literal['derived', 'authored', 'unclassified']
    graph: tuple[GraphEdge, ...]


def _place_payload(place: SourceAddress) -> dict:
    value = {'repository': place.repository, 'root': place.root, 'path': place.path, 'address': place.address}
    if place.name is not None:
        value['name'] = place.name
    return value


def _comparison(selection: SourceSelection) -> ComparisonRecord:
    if selection.kind == 'file':
        if selection.file is None:
            _invalid()
        return exact_comparison(selection.file.source, 'file_bytes')
    if not selection.members or selection.kind not in {'chunk', 'family'}:
        _invalid()
    ordered = tuple(sorted(selection.members, key=lambda member: (member.place.address, member.chunk.identifier)))
    if selection.kind == 'chunk':
        if len(ordered) != 1:
            _invalid()
        return chunk_comparison(ordered[0].chunk)
    projection = tuple({'place': _place_payload(member.place),
                        'comparison': chunk_comparison(member.chunk).as_dict()} for member in ordered)
    return ComparisonRecord('family', FAMILY_REVISION, sha256(canonical_json(projection)).hexdigest())


def _cycle(graph: tuple[GraphEdge, ...]) -> tuple[str, ...]:
    """Return an actual closed path, iteratively for arbitrarily deep fixtures."""
    adjacency: dict[str, set[str]] = {}
    for edge in graph:
        adjacency.setdefault(edge.source, set()).add(edge.dependant)
        adjacency.setdefault(edge.dependant, set())
    done: set[str] = set()
    for start in sorted(adjacency):
        if start in done:
            continue
        path = [start]
        positions = {start: 0}
        stack = [iter(sorted(adjacency[start]))]
        while stack:
            node = next(stack[-1], None)
            if node is None:
                finished = path.pop()
                done.add(finished)
                positions.pop(finished)
                stack.pop()
            elif node in positions:
                return tuple(path[positions[node]:] + [node])
            elif node not in done:
                positions[node] = len(path)
                path.append(node)
                stack.append(iter(sorted(adjacency[node])))
    return ()


def plan_dependencies(dependant: SelectionMember, resolver: SourceResolver,
                      requests: tuple[DependencyRequest, ...], existing: tuple[DependencyRecord, ...], *,
                      pin_version: int, mode: Literal['observe', 'restore', 'inherit', 'edit', 'confirm'] = 'observe',
                      file_role: Literal['authored', 'derived'] | None = None,
                      graph: tuple[GraphEdge, ...] = (),
                      remove_assertions: tuple[AssertedRemoval, ...] = (),
                      baseline_faults: tuple[BaselineFault, ...] = ()) -> DependencyPlan:
    """Stage the entire operation and refuse cycles/confirmation faults first.

    `requests` contains every current declared ref and any new/asserted current
    observations. Omitted assertions survive and are resolved again. Omitted
    declared records release only their own references. `pin_version` selects
    exactly the version whose records identity has authorized this call to use.
    `absent_state` distinguishes an enabled missing source's away/deleted state;
    absent observations must be supplied for old unresolved assertions too.
    """
    if (not isinstance(dependant, SelectionMember) or not isinstance(resolver, SourceResolver)
            or type(pin_version) is not int or pin_version < 1
            or mode not in {'observe', 'restore', 'inherit', 'edit', 'confirm'}
            or file_role not in {None, 'authored', 'derived'}
            or any(type(value) is not tuple for value in (requests, existing, graph, remove_assertions, baseline_faults))
            or any(not isinstance(value, DependencyRequest) for value in requests)
            or any(not isinstance(value, DependencyRecord) for value in existing)
            or any(not isinstance(value, GraphEdge) for value in graph)
            or any(not isinstance(value, AssertedRemoval) for value in remove_assertions)
            or any(not isinstance(value, BaselineFault) for value in baseline_faults)):
        _invalid()
    if (mode in {'observe', 'restore', 'confirm'} and pin_version != dependant.chunk.version
            or len({value.identifier for value in existing}) != len(existing)
            or len({value.identifier for value in requests}) != len(requests)):
        _invalid()
    endpoint = resolver.resolve(dependant.place.address, purpose='endpoint')
    if endpoint.state != 'resolved' or endpoint.selection is None or endpoint.selection.members != (dependant,):
        _invalid()
    dependant_comparison = chunk_comparison(dependant.chunk)
    if baseline_faults:
        first = min(baseline_faults, key=lambda value: value.identifier)
        raise ReconciliationError(first.status, dependencies=tuple(value.identifier for value in baseline_faults))
    by_id = {value.identifier: value for value in existing}
    desired = {value.identifier: value for value in requests}
    graph_owners: dict[str, set[str]] = {}
    for edge in graph:
        graph_owners.setdefault(edge.dependency, set()).add(edge.dependant)
    if any(identifier in graph_owners and (identifier not in by_id or graph_owners[identifier] != {dependant.chunk.identifier})
           for identifier in desired):
        _invalid()  # A new ID cannot overwrite an unrelated/generated dependency.
    if any(graph_owners.get(identifier, {dependant.chunk.identifier}) != {dependant.chunk.identifier} for identifier in by_id):
        _invalid()
    for record in existing:
        value = record.baseline.payload
        if (value['dependantId'] != dependant.chunk.identifier or int(value['dependantVersion']) != pin_version
                or value['ownerRepository'] != dependant.place.repository):
            _invalid()
        if mode in {'observe', 'restore', 'confirm'} and value['dependant']['hash'] != dependant.chunk.snapshot_hash:
            _invalid()
        if mode == 'edit' and ComparisonRecord.from_record(value['dependant']['comparison']) == chunk_comparison(dependant.chunk):
            _invalid()
        if mode == 'inherit' and ComparisonRecord.from_record(value['dependant']['comparison']) != chunk_comparison(dependant.chunk):
            _invalid()
        request = desired.get(record.identifier)
        if request is not None and request.kind != record.kind:
            _invalid()
        if request is None and record.kind == 'asserted':
            desired[record.identifier] = DependencyRequest(record.identifier, 'asserted',
                record.current_declaration or value.get('ref', record.natural_place.address))
    decisions = []
    confirmation_faults = []
    canonical_requests = {}
    for identifier in sorted(set(by_id) | set(desired)):
        old = by_id.get(identifier)
        request = desired.get(identifier)
        baseline = old.baseline if old else None
        natural = old.natural_place if old else None
        if request is None:
            decisions.append(DependencyDecision(identifier, old.kind, baseline.payload.get('ref', natural.address),
                'release', baseline, natural, None, 'unresolved'))
            continue
        resolution = resolver.resolve(request.declaration)
        selection = resolution.selection
        if selection is not None and selection.kind == 'index':
            _invalid()
        if old and selection is not None:
            if baseline.payload['selection'] != selection.kind:
                _invalid()
            previous_id = old.current_anchor or next((value.get('id') for value in baseline.payload['members']
                                if value['place']['address'] == baseline.payload['source']['address']), None)
            current_id = (selection.file.identifier if selection.kind == 'file' and selection.file is not None else
                          next((value.chunk.identifier for value in selection.members if value.place == selection.place), None))
            if selection.place != natural and (previous_id is None or previous_id != current_id):
                _invalid()  # A supplied record ID does not authorize rebinding an unrelated target.
        if old and selection is None:
            retained_raw = old.current_declaration or baseline.payload.get('ref', natural.address)
            try:
                parsed = parse_source_address(request.declaration)
                same_natural = (parsed.repository == natural.repository and parsed.path == natural.path
                                and parsed.name == natural.name and parsed.root in {None, natural.root})
            except SourceAddressError:
                same_natural = False
            if request.declaration != retained_raw and not same_natural:
                _invalid()  # A missing/disabled target supplies no identity proof for a rebind.
        matching_removal = request.kind == 'asserted' and any(
            removal.selection == (selection.kind if selection is not None else baseline.payload['selection'] if old else None)
            and removal.place in tuple(place for place in (natural, selection.place if selection else None) if place is not None)
            for removal in remove_assertions)
        if matching_removal:
            if old:
                decisions.append(DependencyDecision(identifier, request.kind, request.declaration, 'release',
                    baseline, natural, None, 'unresolved'))
            continue
        if resolution.state == 'resolved':
            if request.absent_state is not None:
                _invalid()
            token = (request.kind, selection.kind, selection.place.address) if selection is not None else None
            if token in canonical_requests:
                _invalid()  # Caller must reuse the existing assertion/ref identity.
            canonical_requests[token] = identifier
            if selection is None:
                _invalid()
            natural = natural or selection.place
            current = _comparison(selection)
            reasons = []
            if old:
                pinned = ComparisonRecord.from_record(baseline.payload['selectionComparison'])
                pinned.require_supported()
                if current != pinned:
                    reasons.append('source_changed')
                if selection.kind == 'family':
                    present_ids = {member.chunk.identifier for member in selection.members}
                    present_places = {member.place.address for member in selection.members}
                    if any(member.get('id') not in present_ids and member['place']['address'] not in present_places
                           for member in baseline.payload['members']):
                        reasons.insert(0, 'source_removed')
            action = 'capture' if old is None or mode in {'edit', 'confirm'} else 'inherit' if mode == 'inherit' else 'keep'
            if action == 'capture':
                # These direct comparisons describe the replaced baseline.
                # The same transaction pins the complete current selection;
                # an accepted edit/confirmation has answered them already.
                reasons = []
            active = tuple(sorted({member.chunk.identifier for member in selection.members}))
            anchor = (selection.file.identifier if selection.kind == 'file' and selection.file is not None else
                      next((value.chunk.identifier for value in selection.members if value.place == selection.place), None))
            if anchor is None:
                _invalid()
            binding = ResolvedBinding(selection.place, anchor, request.declaration)
            decisions.append(DependencyDecision(identifier, request.kind, request.declaration, action, baseline,
                natural, selection, 'present', active, tuple(reasons), resolution=resolution, binding=binding))
        else:
            absent = resolution.state == 'unresolved' and resolution.fault in {'missing_file', 'missing_name'}
            if old is not None and absent and request.absent_state is None:
                _invalid()  # Do not guess whether a former disk source is away or deleted.
            missing = old is not None and absent and request.absent_state is not None
            if request.absent_state is not None and not absent:
                _invalid()
            state = request.absent_state if missing else 'ineligible' if resolution.state == 'invalid' else 'unresolved'
            action = ('withdraw' if missing and mode in {'edit', 'confirm'} else
                      'inherit' if old and mode == 'inherit' else 'keep' if old else 'unresolved')
            if mode == 'confirm' and not missing:
                confirmation_faults.append(identifier)
            decisions.append(DependencyDecision(identifier, request.kind, request.declaration, action, baseline,
                natural, None, state, (), ('source_removed',) if missing and action != 'withdraw' else (), resolution.fault, resolution))
    if confirmation_faults:
        raise ReconciliationError('invalid_input', dependencies=tuple(confirmation_faults))
    replaced = set(by_id) | set(desired)
    proposed = tuple(sorted(set(
        edge for edge in graph if not (edge.dependant == dependant.chunk.identifier and edge.dependency in replaced)
    ) | {GraphEdge(source, dependant.chunk.identifier, decision.identifier)
         for decision in decisions if decision.action not in {'release', 'withdraw'} for source in decision.active_sources},
        key=lambda edge: (edge.source, edge.dependant, edge.dependency)))
    cycle = _cycle(proposed)
    if cycle:
        raise ReconciliationError('dependency_cycle', cycle=cycle)
    governing = any(decision.action not in {'release', 'withdraw'} and
                    (decision.active_sources or decision.baseline is not None and decision.source_state in {'away', 'deleted'})
                    for decision in decisions)
    # A resolved empty file has no chunk endpoints, but still governs its dependant.
    governing = governing or any(decision.current_selection is not None and decision.action not in {'release', 'withdraw'}
                                 for decision in decisions)
    governing = governing or any(edge.dependant == dependant.chunk.identifier for edge in proposed)
    role = 'derived' if governing else file_role or ('authored' if dependant_comparison.kind == 'code_text' else 'unclassified')
    return DependencyPlan(tuple(decisions), role, proposed)
