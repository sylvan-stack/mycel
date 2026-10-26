"""Finite complete ingest over settings-selected repositories.

Publication owns one atomic identity/policy/collection/detection change. Foreign
files are observed as checked inputs, never published through a source pass.
Paid embedding starts after every requested publication has released its guards.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import datetime, timezone

from ._activity import MutationActivity
from ._capture import CaptureManifest
from ._declared_refs import _text
from ._errors import MycelError
from ._deadline import check_deadline
from ._located_dependencies import LocatedDependencyProducer
from ._located_reconciliation import LocatedCaptureStore
from ._locks import operation_guard, location_guard, read_snapshot
from ._scope import RepositoryLocations
from ._source_refs import SourceAddressError, parse_source_address, read_document_declarations


def _target(value):
    try:
        return parse_source_address(value).repository
    except (SourceAddressError, TypeError):
        return None


def _manifest_targets(manifest: CaptureManifest, resolver_factory=None):
    targets = set()
    resolver = None
    def target(raw):
        nonlocal resolver
        from ._source_refs import parse_entity_uri
        if parse_entity_uri(raw) is None or resolver_factory is None:
            return _target(raw)
        if resolver is None:
            from ._dependency_application import RetainedDependencyResolver
            resolver = RetainedDependencyResolver(resolver_factory(), {})
        result = resolver.resolve(raw)
        return None if result.selection is None else result.selection.place.repository
    for location in manifest.locations:
        for captured in location.files:
            if captured.corpus != 'documents':
                continue
            declarations = read_document_declarations(captured.parsed,
                file=f'{manifest.repository}:@{captured.primary.root}/{captured.primary.path}')
            for chunk in declarations.chunk_sources:
                targets.update(target(ref.ref) for ref in chunk.sources)
            for chunk in declarations.chunk_relations:
                targets.update(target(ref.ref) for ref in chunk.relations)
    return targets - {None}


def _ownership(connection, settings):
    """Read existing natural targets and actual authority endpoints.

    Natural refs include unresolved and retained anchors; concrete edges include
    generated owners without declaration spelling. Both are needed to discover
    upstream guards and downstream refresh/collection ownership before writes.
    """
    enabled = {name for name, value in settings.values['repos'].items() if value['enabled']}
    with read_snapshot(connection):
        dependencies = connection.execute('SELECT repository,declaration,source_place,state FROM '
            'public.mycel_dependencies WHERE repository=ANY(%s)', (sorted(enabled),)).fetchall()
        relations = connection.execute('SELECT repository,right_place,state FROM '
            'public.mycel_relations WHERE repository=ANY(%s)', (sorted(enabled),)).fetchall()
        edges = connection.execute('SELECT DISTINCT d.repository,c.repository FROM public.mycel_edges e '
            'JOIN public.mycel_dependencies d ON d.id=e.dependency JOIN public.mycel_chunk_versions v '
            'ON v.id=e.source_version JOIN public.mycel_chunks c ON c.id=v.chunk_id '
            'WHERE d.repository=ANY(%s)', (sorted(enabled),)).fetchall()
    upstream = {name: set() for name in enabled}
    for owner, declaration, place, state in dependencies:
        raw = _text(state['rawRef']) if 'rawRef' in state else declaration
        upstream[owner].update(target for target in (_target(raw), _target(place)) if target in enabled)
    from ._relations import _relation_raw
    for owner, place, state in relations:
        upstream[owner].update(target for target in (_target(_relation_raw(state)), _target(place))
                               if target in enabled)
    for owner, source in edges:
        if source in enabled:
            upstream[owner].add(source)
    return upstream


def _upstream(owners, links):
    selected, todo = set(owners), list(owners)
    while todo:
        for source in links.get(todo.pop(), ()):
            if source not in selected:
                selected.add(source)
                todo.append(source)
    return selected


@contextmanager
def _publication_guards(connection, settings, manifest):
    check_deadline()
    links = _ownership(connection, settings)
    with read_snapshot(connection):
        collection_owners = {row[0] for row in connection.execute(
            'SELECT DISTINCT d.repository FROM public.mycel_edges e '
            'JOIN public.mycel_dependencies d ON d.id=e.dependency '
            'JOIN public.mycel_chunk_versions v ON v.id=e.source_version '
            'JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository=%s',
            (manifest.repository,)).fetchall()}
    from ._resolver import SourceResolver
    links[manifest.repository].update(_manifest_targets(manifest,
        lambda: SourceResolver.from_store(connection, settings)).intersection(links))
    required = _upstream({manifest.repository}, links)
    affected = {manifest.repository}
    while True:
        expanded = affected | {owner for owner, sources in links.items() if sources.intersection(affected)}
        if expanded == affected:
            break
        affected = expanded
    held_names, busy, writable, pending = set(), set(), set(), set()
    with ExitStack() as held:
        def acquire(name):
            check_deadline()
            if name in held_names:
                return True
            if name in busy:
                return False
            try:
                held.enter_context(operation_guard(connection, name, 'pass'))
            except MycelError as error:
                if error.code != 'busy':
                    raise
                busy.add(name)
                return False
            held_names.add(name)
            return True
        for name in sorted(required):
            if not acquire(name):
                raise MycelError('busy', 'A required source repository has another active pass; ingest was not applied.')
        writable.update(required)
        for owner in sorted(affected - required):
            needs = _upstream({owner}, links)
            if all([acquire(name) for name in sorted(needs)]):
                writable.update(needs)
            else:
                pending.add(owner)
        # Disabled dependants receive no policy or file pass. A collection can
        # still remove their concrete source edges, under their own guard.
        for owner in sorted(collection_owners - set(links)):
            if acquire(owner):
                writable.add(owner)
            else:
                pending.add(owner)
        check_deadline()
        yield tuple(sorted(writable)), tuple(sorted(pending))


def _changed_since_ingest(error) -> MycelError:
    """An evidence fault leaving a pass is a closed input fault, never `internal`."""
    affected = ''.join(f' {address}' for address in getattr(error, 'addresses', ()))
    return MycelError('invalid_input', 'Complete ingest inputs changed before publication '
                      f'({getattr(error, "status", "changed_since_ingest")}):{affected or " the capture"}.')


class _CompleteProducer(LocatedDependencyProducer):
    def verify_in_transaction(self, connection, result):
        from ._evidence import EvidenceError
        try:
            super().verify_in_transaction(connection, result)
        except EvidenceError as error:
            raise _changed_since_ingest(error) from None

    def finalize_in_transaction(self, connection, result):
        from ._overview_store import OverviewStore
        return OverviewStore(connection, location=RepositoryLocations(self.settings).named(
            result.repository)[0].disk_location).reconcile_in_transaction(result.repository)

    def __call__(self, connection, result):
        from ._evidence import EvidenceError
        try:
            changed = super().__call__(connection, result)
        except EvidenceError as error:
            raise _changed_since_ingest(error) from None
        if not self.pending_repositories and not result.counts.get('remaining', {}).get('files'):
            # Successful observation time is operational metadata; a timestamp
            # alone creates no identity decision or activity entry.
            connection.execute('UPDATE public.mycel_repository_state SET last_pass_at=clock_timestamp() '
                               'WHERE repository=%s', (result.repository,))
        return changed


def _embedding_counts(connection, settings, repository):
    from ._embed import retained_contexts
    from ._embedding_store import EmbeddingStore
    contexts, captured = retained_contexts(connection, repository)
    planned = EmbeddingStore(connection, settings).prepare(repository,
        contexts=contexts, _captured=captured, persist=False)
    return planned.counts.to_dict()


def _cumulative(prior, current):
    """Preview counters without mutating already committed reply state."""
    result = dict(prior)
    for key, value in current.items():
        before = result.get(key)
        if key in {'embedding', 'dependencyRepositories'}:
            result[key] = {**(before or {}), **value}
        elif key in {'stale', 'pending', 'stalePending', 'dependencyPending', 'collectionPending'}:
            result[key] = value
        elif type(value) is bool:
            result[key] = bool(before or value)
        elif type(value) is int:
            result[key] = (before or 0) + value
        elif isinstance(value, dict):
            result[key] = _cumulative(before or {}, value)
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value
    return result


def ingest(invocation):
    """Keep every committed publication reply even if later cleanup fails."""
    from ._cli import Result
    state = {}
    try:
        return _ingest(invocation, state)
    except (MycelError, KeyboardInterrupt, Exception) as error:
        if not state.get('started'):
            raise
        interrupted = isinstance(error, KeyboardInterrupt)
        fault = ({'code': 'refused', 'message': 'Ingest was stopped by the caller.'} if interrupted else
                 error.to_dict()['error'] if isinstance(error, MycelError) else
                 {'code': 'internal', 'message': 'The ingest invocation failed after committed work.'})
        reply = state['reply']
        reply['error'] = fault
        reply['stopped'] = 'interrupted' if interrupted else 'gave_up'
        reply['countsState'] = 'committed_prefix'
        return Result(reply, 2 if interrupted else 1)


def _ingest(invocation, state):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store, repository_result
    flags, file_limit = list(invocation.arguments), None
    if '--files' in flags:
        index = flags.index('--files')
        value = flags[index + 1] if index + 1 < len(flags) else ''
        if not value.isdigit() or int(value) < 1:
            raise MycelError('invalid_input', 'Ingest --files takes a positive number of changed files for one step.')
        file_limit = int(value)
        del flags[index:index + 2]
    if len(set(flags)) != len(flags) or any(argument not in {'--embed', '--confirm-empty'} for argument in flags):
        raise MycelError('invalid_input',
                         'Use mycel ingest [--repo <name> | --all] [--files <n>] [--embed] [--confirm-empty].')
    settings = invocation.settings
    if settings is None:
        raise MycelError('internal', 'Settings were not loaded for ingest.')
    settings.require_valid()
    locations = RepositoryLocations(settings)
    selected, repositories = {}, {}
    if invocation.repositories:
        for name in invocation.repositories:
            try:
                for repository in locations.named(name):
                    selected.setdefault(repository.name, repository)
            except MycelError as error:
                repositories[name] = {'ran': False, 'refused': error.message, 'error': error.to_dict()['error']}
    else:
        selected = {repository.name: repository for repository in
                    locations.resolve_scope(all_repositories=invocation.all_repositories)}
    for name, repository in tuple(selected.items()):
        try:
            if not repository.enabled:
                raise MycelError('refused', 'The ingest repository is disabled in settings.')
            repository.require_folders()
        except MycelError as error:
            repositories[name] = {'ran': False, 'refused': error.message, 'error': error.to_dict()['error']}
            del selected[name]
    if not selected:
        return repository_result([{'repository': name, 'error': reply['error']}
                                  for name, reply in repositories.items()], started=False)
    stopped, completed, final_counts = None, [], {}
    state['reply'] = {'repositories': repositories}
    with ExitStack() as stack:
        connection, inspection = stack.enter_context(invocation_store(invocation, operation='ingest'))
        build = current_build()
        activity = None if build is None else MutationActivity(connection, build=build)
        if activity is not None:
            stack.enter_context(activity.session())
        for name in selected:
            try:
                selected_location = RepositoryLocations(settings).named(name)[0].disk_location
                with location_guard(connection, name, selected_location):
                    store = LocatedCaptureStore(connection)
                    manifest = store.capture(settings, name)
                    if not manifest.deletion_safe:
                        raise MycelError('refused', 'The complete repository capture failed; no ingest change was applied.')
                    with _publication_guards(connection, settings, manifest) as (guards, pending):
                        # The pass publishes the capture it read (MYC-1.37):
                        # a file that changes meanwhile is named in the reply
                        # under changedDuringPass and left to the next pass.
                        producer = _CompleteProducer(settings,
                            captured_at=datetime.now(timezone.utc).isoformat(),
                            collection_manifest=manifest, activity=activity,
                            guarded_repositories=guards, pending_repositories=pending,
                            snapshot=manifest)
                        applied = store.apply(settings, manifest, batch_handoff=producer,
                            confirm_empty='--confirm-empty' in invocation.arguments, activity=activity,
                            targeted_detection=True, publish_capture=True,
                            reply_counts=lambda owner, portion: _cumulative(
                                final_counts.get((owner, 'ingest'), {}), portion), file_limit=file_limit)
                        reply = _cumulative(final_counts.get((name, 'ingest'), {}),
                            {'ran': True, 'changed': applied.changed, 'stale': applied.counts.get('stale', 0), **applied.counts})
                        if file_limit is not None:
                            # One step of a pass: the pass is complete when no
                            # changed file remains for a further step (SYL-286).
                            reply['complete'] = not reply.get('remaining', {}).get('files')
                        repositories[name] = reply
                        completed.append(name)
                        state['started'] = True
                        for owner, counts in applied.counts.get('dependencyRepositories', {}).items():
                            if repositories.get(owner, {}).get('ran'):
                                repositories[owner].update(counts)
                                final_counts[(owner, 'ingest')] = repositories[owner]
                            else:
                                final_counts[(owner, 'ingest')] = counts
                        final_counts[(name, 'ingest')] = reply
                # Planning is local and read-only: no embedding credential,
                # provider, saved plan or vector is requested without --embed.
                reply['embedding'] = _embedding_counts(connection, settings, name)
                reply['pending'] = reply['embedding']['versions']['pending']
                from ._classification_local import reconcile_local
                reply['classificationCheck'] = reconcile_local(connection, settings, name, activity=activity)
                if reply['classificationCheck']['reused']:
                    final_counts[name, 'classify'] = reply['classificationCheck']
            except MycelError as error:
                if name in completed:
                    repositories[name]['error'] = error.to_dict()['error']
                else:
                    repositories[name] = {'ran': False, 'refused': error.message, 'error': error.to_dict()['error']}
            except KeyboardInterrupt:
                stopped = 'interrupted'
                repositories.setdefault(name, {'ran': False})['error'] = {
                    'code': 'refused', 'message': 'Ingest was stopped by the caller.'}
                break
        if stopped is not None:
            for name in selected:
                repositories.setdefault(name, {'ran': False, 'error': {
                    'code': 'refused', 'message': 'Ingest was stopped before this repository ran.'}})
        embedding = None
        if '--embed' in invocation.arguments and completed and stopped is None:
            from ._embed import embed
            try:
                embedded = embed(replace(invocation, repositories=tuple(completed),
                    all_repositories=False, arguments=()), _store=(connection, inspection), _activity=activity)
                embedding = embedded.value
                if embedded.status == 2:
                    stopped = 'interrupted'
                for name, portion in embedding.get('repositories', {}).items():
                    if name in completed:
                        repositories[name]['embedding'] = portion
                        if 'pending' in portion:
                            repositories[name]['pending'] = portion['pending']
                        final_counts[(name, 'embed')] = portion
            except (MycelError, KeyboardInterrupt) as error:
                if isinstance(error, KeyboardInterrupt):
                    stopped = 'interrupted'
                    fault = {'code': 'refused', 'message': 'Embedding was stopped by the caller.'}
                else:
                    fault = error.to_dict()['error']
                embedding = {'error': fault}
        if embedding is not None:
            state['reply']['embedding'] = embedding
        failures = [reply['error'] for reply in repositories.values() if 'error' in reply]
        # A step that leaves changed files rechecks the dependants it could not
        # check yet in a later step; only a complete pass reports them as work.
        pending = any(reply.get('dependencyPending') or reply.get('collectionPending') or
                      reply.get('stalePending') and reply.get('complete', True)
                      for reply in repositories.values())
        embedding_failed = embedding is not None and (embedding.get('error') is not None or
            any(portion.get('error') is not None or portion.get('failed', 0)
                for portion in embedding.get('repositories', {}).values()))
        failed = bool(failures or pending or embedding_failed)
        if activity is not None:
            outcome = 'stopped' if stopped is not None else 'failed' if failed else 'done'
            error = None if outcome == 'done' else (failures[0] if failures else
                embedding.get('error') if embedding and embedding.get('error') else
                {'code': 'refused', 'message': 'Some requested work remains incomplete.'})
            activity.finish(outcome, error=error, counts=final_counts)
    if not completed and stopped is None:
        return repository_result([{'repository': name, 'error': reply['error']}
                                  for name, reply in repositories.items()], started=False)
    reply = {'repositories': repositories}
    if embedding is not None:
        reply['embedding'] = embedding
    if stopped is not None:
        reply['stopped'] = stopped
    return Result(reply, 2 if stopped is not None else int(failed))
