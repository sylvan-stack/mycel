"""Guarded, location-owned dependency policy inside a caller's transaction.

The caller chooses the identity-authorized reference version and supplies a
fresh complete-capture rereader. This producer opens no transaction, commits
nothing, and never discards another location's or exact version's pins.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Callable
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._collection import CollectionStore
from ._declared_refs import _raw, _text, _stored, _safe_json
from ._errors import MycelError
from ._evidence import (CaptureLocation, EvidenceError, EvidenceStore,
    InheritanceInputs, PinInputs, _INHERITANCE_OWNER_SQL, _INHERITANCE_REFERENCES_SQL,
    _INHERITANCE_VERSION_SQL, _inheritance_version, _validate_inheritance,
    checked_transaction_input_guard, inherit_baseline)
from ._locks import require_transaction_guards
from ._reconciliation import (AssertedRemoval, DependencyRecord, DependencyRequest,
    DependencyDecision, DependencyPlan, GraphEdge, ReconciliationError, _cycle, plan_dependencies)
from ._resolver import (Resolution, SelectionMember, SourceResolver, replace_resolution, _location_selectors)
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address
from ._store import exact_bytes


class RetainedDependencyResolver(SourceResolver):
    """Use checked existing anchors only after ordinary resolution is absent.

    Ambiguous, disabled and newly resolved spellings remain authoritative. A
    recognized file move or chunk-name change follows an existing stable ID;
    an unrelated new declaration has no anchor and gets ordinary resolution.
    """
    def __init__(self, catalog: SourceResolver, anchors: dict[str, str],
                 syntax_faults: dict[str, str] | None = None, *, endpoint_refs=()):
        # The base catalog already validated its immutable files/chunks. This
        # adapter adds only per-dependant resolution policy; rebuilding that
        # catalog here rehashed every source once per chunk (quadratic work).
        if not isinstance(catalog, SourceResolver):
            raise MycelError('invalid_input', 'Retained resolution requires a validated source catalog.')
        self.settings, self.files, self.index = catalog.settings, catalog.files, catalog.index
        self.anchors = dict(anchors)
        self.base = catalog
        self.syntax_faults = dict(syntax_faults or {})
        # An asserted relation has two one-chunk endpoints. Declared relations
        # and dependencies retain ordinary file/class-family source selection.
        self.endpoint_refs = frozenset(endpoint_refs)

    def resolve(self, declaration: str, *, purpose='source') -> Resolution:
        if purpose == 'source' and declaration in self.syntax_faults:
            return Resolution(declaration, 'invalid', fault=self.syntax_faults[declaration])
        selected_purpose = 'endpoint' if purpose == 'source' and declaration in self.endpoint_refs else purpose
        result = self.base.resolve(declaration, purpose=selected_purpose)
        from ._source_refs import parse_entity_uri
        if parse_entity_uri(declaration) is not None:
            if result.selection is not None and result.selection.kind in {'req', 'dec'}:
                result = replace(result, selection=replace(result.selection, kind='chunk'))
            if result.fault == 'missing_entity':
                result = replace(result, fault='missing_name')
            return result  # the UUID is already the exact anchor, even after a move
        anchor = self.anchors.get(declaration)
        if purpose != 'source' or anchor is None:
            return result
        if result.fault == 'missing_file':
            retained = self.base.resolve_retained(declaration, anchor)
            if selected_purpose == 'endpoint' and retained.selection is not None:
                return replace_resolution(self.base.resolve(retained.selection.place.address,
                                                            purpose='endpoint'), declaration)
            return retained
        if result.fault != 'missing_name':
            return result
        address = parse_source_address(declaration)
        matches = [(file, chunk) for file in self.files if file.repository == address.repository
                   and any(alias.path == address.path and address.root in {None, alias.root} for alias in file.aliases)
                   for chunk in file.chunks if chunk.identifier == anchor]
        if len(matches) != 1:
            return result
        file, chunk = matches[0]
        current = SourceAddress(file.repository, file.primary.root, file.primary.path, chunk.name)
        return replace_resolution(self.base.resolve(current.address, purpose=selected_purpose), declaration)


@dataclass(frozen=True)
class DependencyApplicationReply:
    plan: DependencyPlan
    identifiers: tuple[tuple[str, str], ...]
    changed: int
    captured: int
    inherited: int
    released: int
    roles_changed: int = 0
    metadata_changed: int = 0
    snapshots_collected: int = 0
    manifests_collected: int = 0

    @property
    def mutated(self):
        return bool(self.changed or self.roles_changed or self.metadata_changed
                    or self.snapshots_collected or self.manifests_collected)

    @property
    def counts(self):
        return {'refsChecked': len(self.plan.decisions), 'refsChanged': self.changed,
                'refFaults': sum(decision.fault is not None for decision in self.plan.decisions
                                 if decision.action != 'release'),
                'pinsCaptured': self.captured, 'pinsInherited': self.inherited,
                'dependenciesReleased': self.released, 'rolesChanged': self.roles_changed,
                'declarationMetadataChanged': self.metadata_changed,
                'evidenceSnapshotsCollected': self.snapshots_collected,
                'evidenceManifestsCollected': self.manifests_collected}


@dataclass
class _DependencyBatch:
    connection: object = field(repr=False)
    settings: SettingsSnapshot = field(repr=False)
    scopes: dict[tuple[str, int], frozenset[str]]
    catalogs: tuple[tuple[str, str], ...]
    guarded_repositories: tuple[str, ...]
    completed: set[tuple[str, int]] = field(default_factory=set)
    active: bool = True

    @property
    def exclusions(self):
        return frozenset(identifier for scope, identifiers in self.scopes.items()
                         if scope not in self.completed for identifier in identifiers)


def _invalid(message):
    raise MycelError('invalid_input', message)


def _uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        _invalid('Dependency ownership needs an exact file-location UUID.')


def _current_raw(row):
    return _text(row[6]['rawRef']) if 'rawRef' in row[6] else row[3]


def _same_natural(raw, natural):
    try:
        place = parse_source_address(raw)
        return (place.repository == natural.repository and place.path == natural.path
                and place.name == natural.name and place.root in {None, natural.root})
    except (SourceAddressError, TypeError):
        return False


def _anchor(selection):
    if selection.kind == 'file':
        return selection.file.identifier
    return next(member.chunk.identifier for member in selection.members if member.place == selection.place)


def _match_declarations(refs, rows, resolver, records):
    """Deduplicate equivalent selections and match independently of spelling/order.

    Every occurrence survives in state. Duplicate aliases do not allocate a
    second authoritative edge or baseline. Unresolved exact spellings remain
    separate visible declarations unless their raw ref is identical.
    """
    available = {str(row[0]): row for row in rows if row[5] == 'declared'}
    requests, occurrences, seen = [], {}, {}
    for ref in refs:
        resolution = resolver.resolve(ref.ref)
        selection = resolution.selection
        key = ('resolved', selection.kind, selection.place.address) if selection else ('raw', ref.ref)
        occurrence = {'rawDeclared': _raw(ref.declared), 'rawLine': _raw(ref.raw_line),
                      'origin': ref.origin, 'line': ref.line, 'syntaxFault': ref.fault}
        if key in seen:
            occurrences[seen[key]].append(occurrence)
            continue
        matches = []
        for identifier, row in available.items():
            record = records.get(identifier)
            retained = resolver.resolve(_current_raw(row))
            previous = retained.selection
            if (_current_raw(row) == ref.ref or previous is not None and selection is not None
                    and previous.kind == selection.kind and (previous.place == selection.place
                        or _anchor(previous) == _anchor(selection))
                    or record is not None and selection is not None
                        and record.baseline.payload['selection'] == selection.kind
                        and (record.natural_place == selection.place or record.current_anchor == _anchor(selection))
                    or record is not None and selection is None and _same_natural(ref.ref, record.natural_place)):
                matches.append(identifier)
        if len(matches) > 1:
            _invalid('Multiple existing dependencies match one located declaration.')
        identifier = matches[0] if matches else str(uuid4())
        available.pop(identifier, None)
        seen[key] = identifier
        occurrences[identifier] = [occurrence]
        requests.append(DependencyRequest(identifier, 'declared', ref.ref))
    return tuple(requests), occurrences


_LOCATION_SQL = """SELECT f.repository,l.kind,l.location,l.metadata,v.source_bytes,f.id
FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
JOIN public.mycel_files f ON f.id=v.file_id WHERE l.id=%s FOR SHARE OF l,v,f NOWAIT"""
_ROWS_SQL = """SELECT id,repository,dependant_version,declaration,source_place,kind,state,baseline_owner
FROM public.mycel_dependencies WHERE repository=%s AND dependant_version=%s
AND state->'declarationLocation'->>'file'=%s AND kind=ANY(ARRAY['declared','asserted','generated'])
ORDER BY id FOR UPDATE NOWAIT"""
# Rows this transaction has written so far to the tables the graph reads.
_GRAPH_WRITES_SQL = """SELECT c.relname,pg_stat_get_xact_tuples_inserted(c.oid),
pg_stat_get_xact_tuples_updated(c.oid),pg_stat_get_xact_tuples_deleted(c.oid)
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname=ANY(ARRAY['mycel_dependencies','mycel_edges','mycel_chunk_versions',
'mycel_chunks']) ORDER BY c.relname"""
# The graph needs each row's declaration location, read as text; the digest of
# its complete state still lets a second read detect any change (SYL-286).
_GRAPH_SQL = """SELECT d.id,d.repository,d.dependant_version,
jsonb_typeof(d.state->'declarationLocation')='object',d.state->'declarationLocation'->>'kind',
d.state->'declarationLocation'->>'location',md5(d.state::text),s.id,c.id,e.source_version
FROM public.mycel_dependencies d JOIN public.mycel_chunk_versions v ON v.id=d.dependant_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id JOIN public.mycel_edges e ON e.dependency=d.id
JOIN public.mycel_chunk_versions sv ON sv.id=e.source_version JOIN public.mycel_chunks s ON s.id=sv.chunk_id
WHERE d.kind=ANY(ARRAY['declared','asserted','generated'])
AND d.repository=ANY(%s) ORDER BY d.id,e.source_version"""


class DependencyApplicationStore:
    def __init__(self, connection):
        self.connection = connection

    def _graph(self, settings, catalog, kind, location, *, exclusions=frozenset(),
               guarded_repositories=None):
        """Complete authoritative graph in this exact catalog/location scope."""
        current = {chunk.version: chunk.identifier for file in catalog.files
                   for chunk in file.chunks
                   if settings.values['repos'].get(file.repository, {}).get('enabled')}
        current.update({chunk.version: chunk.identifier for place, chunk in catalog.index
                        if settings.values['repos'].get(place.repository, {}).get('enabled')})
        current_ids = set(current.values())
        eligible = [name for name, value in settings.values['repos'].items() if value['enabled']]
        rows = self.connection.execute(_GRAPH_SQL, (eligible,)).fetchall()
        selected_location, selectors = _location_selectors(settings, kind, location)
        graph, complete = [], []
        for dependency, owner, version, owned, owned_kind, owned_location, _, source, dependant, _ in rows:
            if version not in current or str(source) not in current_ids:
                continue
            expected_location = selected_location if selectors is None else selectors.get(owner)
            if owned and (owned_kind, owned_location) != (kind, expected_location):
                continue
            # Generated/asserted consumers without a declaration location use
            # their current exact dependant version in the selected catalog.
            edge = GraphEdge(str(source), str(dependant), str(dependency))
            complete.append(edge)
            if str(dependency) not in exclusions:
                graph.append(edge)
        if guarded_repositories is not None:
            # Authority affecting our prospective dependants consists of their
            # complete upstream closure. Disjoint owner rows need no pass lock
            # and cannot invalidate this pass's graph comparison.
            owners = {chunk.identifier: file.repository for file in catalog.files for chunk in file.chunks}
            owners.update({chunk.identifier: place.repository for place, chunk in catalog.index})
            relevant = {identifier for identifier, owner in owners.items() if owner in guarded_repositories}
            while True:
                expanded = relevant | {edge.source for edge in complete if edge.dependant in relevant}
                if expanded == relevant:
                    break
                relevant = expanded
            required = tuple(sorted({owners[identifier] for identifier in relevant}))
            if required:
                require_transaction_guards(self.connection, required)
            graph = [edge for edge in graph if edge.dependant in relevant]
            identifiers = {edge.dependency for edge in complete if edge.dependant in relevant}
            rows = [row for row in rows if str(row[0]) in identifiers]
        return tuple(sorted(set(graph), key=lambda edge: (edge.source, edge.dependant, edge.dependency))), rows

    @contextmanager
    def batch_in_transaction(self, settings: SettingsSnapshot, *, scopes: tuple[tuple[str, int], ...],
                             guarded_repositories: tuple[str, ...] | None = None,
                             observation_dependencies: dict[tuple[str, int], tuple[str, ...]] | None = None):
        """Prepare final declaration authority for a complete guarded batch.

        Existing declared/asserted edges belonging to pending exact scopes are
        replaced by those scopes' complete decisions. Unrelated/generated edges
        remain throughout. Every prepared scope must apply, and the final full
        persisted graph is checked before this token can finish successfully.
        No graph exclusions can be supplied through the application API.
        """
        settings.require_valid(require_store=False)
        guards = tuple(settings.values['repos']) if guarded_repositories is None else guarded_repositories
        require_transaction_guards(self.connection, guards)
        if (type(scopes) is not tuple or not scopes or observation_dependencies is not None
                and (type(observation_dependencies) is not dict or
                     set(observation_dependencies) - set(scopes))):
            _invalid('A dependency batch requires complete exact located scopes.')
        owned, catalogs = {}, set()
        for value in scopes:
            if type(value) is not tuple or len(value) != 2 or type(value[1]) is not int or value[1] < 1:
                _invalid('A dependency batch requires exact location/version pairs.')
            location_id, version = _uuid(value[0]), value[1]
            scope = (location_id, version)
            if scope in owned:
                _invalid('A dependency batch cannot repeat an exact located scope.')
            located = self.connection.execute(_LOCATION_SQL, (location_id,)).fetchone()
            if located is None or not settings.values['repos'].get(located[0], {}).get('enabled'):
                _invalid('A dependency batch requires every enabled current file location.')
            owner, kind, location = located[:3]
            require_transaction_guards(self.connection, (owner,))
            row = self.connection.execute('SELECT 1 FROM public.mycel_locations WHERE file_location=%s '
                'AND chunk_version=%s', (location_id, version)).fetchone()
            if row is None:
                _invalid('A dependency batch dependant is absent from its exact location.')
            rows = self.connection.execute(_ROWS_SQL, (owner, version, location_id)).fetchall()
            identifiers = frozenset(str(row[0]) for row in rows if row[5] in {'declared', 'asserted'})
            if observation_dependencies is not None and scope in observation_dependencies:
                values = observation_dependencies[scope]
                if type(values) is not tuple or len(set(values)) != len(values):
                    _invalid('A foreign observation batch requires distinct exact dependency IDs.')
                selected = frozenset(_uuid(value) for value in values)
                if not selected.issubset(identifiers):
                    _invalid('A foreign observation batch cannot select another located owner.')
                identifiers = selected
            owned[scope] = identifiers
            catalogs.add((kind, location))
        token = _DependencyBatch(self.connection, settings, owned, tuple(sorted(catalogs)), guards)
        try:
            yield token
            require_transaction_guards(self.connection, guards)
            if token.completed != set(token.scopes):
                _invalid('A dependency batch cannot finish before every prepared scope is applied.')
            for kind, location in token.catalogs:
                catalog = SourceResolver.from_transaction(self.connection, settings, kind=kind, location=location,
                                                          guarded_repositories=guards)
                graph, _ = self._graph(settings, catalog, kind, location,
                                      guarded_repositories=guarded_repositories)
                cycle = _cycle(graph)
                if cycle:
                    raise ReconciliationError('dependency_cycle', cycle=cycle)
        finally:
            token.active = False

    def _batch_exclusions(self, batch, settings, scope):
        if batch is None:
            return frozenset()
        if (not isinstance(batch, _DependencyBatch) or not batch.active
                or batch.connection is not self.connection or batch.settings.values != settings.values
                or scope not in batch.scopes or scope in batch.completed):
            _invalid('Dependency application requires its active exact batch scope.')
        return batch.exclusions

    def _baseline(self, row, evidence):
        identifier, repository, version, declaration, place, kind, state, owner = row
        if owner is None:
            if state.get('everResolved'):
                raise EvidenceError('baseline_missing')
            return None
        owning = self.connection.execute(_INHERITANCE_OWNER_SQL, (owner,)).fetchone()
        refs = tuple(self.connection.execute(_INHERITANCE_REFERENCES_SQL, (owner, repository)).fetchall())
        if not refs or refs[0][0:2] != (0, None) or refs[0][2] is None:
            raise EvidenceError('baseline_missing')
        baseline = evidence._read_baseline(repository, refs[0][2], lock=True)
        old_version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL, (version,)).fetchone())
        _validate_inheritance(identifier, (repository, version, declaration, place, kind, owner),
                              baseline, owning, refs, old_version)
        return baseline

    def apply_in_transaction(self, settings: SettingsSnapshot, file_location: str, dependant_version: int, *,
            captured_at: str, reread: Callable, mode='observe', pin_version: int | None = None,
            reference_location: str | None = None, inheritance_authorization='normalized_equivalent_edit',
            assertions: tuple[str, ...] = (), remove_assertions: tuple[AssertedRemoval, ...] = (),
            batch: _DependencyBatch | None = None, assertions_only=False,
            assertion_dependencies: tuple[str, ...] | None = None,
            observation_dependencies: tuple[str, ...] | None = None,
            catalogs: dict | None = None,
            guarded_repositories: tuple[str, ...] | None = None) -> DependencyApplicationReply:
        """Apply one entire located chunk's policy in the caller's guarded change.

        ``reread(expected)`` returns fresh PinInputs/InheritanceInputs of exactly
        the expected type, with complete physical/retained capture/settings guards.
        Recreate RetainedDependencyResolver around the fresh catalog using the
        expected catalog's ``anchors``. Capture publication must recheck its
        complete manifest after all such producers and before committing.

        Reference ownership defaults to this exact location. Selecting another
        location is an explicit identity producer decision, never an automatic
        fallback from a missing disk/branch/stash pin. Historical records stay
        owned by their exact versions. Existing current-version records always
        take precedence and force restoration of their own pins.

        Assertion-only observation can select exact asserted dependency IDs.
        Declarations and other assertions keep their rows, evidence and edges;
        their authority remains in the complete graph and role calculation.
        """
        settings.require_valid(require_store=False)
        guards = tuple(settings.values['repos']) if guarded_repositories is None else guarded_repositories
        require_transaction_guards(self.connection, guards)
        if (type(dependant_version) is not int or dependant_version < 1 or not callable(reread)
                or mode not in {'observe', 'restore', 'inherit', 'edit', 'confirm'}
                or type(assertions) is not tuple or any(not isinstance(raw, str) for raw in assertions)
                or type(remove_assertions) is not tuple or type(assertions_only) is not bool
                or assertion_dependencies is not None and (not assertions_only
                    or type(assertion_dependencies) is not tuple
                    or any(not isinstance(value, str) for value in assertion_dependencies)
                    or len(set(assertion_dependencies)) != len(assertion_dependencies))
                or observation_dependencies is not None and (mode != 'observe'
                    or type(observation_dependencies) is not tuple or assertions or remove_assertions
                    or assertions_only or assertion_dependencies is not None)
                or assertions_only and (mode != 'observe' or batch is not None or pin_version is not None
                    or reference_location is not None and reference_location != file_location)):
            _invalid('Dependency application requires complete typed inputs and a fresh rereader.')
        observed = (None if observation_dependencies is None else
                    tuple(_uuid(identifier) for identifier in observation_dependencies))
        if observed is not None and len(set(observed)) != len(observed):
            _invalid('Foreign dependency observations require distinct exact owners.')
        file_location = _uuid(file_location)
        reference_location = file_location if reference_location is None else _uuid(reference_location)
        exclusions = self._batch_exclusions(batch, settings, (file_location, dependant_version))
        pin_version = dependant_version if pin_version is None else pin_version
        if type(pin_version) is not int or pin_version < 1:
            _invalid('Dependency application requires an exact reference version.')
        located = self.connection.execute(_LOCATION_SQL, (file_location,)).fetchone()
        if located is None:
            _invalid('The selected declaration file location is absent.')
        owner, kind, location, file_metadata, raw, file_id = located
        require_transaction_guards(self.connection, (owner,))
        catalog = SourceResolver.from_transaction(self.connection, settings, kind=kind, location=location,
                                                  guarded_repositories=guards, catalogs=catalogs)
        files = [file for file in catalog.files if file.identifier == str(file_id)]
        if len(files) != 1 or files[0].source != exact_bytes(raw):
            _invalid('The selected location differs from its complete current catalog.')
        file = files[0]
        members = [member for member in catalog._members(file, file.chunks) if member.chunk.version == dependant_version]
        if len(members) != 1:
            _invalid('The dependant exact version is absent from the selected file location.')
        dependant = members[0]
        reference = self.connection.execute(_INHERITANCE_VERSION_SQL, (pin_version,)).fetchone()
        if reference is None or str(reference[1]) != dependant.chunk.identifier or reference[2] != owner:
            _invalid('The identity-selected reference version belongs to another dependant.')
        current_rows = self.connection.execute(_ROWS_SQL, (owner, dependant_version, file_location)).fetchall()
        if current_rows and mode != 'confirm':
            # A known restored version keeps its own existing location pins,
            # regardless of the newer disk version selected by name matching.
            mode, pin_version, reference_location = 'restore', dependant_version, file_location
        all_rows = self.connection.execute(_ROWS_SQL, (owner, pin_version, reference_location)).fetchall()
        rows = [row for row in all_rows if row[5] == 'asserted' and
                (assertion_dependencies is None or str(row[0]) in assertion_dependencies)] if assertions_only else all_rows
        if observed is not None:
            rows = [row for row in rows if str(row[0]) in observed]
            if {str(row[0]) for row in rows} != set(observed):
                _invalid('A foreign dependency observation cannot select another owner.')
            if batch is not None and batch.scopes[(file_location, dependant_version)] != frozenset(observed):
                _invalid('A foreign observation must apply its exact prepared batch scope.')
        if assertion_dependencies is not None and {str(row[0]) for row in rows} != set(assertion_dependencies):
            _invalid('An assertion command cannot select a foreign dependency owner.')
        evidence = EvidenceStore(self.connection)
        collection = CollectionStore(self.connection)
        captures, records = {}, {}
        for row in rows:
            if row[5] not in {'declared', 'asserted'}:
                continue
            identifier = str(row[0])
            capture = self._baseline(row, evidence)
            if capture is not None:
                captures[identifier] = capture
                place = parse_source_address(row[4]) if row[4] else None
                records[identifier] = DependencyRecord(identifier, capture.manifest, place,
                    row[6].get('anchor'), _current_raw(row))
        anchors = {_current_raw(row): row[6]['anchor'] for row in rows if row[6].get('anchor')}
        declarations = file.document_declarations if dependant.chunk.kind == 'document' else None
        refs = next((chunk.sources for chunk in declarations.chunk_sources if chunk.chunk == dependant.chunk.name), ()) if declarations else ()
        if assertions_only:
            refs = ()
        elif observed is not None:
            declared_refs = {_current_raw(row) for row in rows if row[5] == 'declared'}
            refs = tuple(ref for ref in refs if ref.ref in declared_refs)
        resolver = RetainedDependencyResolver(catalog, anchors, {ref.ref: ref.fault for ref in refs if ref.fault})
        requests, occurrences = _match_declarations(refs, rows, resolver, records)
        desired = list(requests)
        asserted_ids = set()
        for declaration in assertions:
            selection = resolver.resolve(declaration).selection
            matching = [str(row[0]) for row in rows if row[5] == 'asserted' and
                (_current_raw(row) == declaration or selection is not None and str(row[0]) in records
                 and records[str(row[0])].baseline.payload['selection'] == selection.kind
                 and (records[str(row[0])].natural_place == selection.place
                      or records[str(row[0])].current_anchor == _anchor(selection)))]
            if len(matching) > 1:
                _invalid('Multiple assertions match the selected natural dependency.')
            identifier = matching[0] if matching else str(uuid4())
            if identifier not in asserted_ids:
                if matching:
                    # An identical asserted selection retains its original
                    # spelling as well as its pin. A qualified/legacy alias
                    # cannot manufacture an assertion mutation or audit row.
                    declaration = _current_raw(next(row for row in rows if str(row[0]) == identifier))
                desired.append(DependencyRequest(identifier, 'asserted', declaration))
                asserted_ids.add(identifier)
        # Never-resolved assertions survive too; the pure planner can only
        # supply implicit requests for assertions that have baseline records.
        for row in rows:
            identifier = str(row[0])
            if row[5] == 'asserted' and identifier not in asserted_ids:
                desired.append(DependencyRequest(identifier, 'asserted', _current_raw(row)))
        for index, request in enumerate(desired):
            resolution = resolver.resolve(request.declaration)
            if request.identifier in records and resolution.fault in {'missing_file', 'missing_name'}:
                natural = records[request.identifier].natural_place
                # Existence in any other eligible location establishes away;
                # no text from that other location enters current evidence.
                if records[request.identifier].baseline.payload['selection'] == 'file':
                    elsewhere = self.connection.execute('SELECT 1 FROM public.mycel_file_locations l '
                        'JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id '
                        'WHERE f.repository=%s AND f.id=%s LIMIT 1',
                        (natural.repository, records[request.identifier].current_anchor)).fetchone()
                else:
                    elsewhere = self.connection.execute('SELECT 1 FROM public.mycel_locations l '
                        'JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version JOIN public.mycel_chunks c ON c.id=v.chunk_id '
                        'WHERE c.repository=%s AND c.id=%s LIMIT 1',
                        (natural.repository, records[request.identifier].current_anchor)).fetchone()
                desired[index] = replace(request, absent_state='away' if elsewhere else 'deleted')
        graph, graph_rows = self._graph(settings, catalog, kind, location, exclusions=exclusions,
                                       guarded_repositories=guarded_repositories)
        graph_writes = self.connection.execute(_GRAPH_WRITES_SQL).fetchall()
        planner_records = tuple(records.values())
        planner_mode, planner_version = mode, pin_version
        if mode == 'inherit':
            if inheritance_authorization not in {'recognized_rename', 'normalized_equivalent_edit'}:
                _invalid('Inheritance requires the accepted identity decision.')
            inherited = []
            for record in planner_records:
                capture = captures[record.identifier]
                version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL,
                    (int(capture.manifest.payload['dependantVersion']),)).fetchone())
                previous_file = evidence._inheritance_file(capture, version,
                    InheritanceInputs(settings, dependant, file, CaptureLocation(kind,
                        file_metadata.get('commit') if kind != 'disk' else None), resolver.resolve(''), resolver), lock=True)
                projected = inherit_baseline(capture, dependant, file, authorization=inheritance_authorization,
                                             previous_file_source=previous_file)
                inherited.append(replace(record, baseline=projected.manifest))
            planner_records = tuple(inherited)
            planner_mode, planner_version = 'observe', dependant_version
        file_role = declarations.role if declarations else None
        if assertions_only or observed is not None:
            # Declared owners stay outside the command's mutation scope. Their
            # present empty-file or retained missing authority still governs
            # role, even without any live chunk-to-chunk graph endpoints.
            for row in all_rows:
                if row[5] not in {'declared', 'asserted'} or row in rows or row[7] is None:
                    continue
                try:
                    target = parse_source_address(row[4] or _current_raw(row)).repository
                except SourceAddressError:
                    continue
                authoritative = (row[6].get('sourceExistence') in {'away', 'deleted'}
                    or row[6].get('sourceState') == 'present' and
                       row[6].get('resolution', {}).get('state') == 'resolved')
                if (settings.values['repos'].get(target, {}).get('enabled')
                        and row[6].get('everResolved') and authoritative):
                    file_role = 'derived'
        plan = plan_dependencies(dependant, resolver, tuple(desired), planner_records, pin_version=planner_version,
            mode=planner_mode, file_role=file_role, graph=graph,
            remove_assertions=remove_assertions)
        unmatched_unpinned = [DependencyDecision(str(row[0]), 'declared', _current_raw(row),
            'release', None, None, None, 'unresolved') for row in rows if row[5] == 'declared'
            and str(row[0]) not in records and str(row[0]) not in {request.identifier for request in desired}]
        if unmatched_unpinned:
            plan = replace(plan, decisions=tuple(sorted((*plan.decisions, *unmatched_unpinned), key=lambda item: item.identifier)))
        if mode == 'inherit':
            plan = replace(plan, decisions=tuple(replace(decision, action='inherit',
                baseline=records[decision.identifier].baseline) if decision.identifier in records and decision.action == 'keep'
                else decision for decision in plan.decisions))
        capture_location = CaptureLocation(kind, file_metadata.get('commit') if kind != 'disk' else None)
        # Even removals and malformed/unresolved declarations must freshly guard
        # complete dependant bytes, metadata, settings and the chosen location.
        guard = InheritanceInputs(settings, dependant, file, capture_location, resolver.resolve(''), resolver,
            {'dependencyApplication': {'location': file_location, 'kind': kind, 'locationKey': location,
                                      'referenceLocation': reference_location, 'pinVersion': pin_version,
                                      'sourcePlaces': {_current_raw(row): records[str(row[0])].natural_place.address
                                          for row in rows if str(row[0]) in records}}})
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            for decision in plan.decisions:
                if decision.resolution is None:
                    continue
                # Observation/restoration also guard present source bytes and
                # current alias bindings; keeping a pin is no exemption from
                # complete current selection and absence checks.
                observation = InheritanceInputs(settings, dependant, file, capture_location,
                    decision.resolution, resolver, guard.guards)
                with checked_transaction_input_guard(self.connection, observation, lambda: reread(observation)):
                    pass
            # The graph rows that matter are guarded; only this transaction's
            # own writes can change them, so a second read follows one.
            if (self.connection.execute(_ROWS_SQL, (owner, pin_version, reference_location)).fetchall() != all_rows
                    or self.connection.execute(_GRAPH_WRITES_SQL).fetchall() != graph_writes
                    and self._graph(settings, catalog, kind, location,
                                    guarded_repositories=guarded_repositories)[1] != graph_rows):
                raise EvidenceError('changed_since_ingest', (dependant.place.address,))
        row_by_id = {str(row[0]): row for row in rows}
        identities, changed, captured_count, inherited_count, released = [], 0, 0, 0, 0
        for decision in plan.decisions:
            previous = row_by_id.get(decision.identifier)
            same_version = previous is not None and pin_version == dependant_version and reference_location == file_location
            identifier = decision.identifier if previous is None or same_version else str(uuid4())
            identities.append((decision.identifier, identifier))
            if decision.action == 'release':
                if same_version:
                    # Classification work can own separate request evidence;
                    # gather/release those concrete owners before the dependency
                    # cascade removes their only live owning rows.
                    collection.release_dependency_in_transaction(identifier, owner)
                    changed += 1
                    released += 1
                continue
            previous_owner = previous[7] if previous is not None and same_version else None
            if decision.action == 'capture':
                selected = decision.current_selection
                inputs = PinInputs(settings, dependant, file, selected, capture_location,
                    decision.resolution, resolver, guard.guards)
                if same_version:
                    # The old manifest remains immutable. A checked authorized
                    # replacement binds the new declaration/place for its CAS.
                    self.connection.execute('UPDATE public.mycel_dependencies SET declaration=%s,source_place=%s WHERE id=%s',
                        (decision.declaration, selected.place.address, identifier))
                authorization = ('owner_confirmation' if mode == 'confirm' else 'dependant_edit' if mode == 'edit'
                                 and previous is not None else 'initial_resolution')
                with checked_transaction_input_guard(self.connection, inputs, lambda: reread(inputs)) as token:
                    evidence.pin_in_transaction(token, dependency_id=identifier, kind=decision.kind,
                        declaration=decision.declaration, captured_at=captured_at,
                        authorization=authorization, expected_owner=previous_owner)
                captured_count += 1
            elif decision.action == 'inherit':
                # Evidence reader validates the immutable audit declaration;
                # the current alias is stored separately below.
                old_resolution = resolver.resolve(previous[3])
                inputs = InheritanceInputs(settings, dependant, file, capture_location,
                    old_resolution, resolver, guard.guards)
                with checked_transaction_input_guard(self.connection, inputs, lambda: reread(inputs)) as token:
                    evidence.inherit_in_transaction(token, previous_dependency=decision.identifier,
                        dependency_id=identifier, authorization=inheritance_authorization)
                inherited_count += 1
            elif previous is None or not same_version:
                self.connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
                    (identifier, owner, dependant_version, _stored(decision.declaration), '', decision.kind, Jsonb({})))
            if decision.action == 'withdraw' and previous_owner is not None:
                self.connection.execute('UPDATE public.mycel_dependencies SET baseline_owner=NULL WHERE id=%s', (identifier,))
                collection.release_baseline_owner_in_transaction(previous_owner, owner)
                released += 1
            current = self.connection.execute('SELECT state,source_place,baseline_owner FROM public.mycel_dependencies WHERE id=%s',
                                             (identifier,)).fetchone()
            state = {**(previous[6] if previous is not None else {}),
                'declarationLocation': {'file': file_location, 'kind': kind, 'location': location},
                'rawRef': _raw(decision.declaration), 'sourceState': 'source_removed' if decision.source_state in {'away', 'deleted'}
                    and decision.action != 'withdraw' else decision.source_state,
                'baselineStatus': 'retained' if current[2] is not None else 'baseline_missing',
                'resolution': {'state': decision.resolution.state if decision.resolution else 'unresolved',
                    'fault': decision.fault, 'candidates': list(decision.resolution.candidates) if decision.resolution else [],
                    'candidateCount': decision.resolution.candidate_count if decision.resolution else 0,
                    'place': decision.current_selection.place.address if decision.current_selection else None},
                'reasons': list(decision.reasons)}
            state['sourceExistence'] = decision.source_state
            if decision.source_state in {'away', 'deleted'} and decision.action != 'withdraw':
                baseline = records[decision.identifier].baseline.payload
                previous_absence = previous[6].get('sourceAbsence') if previous is not None else None
                absence = {'state': decision.source_state, 'place': records[decision.identifier].natural_place.address,
                    'previousFileHash': (previous[6].get('selection', {}).get('fileHash')
                        if previous is not None else None)
                        or (previous_absence.get('previousFileHash') if isinstance(previous_absence, dict) else None)
                        or baseline['members'][0]['evidence'].get('fileHash')}
                if isinstance(previous_absence, dict) and all(previous_absence.get(key) == value
                        for key, value in absence.items()):
                    state['sourceAbsence'] = previous_absence
                else:
                    state['sourceAbsence'] = {**absence, 'observedAt': captured_at}
            else:
                state.pop('sourceAbsence', None)
            if decision.identifier in occurrences:
                occurrence = occurrences[decision.identifier][0]
                state.update(occurrence)
                state['occurrences'] = occurrences[decision.identifier]
            if decision.binding is not None:
                state.update({'anchor': decision.binding.anchor, 'everResolved': True,
                    'selection': {'kind': decision.current_selection.kind,
                        'fileHash': decision.current_selection.file.snapshot_hash,
                        'members': [{'id': member.chunk.identifier, 'version': member.chunk.version,
                            'place': member.place.address, 'hash': member.chunk.snapshot_hash}
                            for member in decision.current_selection.members]}})
            else:
                state.pop('selection', None)
            # Withdrawn missing refs remain visibly unresolved and may initially
            # resolve again later; they no longer claim a surviving baseline.
            if decision.action == 'withdraw':
                state['everResolved'] = False
            place = decision.binding.place.address if decision.binding else previous[4] if previous else ''
            versions = tuple(sorted({member.chunk.version for member in decision.current_selection.members})) if decision.current_selection else ()
            old_edges = tuple(row[0] for row in self.connection.execute('SELECT source_version FROM public.mycel_edges '
                'WHERE dependency=%s ORDER BY source_version', (identifier,)).fetchall())
            old_fault = self.connection.execute('SELECT fault FROM public.mycel_ref_faults WHERE id=%s', (identifier,)).fetchone()
            fault = state['resolution'] if decision.fault is not None else None
            effects = (current[0] != state or current[1] != place or old_edges != versions
                       or old_fault != (None if fault is None else (fault,))
                       or decision.action in {'capture', 'inherit', 'withdraw'})
            if effects:
                self.connection.execute('UPDATE public.mycel_dependencies SET state=%s,source_place=%s WHERE id=%s',
                    (Jsonb(state), place, identifier))
                self.connection.execute('DELETE FROM public.mycel_edges WHERE dependency=%s', (identifier,))
                for version in versions:
                    self.connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (identifier, version))
                self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
                if fault is not None:
                    self.connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,%s,%s)',
                        (identifier, owner, dependant_version, _stored(decision.declaration), Jsonb(fault)))
                changed += 1
        roles_changed, metadata_changed = 0, 0
        location_rows = self.connection.execute('SELECT id,metadata FROM public.mycel_locations WHERE file_location=%s '
            'AND chunk_version=%s ORDER BY id', (file_location, dependant_version)).fetchall()
        for identifier, metadata in location_rows:
            if metadata.get('role') != plan.role:
                self.connection.execute('UPDATE public.mycel_locations SET metadata=%s WHERE id=%s',
                                        (Jsonb({**metadata, 'role': plan.role}), identifier))
                roles_changed += 1
        if declarations is not None and not assertions_only and observed is None:
            metadata = {**file_metadata, 'documentDeclarations': {'metadata': _safe_json(declarations.metadata),
                'diagnostics': [{'code': item.code, 'message': item.message, 'key': item.key, 'line': item.line}
                                for item in declarations.diagnostics]}}
            if metadata != file_metadata:
                self.connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                                        (Jsonb(metadata), file_location))
                metadata_changed += 1
        snapshots, manifests = (collection.collect_evidence_in_transaction(owner)
            if not (assertions_only or observed is not None) or changed or roles_changed or metadata_changed else (0, 0))
        if batch is not None:
            batch.completed.add((file_location, dependant_version))
        return DependencyApplicationReply(plan, tuple(identities), changed, captured_count, inherited_count,
            released, roles_changed, metadata_changed, snapshots, manifests)
