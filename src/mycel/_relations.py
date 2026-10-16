"""Exact location-owned relations, independent of the authority graph.

Every baseline belongs to one dependant version and one declaration location.
The producer opens no transaction; callers retain complete capture guards until
publication and its activity have both finished.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._collection import CollectionStore
from ._declared_refs import _raw, _stored, _text
from ._dependency_application import (RetainedDependencyResolver, _LOCATION_SQL,
    _anchor, _match_declarations, _same_natural, _uuid)
from ._errors import MycelError
from ._evidence import (CaptureLocation, ComparisonRecord, EvidenceError, EvidenceStore,
    InheritanceInputs, PinInputs, _INHERITANCE_OWNER_SQL, _INHERITANCE_REFERENCES_SQL,
    _INHERITANCE_VERSION_SQL, _inheritance_version, _validate_inheritance,
    capture_baseline, checked_transaction_input_guard, chunk_comparison, inherit_baseline)
from ._locks import require_transaction_guards
from ._markdown import split_markdown
from ._reconciliation import DependencyRequest, _comparison
from ._resolver import SourceResolver
from ._source_refs import parse_source_address, read_document_declarations
from ._store import exact_bytes


RELATION_ROWS_SQL = """SELECT id,repository,left_version,right_place,state,baseline_owner
FROM public.mycel_relations WHERE repository=%s AND left_version=%s
AND state->'declarationLocation'->>'file'=%s ORDER BY id FOR UPDATE NOWAIT"""


def _relation_raw(state):
    return _text(state['rawRefHex']) if 'rawRefHex' in state else state['rawRef']


def _relation_syntax_faults(refs, resolver):
    # A malformed occurrence cannot invalidate a separately valid declaration
    # of the same selection. Keep its own fault in the occurrence evidence.
    selections = {ref.ref: resolver.resolve(ref.ref).selection for ref in refs}
    valid_refs = {ref.ref for ref in refs if ref.fault is None}
    valid = {(selection.kind, selection.place.address) for ref in refs
             if ref.fault is None and (selection := selections[ref.ref]) is not None}
    return {ref.ref: ref.fault for ref in refs if ref.fault and ref.ref not in valid_refs and
            ((selection := selections[ref.ref]) is None or
             (selection.kind, selection.place.address) not in valid)}


@dataclass(frozen=True)
class _RelationRecord:
    baseline: object
    natural_place: object
    current_anchor: str | None


def relation_baseline(connection, row, evidence=None):
    identifier, repository, version, place, state, owner = row
    if owner is None:
        if state.get('everResolved'):
            raise EvidenceError('baseline_missing')
        return None
    evidence = evidence or EvidenceStore(connection)
    refs = tuple(connection.execute(_INHERITANCE_REFERENCES_SQL, (owner, repository)).fetchall())
    if not refs or refs[0][:2] != (0, None) or refs[0][2] is None:
        raise EvidenceError('baseline_missing')
    baseline = evidence._read_baseline(repository, refs[0][2], lock=True)
    previous = _inheritance_version(connection.execute(_INHERITANCE_VERSION_SQL, (version,)).fetchone())
    _validate_inheritance(identifier, (repository, version,
        state.get('baselineRef', _relation_raw(state)), place, 'related', owner), baseline,
        connection.execute(_INHERITANCE_OWNER_SQL, (owner,)).fetchone(), refs, previous)
    return baseline


@dataclass(frozen=True)
class RelationApplicationReply:
    changed: int
    checked: int
    captured: int
    inherited: int
    released: int
    faults: int
    identifiers: tuple[tuple[str, str], ...] = ()

    @property
    def mutated(self):
        return bool(self.changed)

    @property
    def counts(self):
        return {'relationsChecked': self.checked, 'relationsChanged': self.changed,
                'relationPinsCaptured': self.captured, 'relationPinsInherited': self.inherited,
                'relationBaselinesReleased': self.released, 'relationFaults': self.faults}


class RelationApplicationStore:
    def __init__(self, connection):
        self.connection = connection

    def apply_in_transaction(self, settings, file_location, dependant_version, *, captured_at,
            reread, mode='observe', pin_version=None, reference_location=None,
            inheritance_authorization='normalized_equivalent_edit', assertions=(),
            assertions_only=False, selected_assertions=None, remove=False,
            observation_relations: tuple[str, ...] | None = None,
            guarded_repositories: tuple[str, ...] | None = None):
        settings.require_valid(require_store=False)
        guards = tuple(settings.values['repos']) if guarded_repositories is None else guarded_repositories
        require_transaction_guards(self.connection, guards)
        if (type(dependant_version) is not int or dependant_version < 1 or not callable(reread)
                or mode not in {'observe', 'restore', 'inherit', 'edit', 'confirm'}
                or type(assertions) is not tuple or any(not isinstance(raw, str) for raw in assertions)
                or type(assertions_only) is not bool or type(remove) is not bool
                or remove and not assertions_only
                or selected_assertions is not None and (not assertions_only
                    or type(selected_assertions) is not tuple)
                or observation_relations is not None and (mode != 'observe'
                    or type(observation_relations) is not tuple or assertions
                    or assertions_only or selected_assertions is not None or remove)):
            raise MycelError('invalid_input', 'Relations require complete exact typed inputs.')
        observed = (None if observation_relations is None else
                    tuple(_uuid(identifier) for identifier in observation_relations))
        if observed is not None and len(set(observed)) != len(observed):
            raise MycelError('invalid_input', 'Relation observations require distinct exact owners.')
        file_location = _uuid(file_location)
        reference_location = file_location if reference_location is None else _uuid(reference_location)
        pin_version = dependant_version if pin_version is None else pin_version
        located = self.connection.execute(_LOCATION_SQL, (file_location,)).fetchone()
        if located is None:
            raise MycelError('invalid_input', 'The relation location is absent.')
        owner, kind, location, metadata, raw, file_id = located
        require_transaction_guards(self.connection, (owner,))
        catalog = SourceResolver.from_transaction(self.connection, settings, kind=kind, location=location,
                                                  guarded_repositories=guards)
        files = [file for file in catalog.files if file.identifier == str(file_id)]
        if len(files) != 1 or files[0].source != exact_bytes(raw):
            raise EvidenceError('changed_since_ingest')
        file = files[0]
        members = [member for member in catalog._members(file, file.chunks)
                   if member.chunk.version == dependant_version]
        if len(members) != 1:
            raise MycelError('invalid_input', 'The relation needs one exact located dependant.')
        dependant = members[0]
        reference = self.connection.execute(_INHERITANCE_VERSION_SQL, (pin_version,)).fetchone()
        if reference is None or str(reference[1]) != dependant.chunk.identifier or reference[2] != owner:
            raise MycelError('invalid_input', 'The relation reference version belongs to another dependant.')
        current_rows = self.connection.execute(RELATION_ROWS_SQL, (owner, dependant_version, file_location)).fetchall()
        if current_rows and mode != 'confirm':
            mode, pin_version, reference_location = 'restore', dependant_version, file_location
        all_rows = self.connection.execute(RELATION_ROWS_SQL, (owner, pin_version, reference_location)).fetchall()
        rows = [row for row in all_rows if row[4].get('ownership') == 'asserted' and
                (selected_assertions is None or str(row[0]) in selected_assertions)] if assertions_only else all_rows
        if observed is not None:
            # A foreign source pass observes only its selected incoming records.
            # The remaining rows still participate in exact owner validation;
            # their evidence and source observations must stay untouched.
            rows = [row for row in rows if str(row[0]) in observed]
            if {str(row[0]) for row in rows} != set(observed):
                raise MycelError('invalid_input', 'Relation observations cannot select another owner.')
        if selected_assertions is not None and {str(row[0]) for row in rows} != set(selected_assertions):
            raise MycelError('invalid_input', 'A relation command cannot select another owner.')
        evidence, collection = EvidenceStore(self.connection), CollectionStore(self.connection)
        captures, records = {}, {}
        mapped = []
        for row in rows:
            identifier, _, version, place, state, _ = row
            if state.get('ownership') not in {'declared', 'asserted'}:
                raise MycelError('invalid_input', 'A relation requires exact declared/asserted ownership.')
            capture = relation_baseline(self.connection, row, evidence)
            if capture is not None:
                if (capture.manifest.payload['dependantId'] != dependant.chunk.identifier
                        or mode in {'observe', 'restore', 'confirm'} and
                           capture.manifest.payload['dependant']['hash'] != dependant.chunk.snapshot_hash
                        or mode == 'edit' and ComparisonRecord.from_record(
                            capture.manifest.payload['dependant']['comparison']) == chunk_comparison(dependant.chunk)):
                    raise EvidenceError('changed_since_ingest', (dependant.place.address,))
                captures[str(identifier)] = capture
                records[str(identifier)] = _RelationRecord(capture.manifest,
                    parse_source_address(place), state.get('anchor'))
            mapped.append((identifier, owner, version, _relation_raw(state), place, state['ownership'],
                           {**state, 'rawRef': _raw(_relation_raw(state))}, row[5]))
        declarations = (read_document_declarations(split_markdown(file.source), file=file.primary.address)
                        if dependant.chunk.kind == 'document' else None)
        refs = next((group.relations for group in declarations.chunk_relations
                     if group.chunk == dependant.chunk.name), ()) if declarations and not assertions_only else ()
        if observed is not None:
            declared_refs = {_relation_raw(row[4]) for row in rows if row[4]['ownership'] == 'declared'}
            refs = tuple(ref for ref in refs if ref.ref in declared_refs)
        if mode == 'confirm' and any(ref.fault for ref in refs):
            raise MycelError('invalid_input', 'Confirmation requires every relation declaration to be valid.')
        anchors = {_relation_raw(row[4]): row[4]['anchor'] for row in rows if row[4].get('anchor')}
        syntax_faults = _relation_syntax_faults(refs, RetainedDependencyResolver(catalog, anchors))
        resolver = RetainedDependencyResolver(catalog, anchors, syntax_faults)
        # Valid selections claim their existing owners before fault-only refs
        # can match a former natural spelling. Restore physical report order.
        requests, occurrences = _match_declarations(
            sorted(refs, key=lambda ref: ref.fault is not None), mapped, resolver, records)
        for values in occurrences.values():
            values.sort(key=lambda occurrence: occurrence['line'] or 0)
        desired = list(requests)
        desired_ids = {request.identifier for request in desired}
        for raw_ref in assertions:
            selection = RetainedDependencyResolver(catalog, anchors, endpoint_refs=(raw_ref,)).resolve(raw_ref).selection
            matches = [row for row in rows if row[4]['ownership'] == 'asserted' and
                (_relation_raw(row[4]) == raw_ref or selection is not None and
                 (row[3] == selection.place.address or row[4].get('anchor') == _anchor(selection)))]
            if len(matches) > 1:
                raise MycelError('invalid_input', 'Multiple asserted relations match one selection.')
            identifier = str(matches[0][0]) if matches else str(uuid4())
            if identifier not in desired_ids:
                desired.append(DependencyRequest(identifier, 'asserted',
                    _relation_raw(matches[0][4]) if matches else raw_ref))
                desired_ids.add(identifier)
        for row in rows:
            identifier = str(row[0])
            if identifier not in desired_ids and (row[4]['ownership'] == 'asserted'
                    or not row[4].get('managedDeclaration')):
                # Earlier retained-only callers supply independently observed
                # links, not a complete declaration reconciliation batch.
                desired.append(DependencyRequest(identifier, row[4]['ownership'], _relation_raw(row[4])))
        by_id = {str(row[0]): row for row in rows}
        capture_location = CaptureLocation(kind, metadata.get('commit') if kind != 'disk' else None)
        source_places = {_relation_raw(row[4]): row[3] for row in rows if str(row[0]) in records}
        guards = {'dependencyApplication': {'sourcePlaces': source_places}}
        changed = captured = inherited = released = faults = 0
        identities = []
        guard = InheritanceInputs(settings, dependant, file, capture_location, resolver.resolve(''), resolver, guards)
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            if self.connection.execute(RELATION_ROWS_SQL, (owner, pin_version, reference_location)).fetchall() != all_rows:
                raise EvidenceError('changed_since_ingest', (dependant.place.address,))
        for request in (*desired, *(DependencyRequest(identifier, 'declared', _relation_raw(row[4]))
                for identifier, row in by_id.items() if identifier not in {item.identifier for item in desired})):
            previous = by_id.get(request.identifier)
            same = previous is not None and pin_version == dependant_version and reference_location == file_location
            identifier = request.identifier if previous is None or same else str(uuid4())
            identities.append((request.identifier, identifier))
            discard = request not in desired or remove and request.kind == 'asserted'
            old_owner = previous[5] if previous is not None and same else None
            old = captures.get(request.identifier)
            resolver = RetainedDependencyResolver(catalog, anchors,
                syntax_faults if request.kind == 'declared' else {},
                endpoint_refs=(request.declaration,) if request.kind == 'asserted' else ())
            resolution = resolver.resolve(request.declaration)
            observation = InheritanceInputs(settings, dependant, file, capture_location, resolution, resolver, guards)
            with checked_transaction_input_guard(self.connection, observation, lambda: reread(observation)):
                if discard:
                    if same:
                        self.connection.execute('DELETE FROM public.mycel_relations WHERE id=%s', (identifier,))
                        self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
                        self.connection.execute("DELETE FROM public.mycel_stale_reasons WHERE reason->>'relation'=%s", (identifier,))
                        if old_owner is not None:
                            collection.release_baseline_owner_in_transaction(old_owner, owner)
                            released += 1
                        changed += 1
                    continue
                selection = resolution.selection
                missing = old is not None and resolution.fault in {'missing_file', 'missing_name'}
                if missing and mode in {'edit', 'confirm'} and request.kind == 'asserted':
                    if same:
                        self.connection.execute('DELETE FROM public.mycel_relations WHERE id=%s', (identifier,))
                        self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
                        self.connection.execute("DELETE FROM public.mycel_stale_reasons WHERE reason->>'relation'=%s", (identifier,))
                        if old_owner is not None:
                            collection.release_baseline_owner_in_transaction(old_owner, owner)
                            released += 1
                    changed += int(same)
                    continue
                if mode == 'confirm' and selection is None and not missing:
                    raise MycelError('invalid_input', 'Confirmation requires every relation to resolve.')
                if (old is not None and selection is not None
                        and selection.place.address != previous[3]
                        and previous[4].get('anchor') != _anchor(selection)):
                    raise MycelError('invalid_input', 'An existing relation cannot bind another source selection.')
                natural = selection.place.address if selection is not None else previous[3] if previous else _stored(request.declaration)
                state = {**(previous[4] if previous else {}), 'rawRef': _stored(request.declaration),
                    'rawRefHex': _raw(request.declaration), 'ownership': request.kind,
                    'endpoint': request.kind == 'asserted',
                    'declarationLocation': {'file': file_location, 'kind': kind, 'location': location},
                    'resolution': {'state': resolution.state, 'fault': resolution.fault,
                        'candidates': list(resolution.candidates), 'candidateCount': resolution.candidate_count,
                        'place': selection.place.address if selection else None}}
                if request.identifier in occurrences:
                    state.update(managedDeclaration=True, occurrences=occurrences[request.identifier])
                baseline_owner = old_owner
                repin = selection is not None and (old is None or mode in {'edit', 'confirm'})
                if repin:
                    inputs = PinInputs(settings, dependant, file, selection, capture_location, resolution, resolver, guards)
                    baseline = capture_baseline(owner, dependant, file, selection, kind='related',
                        declaration=request.declaration, captured_at=captured_at, location=capture_location)
                    with checked_transaction_input_guard(self.connection, inputs, lambda: reread(inputs)) as token:
                        baseline_owner = evidence._write(token, baseline, f'{identifier}:{baseline.manifest.identifier}')
                    state['baselineRef'] = request.declaration
                    captured += 1
                elif old is not None and not same and mode in {'inherit', 'restore'}:
                    previous_version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL,
                        (pin_version,)).fetchone())
                    previous_file = evidence._inheritance_file(old, previous_version, observation, lock=True)
                    baseline = inherit_baseline(old, dependant, file, authorization=inheritance_authorization,
                                                previous_file_source=previous_file)
                    with checked_transaction_input_guard(self.connection, observation, lambda: reread(observation)) as token:
                        baseline_owner = evidence._write(token, baseline, f'{identifier}:{baseline.manifest.identifier}',
                                                         include_sources=False)
                    inherited += 1
                elif missing and mode in {'edit', 'confirm'}:
                    baseline_owner = None
                    state.pop('baselineRef', None)
                elif mode == 'edit' and request.declaration in syntax_faults:
                    baseline_owner = None
                    state.pop('baselineRef', None)
                elif old is not None and not same:
                    raise MycelError('invalid_input', 'A new relation version needs edit or inherited evidence.')
                reasons = []
                if old is not None and selection is not None and not repin:
                    if ComparisonRecord.from_record(old.manifest.payload['selectionComparison']) != _comparison(selection):
                        reasons.append('related_changed')
                    if old.manifest.payload['selection'] == 'family':
                        present = {member.chunk.identifier for member in selection.members}
                        places = {member.place.address for member in selection.members}
                        if any(member['id'] not in present and member['place']['address'] not in places
                               for member in old.manifest.payload['members']):
                            reasons.insert(0, 'source_removed')
                existence = 'present' if selection is not None else 'ineligible' if resolution.state == 'invalid' else 'unresolved'
                if missing and baseline_owner is not None:
                    place = parse_source_address(previous[3])
                    table = ('mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version '
                             'JOIN public.mycel_files c ON c.id=v.file_id') if old.manifest.payload['selection'] == 'file' else (
                             'mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version '
                             'JOIN public.mycel_chunks c ON c.id=v.chunk_id')
                    away = self.connection.execute(f'SELECT 1 FROM public.{table} WHERE c.repository=%s '
                        'AND c.id::text=%s LIMIT 1', (place.repository, previous[4].get('anchor'))).fetchone()
                    existence = 'away' if away else 'deleted'
                    reasons = ['source_removed']
                    absence = {'state': existence, 'place': natural, 'previousFileHash':
                        previous[4].get('selection', {}).get('fileHash') or
                        previous[4].get('sourceAbsence', {}).get('previousFileHash') or
                        old.manifest.payload['members'][0]['evidence'].get('fileHash')}
                    existing_absence = previous[4].get('sourceAbsence')
                    state['sourceAbsence'] = (existing_absence if existing_absence and
                        all(existing_absence.get(key) == value for key, value in absence.items())
                        else {**absence, 'observedAt': captured_at})
                else:
                    state.pop('sourceAbsence', None)
                state.update(everResolved=baseline_owner is not None,
                    baselineStatus='retained' if baseline_owner is not None else 'baseline_missing',
                    sourceState='source_removed' if existence in {'away', 'deleted'} else existence,
                    sourceExistence=existence, reasons=reasons)
                if selection is not None:
                    state.update(anchor=_anchor(selection), selection={'kind': selection.kind,
                        'fileHash': selection.file.snapshot_hash, 'members': [{'id': member.chunk.identifier,
                            'version': member.chunk.version, 'place': member.place.address,
                            'hash': member.chunk.snapshot_hash} for member in selection.members]})
                else:
                    state.pop('selection', None)
                faults += int(resolution.fault is not None or any(
                    occurrence['syntaxFault'] for occurrence in occurrences.get(request.identifier, ())))
                effects = not same or previous[3] != natural or previous[4] != state or previous[5] != baseline_owner
                if effects:
                    if same:
                        self.connection.execute('UPDATE public.mycel_relations SET right_place=%s,state=%s,baseline_owner=%s '
                            'WHERE id=%s', (natural, Jsonb(state), baseline_owner, identifier))
                    else:
                        self.connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,%s,%s)',
                            (identifier, owner, dependant_version, natural, Jsonb(state), baseline_owner))
                    self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
                    if resolution.fault is not None:
                        self.connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,%s,%s)',
                            (identifier, owner, dependant_version, _stored(request.declaration), Jsonb(state['resolution'])))
                    if old_owner is not None and old_owner != baseline_owner:
                        collection.release_baseline_owner_in_transaction(old_owner, owner)
                        released += 1
                    if repin or missing and baseline_owner is None:
                        self.connection.execute("DELETE FROM public.mycel_stale_reasons WHERE reason->>'relation'=%s", (identifier,))
                    changed += 1
        if changed:
            collection.collect_evidence_in_transaction(owner)
        return RelationApplicationReply(changed, len(desired), captured, inherited, released, faults, tuple(identities))
