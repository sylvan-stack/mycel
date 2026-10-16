"""Bounded search freshness followed by one coherent reporting snapshot.

Query preparation belongs to the caller. This composition owns the ordinary
ingest and activity boundary, then retains candidates, citations and dependency
marks together without adding checked upstream repositories to result scope.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import psycopg

from ._activity import MutationActivity
from ._build_identity import current_build
from ._deadline import DeadlineConnection, deadline_guard
from ._declared_refs import _text
from ._document_links import document_links
from ._embedding_store import _vector
from ._errors import MycelError
from ._freshness import Deadline, RepositoryStatus, run_freshness
from ._freshness_store import StoreFreshnessAdapter, freshness_scope
from ._markdown import split_markdown
from ._ranking import rank_repository
from ._ranking_store import graph_for
from ._read import ReadSelection, _lines
from ._read_store import _READ_FAULTS, _ingested
from ._refs import _PUBLIC_FAULTS, _place
from ._retrieval import _unit_vector, validate_search
from ._retrieval_store import StoreCandidates
from ._scope import RepositoryLocations
from ._search_reply import SEARCH_REPLY, search_reply
from ._source_refs import SourceAddressError, parse_source_address, read_document_declarations
from ._store import checked_store


def _run_search_freshness(connection, settings, scope, *, deadline, no_fresh, build):
    """Retain the invocation's audit and committed ingest counters together."""
    proxy = connection if isinstance(connection, DeadlineConnection) else DeadlineConnection(connection)

    def reader(activity=None):
        return StoreFreshnessAdapter(proxy, settings, activity=activity)

    if no_fresh:
        adapter = reader()
        return run_freshness(scope, adapter, deadline=deadline, no_fresh=True), adapter
    identity = current_build() if build is None else build
    result, adapter = None, None
    try:
        with ExitStack() as stack:
            activity = None
            if identity is not None:
                with deadline_guard(deadline):
                    activity = stack.enter_context(MutationActivity(proxy, build=identity,
                        started_by='freshness_check').session())
            adapter = reader(activity)
            result = run_freshness(scope, adapter, deadline=deadline)
            from ._classification_local import reconcile_freshness
            result = reconcile_freshness(adapter, result, deadline=deadline)
            if activity is not None:
                outcome = 'done' if result.finished else 'refused'
                error = None if result.finished else {'code': 'refused',
                    'message': result.reason or 'Required freshness work remains pending.'}
                activity.finish(outcome, error=error, counts=adapter.counts)
        return result, adapter
    except Exception as error:
        if result is None:
            # An audit startup refusal permits discovery, never publication.
            adapter = reader()

            class RefusedStartup:
                def discover(self, original_scope, *, deadline):
                    return adapter.discover(original_scope, deadline=deadline)

                def refresh(self, repository, *, deadline):
                    raise error

            return run_freshness(scope, RefusedStartup(), deadline=deadline), adapter
        reason = 'Freshness activity finalization did not complete.'
        affected = {owner for owner, _ in adapter.counts}
        rows = tuple(RepositoryStatus(row.repository, 'pending', reason, row.scan_required)
            if row.repository in affected else row for row in result.repositories)
        return replace(result, repositories=rows, finished=False, reason=reason,
            incomplete_repositories=tuple(sorted(set(result.incomplete_repositories) | affected))), adapter


def _readable_file(place, settings):
    """Check the actual configured binding without loading the whole file."""
    if place.root == 'index':
        return {'unreadable': 'This chunk is generated in the index and has no file.'}
    try:
        root_key = 'code_root' if place.root == 'code' else 'artifact_root'
        binding = settings.values['repos'][place.repository].get(root_key)
        if binding is None:
            repository = RepositoryLocations(settings).named(place.repository)[0]
            repository.require_folders()
            folder = repository.code if place.root == 'code' else repository.documents
            binding = None if folder is None else folder.path
        if binding is None:
            return {'unreadable': 'The configured source root is unavailable.'}
        configured = Path(binding) / place.path
        root, path = Path(binding).resolve(), configured.resolve()
        if not path.is_relative_to(root):
            return {'unreadable': 'The chunk file no longer belongs to its configured source root.'}
        if not path.is_file():
            return {'unreadable': 'The chunk file cannot be read.'}
        with path.open('rb') as stream:
            stream.read(1)
        return {'file': str(configured.absolute())}
    except (OSError, ValueError, RuntimeError):
        return {'unreadable': 'The chunk file cannot be read.'}
    except MycelError:
        return {'unreadable': 'The configured source root is unavailable.'}


def _fault_records(freshness, resolver, selected, places, fault_places=None):
    key = selected.chunk.identifier, selected.chunk.version
    requirement = next((item for item in freshness.chunk_requirements
                        if item.repository == selected.place.repository and item.chunk == key), None)
    # A discovery that ended before this chunk must never attach another
    # result's faults. Its directly retained faults are read separately below.
    faults = requirement.faults if requirement is not None else tuple(
        item for item in freshness.faults if item.chunk == key)
    records = []
    fault_places = {} if fault_places is None else fault_places
    for fault in faults:
        origins = tuple(_place(place) for place in sorted(fault_places.get((key, fault), ()),
                                                         key=lambda place: place.address))
        if not origins and fault.chunk in places:
            origins = (_place(places[fault.chunk]),)
        if not origins:
            origins = ({'repository': fault.repository, 'root': None, 'path': None,
                        'name': None, 'address': None},)
        resolution = resolver.resolve(fault.ref)
        for origin in origins:
            record = {'chunk': origin, 'ref': fault.ref,
                      'fault': _PUBLIC_FAULTS.get(fault.reason, 'not_found')}
            if resolution.candidates:
                record['candidates'] = [_place(parse_source_address(candidate))
                                        for candidate in resolution.candidates]
            if record not in records:
                records.append(record)
    return records


def _metadata(snapshot, rankings, freshness, fault_places=None):
    """Read every returned version and citation mark inside its candidate view."""
    snapshot._require_active()
    selections = {}
    for file in snapshot.resolver.files:
        for member in snapshot.resolver._members(file, file.chunks):
            key = member.chunk.identifier, member.chunk.version
            selections[key] = ReadSelection(member.place, member.chunk, file)
    for place, chunk in snapshot.resolver.index:
        selections[chunk.identifier, chunk.version] = ReadSelection(place, chunk, None)
    places = {key: selected.place for key, selected in selections.items()}
    required = {}
    for ranking in rankings:
        for entry in ranking.results:
            for chunk in (entry.chunk, *((entry.via,) if entry.via else ()), *entry.documented_in):
                required[chunk.key] = chunk
    reasons = defaultdict(list)
    for repository, version, reason in snapshot._connection.execute(
            'SELECT repository,chunk_version,reason FROM public.mycel_stale_reasons '
            'WHERE chunk_version=ANY(%s) ORDER BY id',
            (sorted({key[1] for key in required}),)).fetchall():
        reasons[repository, version].append(reason)
    heartwood = {}
    descriptions = document_links(snapshot._connection, snapshot.resolver)
    result = {}
    for key, chunk in required.items():
        selected = selections[key]
        faults = _fault_records(freshness, snapshot.resolver, selected, places, fault_places)
        file_id = None if selected.file is None else selected.file.identifier
        for declaration, fault, raw_ref in snapshot._connection.execute(_READ_FAULTS,
                (chunk.repository, chunk.version, file_id, file_id)).fetchall():
            record = {'chunk': _place(selected.place), 'ref': _text(raw_ref) if raw_ref else declaration,
                      'fault': _PUBLIC_FAULTS.get(fault.get('fault', fault.get('reason')), 'not_found')}
            if fault.get('candidates'):
                record['candidates'] = [_place(parse_source_address(candidate))
                                        for candidate in fault['candidates']]
            if record not in faults:
                faults.append(record)
        if file_id not in heartwood:
            heartwood[file_id] = chunk.origin == 'documents' and read_document_declarations(
                split_markdown(selected.file.source), file=selected.file.primary.address).heartwood
        values = {'staleReasons': reasons[chunk.repository, chunk.version],
                  'heartwood': bool(heartwood[file_id]), 'faults': faults,
                  **_readable_file(selected.place, snapshot._settings)}
        if chunk.origin == 'code':
            values['described'] = bool(descriptions.get(key))
        lines = _lines(selected)
        if lines is not None:
            values['lines'] = lines
        result[key] = values
    return result


def _organization(settings, names, cwd, repositories):
    """Keep the organization wrapper even when it has one enabled member."""
    if len(names) == 1 and names[0] in settings.values['organizations']:
        return names[0]
    if names:
        return None
    locations = RepositoryLocations(settings)
    current = Path.cwd() if cwd is None else Path(cwd)
    current = current.resolve()
    roots = [(len(root.resolve().parts), organization.name) for organization in locations.organizations
             for root in (organization.root, organization.documents) if root is not None
             and current.is_relative_to(root.resolve())]
    if not roots:
        return None
    _, name = max(roots)
    if any(folder is not None and current.is_relative_to(folder.path.resolve())
           for repository in locations.repositories
           for folder in (repository.code, repository.documents)):
        return None
    members = tuple(repository.name for repository in locations.named(name))
    return name if members == repositories else None


def search_from_store(connection, settings, query, names=(), *, query_vector=None,
                      meaning_reason=None, k=10, only=None, cwd=None, deadline,
                      no_fresh=False, build=None) -> dict:
    """Answer each fixed enabled member after one bounded recursive check."""
    validate_search(query, k, only)
    if not isinstance(deadline, Deadline) or type(no_fresh) is not bool:
        raise MycelError('invalid_input', 'Search requires a deadline and a boolean freshness option.')
    if meaning_reason is not None and (not isinstance(meaning_reason, str) or not meaning_reason.strip()):
        raise MycelError('invalid_input', 'A missing meaning arm requires a nonempty reason.')
    catalog = StoreCandidates(connection, settings)
    frozen = catalog._settings
    scope = freshness_scope(frozen, names, cwd=cwd, only=only)
    organization = _organization(frozen, names, cwd, scope.repositories)
    dimensions = frozen.values['embedding']['dimensions']
    try:
        with checked_store(connection, dimensions=dimensions) as inspection:
            if inspection.dimensions != dimensions:
                prepared = None
                meaning_reason = 'The store dimensions do not match the configured embedding dimensions.'
            else:
                prepared = None if query_vector is None else _vector(query_vector, dimensions)
                if prepared is not None:
                    _unit_vector(prepared)
            freshness, adapter = _run_search_freshness(connection, frozen, scope,
                deadline=deadline, no_fresh=no_fresh, build=build)
            with catalog.snapshot(scope.repositories) as snapshot:
                candidates = snapshot.candidates(query, prepared, k=k, only=only)
                rankings = tuple(rank_repository(frozen, query, member,
                    graph_for(snapshot, member.repository, only=only), prepared, k=k, only=only)
                    for member in candidates)
                metadata = _metadata(snapshot, rankings, freshness, adapter.fault_places)
                replies = [search_reply(ranking, member, metadata=metadata, freshness=freshness,
                    checked=not no_fresh, ingested=_ingested(adapter), meaning_reason=meaning_reason)
                    for ranking, member in zip(rankings, candidates, strict=True)]
                for reply, member in zip(replies, candidates, strict=True):
                    reply['classificationCheck'] = getattr(adapter, 'classification_checks', {}).get(
                        member.repository, {'checked': False, 'complete': False,
                            'reason': 'no_fresh' if no_fresh else 'sources_unchecked'})
        if organization is not None:
            return {'schema': SEARCH_REPLY, 'organization': organization, 'repositories': replies}
        return replies[0] if len(replies) == 1 else {'schema': SEARCH_REPLY, 'repositories': replies}
    except psycopg.Error:
        raise MycelError('store_unavailable', 'The search reply could not be read.') from None
    except (KeyError, TypeError, ValueError, SourceAddressError):
        raise MycelError('store_format', 'The search catalog has incompatible retained metadata.') from None
