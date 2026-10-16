"""Explicit, chunk-scoped upstream discovery and complete search ingest.

The result members stay fixed. Capturing an upstream repository never selects
its other files as results or makes their declarations recursive authority.
All publication work uses the ordinary complete, guarded ingest producer.

The captured frontier follows retained chunk-name changes only within an
exact current indexed file binding. Prepublication file relocations still
belong to normal guarded ingest; new refs without committed source evidence
can leave that owner and its dependant checks failed and incomplete.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import psycopg

from ._deadline import DeadlineConnection, deadline_guard
from ._declared_refs import _text
from ._dependency_application import RetainedDependencyResolver
from ._disk_reconciliation import _inputs, _known, _metadata
from ._errors import MycelError
from ._freshness import (ChunkRequirement, DeadlineExceeded, DependencyFault,
                         FreshnessDiscovery, RefreshResult, RepositoryUpdate)
from ._ingest import _CompleteProducer, _cumulative, _publication_guards
from ._identity import reconcile_file
from ._located_reconciliation import LocatedCaptureStore, _catalog
from ._locks import operation_guard, snapshot_transaction
from ._markdown import split_markdown
from ._resolver import ResolvedFile, SourceResolver, _chunk
from ._retrieval import RetrievalChunk, resolve_search_scope, select_chunks, selected_shared_document
from ._retrieval_store import _copy
from ._scope import RepositoryLocations
from ._settings import _freeze
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address, read_document_declarations
from ._store import checked_store, exact_text


_DEPENDENCIES = """SELECT d.repository,d.dependant_version,d.kind,d.declaration,d.source_place,d.state
    FROM public.mycel_dependencies d
    JOIN public.mycel_file_locations fl ON fl.id::text=d.state->'declarationLocation'->>'file'
    JOIN public.mycel_locations l ON l.file_location=fl.id AND l.chunk_version=d.dependant_version
    WHERE d.kind=ANY(ARRAY['declared','asserted']) AND fl.kind='disk' AND l.kind='disk'
      AND fl.location=l.location ORDER BY d.repository,d.dependant_version,d.id"""


def _raw(row):
    return _text(row[5]['rawRef']) if 'rawRef' in row[5] else row[3]


def _target(settings, ref):
    try:
        address = parse_source_address(ref)
    except (SourceAddressError, TypeError):
        return None
    if (address.root == 'index' or not settings.values['repos'].get(address.repository, {}).get('enabled')):
        return None
    return address.repository


def _pending(counts):
    """Preserve every affected owner, without turning updates into file scans."""
    reasons = defaultdict(set)
    for field in ('dependencyPending', 'collectionPending'):
        for owner in counts.get(field, ()):
            reasons[owner].add('dependency_update_pending' if field == 'dependencyPending' else 'collection_pending')
    for item in counts.get('stalePending', ()):
        chunk = item.get('chunk', {})
        owner = chunk.get('repository')
        if owner is None and chunk.get('address'):
            try:
                owner = parse_source_address(chunk['address']).repository
            except SourceAddressError:
                pass
        if owner is not None:
            reasons[owner].add(item.get('reason', 'dependency_update_pending'))
    return reasons


class StoreFreshnessAdapter:
    """Read explicit source selections and publish one checked repository.

    ``activity`` must use this adapter's connection, so callers can own one
    durable invocation across its committed repository prefix. The adapter
    neither starts provider work nor creates a saved embedding plan.
    """
    def __init__(self, connection, settings, *, activity=None):
        settings.require_valid()
        self.connection = connection if isinstance(connection, DeadlineConnection) else DeadlineConnection(connection)
        self.settings = replace(settings, values=_freeze(_copy(settings.values)))
        if activity is not None and activity.connection is not self.connection:
            raise MycelError('invalid_input', 'Freshness activity requires the exact deadline connection.')
        self.activity = activity
        self._scope = None
        self._required = set()
        self.counts = {}
        # A complete capture can expose new refs before its guarded producer
        # can publish. Retain only that invocation's exact manifest frontier.
        self._captures = {}
        # Faults in unpublished chunks have no retained version key. Keep
        # their exact captured places outside the public scheduling result.
        self.fault_places = {}

    def scope(self, names=(), *, cwd=None, only=None):
        """Resolve fixed result members and known shared suppliers before SQL."""
        return freshness_scope(self.settings, names, cwd=cwd, only=only)

    def discover(self, scope, *, deadline):
        if self._scope is not None and scope != self._scope:
            raise MycelError('invalid_input', 'A freshness adapter owns one immutable result scope.')
        self._scope = scope
        required = set(scope.repositories)
        if scope.only != 'code':
            required.update(selection['repo'] for selection in self.settings.values['search']['shared_documents']
                if self.settings.values['repos'].get(selection['repo'], {}).get('enabled'))
        faults, dependencies, nodes, links, node_faults, result_keys = set(), set(), {}, defaultdict(set), defaultdict(set), set()
        complete, reason, seen = True, None, set()
        fault_places, captured_places = {}, {}
        node_fault_places = defaultdict(lambda: defaultdict(set))
        try:
            with deadline_guard(deadline), checked_store(self.connection), snapshot_transaction(self.connection):
                resolver = SourceResolver.from_read_transaction(self.connection, self.settings)
                file_ids = [file.identifier for file in resolver.files]
                origins = {str(identifier): corpus for identifier, corpus in self.connection.execute(
                    'SELECT id,corpus FROM public.mycel_files WHERE id=ANY(%s::uuid[])', (file_ids,)).fetchall()}
                rows = defaultdict(list)
                for row in self.connection.execute(_DEPENDENCIES).fetchall():
                    rows[row[1]].append(row)
                declarations = {}
                disk = []
                for file in resolver.files:
                    deadline.check()
                    origin = origins.get(file.identifier)
                    if origin not in {'code', 'documents'}:
                        raise MycelError('store_format', 'The freshness catalog has an incompatible corpus origin.')
                    parsed = (read_document_declarations(split_markdown(file.source), file=file.primary.address)
                              if origin == 'documents' else None)
                    declarations[file.identifier] = {group.chunk: group.sources for group in parsed.chunk_sources} if parsed else {}
                    aliases = tuple(alias.path for alias in file.aliases if alias.root == 'artifact')
                    for chunk in file.chunks:
                        key = (chunk.identifier, chunk.version)
                        nodes[key] = (file.repository, file, chunk.name)
                        disk.append(RetrievalChunk(chunk.identifier, chunk.version, file.repository,
                            file.primary.root, file.primary.path, chunk.name, chunk.kind, origin,
                            exact_text(chunk.source), artifact_paths=aliases))
                for owner in scope.repositories:
                    result_keys.update(chunk.key for chunk in select_chunks(self.settings, owner, disk, only=scope.only))
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
                            captured_places[token] = place
                            identifier = decision.chunk_id or ('captured-chunk:' + place.address)
                            members.append(_chunk(identifier, 1, sha256(raw).hexdigest(), raw, metadata, {}))
                            captured_tokens[(identifier, 1)] = token
                            own = owner in scope.repositories
                            shared = scope.only != 'code' and captured.corpus == 'documents' and any(
                                alias.root == 'artifact' and selected_shared_document(self.settings, owner, alias.path)
                                for alias in captured.aliases)
                            eligible = scope.only is None or (scope.only == 'docs') == (captured.corpus == 'documents')
                            if eligible and (own or shared):
                                roots.add(token)
                        primary = SourceAddress(owner, captured.primary.root, captured.primary.path)
                        captured_files.append(ResolvedFile('captured-file:' + primary.address, owner, primary,
                            tuple(SourceAddress(owner, alias.root, alias.path) for alias in captured.aliases),
                            captured.source, captured.file_hash, tuple(members)))
                prospective = SourceResolver(self.settings, tuple(captured_files))
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
                    references.extend((_raw(row), None, row) for row in stored if row[2] == 'asserted')
                    for raw, syntax_fault, retained in references:
                        deadline.check()
                        anchor = retained[5].get('anchor') if retained else None
                        selected = RetainedDependencyResolver(resolver, {raw: anchor} if anchor else {},
                            {raw: syntax_fault} if syntax_fault else {}).resolve(raw)
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
                            if token in captured_places:
                                node_fault_places[token][value].add(captured_places[token])
                        # A required newly captured file can be absent from
                        # the old index. Follow only its exact source selection
                        # so its own declared refs extend the same frontier
                        # before the complete producer can safely publish it.
                        captured_selection = (RetainedDependencyResolver(prospective,
                            {raw: anchor} if anchor else {}).resolve(raw) if not syntax_fault
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
                local_places = defaultdict(set)
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
                    for fault, places in node_fault_places[token].items():
                        local_places[fault].update(places)
                    todo.extend(links[token])
                requirements.append(ChunkRequirement(nodes[key][0], key, tuple(sorted(owners)),
                    tuple(sorted(local_faults, key=_fault_order))))
                fault_places.update({(key, fault): tuple(sorted(places, key=lambda place: place.address))
                                     for fault, places in local_places.items()})
        except DeadlineExceeded:
            complete, reason = False, 'time_limit'
        self._required.update(required)
        self.fault_places = fault_places
        return FreshnessDiscovery(tuple(sorted(required)), tuple(sorted(faults, key=_fault_order)),
            tuple(sorted(dependencies)), tuple(requirements), complete, reason)

    def refresh(self, repository, *, deadline):
        deadline.check()
        if self._scope is None:
            raise MycelError('invalid_input', 'Freshness refresh requires its original scope discovery.')
        selected = RepositoryLocations(self.settings).named(repository)
        if len(selected) != 1 or not selected[0].enabled:
            return RefreshResult('refused', 'disabled_repository')
        selected[0].require_folders()
        with deadline_guard(deadline), checked_store(self.connection), operation_guard(self.connection, repository, 'pass'):
            store = LocatedCaptureStore(self.connection)
            manifest = store.capture(self.settings, repository)
            deadline.check()
            if not manifest.deletion_safe:
                return RefreshResult('refused', 'incomplete_capture')
            self._captures[repository] = manifest
            known = set(self._required)
            discovery = self.discover(self._scope, deadline=deadline)
            additions = set(discovery.required_repositories) - known
            if additions:
                return RefreshResult('pending', 'upstream_check_required', (),
                    tuple(sorted(additions)), discovery.dependencies)
            with _publication_guards(self.connection, self.settings, manifest) as (guards, pending):
                producer = _CompleteProducer(self.settings, captured_at=datetime.now(timezone.utc).isoformat(),
                    collection_manifest=manifest, activity=self.activity,
                    guarded_repositories=guards, pending_repositories=pending,
                    defer_changed_dependants=True)
                applied = store.apply(self.settings, manifest, batch_handoff=producer,
                    activity=self.activity, targeted_detection=True,
                    reply_counts=lambda owner, portion: _cumulative(self.counts.get((owner, 'ingest'), {}), portion))
                for owner, counts in applied.counts.get('dependencyRepositories', {}).items():
                    self.counts[(owner, 'ingest')] = counts
                self.counts[(repository, 'ingest')] = _cumulative(self.counts.get((repository, 'ingest'), {}),
                    applied.counts)
            pending_updates = _pending(applied.counts)
            updates = tuple(RepositoryUpdate(owner, 'pending' if owner in pending_updates else 'done',
                ','.join(sorted(pending_updates[owner])) if owner in pending_updates else None)
                for owner in sorted(set(applied.counts.get('dependencyRepositories', {})) | set(pending_updates)))
            return RefreshResult('done', dependency_updates=updates, ingested=applied.changed)


def _fault_order(fault):
    return fault.repository, fault.ref, fault.reason, fault.chunk or ('', -1)


def freshness_scope(settings, names=(), *, cwd=None, only=None):
    from ._freshness import FreshnessScope
    members = tuple(repository.name for repository in resolve_search_scope(settings, names, cwd=cwd))
    suppliers = () if only == 'code' else tuple(sorted({selection['repo']
        for selection in settings.values['search']['shared_documents']
        if settings.values['repos'].get(selection['repo'], {}).get('enabled')}))
    return FreshnessScope(members, only, suppliers)


def run_store_freshness(connection, settings, names=(), *, cwd=None, only=None,
                        deadline, no_fresh=False, build=None):
    """Own one production freshness invocation and its durable activity prefix.

    Current Build identity is supplied by the installed runtime. An explicit
    private ``build`` seam lets real-store proofs exercise the same audit path.
    The final audit close reports already committed work after the freshness
    allowance ends; it never starts another file check or source publication.
    """
    from ._activity import MutationActivity
    from ._build_identity import current_build
    from ._freshness import RepositoryStatus, run_freshness

    scope = freshness_scope(settings, names, cwd=cwd, only=only)
    proxy = connection if isinstance(connection, DeadlineConnection) else DeadlineConnection(connection)
    if no_fresh:
        return run_freshness(scope, StoreFreshnessAdapter(proxy, settings), deadline=deadline, no_fresh=True)
    identity = current_build() if build is None else build
    result, adapter = None, None
    try:
        with ExitStack() as stack:
            activity = None
            if identity is not None:
                with deadline_guard(deadline):
                    activity = stack.enter_context(MutationActivity(proxy, build=identity,
                        started_by='freshness_check').session())
            adapter = StoreFreshnessAdapter(proxy, settings, activity=activity)
            result = run_freshness(scope, adapter, deadline=deadline)
            if activity is not None:
                outcome = 'done' if result.finished else 'refused'
                error = None if result.finished else {'code': 'refused',
                    'message': result.reason or 'Required freshness work remains pending.'}
                activity.finish(outcome, error=error, counts=adapter.counts)
        return result
    except Exception as error:
        if result is None:
            # Startup refusal must not publish without its required audit
            # session. Bounded discovery can still report the known graph.
            class RefusedStartup:
                def __init__(self):
                    self.reader = StoreFreshnessAdapter(proxy, settings)

                def discover(self, original_scope, *, deadline):
                    return self.reader.discover(original_scope, deadline=deadline)

                def refresh(self, repository, *, deadline):
                    raise error

            return run_freshness(scope, RefusedStartup(), deadline=deadline)
        # Final audit failure does not undo earlier atomic publications. Keep
        # their index usable and report the outstanding finalization explicitly.
        reason = 'Freshness activity finalization did not complete.'
        affected = {owner for owner, _ in adapter.counts}
        rows = tuple(RepositoryStatus(row.repository, 'pending', reason, row.scan_required)
            if row.repository in affected else row for row in result.repositories)
        return replace(result, repositories=rows, finished=False, reason=reason,
            incomplete_repositories=tuple(sorted(set(result.incomplete_repositories) | affected)))
