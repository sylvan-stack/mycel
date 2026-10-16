"""Read persisted work in one coherent, read-only history snapshot."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg

from ._activity import KINDS, activity_state, effective_outcome
from ._cli import Invocation, Result, invocation_store
from ._errors import MycelError
from ._locks import read_snapshot
from ._scope import RepositoryLocations
from ._store import checked_store


_ENTRY_COLUMNS = ('id', 'repository', 'invocation', 'indexGeneration', 'kind', 'startedBy',
                  'build', 'startedAt', 'endedAt', 'outcome', 'counts', 'error')
_ENTRIES_SQL = """SELECT id,repository,invocation,index_generation,kind,trigger,build,
    started_at,ended_at,outcome,counts,error FROM public.mycel_activity
    WHERE (%s::boolean OR repository=%s) AND (%s::text IS NULL OR kind=%s)
    ORDER BY started_at DESC,id DESC LIMIT %s"""


def _identifier(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", value):
        raise MycelError("invalid_input", "Activity --entry requires a positive decimal entry identifier.")
    identifier = int(value)
    if identifier > 2**63 - 1:
        raise MycelError("invalid_input", "The activity entry identifier is outside the stored range.")
    return identifier


def _count(value: str) -> int:
    """Validate decimal counts without converting an unbounded digit string."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
        raise MycelError('invalid_input', 'Activity --k requires a positive decimal count.')
    significant = value.lstrip('0')
    if not significant:
        raise MycelError('invalid_input', 'Activity --k requires a positive decimal count.')
    return 500 if len(significant) > 3 else min(int(significant), 500)


def _options(arguments):
    values = {'identifier': None, 'kind': None, 'k': None}
    mapping = {'--entry': 'identifier', '--kind': 'kind', '--k': 'k'}
    seen = set()
    arguments = iter(arguments)
    for argument in arguments:
        if argument not in mapping or argument in seen:
            raise MycelError('invalid_input', 'Use activity with --entry, or repository, --kind and --k filters.')
        seen.add(argument)
        value = next(arguments, None)
        if value is None:
            raise MycelError('invalid_input', 'An activity option requires its value.')
        values[mapping[argument]] = (_identifier(value) if argument == '--entry' else
                                     _count(value) if argument == '--k' else value)
    return values


def _validate(names, all_repositories, identifier, kind, k):
    if (type(all_repositories) is not bool or len(names) > 1
            or any(not isinstance(name, str) or not name.strip() or '\0' in name for name in names)
            or names and all_repositories):
        raise MycelError('invalid_input', 'Activity takes one repository or --all.')
    if identifier is not None:
        if type(identifier) is not int or not 1 <= identifier <= 2**63 - 1:
            raise MycelError('invalid_input', 'Activity --entry requires a positive decimal entry identifier.')
        if names or all_repositories or kind is not None or k is not None:
            raise MycelError('invalid_input', 'Activity --entry is exclusive with repository, kind and count filters.')
    if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
        raise MycelError('invalid_input', 'The activity kind is unsupported.')
    if k is not None and (type(k) is not int or k <= 0):
        raise MycelError('invalid_input', 'Activity --k requires a positive integer.')


def _summary(row: dict) -> dict:
    result = {"id": str(row["id"]), "kind": row["kind"],
              "invocation": str(row["invocation"]), "indexGeneration": str(row["indexGeneration"]),
              "startedBy": row["startedBy"],
              "build": format(row["build"], "x"), "startedAt": row["startedAt"].isoformat(),
              "outcome": row["outcome"], "counts": row["counts"]}
    for key in ("repository", "error"):
        if row[key] is not None:
            result[key] = row[key]
    if row["endedAt"] is not None:
        result["endedAt"] = row["endedAt"].isoformat()
    return result


def _detail(row: dict) -> dict:
    result = {**_summary(row), 'files': row['files'], 'decisions': [], 'classifications': []}
    for decision in row["decisions"]:
        item = {key: decision[key] for key in ("root", "path", "location", "decision", "name")}
        if decision["previousName"] is not None:
            item["previousName"] = decision["previousName"]
        result["decisions"].append(item)
    for classification in row["classifications"]:
        result["classifications"].append({**classification, "bundle": str(classification["bundle"])})
    return result


def _repository(connection, settings, names, cwd):
    """Permit explicit stored names without inspecting any source folder."""
    if names:
        name = names[0]
        if name in settings.values['organizations']:
            raise MycelError('invalid_input', 'Activity takes one repository; an organization is not accepted.')
        if name in settings.values['repos']:
            return name
        row = connection.execute('SELECT EXISTS (SELECT 1 FROM public.mycel_repository_state '
                                 'WHERE repository=%s)', (name,)).fetchone()
        if row is not None and row[0] is True:
            return name
        raise MycelError('unknown_repository', 'The requested activity repository is not configured or stored.')
    locations = RepositoryLocations(settings)
    selected = locations.resolve_scope(cwd=cwd)
    if len(selected) != 1:
        raise MycelError('invalid_input', 'Activity takes one repository; an organization is not accepted.')
    repository = selected[0]
    try:
        current = (Path.cwd() if cwd is None else Path(cwd)).resolve()
        bindings = [(len(folder.path.resolve().parts), 1)
                    for folder in (repository.code, repository.documents) if folder is not None
                    and current.is_relative_to(folder.path.resolve())]
        organizations = [(len(root.resolve().parts), 0)
                         for organization in locations.organizations
                         for root in (organization.root, organization.documents)
                         if current.is_relative_to(root.resolve())]
        if not bindings or (organizations and max(organizations) > max(bindings)):
            raise MycelError('invalid_input', 'Activity requires a repository folder or an explicit repository.')
    except (OSError, RuntimeError, ValueError):
        raise MycelError('unknown_repository', 'The activity repository folder cannot be resolved.') from None
    return repository.name


def activity_from_store(connection, settings, names=(), *, all_repositories=False,
                        identifier=None, kind=None, k=None, cwd=None):
    """Read summaries or one complete entry, without pruning or detail N+1 reads.

    ``k=None`` means the listing default of 25 and keeps an explicitly supplied
    count distinguishable for --entry exclusivity. An explicit repository can
    be disabled, folderless or absent from settings when its rows remain stored.
    --all includes the separate global init/remove history and every stored name.
    """
    _validate(names, all_repositories, identifier, kind, k)
    settings.require_valid()
    try:
        if identifier is not None:
            row = activity_state(connection, identifier)
            if row is None:
                raise MycelError('refused', 'The activity entry was not found or has been pruned.')
            return {'entries': [_detail(row)]}
        limit = 25 if k is None else min(k, 500)
        with checked_store(connection, dimensions=settings.values['embedding']['dimensions']), read_snapshot(connection):
            repository = None if all_repositories else _repository(connection, settings, names, cwd)
            entries = []
            for values in connection.execute(_ENTRIES_SQL,
                    (all_repositories, repository, kind, kind, limit)).fetchall():
                row = dict(zip(_ENTRY_COLUMNS, values))
                row['outcome'] = effective_outcome(connection, invocation=row['invocation'], outcome=row['outcome'])
                entries.append(_summary(row))
            return {'entries': entries}
    except psycopg.Error:
        raise MycelError('store_unavailable', 'The activity history could not be read.') from None
    except (KeyError, TypeError, ValueError):
        raise MycelError('store_format', 'The activity history has incompatible retained metadata.') from None


def handle_activity(invocation: Invocation) -> Result:
    options = _options(invocation.arguments)
    _validate(invocation.repositories, invocation.all_repositories, **options)
    if invocation.settings is None:
        raise MycelError('internal', 'Settings were not loaded for this invocation.')
    with invocation_store(invocation) as (connection, _):
        return Result(activity_from_store(connection, invocation.settings, invocation.repositories,
            all_repositories=invocation.all_repositories, **options))
