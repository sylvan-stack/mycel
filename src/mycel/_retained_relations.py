"""Guarded observation/withdrawal of an existing exact relation baseline.

Initial relation creation and ordinary edit/inheritance producers are separate.
This boundary prevents source deletion from deleting another repository's
relation evidence, and gives those producers the checked withdrawal transition.
Relations supply no authority graph or derived role.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._collection import CollectionStore
from ._dependency_application import RetainedDependencyResolver, _LOCATION_SQL, _anchor
from ._errors import MycelError
from ._evidence import (CaptureLocation, ComparisonRecord, EvidenceError, EvidenceStore,
    InheritanceInputs, _INHERITANCE_OWNER_SQL, _INHERITANCE_REFERENCES_SQL,
    _INHERITANCE_VERSION_SQL, _inheritance_version, _validate_inheritance,
    checked_transaction_input_guard, chunk_comparison)
from ._locks import require_transaction_guards
from ._reconciliation import _comparison
from ._resolver import SourceResolver
from ._source_refs import parse_source_address
from ._store import exact_bytes


@dataclass(frozen=True)
class RetainedRelationReply:
    identifier: str
    changed: bool
    released: int
    state: str

    @property
    def counts(self):
        return {'relationsChecked': 1, 'relationsChanged': int(self.changed),
                'relationBaselinesReleased': self.released,
                'relationFaults': int(self.state in {'away', 'deleted', 'ineligible', 'unresolved'})}


def _invalid(message):
    raise MycelError('invalid_input', message)


class RetainedRelationStore:
    def __init__(self, connection):
        self.connection = connection

    def apply_in_transaction(self, settings, file_location: str, dependant_version: int,
            relation_id: str, *, captured_at: str, reread, authorization=None, remove=False):
        """Observe one existing current relation, or withdraw its missing pin.

        A verified substantive edit may select its prior exact relation and
        publish an unpinned current-version fault. The prior version's relation
        remains intact. Confirmation selects the same exact version; removal
        releases only that selected relation. The caller supplies a fresh full
        DependencyCaptureInputs rereader and retains its final verify hook.
        """
        settings.require_valid(require_store=False)
        require_transaction_guards(self.connection, tuple(settings.values['repos']))
        try:
            relation_id, file_location = str(UUID(relation_id)), str(UUID(file_location))
        except (ValueError, TypeError, AttributeError):
            _invalid('Retained relation requires exact relation/location UUIDs.')
        if (type(dependant_version) is not int or dependant_version < 1 or not callable(reread)
                or authorization not in {None, 'dependant_edit', 'owner_confirmation'}
                or type(remove) is not bool or remove and authorization is not None):
            _invalid('Retained relation requires complete typed inputs.')
        previous = self.connection.execute("""SELECT repository,left_version,right_place,state,baseline_owner
            FROM public.mycel_relations WHERE id=%s FOR UPDATE NOWAIT""", (relation_id,)).fetchone()
        if previous is None:
            _invalid('The selected retained relation is absent.')
        owner, old_version, natural_raw, old_state, baseline_owner = previous
        if (old_state.get('declarationLocation', {}).get('file') != file_location
                or old_state.get('ownership') not in {'declared', 'asserted'}
                or not isinstance(old_state.get('rawRef'), str)):
            _invalid('The retained relation requires its exact located ownership.')
        located = self.connection.execute(_LOCATION_SQL, (file_location,)).fetchone()
        if located is None or located[0] != owner:
            _invalid('The selected relation location is absent or belongs to another repository.')
        _, kind, key, metadata, raw, file_id = located
        if (old_state['declarationLocation'].get('kind'), old_state['declarationLocation'].get('location')) != (kind, key):
            _invalid('The retained relation differs from its exact capture location.')
        catalog = SourceResolver.from_transaction(self.connection, settings, kind=kind, location=key)
        files = [file for file in catalog.files if file.identifier == str(file_id)]
        if len(files) != 1 or files[0].source != exact_bytes(raw):
            _invalid('The relation differs from its complete current catalog.')
        file = files[0]
        members = [member for member in catalog._members(file, file.chunks)
                   if member.chunk.version == dependant_version]
        if len(members) != 1:
            _invalid('The relation dependant is absent from its exact current location.')
        dependant = members[0]
        evidence = EvidenceStore(self.connection)
        baseline = None
        if baseline_owner is not None:
            refs = tuple(self.connection.execute(_INHERITANCE_REFERENCES_SQL, (baseline_owner, owner)).fetchall())
            if not refs or refs[0][:2] != (0, None) or refs[0][2] is None:
                raise EvidenceError('baseline_missing')
            baseline = evidence._read_baseline(owner, refs[0][2], lock=True)
            old = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL, (old_version,)).fetchone())
            _validate_inheritance(relation_id, (owner, old_version,
                old_state.get('baselineRef', old_state['rawRef']), natural_raw, 'related', baseline_owner),
                baseline, self.connection.execute(_INHERITANCE_OWNER_SQL, (baseline_owner,)).fetchone(), refs, old)
            if baseline.manifest.payload['dependantId'] != dependant.chunk.identifier:
                _invalid('The relation reference belongs to another dependant.')
        elif old_state.get('everResolved'):
            raise EvidenceError('baseline_missing')
        elif not remove:
            _invalid('Retained relation observation requires a surviving baseline.')
        if dependant_version != old_version:
            if (authorization != 'dependant_edit' or baseline is None
                    or ComparisonRecord.from_record(baseline.manifest.payload['dependant']['comparison'])
                       == chunk_comparison(dependant.chunk)):
                _invalid('A new relation version needs a verified substantive dependant edit.')
        elif authorization == 'dependant_edit':
            _invalid('An unchanged relation version cannot authorize an edit.')
        natural = parse_source_address(natural_raw)
        declaration = old_state['rawRef']
        resolver = RetainedDependencyResolver(catalog,
            {declaration: old_state['anchor']} if old_state.get('anchor') else {})
        resolution = resolver.resolve(declaration)
        selection = resolution.selection
        state = 'present' if selection is not None else 'ineligible' if resolution.state == 'invalid' else 'unresolved'
        reasons = []
        if baseline is not None and selection is not None:
            comparison = ComparisonRecord.from_record(baseline.manifest.payload['selectionComparison'])
            comparison.require_supported()
            if comparison != _comparison(selection):
                reasons.append('related_changed')
            if baseline.manifest.payload['selection'] == 'family':
                ids = {member.chunk.identifier for member in selection.members}
                places = {member.place.address for member in selection.members}
                if any(member.get('id') not in ids and member['place']['address'] not in places
                       for member in baseline.manifest.payload['members']):
                    reasons.insert(0, 'source_removed')
        absent = baseline is not None and resolution.fault in {'missing_file', 'missing_name'}
        if absent:
            anchor = old_state.get('anchor')
            if baseline.manifest.payload['selection'] == 'file':
                elsewhere = self.connection.execute("""SELECT 1 FROM public.mycel_file_locations l
                    JOIN public.mycel_file_versions v ON v.id=l.file_version
                    JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository=%s AND f.id::text=%s LIMIT 1""",
                    (natural.repository, anchor)).fetchone()
            else:
                elsewhere = self.connection.execute("""SELECT 1 FROM public.mycel_locations l
                    JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
                    JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository=%s AND c.id::text=%s LIMIT 1""",
                    (natural.repository, anchor)).fetchone()
            state, reasons = ('away' if elsewhere else 'deleted'), ['source_removed']
        if authorization is not None and not absent:
            _invalid('This retained relation boundary withdraws only a previously resolved missing source.')
        guard = InheritanceInputs(settings, dependant, file,
            CaptureLocation(kind, metadata.get('commit') if kind != 'disk' else None), resolution, resolver,
            {'dependencyApplication': {'sourcePlaces': {declaration: natural.address}}})
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            if self.connection.execute("""SELECT repository,left_version,right_place,state,baseline_owner
                FROM public.mycel_relations WHERE id=%s FOR UPDATE NOWAIT""", (relation_id,)).fetchone() != previous:
                raise EvidenceError('changed_since_ingest', (dependant.place.address,))
            collection = CollectionStore(self.connection)
            if remove:
                self.connection.execute('DELETE FROM public.mycel_relations WHERE id=%s', (relation_id,))
                self.connection.execute("DELETE FROM public.mycel_stale_reasons WHERE reason->>'relation'=%s", (relation_id,))
                released = int(baseline_owner is not None and
                    collection.release_baseline_owner_in_transaction(baseline_owner, owner))
                collection.collect_evidence_in_transaction(owner)
                return RetainedRelationReply(relation_id, True, released, 'removed')
            updated = {**old_state, 'sourceState': 'source_removed' if absent else state,
                'sourceExistence': state, 'reasons': reasons,
                'resolution': {'state': resolution.state, 'fault': resolution.fault,
                    'candidates': list(resolution.candidates), 'candidateCount': resolution.candidate_count,
                    'place': selection.place.address if selection is not None else None},
                'baselineStatus': 'retained' if baseline_owner is not None else 'baseline_missing'}
            place = selection.place.address if selection is not None else natural.address
            if selection is not None:
                if (baseline is not None and selection.place != natural
                        and old_state.get('anchor') != _anchor(selection)):
                    _invalid('A retained relation cannot change to an unrelated source selection.')
                updated.update({'anchor': _anchor(selection), 'everResolved': True,
                    'selection': {'kind': selection.kind, 'fileHash': selection.file.snapshot_hash,
                        'members': [{'id': member.chunk.identifier, 'version': member.chunk.version,
                            'place': member.place.address, 'hash': member.chunk.snapshot_hash}
                            for member in selection.members]}})
            else:
                updated.pop('selection', None)
            if absent:
                old_absence = old_state.get('sourceAbsence')
                absence = {'state': state, 'place': natural.address,
                    'previousFileHash': old_state.get('selection', {}).get('fileHash')
                        or (old_absence or {}).get('previousFileHash')
                        or baseline.manifest.payload['members'][0]['evidence'].get('fileHash')}
                updated['sourceAbsence'] = (old_absence if isinstance(old_absence, dict)
                    and all(old_absence.get(key) == value for key, value in absence.items())
                    else {**absence, 'observedAt': captured_at})
            else:
                updated.pop('sourceAbsence', None)
            released = 0
            if authorization is not None:
                updated.update({'everResolved': False, 'baselineStatus': 'baseline_missing',
                    'sourceState': 'unresolved', 'reasons': []})
                updated.pop('sourceAbsence', None)
                if dependant_version != old_version:
                    # Preserve the historical version's immutable ownership.
                    relation_id = str(uuid4())
                    self.connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,%s,NULL)',
                        (relation_id, owner, dependant_version, place, Jsonb(updated)))
                    return RetainedRelationReply(relation_id, True, 0, 'unresolved')
                self.connection.execute('UPDATE public.mycel_relations SET baseline_owner=NULL WHERE id=%s', (relation_id,))
                self.connection.execute("DELETE FROM public.mycel_stale_reasons WHERE reason->>'relation'=%s", (relation_id,))
                released = int(collection.release_baseline_owner_in_transaction(baseline_owner, owner))
                baseline_owner = None
            changed = updated != old_state or place != natural_raw or bool(authorization)
            if changed:
                self.connection.execute('UPDATE public.mycel_relations SET state=%s,right_place=%s WHERE id=%s',
                    (Jsonb(updated), place, relation_id))
                collection.collect_evidence_in_transaction(owner)
            return RetainedRelationReply(relation_id, changed, released, state)
