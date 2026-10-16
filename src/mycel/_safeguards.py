"""Internal boundaries for paid work and short-lived child processes.

All model adapters and repository readers must enter through these helpers.
They accept frozen invocation intent, never provider credentials or an inherited
child environment. They are implementation details, not a caller interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence

from ._errors import MycelError
from ._deadline import check_deadline, deadline_seconds


SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
STDOUT_LIMIT = 1024 * 1024
STDERR_LIMIT = 64 * 1024
CLEANUP_SECONDS = 1.0


@dataclass(frozen=True)
class InvocationPolicy:
    command: str
    action: str | None = None
    dry_run: bool = False
    kind: str | None = None
    live: bool = False
    embed: bool = False


def model_call_allowed(policy: InvocationPolicy, purpose: str) -> bool:
    """MYC-0.10: authorize a particular model boundary, not all paid work."""
    if policy.dry_run:
        return False
    if purpose == "embedding":
        if policy.command == "check" and policy.action == "embedding" and policy.live:
            return True
        if policy.command in {"embed", "search", "grep"}:
            return True
        if policy.command == "ingest":
            return policy.embed
        if policy.command == "summaries":
            return policy.action in {"build", "regenerate"}
        return policy.command == "evaluate" and policy.kind in {None, "retrieval"}
    if purpose in {"jev", "reviewer"}:
        return policy.command == "classify" or (
            policy.command == "evaluate" and policy.kind == "drift" and policy.live
        )
    if purpose == "summary":
        return policy.command == "summaries" and policy.action in {"build", "regenerate"}
    return False


def require_model_call(policy: InvocationPolicy, purpose: str) -> None:
    if not model_call_allowed(policy, purpose):
        raise MycelError("refused", "This operation does not permit the requested model call.")


def safe_child_environment(home: Path, private_dir: Path) -> dict[str, str]:
    """MYC-14.23: construct the complete environment without copying any values."""
    return {
        "HOME": str(home.resolve()),
        "PATH": SYSTEM_PATH,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TMPDIR": str(private_dir.resolve()),
    }


def _command_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)) or not argv:
        raise MycelError("settings", "A child command must be a nonempty argument list.")
    if any(not isinstance(arg, str) or "\0" in arg for arg in argv) or not argv[0]:
        raise MycelError("settings", "Child commands require an executable and NUL-free string arguments.")
    return tuple(argv)


def resolve_command(
    argv: Sequence[str], *, home: Path | None = None, allow_path_search: bool = False
) -> tuple[str, ...]:
    """Resolve only the executable; arguments remain byte-for-byte unchanged.

    Reviewer callers use the default: no PATH search. Summary callers may use
    the user's search path to locate their explicitly configured command. That
    path is never forwarded to the child.
    """
    command = _command_argv(argv)
    executable = command[0]
    if executable.startswith("~/"):
        executable = str((home or Path.home()).resolve() / executable[2:])
    elif not Path(executable).is_absolute():
        if not allow_path_search or "/" in executable:
            raise MycelError("settings", "The child executable must have an absolute path.")
        executable = shutil.which(executable) or ""
    path = Path(executable).resolve() if executable else None
    if path is None or not path.is_file() or not os.access(path, os.R_OK | os.X_OK):
        raise ChildProcessFailure("unavailable")
    return (str(path), *command[1:])


@dataclass(frozen=True)
class CompletedChild:
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float


class ChildProcessFailure(MycelError):
    """Safe diagnostics; no command, raw output or OS exception is exposed."""

    def __init__(self, reason: str):
        self.reason = reason
        messages = {
            "unavailable": "The child program is unavailable.",
            "timeout": "The child program exceeded its time limit.",
            "stdout_limit": "The child program exceeded its standard output limit.",
            "stderr_limit": "The child program exceeded its diagnostic output limit.",
            "transport": "The child program could not be run.",
            "input_incomplete": "The child program did not consume its complete request.",
        }
        super().__init__("refused", messages.get(reason, messages["transport"]))


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Darwin may report EPERM while the owned group contains only zombies.
        # Treat it as present until the cleanup grace has elapsed.
        return True


@contextmanager
def _defer_cleanup_signals():
    """Keep repeat signals from abandoning a child midway through cleanup."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    preserve_interrupt = isinstance(sys.exception(), KeyboardInterrupt)
    pending = []
    signals = {signal.SIGINT, signal.SIGTERM}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    previous_handlers = {number: signal.getsignal(number) for number in signals}

    def defer(number, frame):
        pending.append(number)

    try:
        for number in signals:
            signal.signal(number, defer)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        for number, handler in previous_handlers.items():
            signal.signal(number, handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    # A signal arriving during otherwise normal cleanup still stops the caller.
    # An interruption already in flight remains the original KeyboardInterrupt.
    if pending and not preserve_interrupt:
        number = pending[0]
        handler = previous_handlers[number]
        if callable(handler):
            handler(number, None)
        elif handler == signal.SIG_DFL:
            signal.raise_signal(number)


def _end_process_group(process: subprocess.Popen[bytes]) -> None:
    with _defer_cleanup_signals():
        _terminate_process_group(process)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    # Even a successfully exited adapter must not leave a paid request running
    # in a descendant. The group ID remains the original child's PID.
    if process.stdin is not None:
        process.stdin.close()
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    until = time.monotonic() + CLEANUP_SECONDS
    while time.monotonic() < until:
        process.poll()
        if not _group_exists(process.pid):
            break
        time.sleep(min(0.01, max(0.0, until - time.monotonic())))
    if _group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=CLEANUP_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=CLEANUP_SECONDS)


def _run_process(
    argv: tuple[str, ...], request: bytes, *, cwd: Path, environment: dict[str, str],
    timeout_seconds: float, stdout_limit: int, stderr_limit: int,
    cancelled: Callable[[], bool] | None,
    before_spawn: Callable[[], None] | None = None, require_complete_input: bool = False,
    absolute_deadline: float | None = None,
) -> CompletedChild:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise MycelError("invalid_input", "A child process requires a finite positive time limit.")
    if any(type(limit) is not int or limit < 1 for limit in (stdout_limit, stderr_limit)):
        raise MycelError("invalid_input", "Child output limits must be positive integers.")
    if absolute_deadline is not None and (type(absolute_deadline) not in {int, float}
            or not math.isfinite(absolute_deadline)):
        raise MycelError("invalid_input", "A child deadline must be a finite monotonic time.")
    if not isinstance(request, bytes):
        raise MycelError("invalid_input", "Child input must be bytes.")
    started = time.monotonic()
    if before_spawn is not None:
        before_spawn()
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=environment, shell=False, close_fds=True, start_new_session=True,
        )
    except OSError:
        raise ChildProcessFailure("unavailable") from None

    output = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    pending = memoryview(request)
    try:
        with selectors.DefaultSelector() as selector:
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            while selector.get_map() or process.poll() is None:
                check_deadline()
                if cancelled is not None and cancelled():
                    raise KeyboardInterrupt
                remaining = timeout_seconds - (time.monotonic() - started)
                if absolute_deadline is not None:
                    remaining = min(remaining, absolute_deadline - time.monotonic())
                if remaining <= 0:
                    raise ChildProcessFailure("timeout")
                for key, _ in selector.select(min(0.05, remaining)):
                    stream = key.fileobj
                    if key.data == "stdin":
                        try:
                            written = os.write(stream.fileno(), pending[:65536])
                            pending = pending[written:]
                        except BlockingIOError:
                            # Readiness can change before this nonblocking write.
                            # Keep the request registered and retry within its deadline.
                            continue
                        except BrokenPipeError:
                            if require_complete_input:
                                raise ChildProcessFailure("input_incomplete") from None
                            pending = memoryview(b"")
                        if not pending:
                            selector.unregister(stream)
                            stream.close()
                    else:
                        try:
                            data = os.read(stream.fileno(), 65536)
                        except BlockingIOError:
                            # A transient lack of data is not EOF or transport failure.
                            continue
                        if not data:
                            selector.unregister(stream)
                            stream.close()
                        elif len(output[key.data]) + len(data) > limits[key.data]:
                            raise ChildProcessFailure(key.data + "_limit")
                        else:
                            output[key.data].extend(data)
        return CompletedChild(
            process.wait(), bytes(output["stdout"]), bytes(output["stderr"]),
            time.monotonic() - started,
        )
    except OSError:
        raise ChildProcessFailure("transport") from None
    finally:
        try:
            _end_process_group(process)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def run_child(
    argv: Sequence[str], request: bytes = b"", *, timeout_seconds: float,
    home: Path | None = None, stdout_limit: int = STDOUT_LIMIT,
    stderr_limit: int = STDERR_LIMIT, cancelled: Callable[[], bool] | None = None,
) -> CompletedChild:
    """Run resolved argv in a fresh empty directory with bounded pipe transport."""
    user_home = (home or Path.home()).resolve()
    command = resolve_command(argv, home=user_home)
    with tempfile.TemporaryDirectory(prefix="mycel-child-") as directory:
        private_dir = Path(directory)
        private_dir.chmod(0o700)
        return _run_process(
            command, request, cwd=private_dir,
            environment=safe_child_environment(user_home, private_dir),
            timeout_seconds=timeout_seconds, stdout_limit=stdout_limit,
            stderr_limit=stderr_limit, cancelled=cancelled,
        )


def run_model_child(
    policy: InvocationPolicy, purpose: str, argv: Sequence[str], request: bytes, *,
    timeout_seconds: float, home: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CompletedChild:
    require_model_call(policy, purpose)
    if purpose not in {"summary", "reviewer"}:
        raise MycelError("refused", "This model boundary does not use a child program.")
    if purpose == "reviewer" and any(not arg for arg in _command_argv(argv)):
        raise MycelError("settings", "Reviewer command arguments must be nonempty strings.")
    command = resolve_command(argv, home=home, allow_path_search=purpose == "summary")
    return run_child(command, request, timeout_seconds=timeout_seconds, home=home, cancelled=cancelled)


def run_resolved_reviewer(
    policy: InvocationPolicy, argv: Sequence[str], request: bytes, *,
    timeout_seconds: float, home: Path, before_spawn: Callable[[], None],
    cancelled: Callable[[], bool] | None = None,
    absolute_deadline: float | None = None,
) -> CompletedChild:
    """Launch a fingerprinted reviewer literally, with a final caller guard.

    Command resolution belongs to its frozen identity, so this boundary never
    resolves a symlink again or changes any argument. The guard verifies that
    identity and the remaining attempt budget immediately before Popen.
    """
    require_model_call(policy, "reviewer")
    command = _command_argv(argv)
    if any(not argument for argument in command) or not Path(command[0]).is_absolute():
        raise MycelError("settings", "Reviewer commands require absolute executables and nonempty arguments.")
    if not callable(before_spawn):
        raise MycelError("invalid_input", "Reviewer attempts require a fresh launch guard.")
    user_home = home.resolve()
    with tempfile.TemporaryDirectory(prefix="mycel-review-") as directory:
        private_dir = Path(directory)
        private_dir.chmod(0o700)
        return _run_process(
            command, request, cwd=private_dir,
            environment=safe_child_environment(user_home, private_dir),
            timeout_seconds=timeout_seconds, stdout_limit=STDOUT_LIMIT,
            stderr_limit=STDERR_LIMIT, cancelled=cancelled,
            before_spawn=before_spawn, require_complete_input=True,
            absolute_deadline=absolute_deadline,
        )


# Read operations are selected individually. Unknown flags fail closed, including
# output files, filters/textconv, signature verification, external diff and
# revision parsing's --parseopt / --sq-quote executable-oriented modes.
_GIT_OPTIONS = {
    "rev-parse": {"--show-toplevel", "--git-dir", "--absolute-git-dir", "--git-common-dir",
                  "--is-inside-work-tree", "--is-bare-repository", "--verify", "--quiet",
                  "--show-object-format", "--end-of-options"},
    "for-each-ref": set(),
    "show-ref": {"--head", "--heads", "--verify", "--hash", "--quiet", "-q"},
    "ls-tree": {"-r", "-t", "-d", "-l", "-z", "--name-only", "--name-status",
                "--full-name", "--full-tree"},
    "cat-file": {"-p", "-t", "-s", "-e", "--batch", "--batch-check", "--buffer"},
    "ls-files": {"-z", "-s", "-c", "-d", "-m", "-o", "--stage", "--cached", "--deleted",
                 "--modified", "--others", "--exclude-standard", "--full-name", "--error-unmatch"},
    "status": {"-z", "--short", "--branch", "--porcelain", "--porcelain=v1", "--porcelain=v2",
               "--untracked-files=no", "--untracked-files=normal", "--untracked-files=all"},
    "diff": {"-z", "-p", "-s", "-M", "--raw", "--name-only", "--name-status", "--numstat",
             "--shortstat", "--stat", "--patch", "--no-patch", "--no-ext-diff", "--no-textconv"},
    "show": {"-z", "-p", "-s", "--raw", "--name-only", "--name-status", "--patch",
             "--no-patch", "--no-ext-diff", "--no-textconv"},
    "log": {"-z", "-p", "-s", "-g", "--walk-reflogs", "--no-patch", "--oneline",
            "--no-ext-diff", "--no-textconv", "--reverse", "--first-parent"},
}


def _safe_git_format(value: str, command: str) -> bool:
    if command == "for-each-ref":
        stripped = re.sub(
            r"%\((?:refname(?::short)?|objectname(?::short(?:=\d+)?)?|objecttype|subject)\)",
            "", value,
        )
        stripped = re.sub(r"%[0-9a-fA-F]{2}", "", stripped)
    else:
        stripped = re.sub(r"%(?:[HhTtPpsbBnt]|[ac](?:n|e|d|D|r|t|i|I)|x[0-9a-fA-F]{2})", "", value)
    return "%" not in stripped.replace("%%", "")


def validate_read_only_git_args(args: Sequence[str]) -> tuple[str, ...]:
    """MYC-1.24: accept a small, explicit grammar, never global git options."""
    command = _command_argv(args)
    name, *arguments = command
    if name == "config" and command == ("config", "--bool", "--get", "core.ignorecase"):
        return command
    if name == "stash" and arguments[:1] == ["list"]:
        name = "log"
        arguments = arguments[1:]
    if name not in _GIT_OPTIONS:
        raise MycelError("refused", "The requested git operation is not a permitted read.")
    paths_only = False
    for arg in arguments:
        if paths_only or not arg.startswith("-"):
            continue
        if arg == "--":
            paths_only = True
            continue
        if arg in _GIT_OPTIONS[name]:
            continue
        if name in {"log", "show", "for-each-ref"} and arg.startswith("--format="):
            if _safe_git_format(arg[len("--format="):], name):
                continue
        if name in {"log", "show", "for-each-ref"} and re.fullmatch(r"--(?:max-count|count)=\d+", arg):
            continue
        if name in {"ls-tree", "show-ref"} and re.fullmatch(r"--abbrev=\d+", arg):
            continue
        if name == "for-each-ref" and re.fullmatch(r"--sort=-?(?:refname|objectname)", arg):
            continue
        raise MycelError("refused", "The requested git option is not a permitted read option.")
    return command


def run_git(
    args: Sequence[str], *, cwd: Path, request: bytes = b"", timeout_seconds: float = 10.0,
    stdout_limit: int = STDOUT_LIMIT, cancelled: Callable[[], bool] | None = None,
) -> CompletedChild:
    timeout_seconds = deadline_seconds(timeout_seconds)
    arguments = validate_read_only_git_args(args)
    executable = shutil.which("git", path=SYSTEM_PATH)
    if executable is None:
        raise ChildProcessFailure("unavailable")
    # These are owned options, never supplied by a caller. They prevent readers
    # from refreshing the index, starting configured executables or lazy-fetching.
    argv = (
        executable, "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false",
        *arguments,
    )
    if arguments[0] in {"show", "diff", "log", "stash"}:
        # Insert before all caller revisions and '--' path separators.
        offset = len(argv) - len(arguments) + (2 if arguments[0] == "stash" else 1)
        argv = (*argv[:offset], "--no-ext-diff", "--no-textconv", *argv[offset:])
    with tempfile.TemporaryDirectory(prefix="mycel-git-") as directory:
        environment = safe_child_environment(Path.home(), Path(directory))
        environment.update({
            "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
        })
        return _run_process(
            argv, request, cwd=Path(cwd), environment=environment,
            timeout_seconds=timeout_seconds, stdout_limit=stdout_limit,
            stderr_limit=STDERR_LIMIT, cancelled=cancelled,
        )
