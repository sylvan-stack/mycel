"""Finite internal command dispatch and output boundary."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import json
import os
import shutil
import signal
import subprocess
import sys
from typing import Callable, Sequence, TextIO

from ._commands import BY_NAME, help_reply
from ._errors import ErrorCode, MycelError
from ._settings import SettingsSnapshot, load_settings
from ._scope import Repository, RepositoryLocations
from ._safeguards import _end_process_group


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default message includes arbitrary argv values. Do not
        # repeat possibly sensitive input or print a second result on stderr.
        raise MycelError(ErrorCode.INVALID_INPUT, "Invalid command arguments; use --help for the supported syntax.")


@dataclass(frozen=True)
class Invocation:
    command: str
    repositories: tuple[str, ...] = ()
    all_repositories: bool = False
    arguments: tuple[str, ...] = ()
    raw: bool = False
    settings: SettingsSnapshot | None = field(default=None, compare=False, repr=False)
    grep_plain: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class Result:
    value: dict
    status: int = 0

    def __post_init__(self) -> None:
        if self.status not in (0, 1, 2):
            raise ValueError("Invalid JSON command status")


@dataclass(frozen=True)
class StreamedResult:
    """Reserved for the grep handler, which owns all inherited streams."""

    status: int


Handler = Callable[[Invocation], Result | StreamedResult]


def _settings_info(invocation: Invocation) -> Result:
    if invocation.arguments:
        raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel info without arguments.")
    snapshot = invocation.settings
    if snapshot is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    store = {"state": "settings", "reason": "Store diagnostics require valid settings."}
    if snapshot.valid:
        from ._credentials import Credentials
        from ._database import store_connection
        from ._safeguards import InvocationPolicy
        from ._store import inspect_store
        credentials = Credentials(snapshot, InvocationPolicy("info"))
        address = credentials.store_target().address
        try:
            with store_connection(credentials) as connection:
                store = inspect_store(connection).diagnostic()
        except MycelError as error:
            store = {"state": "unavailable", "error": error.to_dict()["error"]}
        store["location"] = address
    from ._commands import COMMANDS
    from ._build_identity import current_build
    build = current_build()
    result = {"version": help_reply()["version"], "settingsFile": str(snapshot.file),
              "settings": snapshot.report(), "store": store,
              "models": ({"embedding": {"model": snapshot.values["embedding"]["model"],
                                         "dimensions": snapshot.values["embedding"]["dimensions"]},
                         "classification": {"model": snapshot.values["drifts"]["model"]},
                         "reviewer": {"configured": "review_command" in snapshot.values["drifts"],
                                      **{key.removeprefix("review_"): snapshot.values["drifts"][key]
                                         for key in ("review_provider", "review_model", "review_revision")
                                         if key in snapshot.values["drifts"]}}}
                         if snapshot.valid else {"state": "settings"}),
              "commands": [command.name for command in COMMANDS], "readReply": 1, "searchReply": 3,
              "stage": "Settings and store diagnostics; full installed Build diagnostics remain pending."}
    if build is not None:
        result["build"] = format(build, "x")
    return Result(result)


def _api_key(invocation: Invocation) -> Result:
    from ._credentials import prompt_api_key, store_api_key
    provider, = invocation.arguments
    return Result(store_api_key(provider, prompt_api_key(provider)))


def _init(invocation: Invocation) -> Result:
    if invocation.arguments:
        raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel init without arguments.")
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    from ._credentials import Credentials
    from ._database import store_connection
    from ._safeguards import InvocationPolicy
    from ._store import initialize_store
    from ._build_identity import current_build
    credentials = Credentials(invocation.settings, InvocationPolicy("init"))
    address = credentials.store_target().address
    with store_connection(credentials) as connection:
        build = current_build()
        audit = {} if build is None else {"build": build, "address": address}
        initialized = initialize_store(connection, dimensions=invocation.settings.values["embedding"]["dimensions"], **audit)
    return Result(initialized.reply(address))


def _read_chunk(invocation: Invocation) -> Result:
    """Read one current indexed selection under the existing freshness budget."""
    from ._build_identity import current_build
    from ._freshness import Deadline
    from ._read_store import read_from_store
    arguments = iter(invocation.arguments)
    place, identifier, context, no_fresh = None, None, None, False
    for argument in arguments:
        if argument == "--id":
            identifier = next(arguments)
        elif argument == "--context":
            context = int(next(arguments))
        elif argument == "--no-fresh":
            no_fresh = True
        else:
            place = argument
    deadline = Deadline.after(invocation.settings.values["search"]["freshness_seconds"])
    with invocation_store(invocation) as (connection, _inspection):
        return Result(read_from_store(connection, invocation.settings, place,
            identifier=identifier, context=context, deadline=deadline, no_fresh=no_fresh,
            build=current_build(), repository=invocation.repositories[0] if invocation.repositories else None))


@contextmanager
def invocation_store(invocation: Invocation, *, operation: str = "read"):
    """A feature's shared preflight and no-DDL store guard for its whole work."""
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    from ._credentials import Credentials
    from ._database import store_connection
    from ._safeguards import InvocationPolicy
    from ._store import checked_store
    credentials = Credentials(invocation.settings, InvocationPolicy(invocation.command))
    with store_connection(credentials) as connection:
        with checked_store(connection, dimensions=invocation.settings.values["embedding"]["dimensions"],
                           operation=operation) as inspection:
            yield connection, inspection


@contextmanager
def classification_store(invocation: Invocation, *, dry_run: bool = False):
    """Reach the store as every command does; a dry-run's policy refuses model credentials (MYC-D41)."""
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    from ._credentials import Credentials
    from ._database import store_connection
    from ._deadline import deadline_seconds
    from ._safeguards import InvocationPolicy
    from ._store import checked_store

    target = Credentials(invocation.settings, InvocationPolicy('classify', dry_run=dry_run))
    with store_connection(target, timeout_seconds=deadline_seconds(5)) as connection:
        with checked_store(connection, dimensions=invocation.settings.values["embedding"]["dimensions"]) as inspection:
            yield connection, inspection


def _repos(invocation: Invocation) -> Result:
    if invocation.arguments:
        if invocation.arguments[0] == "remove":
            if (len(invocation.arguments) < 2
                    or any(not name.strip() or "\0" in name for name in invocation.arguments[1:])):
                raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel repos remove <name> [<name> ...].")
            from ._repository_removal import RepositoryRemovalStore
            from ._build_identity import current_build
            entries = []
            names = tuple(dict.fromkeys(invocation.arguments[1:]))
            build = current_build()
            try:
                with invocation_store(invocation) as (connection, _inspection):
                    removal = RepositoryRemovalStore(connection)
                    for name in names:
                        try:
                            reply = removal.remove(invocation.settings, name, build=build)
                            entries.append({"repository": name, "result": reply})
                            if reply.get("stopped") == "interrupted":
                                raise KeyboardInterrupt
                        except MycelError as error:
                            entries.append({"repository": name, "error": error.to_dict()["error"]})
            except (MycelError, KeyboardInterrupt) as error:
                if not any("result" in entry for entry in entries):
                    raise
                interrupted = isinstance(error, KeyboardInterrupt)
                fault = ({"code": "refused", "message": "Stopped by the caller."} if interrupted
                         else error.to_dict()["error"])
                represented = {entry["repository"] for entry in entries}
                entries.extend({"repository": name, "error": fault}
                               for name in names if name not in represented)
                return Result({"repositories": entries, "error": fault,
                               "countsState": "committed_prefix"}, 2 if interrupted else 1)
            result = repository_result(entries)
            if any(entry.get("result", {}).get("stopped") == "interrupted" for entry in entries):
                return Result(result.value, 2)
            return Result(result.value, int(bool(result.status or any(
                "error" in entry.get("result", {}) for entry in entries))))
        raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel repos without arguments to list configured repositories.")
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    return Result(RepositoryLocations(invocation.settings).repositories_reply())


def for_repositories(invocation: Invocation, operation: Callable[[Repository], dict], *,
                     needs_folders: bool = True, prepare: Callable[[], None] | None = None) -> Result:
    """Run a feature handler's operation per settings-selected repository.

    Selector and folder faults are local when another repository can run. The
    helper starts no unavailable handler and never consults store registrations.
    Store-backed handlers provide their shared connection/format preflight as
    ``prepare``; its failure is invocation-wide before any operation can start.
    """
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    locations = RepositoryLocations(invocation.settings)
    selected: dict[str, Repository] = {}
    entries: list[dict] = []
    if invocation.repositories:
        for name in invocation.repositories:
            try:
                for repository in locations.named(name):
                    selected.setdefault(repository.name, repository)
            except MycelError as error:
                entries.append({"repository": name, "error": error.to_dict()["error"]})
    else:
        for repository in locations.resolve_scope(all_repositories=invocation.all_repositories):
            selected[repository.name] = repository
    started = False
    prepared = False
    for repository in selected.values():
        try:
            if not repository.enabled:
                raise MycelError(ErrorCode.REFUSED, "The selected repository is disabled in settings.")
            if needs_folders:
                repository.require_folders()
        except MycelError as error:
            entries.append({"repository": repository.name, "error": error.to_dict()["error"]})
            continue
        if not prepared:
            if prepare is not None:
                prepare()
            prepared = True
        try:
            started = True
            entries.append({"repository": repository.name, "result": operation(repository)})
        except MycelError as error:
            entries.append({"repository": repository.name, "error": error.to_dict()["error"]})
    return repository_result(entries, started=started)


def _plain_grep(invocation: Invocation) -> StreamedResult:
    """Run only literal system grep with its inherited streams and status."""
    executable = shutil.which("grep")
    if not executable:
        sys.stderr.write("The grep program is unavailable.\n")
        return StreamedResult(127)
    environment = {"PATH": os.environ.get("PATH", os.defpath)}
    for name in ("HOME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_COLLATE", "LC_MESSAGES",
                 "LC_NUMERIC", "LC_TIME", "LC_MONETARY", "TERM", "GREP_COLORS", "GREP_COLOR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    try:
        process = subprocess.Popen([executable, *invocation.arguments], env=environment,
                                   close_fds=True, start_new_session=True)
    except OSError:
        sys.stderr.write("The grep program could not be started.\n")
        return StreamedResult(127)
    try:
        status = process.wait()
        return StreamedResult(status if status >= 0 else 128 - status)
    except KeyboardInterrupt as stop:
        return StreamedResult(128 + getattr(stop, "signal_number", signal.SIGINT))
    finally:
        _end_process_group(process)


def parse(argv: Sequence[str]) -> Invocation | Result:
    args = list(argv)
    if args[:1] == ["-v"]:
        if len(args) < 2 or not args[1] or args[1].startswith("-"):
            raise MycelError(ErrorCode.INVALID_INPUT, "Build selection requires a number as the first argument.")
        raise MycelError(ErrorCode.REFUSED, "Build selection requires the installed Mycel launcher.")
    if not args or args == ["--help"] or args == ["-h"]:
        return Result(help_reply())
    name, *rest = args
    if name not in BY_NAME:
        raise MycelError(ErrorCode.INVALID_INPUT, "Unknown command; use --help for the command list.")
    spec = BY_NAME[name]
    if spec.raw_arguments:
        return Invocation(name, arguments=tuple(rest), raw=True)
    parser = _Parser(prog=f"mycel {name}", add_help=False, allow_abbrev=False)
    parser.add_argument("-h", "--help", action="store_true")
    if spec.scope:
        parser.add_argument("--repo", action="append", default=[])
    if spec.all_repositories:
        parser.add_argument("--all", action="store_true")
    if name == "refs":
        parser.add_argument("--unresolved", action="store_true")
    if name == "drifts":
        parser.add_argument("--closed", action="store_true")
        parser.add_argument("--all-versions", action="store_true")
    if name in {"derive", "relate"}:
        parser.add_argument("--remove", action="store_true")
    if name == "confirm":
        parser.add_argument("--by")
        parser.add_argument("--how", choices=("read", "check"))
    if name == "verifications":
        parser.add_argument("--history", action="store_true")
    if name == "overview":
        parser.add_argument("--dir")
    if name == "undocumented":
        parser.add_argument("--path", action="append", default=[])
        parser.add_argument("--no-fresh", action="store_true")
    if name in {"embed", "summaries", "classify"}:
        parser.add_argument("--dry-run", action="store_true")
    if name == "classify":
        parser.add_argument("--k", type=int)
    if name == "embed":
        parser.add_argument("--retry-failed", action="store_true")
    if name == "ingest":
        parser.add_argument("--embed", action="store_true")
        parser.add_argument("--confirm-empty", action="store_true")
    if name == "activity":
        from ._activity import KINDS
        parser.add_argument("--entry")
        parser.add_argument("--kind", choices=sorted(KINDS))
        parser.add_argument("--k")
    if name == "evaluate":
        parser.add_argument("--kind", choices=("retrieval", "drift"), default="retrieval")
        parser.add_argument("--live", action="store_true")
    if name == "read":
        parser.add_argument("--id")
        parser.add_argument("--context", type=int)
        parser.add_argument("--no-fresh", action="store_true")
    if name == "search":
        parser.add_argument("--k", type=int, default=10)
        parser.add_argument("--only", choices=("code", "docs"))
        parser.add_argument("--no-fresh", action="store_true")
    parser.add_argument("arguments", nargs="*")
    parsed = parser.parse_intermixed_args(rest)
    if name in {"classify", "drifts", "stale", "status"} and parsed.arguments:
        raise MycelError(ErrorCode.INVALID_INPUT, "This command takes repository selectors and named options only.")
    if name == "classify" and parsed.k is not None and parsed.k <= 0:
        raise MycelError(ErrorCode.INVALID_INPUT, "Classification --k must be a positive integer.")
    repos = getattr(parsed, "repo", [])
    all_repositories = getattr(parsed, "all", False)
    if any(not r.strip() for r in repos) or (repos and all_repositories):
        raise MycelError(ErrorCode.INVALID_INPUT, "Select named repositories or --all, with nonempty names.")
    if parsed.help:
        return Result(help_reply(name))
    if name == "api-key" and tuple(parsed.arguments) not in {("voyage",), ("jev",)}:
        raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel api-key voyage|jev.")
    if name == "search" and (len(parsed.arguments) > 1 or (parsed.arguments and not parsed.arguments[0].strip())
                              or not 1 <= parsed.k <= 100):
        raise MycelError(ErrorCode.INVALID_INPUT, "Search takes one nonempty query, --k 1..100, --only code|docs and --no-fresh.")
    if name == "read" and (len(repos) > 1 or
            ((parsed.id is None and len(parsed.arguments) != 1) or
             (parsed.id is not None and (parsed.arguments or not parsed.id.strip()))) or
            (parsed.context is not None and not 0 <= parsed.context <= 50)):
        raise MycelError(ErrorCode.INVALID_INPUT, "Read takes one place or --id, one repository, and optional --context 0..50 and --no-fresh.")
    if name == "confirm" and (len(parsed.arguments) != 1 or
            (parsed.by is not None and not parsed.by.strip())):
        raise MycelError(ErrorCode.INVALID_INPUT, "Confirm takes one chunk address and optional --by and --how read|check.")
    if name == "verifications" and (parsed.arguments or len(repos) > 1):
        raise MycelError(ErrorCode.INVALID_INPUT, "Verifications takes one repository and optional --history.")
    if name == "overview" and (parsed.arguments or len(repos) > 1):
        raise MycelError(ErrorCode.INVALID_INPUT, "Overview takes one repository and optional --dir.")
    if name == "undocumented" and (parsed.arguments or len(repos) > 1):
        raise MycelError(ErrorCode.INVALID_INPUT, "Undocumented takes one repository, repeatable --path and optional --no-fresh.")
    if name == "evaluate" and (parsed.arguments or len(repos) > 1 or (parsed.live and parsed.kind != "drift")):
        raise MycelError(ErrorCode.INVALID_INPUT, "Evaluate takes one repository and --kind retrieval|drift; --live requires --kind drift.")
    if name == 'activity':
        from ._activity_reader import _count, _identifier, _validate
        if parsed.arguments:
            raise MycelError(ErrorCode.INVALID_INPUT, 'Activity takes named repository, entry, kind and count options only.')
        activity_entry = _identifier(parsed.entry) if parsed.entry is not None else None
        activity_count = _count(parsed.k) if parsed.k is not None else None
        _validate(repos, all_repositories, activity_entry, parsed.kind, activity_count)
    if name == 'ingest' and parsed.arguments:
        raise MycelError(ErrorCode.INVALID_INPUT, 'Ingest takes repository selectors and --embed or --confirm-empty only.')
    if name == "summaries" and (len(repos) > 1 or tuple(parsed.arguments) not in
            {(), ("status",), ("build",), ("regenerate",), ("remove",)} or
            (parsed.dry_run and tuple(parsed.arguments) not in {("build",), ("regenerate",)})):
        raise MycelError(ErrorCode.INVALID_INPUT, "Summaries takes one repository and status, build, regenerate or remove; --dry-run requires build or regenerate.")
    arguments = (("--unresolved",) if getattr(parsed, "unresolved", False) else ()) + \
                (("--remove",) if getattr(parsed, "remove", False) else ()) + \
                (("--dry-run",) if getattr(parsed, "dry_run", False) else ()) + \
                (("--retry-failed",) if getattr(parsed, "retry_failed", False) else ()) + tuple(parsed.arguments)
    if name == 'ingest':
        arguments = (("--embed",) if parsed.embed else ()) + (("--confirm-empty",) if parsed.confirm_empty else ())
    if name == 'activity':
        arguments = (('--entry', str(activity_entry)) if activity_entry is not None else ()) + \
                    (('--kind', parsed.kind) if parsed.kind is not None else ()) + \
                    (('--k', str(activity_count)) if activity_count is not None else ())
    if name == "evaluate":
        arguments = ("--kind", parsed.kind) + (("--live",) if parsed.live else ())
    if name == "confirm":
        arguments = (("--by", parsed.by) if parsed.by is not None else ()) + \
                    (("--how", parsed.how) if parsed.how is not None else ()) + tuple(parsed.arguments)
    if name == "verifications":
        arguments = ("--history",) if parsed.history else ()
    if name == "overview":
        from ._overview_render import normalize_directory
        arguments = ("--dir", normalize_directory(parsed.dir)) if parsed.dir is not None else ()
    if name == "undocumented":
        from ._undocumented import normalize_paths
        arguments = tuple(value for path in normalize_paths(parsed.path) for value in ("--path", path)) + \
                    (("--no-fresh",) if parsed.no_fresh else ())
    if name == "read":
        arguments = (("--id", parsed.id) if parsed.id is not None else tuple(parsed.arguments)) + \
                    (("--context", str(parsed.context)) if parsed.context is not None else ()) + \
                    (("--no-fresh",) if parsed.no_fresh else ())
    if name == "search":
        arguments = ('--k', str(parsed.k)) + \
                    (('--only', parsed.only) if parsed.only is not None else ()) + \
                    (('--no-fresh',) if parsed.no_fresh else ()) + (('--', parsed.arguments[0]) if parsed.arguments else ())
    if name == "classify":
        arguments = (("--k", str(parsed.k)) if parsed.k is not None else ()) + \
                    (("--dry-run",) if parsed.dry_run else ())
    if name == "drifts":
        arguments = (("--closed",) if parsed.closed else ()) + \
                    (("--all-versions",) if parsed.all_versions else ())
    return Invocation(name, tuple(repos), all_repositories, arguments)


def dispatch(invocation: Invocation, handlers: dict[str, Handler]) -> Result | StreamedResult:
    handler = handlers.get(invocation.command)
    if handler is None:
        raise MycelError(ErrorCode.REFUSED, "This command is not implemented in the CLI foundation.")
    result = handler(invocation)
    if isinstance(result, StreamedResult) and invocation.command != "grep":
        raise MycelError(ErrorCode.INTERNAL, "Only grep may own the command streams.")
    if not isinstance(result, (Result, StreamedResult)):
        raise MycelError(ErrorCode.INTERNAL, "The command returned an invalid result.")
    return result


def repository_result(entries: Sequence[dict], *, started: bool | None = None) -> Result:
    """Keep complete per-repository results, including entirely refused scopes.

    Every entry has repository plus either result or a closed error object.
    Scope resolution itself is supplied by the settings/scope feature tasks.
    """
    if not entries:
        raise MycelError(ErrorCode.REFUSED, "No enabled repository could be selected.")
    for entry in entries:
        if set(entry) not in ({"repository", "result"}, {"repository", "error"}):
            raise MycelError(ErrorCode.INTERNAL, "Invalid repository result entry.")
        if "error" in entry:
            error = entry["error"]
            if not isinstance(error, dict) or set(error) != {"code", "message"}:
                raise MycelError(ErrorCode.INTERNAL, "Invalid repository error entry.")
            ErrorCode(error["code"])
    failures = [e for e in entries if "error" in e]
    return Result({"repositories": list(entries)}, int(bool(failures)))


def run(argv: Sequence[str], *, handlers: dict[str, Handler] | None = None,
        stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parsed: Invocation | Result | None = None
    try:
        parsed = parse(argv)
        if (isinstance(parsed, Invocation) and parsed.command == 'grep'
                and (handlers is None or 'grep' not in handlers)):
            # Literal grep is independent of settings and every optional
            # service. Injected handlers retain the loaded invocation contract
            # below; the public handler loads tail settings only after grep.
            from ._grep import handle_grep
            return handle_grep(parsed, stdout=stdout, stderr=stderr).status
        if isinstance(parsed, Result):
            result = parsed
        else:
            snapshot = load_settings()
            parsed = replace(parsed, settings=snapshot,
                             grep_plain=parsed.command == "grep" and
                             (os.environ.get("MYCEL_GREP_PLAIN") == "1" or not snapshot.valid))
            if parsed.command not in {"info", "grep"}:
                snapshot.require_valid()
            selected_handlers = {"api-key": _api_key, "info": _settings_info, "grep": _plain_grep, "repos": _repos, "init": _init}
            selected_handlers["read"] = _read_chunk
            from ._search import handle_search
            selected_handlers["search"] = handle_search
            from ._undocumented import handle_undocumented
            selected_handlers["undocumented"] = handle_undocumented
            from ._refs import refs
            selected_handlers["refs"] = refs
            from ._derive import derive
            selected_handlers["derive"] = derive
            from ._relate import relate
            selected_handlers["relate"] = relate
            from ._verification import handle_confirm
            selected_handlers["confirm"] = handle_confirm
            from ._verification_reader import handle_verifications
            selected_handlers["verifications"] = handle_verifications
            from ._embed import embed
            selected_handlers["embed"] = embed
            from ._ingest import ingest
            selected_handlers['ingest'] = ingest
            from ._activity_reader import handle_activity
            selected_handlers['activity'] = handle_activity
            from ._evaluate import evaluate
            selected_handlers["evaluate"] = evaluate
            from ._summaries import handle_summaries
            selected_handlers["summaries"] = handle_summaries
            from ._overview import handle_overview
            selected_handlers["overview"] = handle_overview
            from ._classify import handle_classify
            selected_handlers["classify"] = handle_classify
            from ._provenance_reports import handle_drifts, handle_stale, handle_status
            selected_handlers.update(drifts=handle_drifts, stale=handle_stale, status=handle_status)
            if handlers is not None:
                selected_handlers.update(handlers)
            result = dispatch(parsed, selected_handlers)
        if isinstance(result, StreamedResult):
            return result.status
        # Serialize in full before any write; an invalid reply cannot leave a
        # half JSON document followed by an error object.
        encoded = json.dumps(result.value, ensure_ascii=True, allow_nan=False)
        status = result.status
    except KeyboardInterrupt:
        if isinstance(parsed, Invocation) and parsed.command == "grep":
            return 128 + getattr(sys.exception(), "signal_number", signal.SIGINT)
        encoded = json.dumps(MycelError(ErrorCode.REFUSED, "Stopped by the caller.").to_dict())
        status = 2
        stderr.write("Stopped by the caller.\n")
    except MycelError as error:
        if isinstance(parsed, Invocation) and parsed.command == "grep":
            stderr.write(error.message + "\n")
            return 2
        encoded = json.dumps(error.to_dict(), ensure_ascii=True, allow_nan=False)
        status = 1
    except Exception:
        if isinstance(parsed, Invocation) and parsed.command == "grep":
            stderr.write("The grep operation failed internally.\n")
            return 2
        encoded = json.dumps(MycelError(ErrorCode.INTERNAL, "The command failed internally.").to_dict())
        status = 1
        stderr.write("The command failed internally.\n")
    try:
        stdout.write(encoded + "\n")
        stdout.flush()
    except (OSError, UnicodeError):
        # The receiver closed or cannot accept the result. A second write
        # would risk concatenating an error onto partially delivered JSON.
        stderr.write("The result could not be written.\n")
        return 1
    return status


def _stop(signum: int, frame: object) -> None:
    stop = KeyboardInterrupt()
    stop.signal_number = signum
    raise stop


def main() -> int:
    previous = {s: signal.signal(s, _stop) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        return run(sys.argv[1:])
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
