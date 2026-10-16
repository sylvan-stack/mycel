"""List current disk code without direct document dependencies."""
from __future__ import annotations

from pathlib import PurePosixPath

import psycopg

from ._errors import MycelError
from ._freshness import Deadline
from ._freshness_store import freshness_scope
from ._locks import snapshot_transaction
from ._overview import overview_repository
from ._refs import _place
from ._resolver import SourceResolver
from ._source_refs import SourceAddressError
from ._store import checked_store


def normalize_paths(paths):
    """Keep filters relative to a configured root, with component boundaries."""
    normalized = []
    for value in paths:
        if (not isinstance(value, str) or not value or '\0' in value
                or PurePosixPath(value).is_absolute()):
            raise MycelError('invalid_input', 'Undocumented paths must be relative to the code root.')
        parts = []
        for part in value.split('/'):
            if part in {'', '.'}:
                continue
            if part == '..':
                if not parts:
                    raise MycelError('invalid_input', 'An undocumented path escapes the code root.')
                parts.pop()
            else:
                parts.append(part)
        path = '/'.join(parts) or '.'
        if path not in normalized:
            normalized.append(path)
    return tuple(normalized)


def undocumented_from_store(connection, settings, names=(), *, paths=(), cwd=None,
                            deadline, no_fresh=False, build=None):
    """Run the existing bounded check, then report one coherent disk snapshot.

    Selection uses stored corpus ownership rather than file extensions. No
    vector/tokenizer query or new dependency assertion is needed for this report.
    """
    from ._document_links import document_links
    from ._search_store import _run_search_freshness

    if not isinstance(deadline, Deadline) or type(no_fresh) is not bool:
        raise MycelError('invalid_input', 'Undocumented requires a deadline and a boolean freshness option.')
    filters = normalize_paths(paths)
    repository = overview_repository(settings, names, cwd=cwd)
    scope = freshness_scope(settings, (repository,), only='code')
    try:
        with checked_store(connection, dimensions=settings.values['embedding']['dimensions']):
            freshness, adapter = _run_search_freshness(connection, settings, scope,
                deadline=deadline, no_fresh=no_fresh, build=build)
            with snapshot_transaction(connection):
                resolver = SourceResolver.from_read_transaction(connection, settings)
                links = document_links(connection, resolver)
                code_files = {str(row[0]) for row in connection.execute(
                    "SELECT id FROM public.mycel_files WHERE repository=%s AND corpus='code'",
                    (repository,)).fetchall()}
                chunks = {}
                for file in resolver.files:
                    if file.identifier not in code_files:
                        continue
                    for member in resolver._members(file, file.chunks):
                        place = member.place
                        if (filters and not any(path == '.' or place.path == path
                                or place.path.startswith(path + '/') for path in filters)):
                            continue
                        if not links.get((member.chunk.identifier, member.chunk.version)):
                            chunks[place.address] = _place(place)
                ordered = sorted(chunks.values(), key=lambda row:
                    (row['root'], row['path'], row.get('name', ''), row['address']))
        ingested = {}
        from ._read_store import _ingested
        ingested.update(_ingested(adapter))
        checked = not no_fresh
        repositories = []
        for row in freshness.repositories:
            state = row.status if checked else 'pending'
            record = {'repository': row.repository, 'state': state,
                      'ingested': ingested.get(row.repository, 0) if checked else 0}
            if state != 'done':
                record['reason'] = row.reason or ('The required check is pending.' if checked
                    else 'Freshness checking was turned off.')
            repositories.append(record)
        return {'repository': repository, 'paths': list(filters), 'chunks': ordered,
                'freshness': {'checked': checked, 'finished': bool(checked and freshness.finished),
                              'repositories': repositories}}
    except psycopg.Error:
        raise MycelError('store_unavailable', 'Undocumented code could not be read.') from None
    except (KeyError, TypeError, ValueError, SourceAddressError):
        raise MycelError('store_format', 'The undocumented code catalog has incompatible metadata.') from None


def handle_undocumented(invocation):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store

    if invocation.settings is None:
        raise MycelError('internal', 'Settings were not loaded for this invocation.')
    if invocation.all_repositories:
        raise MycelError('invalid_input', 'Undocumented takes one repository; --all is not accepted.')
    paths, no_fresh = [], False
    arguments = iter(invocation.arguments)
    for argument in arguments:
        if argument == '--path':
            path = next(arguments, None)
            if path is None:
                raise MycelError('invalid_input', 'Undocumented --path requires a relative path.')
            paths.append(path)
        elif argument == '--no-fresh':
            no_fresh = True
        else:
            raise MycelError('invalid_input', 'Use undocumented with --path and --no-fresh only.')
    normalize_paths(paths)
    overview_repository(invocation.settings, invocation.repositories)
    deadline = Deadline.after(invocation.settings.values['search']['freshness_seconds'])
    with invocation_store(invocation) as (connection, _):
        return Result(undocumented_from_store(connection, invocation.settings,
            invocation.repositories, paths=paths, deadline=deadline,
            no_fresh=no_fresh, build=current_build()))
