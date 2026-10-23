"""Stored Origin Coverage and reasoned requirement exemptions, without models."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation, MutationActivity
from ._derive import _disk_key, _fault, _validate_ref_syntax
from ._errors import MycelError
from ._justify import checked_link, public_reference
from ._locks import atomic_transaction, operation_guard, snapshot_transaction
from ._resolver import SourceResolver, SourceSelection, require_read_transaction
from ._scope import RepositoryLocations
from ._store import checked_store
from ._undocumented import normalize_paths
from ._verification import _identity, _located


def _selection(file, member):
    return SourceSelection(member.chunk.kind if member.chunk.kind in {'req','dec'} else 'chunk',
                           member.place, file, (member,))


def _baseline_versions(connection, repository):
    readonly = repository.readonly_root
    primary = repository.primary_code or repository.code
    if readonly is None or primary is None:
        raise MycelError('invalid_input', 'Changes require a configured readonly_root and its indexed main branch.')
    clone = None if readonly.resolve() == primary.path.resolve() else str(readonly.resolve())
    state = connection.execute('SELECT read_locations FROM public.mycel_repository_state WHERE repository=%s',
                               (repository.name,)).fetchone()
    def baseline(value):
        return (value.get('kind') == 'branch' and value.get('identity') == 'refs/heads/main'
                and value.get('checkout') == 'code' and value.get('clone') == clone)
    if state is None or not any(baseline(item['location']) for item in state[0]):
        raise MycelError('invalid_input', 'Changes require the retained main branch of readonly_root; ingest it first.')
    rows = connection.execute("""SELECT DISTINCT l.chunk_version,f.metadata->'captureLocation'
        FROM public.mycel_locations l JOIN public.mycel_file_locations f ON f.id=l.file_location
        WHERE f.kind='branch' AND f.metadata->'captureLocation'->>'identity'='refs/heads/main'
          AND f.metadata->'captureLocation'->>'clone' IS NOT DISTINCT FROM %s
          AND EXISTS (SELECT 1 FROM public.mycel_file_versions v JOIN public.mycel_files c ON c.id=v.file_id
                      WHERE v.id=f.file_version AND c.repository=%s)""", (clone,repository.name)).fetchall()
    return {row[0] for row in rows}


def origins_in_transaction(connection, settings, repository, *, chunk=None, missing=False,
                           paths=(), changes=False, unresting=False):
    """Project one coherent current-location snapshot; never capture or write."""
    require_read_transaction(connection)
    if any(type(value) is not bool for value in (missing,changes,unresting)):
        raise MycelError('invalid_input', 'Origins report options must be booleans.')
    paths = normalize_paths(paths)
    catalog = SourceResolver.from_read_transaction(connection,settings)
    repo = RepositoryLocations(settings).named(repository)[0]
    selected = None
    if chunk is not None:
        _validate_ref_syntax((chunk,))
        result = catalog.resolve(chunk,purpose='endpoint')
        if result.state != 'resolved':
            _fault(result,endpoint=True)
        selected = result.selection.members[0].chunk.identifier
        if result.selection.place.repository != repository:
            raise MycelError('invalid_input', 'The chunk must belong to the selected repository.')
    baseline = _baseline_versions(connection,repo) if changes else set()
    current = {member.chunk.version:(file,member) for file in catalog.files
               for member in catalog._members(file,file.chunks)}
    locations = {name:_disk_key(settings,name) for name in settings.values['repos']}
    rows = connection.execute("""SELECT d.dependant_version,d.repository,d.state,
        ARRAY(SELECT c.id::text FROM public.mycel_edges e
              JOIN public.mycel_chunk_versions v ON v.id=e.source_version
              JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE e.dependency=d.id)
        FROM public.mycel_dependencies d WHERE d.state ? 'originLink' ORDER BY d.id""").fetchall()
    links, rested = {}, set()
    for version,owner,state,origins in rows:
        if (version not in current or state.get('declarationLocation',{}).get('location') != locations.get(owner)):
            continue
        link = checked_link(state['originLink'])
        links.setdefault(version,[]).append(link)
        rested.update(origins)
        if state.get('originId') is not None:
            rested.add(state['originId'])
    marks = {str(identifier):metadata.get('needsNothing') for identifier,metadata in connection.execute(
        "SELECT id,metadata FROM public.mycel_chunks WHERE repository=%s AND kind='req'",(repository,)).fetchall()}
    chunks, unused = [], []
    for version,(file,member) in sorted(current.items(),key=lambda item:item[1][1].place.address):
        if file.repository != repository:
            continue
        selection = _selection(file,member)
        reference = public_reference(selection)
        in_scope = ((selected is None or selected == member.chunk.identifier)
            and (not paths or any(path == '.' or member.place.path == path
                or member.place.path.startswith(path+'/') for path in paths))
            and (not changes or version not in baseline))
        if not in_scope:
            continue
        statements = sorted(links.get(version,()),key=lambda link:(link['origin'],link['method'],link['when'],link['who']))
        if not missing or not statements:
            chunks.append({'chunk':reference,'links':statements})
        if unresting and member.chunk.kind in {'req','dec'} and member.chunk.identifier not in rested:
            mark = marks.get(member.chunk.identifier)
            if mark is not None:
                if (not isinstance(mark,dict) or set(mark) != {'reason','who','when'}
                        or any(not isinstance(value,str) or not value.strip() for value in mark.values())):
                    raise MycelError('store_format','A needs-nothing mark has incompatible metadata.')
                continue
            unused.append({'origin':reference})
    result = {'scope':{'repository':repository,'location':repo.disk_location,'paths':list(paths),'changes':changes},
              'chunks':chunks}
    if unresting:
        result['unresting'] = unused
    return result


def mark_needs_nothing(connection, settings, requirement, *, reason=None, clear=False, by=None, build=None):
    _validate_ref_syntax((requirement,))
    if type(clear) is not bool or (not clear and (not isinstance(reason,str) or not reason.strip())):
        raise MycelError('invalid_input','Needs-nothing requires a nonempty reason.')
    by = _identity(by)
    guarded = tuple(sorted(settings.values['repos']))
    with ExitStack() as stack:
        stack.enter_context(checked_store(connection))
        for owner in guarded:
            stack.enter_context(operation_guard(connection,owner,'pass'))
        audit = None if build is None else MutationActivity(connection,build=build)
        stack.enter_context(nullcontext() if audit is None else audit.session())
        with atomic_transaction(connection):
            catalog = SourceResolver.from_transaction(connection,settings)
            resolved = catalog.resolve(requirement,purpose='endpoint')
            if resolved.state != 'resolved':
                _fault(resolved,endpoint=True)
            selection = resolved.selection
            member = selection.members[0]
            if member.chunk.kind != 'req':
                raise MycelError('invalid_input','Needs-nothing marks apply only to requirements.')
            _located(connection,selection,settings=settings)
            previous, = connection.execute('SELECT metadata FROM public.mycel_chunks WHERE id=%s FOR UPDATE NOWAIT',
                                           (member.chunk.identifier,)).fetchone()
            metadata = dict(previous)
            mark = None if clear else {'reason':reason.strip(),'who':by,
                                      'when':datetime.now(timezone.utc).isoformat(timespec='microseconds')}
            if clear:
                metadata.pop('needsNothing',None)
            else:
                metadata['needsNothing'] = mark
            changed = metadata != previous
            if changed:
                connection.execute('UPDATE public.mycel_chunks SET metadata=%s WHERE id=%s',
                                   (Jsonb(metadata),member.chunk.identifier))
            reply = {'requirement':public_reference(selection),'needsNothing':mark,'changed':changed}
            owner = selection.place.repository
            if audit is not None:
                audit.record_in_transaction(owner,'origins',AppliedMutation(changed,reply))
        if audit is not None:
            audit.finish('done',counts={(owner,'origins'):reply})
        return reply


def handle_origins(invocation):
    from ._build_identity import current_build
    from ._cli import Invocation,Result,invocation_store
    arguments = iter(invocation.arguments)
    flags,values,paths,refs = set(),{},[],[]
    for argument in arguments:
        if argument in {'--missing','--changes','--unresting','--no-fresh'}:
            flags.add(argument)
        elif argument in {'--path','--needs-nothing','--clear-needs-nothing','--reason'}:
            value = next(arguments,None)
            if value is None:
                raise MycelError('invalid_input','Origins option requires a value.')
            if argument == '--path':
                paths.append(value)
            elif argument in values:
                raise MycelError('invalid_input','Origins options cannot repeat.')
            else:
                values[argument] = value
        else:
            refs.append(argument)
    marking = '--needs-nothing' in values or '--clear-needs-nothing' in values
    if marking:
        if (flags or paths or refs or invocation.repositories or len(values) != (2 if '--needs-nothing' in values else 1)
                or ('--needs-nothing' in values and '--reason' not in values)):
            raise MycelError('invalid_input','Use needs-nothing with a reason, or clear-needs-nothing, by requirement reference.')
        clear = '--clear-needs-nothing' in values
        with invocation_store(invocation,operation='write') as (connection,_):
            return Result(mark_needs_nothing(connection,invocation.settings,
                values['--clear-needs-nothing' if clear else '--needs-nothing'],reason=values.get('--reason'),
                clear=clear,build=current_build()))
    if values or len(refs)>1:
        raise MycelError('invalid_input','Origins accepts one chunk reference and named report options.')
    paths = normalize_paths(paths)
    locations = RepositoryLocations(invocation.settings)
    selected = locations.resolve_scope(invocation.repositories)
    if len(selected) != 1 or not selected[0].enabled:
        raise MycelError('invalid_input','Origins requires one enabled repository.')
    repository = selected[0].name
    if '--no-fresh' not in flags:
        from ._ingest import ingest
        ingested = ingest(Invocation('ingest',repositories=(repository,),settings=invocation.settings))
        if ingested.status:
            return ingested
    with invocation_store(invocation) as (connection,_),snapshot_transaction(connection):
        return Result(origins_in_transaction(connection,invocation.settings,repository,
            chunk=refs[0] if refs else None,missing='--missing' in flags,paths=paths,
            changes='--changes' in flags,unresting='--unresting' in flags))
