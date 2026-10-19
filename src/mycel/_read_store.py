"""One exact read with chunk-scoped recursive freshness and stored marks.

The final selection and its metadata share one read-only repeatable snapshot.
Freshness uses the ordinary guarded ingest publisher, retains its committed
prefix and audit, and follows only the requested chunk's explicit sources.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256

import psycopg

from ._activity import MutationActivity
from ._build_identity import current_build
from ._deadline import DeadlineConnection, deadline_guard
from ._declared_refs import _text
from ._dependency_application import RetainedDependencyResolver
from ._disk_reconciliation import _inputs, _known, _metadata
from ._document_links import document_links
from ._errors import MycelError
from ._freshness import (ChunkRequirement, DeadlineExceeded, DependencyFault, FreshnessDiscovery,
                        FreshnessScope, RepositoryStatus, run_freshness)
from ._freshness_store import StoreFreshnessAdapter, _DEPENDENCIES, _fault_order, _raw, _target
from ._generated import generated_resolution
from ._identity import reconcile_file
from ._located_reconciliation import _catalog
from ._locks import snapshot_transaction
from ._markdown import split_markdown
from ._read import (ReadSelectionError, dependency_faults, read_address, read_chunk, require_repository,
                    select_chunk, validate_read)
from ._refs import _PUBLIC_FAULTS, _place
from ._resolver import ResolvedFile, SourceResolver, _chunk
from ._source_refs import (SourceAddress, SourceAddressError, parse_entity_uri, parse_source_address,
                           read_document_declarations)
from ._store import checked_store


_READ_DEPENDENCIES = _DEPENDENCIES.replace(' ORDER BY d.repository,d.dependant_version,d.id', '') + """
    UNION ALL
    SELECT d.repository,d.dependant_version,d.kind,d.declaration,d.source_place,d.state
    FROM public.mycel_dependencies d
    JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version AND l.kind='index'
    WHERE d.kind='generated' ORDER BY 1,2"""

_READ_FAULTS = """SELECT f.declaration,f.fault,
      COALESCE((SELECT d.state->>'rawRef' FROM public.mycel_dependencies d WHERE d.id=f.id),
               (SELECT r.state->>'rawRef' FROM public.mycel_relations r WHERE r.id=f.id))
    FROM public.mycel_ref_faults f
    WHERE f.repository=%s AND f.chunk_version=%s AND (
      EXISTS (SELECT 1 FROM public.mycel_dependencies d
        LEFT JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version
        LEFT JOIN public.mycel_file_locations fl ON fl.id=l.file_location
        JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
        JOIN public.mycel_chunks c ON c.id=v.chunk_id
        WHERE d.id=f.id AND d.repository=f.repository AND d.dependant_version=f.chunk_version
          AND ((d.kind='generated' AND l.kind='index' AND c.file_id IS NULL)
            OR (l.kind='disk' AND fl.kind='disk' AND l.location=fl.location
              AND fl.id::text=d.state->'declarationLocation'->>'file' AND c.file_id::text=%s)))
      OR EXISTS (SELECT 1 FROM public.mycel_relations r
        JOIN public.mycel_locations l ON l.chunk_version=r.left_version
        JOIN public.mycel_file_locations fl ON fl.id=l.file_location
        JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
        JOIN public.mycel_chunks c ON c.id=v.chunk_id
        WHERE r.id=f.id AND r.repository=f.repository AND r.left_version=f.chunk_version
          AND l.kind='disk' AND fl.kind='disk' AND l.location=fl.location
          AND fl.id::text=r.state->'declarationLocation'->>'file' AND c.file_id::text=%s))
    ORDER BY f.id"""


def _generated_resolution(resolver, row):
    # The common generated resolver retains one exact logical member across
    # recognized moves and never expands a pinned class header to its family.
    return generated_resolution(resolver, (None, row[0], row[1], row[3], row[4], row[2], row[5]))


class StoreReadFreshnessAdapter(StoreFreshnessAdapter):
    """Keep the standard ingest/audit boundary with one logical read root."""

    def __init__(self, connection, settings, place=None, *, identifier=None, repository=None, activity=None):
        super().__init__(connection, settings, activity=activity)
        self.place, self.identifier, self.repository = place, identifier, repository
        self.selection_error = None

    def _selection(self, resolver, *, prospective=False):
        try:
            selected = select_chunk(resolver, self.place, identifier=self.identifier, repository=self.repository)
            if prospective:
                self.selection_error = None
            return selected
        except ReadSelectionError as error:
            if error.candidates:
                if prospective:
                    self.selection_error = error
                raise
            if prospective:
                self.selection_error = None
            # A new file/name must get its repository pass before selection.
            return None

    def discover(self, scope, *, deadline):
        if self._scope is not None and scope != self._scope:
            raise MycelError('invalid_input', 'A freshness adapter owns one immutable result scope.')
        self._scope = scope
        required = set(scope.repositories)
        faults, dependencies, nodes, links, node_faults, result_keys = set(), set(), {}, defaultdict(set), defaultdict(set), set()
        complete, reason, seen = True, None, set()
        try:
            with deadline_guard(deadline), checked_store(self.connection), snapshot_transaction(self.connection):
                resolver = SourceResolver.from_read_transaction(self.connection, self.settings)
                file_ids = [file.identifier for file in resolver.files]
                origins = {str(identifier): corpus for identifier, corpus in self.connection.execute(
                    'SELECT id,corpus FROM public.mycel_files WHERE id=ANY(%s::uuid[])', (file_ids,)).fetchall()}
                rows = defaultdict(list)
                for row in self.connection.execute(_READ_DEPENDENCIES).fetchall():
                    rows[row[1]].append(row)
                declarations = {}
                for file in resolver.files:
                    deadline.check()
                    origin = origins.get(file.identifier)
                    if origin not in {'code', 'documents'}:
                        raise MycelError('store_format', 'The freshness catalog has an incompatible corpus origin.')
                    parsed = (read_document_declarations(split_markdown(file.source), file=file.primary.address)
                              if origin == 'documents' else None)
                    declarations[file.identifier] = {group.chunk: group.sources for group in parsed.chunk_sources} if parsed else {}
                    for chunk in file.chunks:
                        key = (chunk.identifier, chunk.version)
                        nodes[key] = (file.repository, file, chunk.name)
                for place, chunk in resolver.index:
                    nodes[(chunk.identifier, chunk.version)] = (place.repository, None, chunk.name)
                selected = self._selection(resolver)
                if selected is not None:
                    result_keys.add((selected.chunk.identifier, selected.chunk.version))
                roots = set(result_keys)
                captured_refs = {}
                captured_files, captured_tokens = [], {}
                for owner, manifest in self._captures.items():
                    catalog = _catalog(self.connection, owner)
                    for captured in manifest.disk.files:
                        deadline.check()
                        refs = (read_document_declarations(captured.parsed,
                            file=f'{owner}:@{captured.primary.root}/{captured.primary.path}')
                            if captured.corpus == 'documents' else None)
                        grouped = {group.chunk: group.sources for group in refs.chunk_sources} if refs else {}
                        chunks = captured.parsed.chunks if captured.corpus == 'documents' else captured.parsed
                        places = {(alias.root, alias.path) for alias in captured.aliases}
                        previous = [file for file in resolver.files if file.repository == owner
                                    and places.intersection((alias.root, alias.path) for alias in file.aliases)]
                        old = previous[0] if len(previous) == 1 else None
                        located = [row for row in catalog[0] if old is not None
                                   and str(row[0]) == old.identifier and row[8] == 'disk']
                        known = _known(old.identifier, str(located[0][4]), catalog[2]) if len(located) == 1 else ()
                        # Follow a retained heading only when the normal pure
                        # same-file identity planner preserves its logical ID.
                        # File moves still need the ingest owner's checked
                        # physical/Git binding rather than a guessed alias.
                        plan = reconcile_file(_inputs(captured), known)
                        prior_keys = {(chunk.identifier): (chunk.identifier, chunk.version)
                                      for chunk in old.chunks} if old else {}
                        members = []
                        for index, (chunk, decision) in enumerate(zip(chunks, plan.decisions)):
                            metadata = _metadata(captured, index)
                            name = metadata['name']
                            token = prior_keys.get(decision.chunk_id, ('captured', owner,
                                captured.primary.root, captured.primary.path, name))
                            captured_refs[token] = grouped.get(name, ())
                            if token not in nodes:
                                nodes[token] = (owner, None, name)
                            raw = chunk.text.encode('utf-8')
                            # Synthetic identities stay inside this invocation's
                            # captured frontier; they are never search results,
                            # persisted versions, or pinned evidence.
                            place = SourceAddress(owner, captured.primary.root, captured.primary.path, name)
                            identifier = decision.chunk_id or ('captured-chunk:' + place.address)
                            members.append(_chunk(identifier, 1, sha256(raw).hexdigest(), raw, metadata, {}))
                            captured_tokens[(identifier, 1)] = token
                        primary = SourceAddress(owner, captured.primary.root, captured.primary.path)
                        captured_files.append(ResolvedFile('captured-file:' + primary.address, owner, primary,
                            tuple(SourceAddress(owner, alias.root, alias.path) for alias in captured.aliases),
                            captured.source, captured.file_hash, tuple(members)))
                # Captured files replace the exact old bindings only within
                # this unpublished frontier. Other repositories remain indexed.
                bindings = {(file.repository, alias.root, alias.path) for file in captured_files
                            for alias in file.aliases}
                untouched = tuple(file for file in resolver.files if not any(
                    (file.repository, alias.root, alias.path) in bindings for alias in file.aliases))
                prospective = SourceResolver(self.settings, (*untouched, *captured_files), index=resolver.index)
                selected = self._selection(prospective, prospective=True)
                if selected is not None:
                    key = (selected.chunk.identifier, selected.chunk.version)
                    roots = {captured_tokens.get(key, key)}
                todo, seen = list(roots), set()
                while todo:
                    deadline.check()
                    token = todo.pop()
                    if token in seen:
                        continue
                    seen.add(token)
                    owner, file, name = nodes[token]
                    stored = rows[token[1]] if len(token) == 2 else ()
                    declared = captured_refs.get(token, declarations[file.identifier].get(name, ()) if file else ())
                    references = []
                    for ref in declared:
                        retained = next((row for row in stored if row[2] == 'declared' and _raw(row) == ref.ref), None)
                        references.append((ref.ref, ref.fault, retained))
                    references.extend((_raw(row), None, row) for row in stored if row[2] in {'asserted', 'generated'})
                    for raw, syntax_fault, retained in references:
                        deadline.check()
                        anchor = retained[5].get('anchor') if retained else None
                        generated = retained is not None and retained[2] == 'generated'
                        selected = (_generated_resolution(resolver, retained) if generated else
                            RetainedDependencyResolver(resolver, {raw: anchor} if anchor else {},
                            {raw: syntax_fault} if syntax_fault else {}).resolve(raw))
                        targets = set()
                        target = _target(self.settings, raw)
                        if target is not None and selected.state != 'invalid':
                            targets.add(target)
                        if retained is not None and selected.state != 'invalid':
                            missing = retained[5].get('sourceAbsence', {})
                            for place in (retained[4], missing.get('place')):
                                target = _target(self.settings, place)
                                if target is not None:
                                    targets.add(target)
                        for target in targets:
                            required.add(target)
                            dependencies.add((owner, target))
                            # A missing selection still owns its required
                            # enabled repository in this exact chunk's closure.
                            links[token].add(('repository', target))
                        persisted_fault = retained[5].get('resolution', {}).get('fault') if retained else None
                        fault = selected.fault or (persisted_fault if selected.state != 'resolved' else None)
                        if fault:
                            value = DependencyFault(owner, raw, fault, token if len(token) == 2 else None)
                            faults.add(value)
                            node_faults[token].add(value)
                        # A required newly captured file can be absent from
                        # the old index. Follow only its exact source selection
                        # so its own declared refs extend the same frontier
                        # before the complete producer can safely publish it.
                        captured_selection = ((_generated_resolution(prospective, retained) if generated else
                            RetainedDependencyResolver(prospective,
                            {raw: anchor} if anchor else {}).resolve(raw)) if not syntax_fault
                            and selected.state != 'invalid' else None)
                        traversal = (captured_selection.selection if captured_selection is not None
                            and captured_selection.selection is not None else selected.selection)
                        if traversal is not None:
                            for member in traversal.members:
                                key = (member.chunk.identifier, member.chunk.version)
                                key = captured_tokens.get(key, key)
                                links[token].add(key)
                                if key not in seen:
                                    todo.append(key)
        except DeadlineExceeded:
            complete, reason = False, 'time_limit'
        except psycopg.errors.QueryCanceled:
            complete, reason = False, 'time_limit'
        except MycelError:
            if not deadline.cancelled():
                raise
            complete, reason = False, 'time_limit'
        requirements = []
        try:
            for key in sorted(result_keys | {token for token in seen if len(token) == 2 and token[0] != 'repository'}):
                deadline.check()
                todo, visited, owners, local_faults = [key], set(), set(), set()
                while todo:
                    deadline.check()
                    token = todo.pop()
                    if token in visited:
                        continue
                    visited.add(token)
                    if token[0] == 'repository':
                        owners.add(token[1])
                        continue
                    if token in nodes:
                        owners.add(nodes[token][0])
                    local_faults.update(node_faults[token])
                    todo.extend(links[token])
                requirements.append(ChunkRequirement(nodes[key][0], key, tuple(sorted(owners)),
                    tuple(sorted(local_faults, key=_fault_order))))
        except DeadlineExceeded:
            complete, reason = False, 'time_limit'
        self._required.update(required)
        return FreshnessDiscovery(tuple(sorted(required)), tuple(sorted(faults, key=_fault_order)),
            tuple(sorted(dependencies)), tuple(requirements), complete, reason)


def _ingested(adapter):
    result = {}
    for (owner, command), counts in adapter.counts.items():
        if command == 'ingest':
            chunks = counts.get('chunks', {})
            result[owner] = sum(chunks.get(reason, 0) for reason in ('new', 'edited', 'renamed'))
    return result


def _run_read_freshness(connection, settings, scope, place, identifier, repository, *, deadline, no_fresh, build):
    proxy = connection if isinstance(connection, DeadlineConnection) else DeadlineConnection(connection)

    def reader(activity=None):
        return StoreReadFreshnessAdapter(proxy, settings, place, identifier=identifier,
                                        repository=repository, activity=activity)

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
            # A rejected audit startup authorizes discovery, never publication.
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


def read_from_store(connection, settings, place=None, *, identifier=None, repository=None,
                    context=None, deadline, no_fresh=False, build=None, credentials=None) -> dict:
    """Read one current disk/index chunk after one bounded recursive check.

    Initially missing places can be published by the repository pass. IDs
    obtain their configured owner from retained rows, while a disabled owner's
    rows remain hidden. Ambiguous physical paths are refused before freshness.
    Reporting snapshots perform no DDL, lock registration or evidence pruning.
    """
    validate_read(place, identifier=identifier, repository=repository, context=context)
    if type(no_fresh) is not bool:
        raise MycelError('invalid_input', 'Read requires a boolean freshness option.')
    settings.require_valid()
    if repository is not None:
        require_repository(settings, repository)
    expected_kind = None
    uri = parse_entity_uri(place) if place is not None else None
    if uri is not None:
        # MYC-17: an Entity URI is the entity's UUID; the kind tag is checked
        # on the selected chunk, and a chat is no chunk of the Index Store.
        if uri.kind not in {'req', 'dec'}:
            raise ReadSelectionError('An Entity URI of this kind names no chunk of the Index Store.')
        place, identifier, expected_kind = None, uri.uuid, uri.kind
    try:
        if place is not None:
            address = read_address(place, repository=repository)
            owner = address.repository
            require_repository(settings, owner)
        with checked_store(connection), snapshot_transaction(connection):
            if identifier is not None:
                row = connection.execute('SELECT repository,kind FROM public.mycel_chunks WHERE id::text=%s',
                                         (identifier,)).fetchone()
                if row is None or (repository is not None and row[0] != repository):
                    raise ReadSelectionError('No current indexed chunk has that identifier.')
                if expected_kind is not None and row[1] != expected_kind:
                    raise ReadSelectionError('The kind tag of the Entity URI does not match the entity.')
                owner = row[0]
                require_repository(settings, owner)
            resolver = SourceResolver.from_read_transaction(connection, settings)
            try:
                select_chunk(resolver, place, identifier=identifier, repository=repository)
            except ReadSelectionError as error:
                if no_fresh or error.candidates:
                    raise
        scope = FreshnessScope((owner,))
        freshness, adapter = _run_read_freshness(connection, settings, scope, place, identifier, repository,
            deadline=deadline, no_fresh=no_fresh, build=build)
        if adapter.selection_error is not None:
            raise adapter.selection_error
        with checked_store(connection), snapshot_transaction(connection):
            resolver = SourceResolver.from_read_transaction(connection, settings)
            selected = select_chunk(resolver, place, identifier=identifier, repository=repository)
            if expected_kind is not None and selected.chunk.kind != expected_kind:
                raise ReadSelectionError('The kind tag of the Entity URI does not match the entity.')
            reasons = [row[0] for row in connection.execute('SELECT reason FROM public.mycel_stale_reasons '
                'WHERE repository=%s AND chunk_version=%s ORDER BY id',
                (owner, selected.chunk.version)).fetchall()]
            faults = dependency_faults(freshness, resolver, selected)
            # Keep directly retained faults visible even when discovery used
            # its entire allowance before reaching this chunk's declarations.
            file_id = selected.file.identifier if selected.file is not None else None
            for declaration, fault, raw_ref in connection.execute(_READ_FAULTS,
                (owner, selected.chunk.version, file_id, file_id)).fetchall():
                record = {'chunk': _place(selected.place), 'ref': _text(raw_ref) if raw_ref else declaration,
                          'fault': _PUBLIC_FAULTS.get(fault.get('fault', fault.get('reason')), 'not_found')}
                candidates = fault.get('candidates', ())
                if candidates:
                    record['candidates'] = [_place(parse_source_address(candidate)) for candidate in candidates]
                if record not in faults:
                    faults.append(record)
            metadata = {'staleReasons': reasons, 'faults': faults}
            if selected.chunk.kind == 'dec' and selected.chunk.entity is not None:
                from ._credentials import Credentials
                from ._discussion import read_discussions
                from ._safeguards import InvocationPolicy
                reader = credentials if credentials is not None else Credentials(settings, InvocationPolicy('read'))
                metadata['discussion'] = read_discussions(settings, selected.chunk.entity.get('discussion', ()),
                                                          credentials=reader, deadline=deadline)
            reply = read_chunk(resolver, place, identifier=identifier, repository=repository, context=context,
                freshness=freshness, metadata={**metadata,
                    'documents': document_links(connection, resolver).get(
                        (selected.chunk.identifier, selected.chunk.version), ()),
                    'checked': not no_fresh, 'ingested': _ingested(adapter)})
            reply['classificationCheck'] = getattr(adapter, 'classification_checks', {}).get(owner,
                {'checked': False, 'complete': False, 'reason': 'no_fresh' if no_fresh else 'sources_unchecked'})
            return reply
    except psycopg.Error:
        raise MycelError('store_unavailable', 'The requested indexed chunk could not be read.') from None
    except (KeyError, TypeError, ValueError, SourceAddressError):
        raise MycelError('store_format', 'The read catalog has incompatible retained metadata.') from None
