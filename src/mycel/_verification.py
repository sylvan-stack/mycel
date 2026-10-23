"""Exact current-disk confirmation with independently retained evidence.

Dependency pins, related pins, the verification record and applied activity
share one rollback boundary. No path in this producer publishes disk inputs.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import getpass
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation, MutationActivity
from ._capture import LocationId
from ._dependency_application import DependencyApplicationStore, RetainedDependencyResolver, _ROWS_SQL, _current_raw
from ._dependency_inputs import DependencyCaptureInputs
from ._derive import _fault, _place, _canonical_refs, _validate_ref_syntax, _disk_key
from ._errors import MycelError
from ._evidence import (CaptureLocation, EvidenceError, EvidenceStore, InheritanceInputs,
    _chunk_snapshot, canonical_json, checked_transaction_input_guard)
from ._ingest import _ownership, _target, _upstream
from ._locks import atomic_transaction, operation_guard, read_snapshot, require_transaction_guards
from ._markdown import split_markdown
from ._reconciliation import ReconciliationError
from ._relations import RELATION_ROWS_SQL, RelationApplicationStore, _relation_raw, relation_baseline
from ._resolver import SelectionMember, SourceResolver
from ._source_refs import SourceAddressError, parse_source_address, read_document_declarations, parse_entity_uri
from ._staleness import (StaleEdge, StaleNode, StaleReason, _closure, _stored_link,
    plan_staleness, inactive_policy_links)
from ._store import checked_store


def _identity(by):
    by = getpass.getuser() if by is None else by
    if not isinstance(by, str) or not by.strip() or any(ord(char) < 32 for char in by):
        raise MycelError('invalid_input', 'Verification requires a nonempty --by identity.')
    return by


def _arguments(dependant, by, how):
    try:
        place = parse_source_address(dependant)
    except (SourceAddressError, TypeError):
        raise MycelError('invalid_input', 'Confirmation requires one valid Source Ref.') from None
    if place.root == 'index':
        raise MycelError('refused', 'Generated text must be regenerated; it cannot be confirmed.')
    if place.name is None:
        raise MycelError('invalid_input', 'Confirmation requires one current on-disk chunk.')
    by = _identity(by)
    if not isinstance(how, str) or how not in {'read', 'check'}:
        raise MycelError('invalid_input', 'Confirmation --how must be read or check.')
    return place, by


def _time(captured_at):
    try:
        parsed = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
    except (AttributeError, TypeError, ValueError):
        raise MycelError('invalid_input', 'Confirmation requires an exact timezone-aware recording time.') from None
    return parsed


def _located(connection, selection, *, settings=None, lock=True):
    member = selection.members[0]
    rows = connection.execute("""SELECT l.id,l.metadata FROM public.mycel_file_locations l
        JOIN public.mycel_file_versions v ON v.id=l.file_version
        JOIN public.mycel_locations c ON c.file_location=l.id
        WHERE v.file_id=%s AND l.kind='disk' AND l.location=%s AND c.chunk_version=%s
        ORDER BY l.id""" + (' FOR SHARE OF l,v,c NOWAIT' if lock else ''),
        (selection.file.identifier, 'disk' if settings is None else _disk_key(settings, member.place.repository), member.chunk.version)).fetchall()
    if len(rows) != 1:
        raise MycelError('invalid_input', 'Confirmation requires one exact owning disk location.')
    return str(rows[0][0]), rows[0][1]


def _require_confirmable(connection, member, metadata):
    if metadata.get('documentDeclarations', {}).get('metadata', {}).get('generated') is True or connection.execute(
            """SELECT 1 FROM public.mycel_dependencies WHERE dependant_version=%s AND kind='generated'
            UNION SELECT 1 FROM public.mycel_generated_state WHERE chunk_id=%s""",
            (member.chunk.version, member.chunk.identifier)).fetchone():
        raise MycelError('refused', 'Generated text must be regenerated; it cannot be confirmed.')


def _graph_rows(connection, catalog):
    """Current exact disk authority and marks, read without observing sources."""
    members = {member.chunk.version: member for file in catalog.files
               for member in catalog._members(file, file.chunks)}
    members.update((chunk.version, SelectionMember(place, chunk)) for place, chunk in catalog.index)
    rows = connection.execute("""SELECT d.id,d.repository,d.dependant_version,d.kind,d.state,e.source_version
        FROM public.mycel_dependencies d LEFT JOIN public.mycel_edges e ON e.dependency=d.id
        WHERE d.kind=ANY(ARRAY['declared','asserted','generated']) ORDER BY d.id,e.source_version""").fetchall()
    edges = []
    selected = []
    for identifier, owner, version, kind, state, source_version in rows:
        if kind == 'generated':
            candidates = [item for item in members.values() if item.chunk.identifier == state.get('memberId')]
            if len(candidates) == 1:
                source_version = candidates[0].chunk.version
        if version not in members or source_version not in members:
            continue
        location = state.get('declarationLocation', {})
        if kind != 'generated' and (location.get('kind'), location.get('location')) != ('disk', _disk_key(catalog.settings, owner)):
            continue
        selected.append((identifier, owner, version, kind, state, source_version))
        edges.append(StaleEdge(members[source_version].chunk.identifier,
            members[version].chunk.identifier, str(identifier), kind))
    return members, tuple(edges), tuple(selected)


def _guard_scope(connection, settings, dependant):
    catalog = SourceResolver.from_store(connection, settings)
    endpoint = catalog.resolve(dependant, purpose='endpoint')
    if endpoint.state != 'resolved':
        _fault(endpoint, endpoint=True)
    member = endpoint.selection.members[0]
    owner = member.place.repository
    with read_snapshot(connection):
        location, _ = _located(connection, endpoint.selection, settings=settings, lock=False)
        dependencies = connection.execute(_ROWS_SQL.replace(' FOR UPDATE NOWAIT', ''),
            (owner, member.chunk.version, location)).fetchall()
        relations = connection.execute(RELATION_ROWS_SQL.replace(' FOR UPDATE NOWAIT', ''),
            (owner, member.chunk.version, location)).fetchall()
        members, edges, _ = _graph_rows(connection, catalog)
    targets = {owner}
    for row in dependencies:
        targets.update(filter(None, (_target(_current_raw(row)), _target(row[4]))))
    for row in relations:
        targets.update(filter(None, (_target(_relation_raw(row[4])), _target(row[3]))))
    if member.chunk.kind == 'document':
        declarations = read_document_declarations(split_markdown(endpoint.selection.file.source),
            file=endpoint.selection.file.primary.address)
        for groups, attribute in ((declarations.chunk_sources, 'sources'),
                                  (declarations.chunk_relations, 'relations')):
            for group in groups:
                if group.chunk == member.chunk.name:
                    targets.update(filter(None, (_target(ref.ref) for ref in getattr(group, attribute))))
    affected = _closure({member.chunk.identifier}, edges)
    targets.update(item.place.repository for item in members.values()
                   if item.chunk.identifier in affected)
    links = _ownership(connection, settings)
    # The dependency graph substrate checks every authoritative owner in the
    # guarded repositories. Include its upstream closure, preserving unrelated
    # repositories' ability to run their own passes.
    return tuple(sorted(_upstream(targets.intersection(links), links))), member.chunk.identifier


class _Repropagation:
    """Recompose a selected confirmation's remaining and downstream reasons.

    Existing direct observations upstream remain claims of their own passes.
    Confirming a direct source never acknowledges those upstream claims.
    """
    def __init__(self, connection, settings, guarded, identifier):
        self.connection, self.settings, self.guarded = connection, settings, guarded
        self.identifier = identifier
        self.signature = None

    def _read(self):
        catalog = SourceResolver.from_transaction(self.connection, self.settings,
            kind='disk', location='disk', guarded_repositories=self.guarded)
        members, edges, rows = _graph_rows(self.connection, catalog)
        affected = _closure({self.identifier}, edges)
        reverse = tuple(StaleEdge(edge.dependant, edge.source, edge.dependency, edge.kind) for edge in edges)
        needed = _closure(affected, reverse)
        selected = tuple(item for item in members.values() if item.chunk.identifier in needed)
        require_transaction_guards(self.connection, tuple(sorted({item.place.repository for item in selected})))
        versions = [item.chunk.version for item in selected]
        stale = tuple(self.connection.execute("""SELECT id,chunk_version,dependency,reason
            FROM public.mycel_stale_reasons WHERE chunk_version=ANY(%s) ORDER BY id""", (versions,)).fetchall())
        inactive = inactive_policy_links(self.connection, self.settings)
        stale = tuple(row for row in stale if _stored_link(row[2], row[3]) not in inactive)
        selectors = {str(item.chunk.version): _disk_key(self.settings, item.place.repository) for item in selected}
        locations = tuple(self.connection.execute("""SELECT l.chunk_version,l.metadata,COALESCE(f.metadata,'{}'::jsonb)
            FROM public.mycel_locations l LEFT JOIN public.mycel_file_locations f ON f.id=l.file_location
            WHERE (l.kind='index' OR (l.kind='disk' AND f.kind='disk'
                AND f.location=(%s::jsonb)->>l.chunk_version::text)) AND l.chunk_version=ANY(%s) ORDER BY l.id""",
            (Jsonb(selectors), versions)).fetchall())
        relevant = tuple(row for row in rows if row[2] in versions)
        return catalog, selected, edges, relevant, stale, locations, affected

    @staticmethod
    def _signature(value):
        _, members, edges, rows, stale, locations, affected = value
        return members, tuple(edge for edge in edges if edge.dependant in {item.chunk.identifier for item in members}), rows, stale, locations, affected

    def apply(self, direct):
        value = self._read()
        _, members, edges, _, stored, locations, affected = value
        metadata = {version: (chunk, file) for version, chunk, file in locations}
        nodes = []
        current = {item.chunk.version: item for item in members}
        for item in members:
            declarations = metadata[item.chunk.version][1].get('documentDeclarations', {}).get('metadata', {})
            nodes.append(StaleNode(item.chunk.identifier, item.chunk.version, item.place,
                item.chunk.kind == 'document' and
                (declarations.get('generated') is True or declarations.get('heartwood') is True)))
        reasons = defaultdict(list)
        for _, version, dependency, reason in stored:
            item = current[version]
            if item.chunk.identifier == self.identifier or reason['kind'] == 'upstream_stale':
                continue
            reasons[item.chunk.identifier].append((_stored_link(dependency, reason),
                StaleReason(reason['kind'], parse_source_address(reason['source']['address']), reason['edge'],
                    tuple(parse_source_address(place['address']) for place in reason.get('via', ())))))
        reasons[self.identifier] = list(direct)
        node_ids = {node.identifier for node in nodes}
        plan = plan_staleness(tuple(nodes), tuple(edge for edge in edges
            if edge.source in node_ids and edge.dependant in node_ids), dict(reasons))
        for node in nodes:
            if node.identifier not in affected:
                continue
            wanted = {}
            for dependency, reason in plan[node.identifier]:
                record = reason.record()
                if reason.edge == 'related':
                    record['relation'] = dependency
                wanted[(dependency, canonical_json(record))] = record
            old = {(_stored_link(dependency, reason), canonical_json({key: val for key, val in reason.items()
                    if key != 'classification'})): identifier for identifier, version, dependency, reason in stored
                   if version == node.version}
            for key in old.keys() - wanted.keys():
                self.connection.execute('DELETE FROM public.mycel_stale_reasons WHERE id=%s', (old[key],))
            for dependency, encoded in sorted(wanted.keys() - old.keys()):
                identifier = uuid5(NAMESPACE_URL, 'mycel:stale:' + str(node.version) + ':' + dependency + ':' + encoded.decode())
                self.connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,%s,%s)',
                    (identifier, node.place.repository, node.version,
                     None if wanted[(dependency, encoded)]['edge'] == 'related' else dependency,
                     Jsonb(wanted[(dependency, encoded)])))
        self.signature = self._signature(self._read())

    def verify(self):
        if self.signature != self._signature(self._read()):
            raise EvidenceError('changed_since_ingest')


class ConfirmationStore:
    def __init__(self, connection):
        self.connection = connection

    def apply(self, settings, dependant, *, by=None, how='read', captured_at=None,
              build=None, settings_home=None):
        settings.require_valid(require_store=False)
        canonical, = _canonical_refs(self.connection, settings, (dependant,), ('endpoint',))
        place, by = _arguments(canonical, by, how)
        if not settings.values['repos'].get(place.repository, {}).get('enabled'):
            raise MycelError('invalid_input', 'Confirmation requires an enabled registered repository.')
        captured_at = (datetime.now(timezone.utc).isoformat(timespec='microseconds')
                       if captured_at is None else captured_at)
        _time(captured_at)
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            guarded, identifier = _guard_scope(self.connection, settings, dependant)
            for repository in guarded:
                stack.enter_context(operation_guard(self.connection, repository, 'pass'))
            audit = None if build is None else MutationActivity(self.connection, build=build)
            stack.enter_context(nullcontext() if audit is None else audit.session())
            try:
                with atomic_transaction(self.connection):
                    reply = self.apply_in_transaction(settings, dependant, by=by, how=how,
                        captured_at=captured_at, settings_home=settings_home, activity=audit,
                        guarded_repositories=guarded, expected_identifier=identifier)
            except EvidenceError as error:
                raise MycelError('invalid_input', 'Confirmation refused: ' + error.status + '; ' +
                    ', '.join(error.addresses or (place.address,)) + '.') from None
            except ReconciliationError as error:
                raise MycelError('invalid_input', f'Confirmation refused: {error.status}.') from None
            if audit is not None:
                audit.finish('done', counts={(place.repository, 'confirm'): reply})
            return reply

    def apply_in_transaction(self, settings, dependant, *, by=None, how='read', captured_at,
                             settings_home=None, activity=None, guarded_repositories=None,
                             expected_identifier=None, inputs=None):
        settings.require_valid(require_store=False)
        _validate_ref_syntax((dependant,))
        _time(captured_at)
        guarded = tuple(settings.values['repos']) if guarded_repositories is None else guarded_repositories
        require_transaction_guards(self.connection, guarded)
        catalog = SourceResolver.from_transaction(self.connection, settings, kind='disk',
            location='disk', guarded_repositories=guarded)
        dependant, = _canonical_refs(self.connection, settings, (dependant,), ('endpoint',), catalog=catalog)
        _, by = _arguments(dependant, by, how)
        endpoint = catalog.resolve(dependant, purpose='endpoint')
        if endpoint.state != 'resolved':
            _fault(endpoint, endpoint=True)
        selection, member = endpoint.selection, endpoint.selection.members[0]
        owner = member.place.repository
        if expected_identifier is not None and member.chunk.identifier != expected_identifier:
            raise EvidenceError('changed_since_ingest', (member.place.address,))
        location, metadata = _located(self.connection, selection, settings=settings)
        _require_confirmable(self.connection, member, metadata)
        # A batch caller passes its shared inputs and verifies them at its end.
        shared = inputs is not None
        if not shared:
            inputs = DependencyCaptureInputs(self.connection, settings, settings_home=settings_home,
                guarded_repositories=guarded)
        reread = inputs.rereader(LocationId('disk', None, 'disk'), owner, None)
        resolver = RetainedDependencyResolver(catalog, {})
        guard = InheritanceInputs(settings, member, selection.file, CaptureLocation('disk'),
            resolver.resolve(''), resolver, {'dependencyApplication': {'sourcePlaces': {}}})
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            dependencies = DependencyApplicationStore(self.connection).apply_in_transaction(settings,
                location, member.chunk.version, mode='confirm', captured_at=captured_at, reread=reread,
                guarded_repositories=guarded)
            RelationApplicationStore(self.connection).apply_in_transaction(settings, location,
                member.chunk.version, mode='confirm', captured_at=captured_at, reread=reread,
                guarded_repositories=guarded)
            captures, selections, sources = [], [], []
            store = DependencyApplicationStore(self.connection)
            evidence = EvidenceStore(self.connection)
            rows = self.connection.execute(_ROWS_SQL, (owner, member.chunk.version, location)).fetchall()
            links = [(row, store._baseline(row, evidence), row[5], _current_raw(row), False) for row in rows
                     if row[5] in {'declared', 'asserted'} and row[7] is not None]
            related = self.connection.execute(RELATION_ROWS_SQL, (owner, member.chunk.version, location)).fetchall()
            links += [(row, relation_baseline(self.connection, row, evidence), 'related', _relation_raw(row[4]),
                       row[4].get('endpoint', False)) for row in related if row[5] is not None]
            for row, capture, kind, raw, endpoint_ref in sorted(links,
                    key=lambda item: (item[2], item[1].manifest.payload['source']['address'], item[3], str(item[0][0]))):
                manifest = capture.manifest
                captures.append(capture)
                checked = []
                for value in manifest.payload['members']:
                    descriptor = value['evidence']
                    item = {'place': dict(value['place']), 'hash': descriptor['hash'],
                        'comparisonHash': descriptor['comparison']['hash'], 'snapshot': descriptor['snapshot']}
                    if manifest.payload['selection'] != 'file':
                        current = next((chunk for file in catalog.files for chunk in file.chunks
                            if chunk.identifier == value['id']), None)
                        if current is None:
                            raise EvidenceError('changed_since_ingest')
                        item.update(chunkId=current.identifier, versionId=current.version)
                    checked.append(item)
                    sources.append({key: value for key, value in item.items() if key not in {'chunkId', 'versionId'}})
                selections.append({'edgeKind': kind, 'rawRef': raw, 'manifest': manifest.identifier,
                    'endpoint': bool(endpoint_ref), 'members': checked})
            blob = _chunk_snapshot(member, selection.file)
            identifier, evidence_owner = str(uuid4()), uuid4()
            self._retain(owner, identifier, evidence_owner, blob, captures)
            # The same exact text can own different refs in other locations.
            # Only this disk location's faults invalidate its confirmation;
            # withdrawn declared sources still retain their owning fault rows.
            from ._verification_reader import has_verification_fault
            has_fault = has_verification_fault(self.connection, owner, member.chunk.version, location)
            public = {'id': identifier, 'chunk': _place(member.place), 'chunkId': member.chunk.identifier,
                'version': member.chunk.snapshot_hash, 'textHash': member.chunk.snapshot_hash,
                'dependantSnapshot': f'snapshot:{blob.evidence.hash}',
                'baselineManifests': [capture.manifest.identifier for capture in captures],
                'sources': sources, 'by': by, 'how': how, 'at': captured_at, 'current': not has_fault}
            record = {**{key: value for key, value in public.items() if key != 'current'}, 'schema': 'mycel-verification-v1',
                'dependant': {'versionId': member.chunk.version, 'textHash': member.chunk.snapshot_hash,
                    'comparisonHash': blob.evidence.comparison.hash, 'place': _place(member.place),
                    'snapshot': f'snapshot:{blob.evidence.hash}'}, 'selections': selections}
            if _disk_key(settings, owner) != 'disk':
                record['diskLocation'] = _disk_key(settings, owner)
            self.connection.execute('INSERT INTO public.mycel_verifications '
                '(id,repository,chunk_id,recorded_at,record,evidence_owner) VALUES (%s,%s,%s,%s,%s,%s)',
                (identifier, owner, member.chunk.identifier, captured_at, Jsonb(record), evidence_owner))
            direct = tuple((decision.identifier, StaleReason(reason, decision.natural_place, decision.kind))
                for decision in dependencies.plan.decisions for reason in decision.reasons)
            propagation = _Repropagation(self.connection, settings, guarded, member.chunk.identifier)
            propagation.apply(direct)
            from ._drift_store import DriftStore
            propagated = propagation._read()
            DriftStore(self.connection).sync_in_transaction(settings, guarded, at=captured_at,
                versions=tuple(item.chunk.version for item in propagated[1]
                    if item.chunk.identifier in propagated[-1]),
                closure={member.chunk.version: 'confirmed'}, verification=public)
            # Classification annotations are work evidence on mechanical reasons;
            # retain them in the exact post-confirmation CAS as well.
            propagation.signature = propagation._signature(propagation._read())
            if activity is not None:
                if activity.connection is not self.connection:
                    raise MycelError('invalid_input', 'Confirmation activity requires its writing connection.')
                activity.record_in_transaction(owner, 'confirm', AppliedMutation(True, public))
            from ._verification_reader import validate_verification_record
            stored = self.connection.execute('SELECT id,repository,chunk_id,recorded_at,record,evidence_owner '
                'FROM public.mycel_verifications WHERE id=%s FOR SHARE NOWAIT', (identifier,)).fetchone()
            if stored is None or stored[4] != record:
                raise EvidenceError('snapshot_corrupt')
            validate_verification_record(self.connection, stored)
            if (self.connection.execute(_ROWS_SQL, (owner, member.chunk.version, location)).fetchall() != rows
                    or self.connection.execute(RELATION_ROWS_SQL,
                        (owner, member.chunk.version, location)).fetchall() != related
                    or has_verification_fault(self.connection, owner, member.chunk.version, location) != has_fault):
                raise EvidenceError('changed_since_ingest', (member.place.address,))
            # The guarded endpoint's complete disk file, each selected source,
            # settings, record evidence and final graph all fit after callbacks.
            reread(guard)
            if not shared:
                inputs.verify()
            propagation.verify()
            return public

    def _retain(self, repository, identifier, owner, dependant, captures):
        snapshots = {dependant.evidence.hash: dependant}
        manifests = {}
        for capture in captures:
            manifests[capture.manifest.identifier] = capture.manifest
            snapshots.update((blob.evidence.hash, blob) for blob in capture.snapshots)
        for digest, blob in sorted(snapshots.items()):
            metadata = {'schema': 1, 'bytes': len(blob.source), 'encoding': blob.evidence.encoding}
            self.connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (repository, digest, blob.source, Jsonb(metadata)))
            row = self.connection.execute('SELECT bytes,metadata FROM public.mycel_snapshots WHERE repository=%s '
                'AND hash=%s FOR SHARE NOWAIT', (repository, digest)).fetchone()
            if row is None or bytes(row[0]) != blob.source or row[1] != metadata:
                raise EvidenceError('snapshot_corrupt')
        self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
            (owner, repository, 'verification', identifier))
        references = [(None, digest) for digest in sorted(manifests)] + [(digest, None) for digest in sorted(snapshots)]
        for ordinal, (snapshot_hash, manifest_hash) in enumerate(references):
            self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                (owner, repository, snapshot_hash, manifest_hash, ordinal))


def handle_confirm(invocation):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store
    arguments, values, refs = iter(invocation.arguments), {}, []
    for argument in arguments:
        if argument in {'--by', '--how'}:
            if argument in values:
                raise MycelError('invalid_input', 'Confirmation options cannot repeat.')
            try:
                values[argument] = next(arguments)
            except StopIteration:
                raise MycelError('invalid_input', 'Confirmation option requires a value.') from None
        else:
            refs.append(argument)
    if len(refs) != 1:
        raise MycelError('invalid_input', 'Use mycel confirm [--by <who>] [--how read|check] <chunk>.')
    if parse_entity_uri(refs[0]) is not None:
        _validate_ref_syntax(refs)
    else:
        _arguments(refs[0], values.get('--by'), values.get('--how', 'read'))
    with invocation_store(invocation, operation='write') as (connection, _):
        return Result(ConfirmationStore(connection).apply(invocation.settings, refs[0],
            by=values.get('--by'), how=values.get('--how', 'read'), build=current_build()))
