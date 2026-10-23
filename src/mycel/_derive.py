"""Guarded assertions and selection-specific withdrawal over current disk text.

An assertion never ingests, confirms, classifies or writes the source. It joins
the existing location-owned policy and its complete exact capture guards.
"""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
from pathlib import Path

from ._activity import AppliedMutation, MutationActivity
from ._capture import LocationId
from ._dependency_application import (DependencyApplicationStore, RetainedDependencyResolver,
    _ROWS_SQL, _anchor, _current_raw, _same_natural)
from ._dependency_inputs import DependencyCaptureInputs
from ._errors import MycelError
from ._evidence import EvidenceError, EvidenceStore, InheritanceInputs, checked_transaction_input_guard
from ._locks import atomic_transaction, operation_guard, require_transaction_guards
from ._reconciliation import AssertedRemoval, ReconciliationError
from ._resolver import SourceResolver
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddressError, parse_source_address, parse_entity_uri
from ._store import checked_store


def _place(place):
    value = {'repository': place.repository, 'root': place.root, 'path': place.path, 'address': place.address}
    if place.name is not None:
        value['name'] = place.name
    return value


def _fault(resolution, *, endpoint=False):
    label = 'dependant' if endpoint else 'source'
    detail = resolution.fault or 'one_chunk_required'
    candidates = ('; candidates: ' + ', '.join(resolution.candidates)) if resolution.candidates else ''
    raise MycelError('invalid_input', f'The {label} selection is invalid: {detail}{candidates}.')


def _addresses(dependant, source):
    try:
        places = (parse_source_address(dependant), parse_source_address(source))
    except (SourceAddressError, TypeError):
        raise MycelError('invalid_input', 'Derive requires two valid Source Refs.') from None
    if any(place.root == 'index' for place in places):
        raise MycelError('invalid_input', 'Derive requires source files and one on-disk dependant chunk.')
    return places



def _validate_ref_syntax(refs):
    for ref in refs:
        if parse_entity_uri(ref) is not None:
            continue
        if isinstance(ref, str) and ref.startswith('[') and ref.endswith(']'):
            raise MycelError('invalid_input', 'The Entity URI is malformed.')
        try:
            parse_source_address(ref)
        except (SourceAddressError, TypeError):
            raise MycelError('invalid_input', 'A selection requires a valid address or Entity URI.') from None


def _canonical_refs(connection, settings, refs, purposes, *, catalog=None):
    """Resolve UUID references afresh inside the eventual writing transaction."""
    _validate_ref_syntax(refs)
    if not any(parse_entity_uri(ref) is not None for ref in refs):
        return tuple(refs)
    catalog = SourceResolver.from_store(connection, settings) if catalog is None else catalog
    result = []
    for ref, purpose in zip(refs, purposes, strict=True):
        if parse_entity_uri(ref) is None:
            result.append(ref)
            continue
        resolution = catalog.resolve(ref, purpose=purpose)
        if resolution.state != 'resolved':
            _fault(resolution, endpoint=purpose == 'endpoint')
        result.append(resolution.selection.place.address)
    return tuple(result)


def _disk_key(settings, repository):
    if not any(value.get('code_clones') for value in settings.values['repos'].values()):
        return 'disk'
    from ._scope import RepositoryLocations
    return RepositoryLocations(settings).named(repository)[0].disk_location


class DeriveStore:
    def __init__(self, connection):
        self.connection = connection

    def apply(self, settings: SettingsSnapshot, dependant: str, source: str, *, remove=False,
              captured_at: str | None = None, build: int | None = None,
              settings_home: Path | None = None) -> dict:
        """Assert/remove one complete selection and audit its actual commit.

        Only a numbered Build opens mutation activity. Source development uses
        the same feature transaction without inventing an installed Build.
        All configured repository guards protect the complete graph/catalog.
        """
        settings.require_valid(require_store=False)
        places = _addresses(*_canonical_refs(self.connection, settings, (dependant, source),
            ("endpoint", "source")))
        if type(remove) is not bool:
            raise MycelError('invalid_input', 'Derive removal must be an explicit boolean.')
        for place in places:
            if not settings.values['repos'].get(place.repository, {}).get('enabled'):
                reason = ('unregistered_repository' if place.repository not in settings.values['repos']
                          else 'disabled_repository')
                raise MycelError('invalid_input', f'The selection is invalid: {reason}.')
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
                places_text = ', '.join(error.addresses or tuple(place.address for place in places))
                raise MycelError('invalid_input', f'Derive refused: {error.status}; {places_text}.') from None
            except ReconciliationError as error:
                detail = ('; cycle: ' + ' -> '.join(error.cycle)) if error.cycle else ''
                raise MycelError('invalid_input', f'Derive refused: {error.status}{detail}.') from None
            if audit is not None:
                audit.finish('done', counts={(places[0].repository, 'derive'): reply})
            return reply

    def apply_in_transaction(self, settings, dependant, source, *, remove, captured_at,
                             settings_home=None, activity=None, inputs=None):
        """Apply on the caller's exact guarded connection, with a final reread.

        A caller that passes its batch `inputs` performs that final reread itself.
        """
        settings.require_valid(require_store=False)
        _validate_ref_syntax((dependant, source))
        if type(remove) is not bool:
            raise MycelError('invalid_input', 'Derive removal must be an explicit boolean.')
        require_transaction_guards(self.connection, tuple(settings.values['repos']))
        catalog = SourceResolver.from_transaction(self.connection, settings, kind='disk', location='disk')
        raw_source = source
        dependant, source = _canonical_refs(self.connection, settings, (dependant, source),
            ('endpoint', 'source'), catalog=catalog)
        _addresses(dependant, source)
        if parse_entity_uri(raw_source) is not None:
            source = raw_source
        endpoint = catalog.resolve(dependant, purpose='endpoint')
        if endpoint.state != 'resolved':
            _fault(endpoint, endpoint=True)
        selected = endpoint.selection
        member = selected.members[0]
        owner = member.place.repository
        located = self.connection.execute("""SELECT l.id,l.metadata FROM public.mycel_file_locations l
            JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE v.file_id=%s AND l.kind='disk' AND l.location=%s AND c.chunk_version=%s
            ORDER BY l.id FOR SHARE OF l,v,c NOWAIT""",
            (selected.file.identifier, _disk_key(settings, owner), member.chunk.version)).fetchall()
        if len(located) != 1:
            raise MycelError('invalid_input', 'The dependant requires one exact on-disk owning location.')
        location, _ = located[0]
        rows = self.connection.execute(_ROWS_SQL, (owner, member.chunk.version, str(location))).fetchall()
        # Existing anchors are used only for recognized moves; ordinary newly
        # resolved paths, ambiguity and settings ineligibility take precedence.
        anchors = {_current_raw(row): row[6]['anchor'] for row in rows if row[6].get('anchor')}
        resolver = RetainedDependencyResolver(catalog, anchors)
        resolution = resolver.resolve(source)
        store = DependencyApplicationStore(self.connection)
        match = None
        natural = None
        removal = None
        for row in rows:
            if row[5] != 'asserted':
                continue
            place = parse_source_address(row[4]) if row[4] else None
            current = resolution.selection
            same = (_current_raw(row) == source or place is not None and _same_natural(source, place)
                    or current is not None and
                       (place == current.place or row[6].get('anchor') == _anchor(current)))
            if not same:
                continue
            baseline = store._baseline(row, EvidenceStore(self.connection))
            if baseline is None:
                continue
            place = place or parse_source_address(baseline.manifest.payload['source']['address'])
            kind = baseline.manifest.payload['selection']
            if current is not None and current.kind != kind:
                raise MycelError('invalid_input', 'The source selection kind differs from its retained assertion.')
            if match is not None:
                raise MycelError('invalid_input', 'The assertion selection matches multiple owners.')
            match, natural, removal = row, place, AssertedRemoval(place, kind)
        if match is not None and match[6].get('anchor'):
            # The owner's checked anchor also guards an alternate literal
            # spelling of its natural place, including every away witness.
            resolver = RetainedDependencyResolver(catalog, {**anchors, source: match[6]['anchor']})
            resolution = resolver.resolve(source)
        if remove:
            if resolution.state != 'resolved' and resolution.fault not in {'missing_file', 'missing_name'}:
                _fault(resolution)
            if natural is None:
                natural = resolution.selection.place if resolution.selection else parse_source_address(source)
                if resolution.selection is not None:
                    removal = AssertedRemoval(natural, resolution.selection.kind)
        elif resolution.state != 'resolved':
            _fault(resolution)
        else:
            natural = resolution.selection.place
        shared = inputs is not None
        if not shared:
            inputs = DependencyCaptureInputs(self.connection, settings, settings_home=settings_home)
        reread = inputs.rereader(LocationId('disk', None, 'disk'), owner, None)
        # A release decision has no active source resolution. Guard the user's
        # complete selected source/explicit absence before releasing its owner.
        source_places = {source: natural.address}
        from ._evidence import CaptureLocation
        guard = InheritanceInputs(settings, member, selected.file, CaptureLocation('disk'), resolution, resolver,
            {'dependencyApplication': {'sourcePlaces': source_places}})
        with checked_transaction_input_guard(self.connection, guard, lambda: reread(guard)):
            if remove and match is None:
                reply = {'dependant': _place(member.place), 'dependantVersion': str(member.chunk.version),
                    'source': _place(natural) if resolution.selection else None,
                    'action': 'remove', 'changed': False,
                    'members': len(resolution.selection.members) if resolution.selection else 0}
                if resolution.selection is None:
                    reply['sourceRef'] = source
                if not shared:
                    inputs.verify()
                return reply
            applied = store.apply_in_transaction(settings, str(location), member.chunk.version,
                mode='observe', captured_at=captured_at, reread=reread,
                assertions=() if remove else (source,), remove_assertions=(removal,) if remove else (),
                assertions_only=True, assertion_dependencies=() if match is None else (str(match[0]),))
        decision = next((item for item in applied.plan.decisions if item.kind == 'asserted' and
            (item.identifier == str(match[0]) if match else item.natural_place == natural)), None)
        baseline = None if decision is None else decision.baseline
        if not remove and decision is not None:
            identifier = dict(applied.identifiers)[decision.identifier]
            row = self.connection.execute("""SELECT r.manifest_hash FROM public.mycel_dependencies d
                JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
                WHERE d.id=%s""", (identifier,)).fetchone()
            baseline_id = row[0] if row else None
        else:
            baseline_id = None
        reply = {'dependant': _place(member.place), 'dependantVersion': str(member.chunk.version),
            'source': _place(natural), 'action': 'remove' if remove else 'assert',
            'changed': applied.mutated,
            'members': (len(resolution.selection.members) if resolution.selection else
                        len(baseline.payload['members']) if baseline else 0)}
        if baseline_id is not None:
            reply['baselineManifest'] = baseline_id
        if applied.mutated:
            from ._drift_store import DriftStore
            DriftStore(self.connection).sync_in_transaction(settings, (owner,),
                versions=(member.chunk.version,), at=captured_at)
        if activity is not None:
            if activity.connection is not self.connection:
                raise MycelError('invalid_input', 'Derive activity requires the exact writing connection.')
            activity.record_in_transaction(owner, 'derive', AppliedMutation(applied.mutated, reply))
        # Audit is in the same rollback boundary. Changes after any producer or
        # audit callback still invalidate the entire assertion/release.
        if not shared:
            inputs.verify()
        return reply


def derive(invocation):
    from ._cli import Result, invocation_store
    from ._build_identity import current_build
    arguments = invocation.arguments
    remove = arguments[:1] == ('--remove',)
    refs = arguments[1:] if remove else arguments
    if len(refs) != 2:
        raise MycelError('invalid_input', 'Use mycel derive [--remove] <dependant> <source>.')
    if any(parse_entity_uri(ref) is not None for ref in refs):
        _validate_ref_syntax(refs)
    else:
        _addresses(*refs)
    with invocation_store(invocation, operation='write') as (connection, _):
        return Result(DeriveStore(connection).apply(invocation.settings, *refs, remove=remove, build=current_build()))
