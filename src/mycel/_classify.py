"""Public finite classification command and its internal dependency seams."""
from contextlib import ExitStack

from ._classification_runner import ClassifyDependencies, run_classification
from ._classification_store import ClassificationStore
from ._errors import MycelError
from ._deadline import deadline_guard, deadline_suspended
from ._freshness import Deadline
from ._scope import RepositoryLocations


def classify_arguments(arguments):
    values = iter(arguments)
    k, dry_run = None, False
    for value in values:
        if value == '--dry-run' and not dry_run:
            dry_run = True
        elif value == '--k' and k is None:
            try:
                raw = next(values)
                k = int(raw)
                if not raw.isascii() or not raw.isdigit() or k < 1:
                    raise ValueError()
            except (StopIteration, ValueError):
                raise MycelError('invalid_input', 'Classification --k requires a positive integer.') from None
        else:
            raise MycelError('invalid_input', 'Use mycel classify [--repo <name> | --all] [--k <pairs>] [--dry-run].')
    return k, dry_run


def handle_classify(invocation, dependencies=None, *, _store=None, _activity=None):
    """Retain committed repository replies even when final audit/close fails."""
    from ._cli import Result, repository_result
    state = {}
    try:
        return _handle_classify(invocation, dependencies, _store=_store, _activity=_activity, _state=state)
    except (MycelError, KeyboardInterrupt) as error:
        entries = state.get('entries', [])
        if not any('result' in entry for entry in entries):
            raise
        interrupted = isinstance(error, KeyboardInterrupt) or state.get('interrupted', False)
        fault = ({'code': 'refused', 'message': 'Classification was stopped by the caller.'}
                 if interrupted else error.to_dict()['error'])
        represented = {entry['repository'] for entry in entries}
        entries.extend({'repository': name, 'error': fault} for name in state.get('selected', ())
                       if name not in represented)
        result = repository_result(entries)
        return Result({**result.value, 'error': fault, 'countsState': 'committed_prefix'},
                      2 if interrupted else 1)


def _handle_classify(invocation, dependencies=None, *, _store=None, _activity=None, _state):
    from ._activity import MutationActivity
    from ._build_identity import current_build
    from ._cli import Result, classification_store, repository_result

    k, dry_run = classify_arguments(invocation.arguments)
    dependencies = dependencies or ClassifyDependencies()
    deadline = Deadline.after(invocation.settings.values['drifts']['seconds'], clock=dependencies.monotonic)
    locations = RepositoryLocations(invocation.settings)
    selected, entries = {}, []
    if invocation.repositories:
        for name in invocation.repositories:
            try:
                for repository in locations.named(name):
                    selected.setdefault(repository.name, repository)
            except MycelError as error:
                entries.append({'repository': name, 'error': error.to_dict()['error']})
    else:
        for repository in locations.resolve_scope(all_repositories=invocation.all_repositories):
            selected[repository.name] = repository
    if not selected:
        return repository_result(entries, started=False)
    _state.update(entries=entries, selected=tuple(selected))
    with ExitStack() as stack:
        stack.enter_context(deadline_guard(deadline))
        connection, _ = (_store if _store is not None else
            stack.enter_context(classification_store(invocation, dry_run=dry_run)))
        build = None if dry_run else current_build()
        activity = None if dry_run else _activity
        if activity is None and build is not None:
            activity = stack.enter_context(MutationActivity(connection, build=build).session())
        status, interrupted, final_counts = 0, False, {}
        for repository in selected.values():
            try:
                repository.require_folders()
            except MycelError as error:
                entries.append({'repository': repository.name, 'error': error.to_dict()['error']})
                status = 1
                continue
            if interrupted:
                reply = {'repository': repository.name, 'status': 1, 'incomplete': True,
                         'error': {'code': 'refused', 'message': 'Classification was stopped by the caller.'}}
            else:
                reply = run_classification(ClassificationStore(connection), invocation.settings,
                    repository.name, k=k, dry_run=dry_run, dependencies=dependencies, activity=activity,
                    deadline=deadline)
            entries.append({'repository': repository.name, 'result': reply})
            final_counts[(repository.name, 'classify')] = reply
            status |= reply['status']
            interrupted |= reply.get('stopped') == 'interrupted'
            _state['interrupted'] = interrupted
        if activity is not None:
            with deadline_suspended():
                activity.finish('stopped' if interrupted else 'failed' if status else 'done',
                    counts=final_counts, **({'error': {'code': 'refused',
                        'message': 'Classification was stopped by the caller.' if interrupted else
                                   'Some selected classifications remain unfinished.'}} if status else {}))
        result = repository_result(entries)
        return Result(result.value, 2 if interrupted else max(result.status, status))
