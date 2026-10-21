"""Public one-chunk relation assertions and exact asserted withdrawal."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone

from ._activity import AppliedMutation, MutationActivity
from ._capture import LocationId
from ._dependency_application import RetainedDependencyResolver, _anchor, _same_natural
from ._dependency_inputs import DependencyCaptureInputs
from ._derive import _fault, _place, _canonical_refs, _validate_ref_syntax, _disk_key
from ._errors import MycelError
from ._evidence import CaptureLocation, EvidenceError, InheritanceInputs, checked_transaction_input_guard
from ._locks import atomic_transaction, operation_guard, require_transaction_guards
from ._relations import RELATION_ROWS_SQL, RelationApplicationStore, _relation_raw, relation_baseline
from ._resolver import SourceResolver
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address, parse_entity_uri
from ._store import checked_store


def _addresses(dependant, source):
    try:
        places = (parse_source_address(dependant), parse_source_address(source))
    except (SourceAddressError, TypeError):
        raise MycelError('invalid_input', 'Relate requires two valid Source Refs.') from None
    if any(place.root == 'index' or place.name is None for place in places):
        raise MycelError('invalid_input', 'Relate requires two current on-disk chunk endpoints.')
    return places


class RelateStore:
    def __init__(self, connection):
        self.connection = connection

    def apply(self, settings, dependant, source, *, remove=False, captured_at=None,
              build=None, settings_home=None):
        settings.require_valid(require_store=False)
        places = _addresses(*_canonical_refs(self.connection, settings, (dependant, source),
            ("endpoint", "endpoint")))
        if type(remove) is not bool:
            raise MycelError('invalid_input', 'Relation removal must be an explicit boolean.')
        for place in places:
            if not settings.values['repos'].get(place.repository, {}).get('enabled'):
                reason = 'unregistered_repository' if place.repository not in settings.values['repos'] else 'disabled_repository'
                raise MycelError('invalid_input', f'The relation selection is invalid: {reason}.')
        captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            for repository in sorted(settings.values['repos']):
                stack.enter_context(operation_guard(self.connection, repository, 'pass'))
            audit = None if build is None else MutationActivity(self.connection, build=build)
            stack.enter_context(nullcontext() if audit is None else audit.session())
            try:
                with atomic_transaction(self.connection):
                    reply = self.apply_in_transaction(settings, dependant, source, remove=remove,
                        captured_at=captured_at, settings_home=settings_home, activity=audit)
            except EvidenceError as error:
                addresses = ', '.join(error.addresses or tuple(place.address for place in places))
                raise MycelError('invalid_input', f'Relate refused: {error.status}; {addresses}.') from None
            if audit is not None:
                audit.finish('done', counts={(places[0].repository, 'relate'): reply})
            return reply

    def apply_in_transaction(self, settings, dependant, source, *, remove=False, captured_at,
                             settings_home=None, activity=None):
        settings.require_valid(require_store=False)
        _validate_ref_syntax((dependant, source))
        if type(remove) is not bool:
            raise MycelError('invalid_input', 'Relation removal must be an explicit boolean.')
        require_transaction_guards(self.connection, tuple(settings.values['repos']))
        catalog = SourceResolver.from_transaction(self.connection, settings, kind='disk', location='disk')
        raw_source = source
        dependant, source = _canonical_refs(self.connection, settings, (dependant, source),
            ('endpoint', 'endpoint'), catalog=catalog)
        _addresses(dependant, source)
        if parse_entity_uri(raw_source) is not None:
            source = raw_source
        endpoint = catalog.resolve(dependant, purpose='endpoint')
        if endpoint.state != 'resolved':
            _fault(endpoint, endpoint=True)
        selected, member = endpoint.selection, endpoint.selection.members[0]
        owner = member.place.repository
        locations = self.connection.execute("""SELECT l.id FROM public.mycel_file_locations l
            JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE v.file_id=%s AND l.kind='disk' AND l.location=%s AND c.chunk_version=%s
            ORDER BY l.id FOR SHARE OF l,v,c NOWAIT""", (selected.file.identifier, _disk_key(settings, owner), member.chunk.version)).fetchall()
        if len(locations) != 1:
            raise MycelError('invalid_input', 'The relation dependant requires one exact owning disk location.')
        location = str(locations[0][0])
        rows = self.connection.execute(RELATION_ROWS_SQL, (owner, member.chunk.version, location)).fetchall()
        assertions = [row for row in rows if row[4].get('ownership') == 'asserted']
        anchors = {_relation_raw(row[4]): row[4]['anchor'] for row in assertions if row[4].get('anchor')}
        resolver = RetainedDependencyResolver(catalog, anchors, endpoint_refs=(source, *anchors))
        resolution = resolver.resolve(source)
        selection = resolution.selection
        matches = []
        for row in assertions:
            natural = parse_source_address(row[3])
            if (_relation_raw(row[4]) == source or _same_natural(source, natural)
                    or selection is not None and (natural == selection.place or row[4].get('anchor') == _anchor(selection))):
                matches.append(row)
        if len(matches) > 1:
            raise MycelError('invalid_input', 'Multiple asserted relations match this selection.')
        match = matches[0] if matches else None
        baseline = relation_baseline(self.connection, match) if match else None
        if match and match[4].get('anchor'):
            resolver = RetainedDependencyResolver(catalog, {**anchors, source: match[4]['anchor']},
                                                  endpoint_refs=(source, *anchors))
            resolution = resolver.resolve(source)
            selection = resolution.selection
        if not remove and resolution.state != 'resolved':
            _fault(resolution)
        if remove and resolution.state != 'resolved' and resolution.fault not in {'missing_file', 'missing_name'}:
            _fault(resolution)
        if selection is not None and (selection.kind != 'chunk' or len(selection.members) != 1):
            _fault(resolution)
        natural = selection.place if selection else parse_source_address(match[3]) if match else None
        if natural is None:
            requested = parse_source_address(source)
            if requested.root is not None:
                natural = requested
            else:
                files = tuple(file for file in catalog.files if file.repository == requested.repository
                    and any(alias.path == requested.path for alias in file.aliases))
                if len(files) != 1:
                    _fault(resolution)
                primary = files[0].primary
                natural = SourceAddress(primary.repository, primary.root, primary.path, requested.name)
        checks = DependencyCaptureInputs(self.connection, settings, settings_home=settings_home)
        reread = checks.rereader(LocationId('disk', None, 'disk'), owner, None)
        guard = InheritanceInputs(settings, member, selected.file, CaptureLocation('disk'), resolution, resolver,
            {'dependencyApplication': {'sourcePlaces': {source: natural.address if natural else None}}})
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            if match is not None and not remove or match is None and remove:
                reply = {'dependant': _place(member.place), 'dependantVersion': str(member.chunk.version),
                    'source': _place(natural), 'action': 'remove' if remove else 'assert',
                    'changed': False, 'members': len(baseline.manifest.payload['members']) if baseline else
                                              len(selection.members) if selection else 0}
                if baseline is not None and not remove:
                    reply['baselineManifest'] = baseline.manifest.identifier
                checks.verify()
                return reply
            applied = RelationApplicationStore(self.connection).apply_in_transaction(settings, location,
                member.chunk.version, captured_at=captured_at, reread=reread,
                assertions=(source,), assertions_only=True,
                selected_assertions=(str(match[0]),) if match else (), remove=remove)
        baseline_id = None
        if not remove:
            identifiers = [identifier for _, identifier in applied.identifiers]
            if len(identifiers) != 1:
                raise MycelError('store_format', 'The asserted relation has incompatible ownership.')
            row = self.connection.execute("""SELECT e.manifest_hash FROM public.mycel_relations r
                JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
                WHERE r.id=%s""", (identifiers[0],)).fetchone()
            baseline_id = row[0] if row else None
        reply = {'dependant': _place(member.place), 'dependantVersion': str(member.chunk.version),
            'source': _place(natural), 'action': 'remove' if remove else 'assert',
            'changed': applied.mutated, 'members': len(selection.members) if selection else
                                                len(baseline.manifest.payload['members']) if baseline else 0}
        if baseline_id is not None:
            reply['baselineManifest'] = baseline_id
        if applied.mutated:
            from ._drift_store import DriftStore
            DriftStore(self.connection).sync_in_transaction(settings, (owner,),
                versions=(member.chunk.version,), at=captured_at)
        committed_rows = self.connection.execute(RELATION_ROWS_SQL, (owner, member.chunk.version, location)).fetchall()
        if activity is not None:
            if activity.connection is not self.connection:
                raise MycelError('invalid_input', 'Relation activity requires the exact writing connection.')
            activity.record_in_transaction(owner, 'relate', AppliedMutation(applied.mutated, reply))
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            if self.connection.execute(RELATION_ROWS_SQL, (owner, member.chunk.version, location)).fetchall() != committed_rows:
                raise EvidenceError('changed_since_ingest', (member.place.address,))
            for row in committed_rows:
                if row[4].get('ownership') == 'asserted' and str(row[0]) in {
                        identifier for _, identifier in applied.identifiers}:
                    relation_baseline(self.connection, row)
        checks.verify()
        return reply


def relate(invocation):
    from ._cli import Result, invocation_store
    from ._build_identity import current_build
    arguments = invocation.arguments
    remove = arguments[:1] == ('--remove',)
    refs = arguments[1:] if remove else arguments
    if len(refs) != 2:
        raise MycelError('invalid_input', 'Use mycel relate [--remove] <dependant> <source>.')
    if any(parse_entity_uri(ref) is not None for ref in refs):
        _validate_ref_syntax(refs)
    else:
        _addresses(*refs)
    with invocation_store(invocation, operation='write') as (connection, _):
        return Result(RelateStore(connection).apply(invocation.settings, *refs, remove=remove, build=current_build()))
