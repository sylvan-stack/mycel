"""The bounded external command boundary for MYC-8 summary generation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import threading
import time

from ._errors import MycelError
from ._safeguards import (
    ChildProcessFailure, _defer_cleanup_signals, _end_process_group, resolve_command,
    safe_child_environment,
)


WRITER_TIMEOUT_SECONDS = 300.0
MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class WriterResult:
    response: bytes | None = field(repr=False)
    reason: str | None
    attempts: int


class _Stopped(Exception):
    """A parallel batch was interrupted by its caller."""


def _check_stopped(stopped: threading.Event) -> None:
    if stopped.is_set():
        raise _Stopped()


class SummaryWriter:
    """Run literal argv with request bytes on stdin and one retry on failure.

    One instance limits concurrent subprocesses across both public methods.
    Output bytes are retained only after a successful UTF-8/nonempty check;
    stderr and exception text never enter results or diagnostics.
    """

    def __init__(self, command: tuple[str, ...], at_once: int, *,
                 _timeout: float = WRITER_TIMEOUT_SECONDS, before_launch=None):
        if (not isinstance(command, tuple) or not command
                or any(not isinstance(argument, str) or "\0" in argument for argument in command)
                or not command[0].strip()):
            raise MycelError("settings", "The summary command must name an executable and string arguments.")
        if type(at_once) is not int or at_once < 1:
            raise MycelError("settings", "The summary concurrency setting must be a positive integer.")
        if (isinstance(_timeout, bool) or not isinstance(_timeout, (int, float))
                or not math.isfinite(_timeout) or _timeout <= 0):
            raise MycelError("settings", "The summary writer deadline must be positive and finite.")
        self.command = command
        self.at_once = at_once
        self._timeout = _timeout
        self._slots = threading.BoundedSemaphore(at_once)
        if before_launch is not None and not callable(before_launch):
            raise MycelError("invalid_input", "The summary launch guard must be callable.")
        self._before_launch = before_launch

    @staticmethod
    def _validate_request(request: bytes) -> None:
        if not isinstance(request, bytes):
            raise MycelError("invalid_input", "A summary request must contain bytes.")

    def write(self, request: bytes) -> WriterResult:
        self._validate_request(request)
        return self._write(request, threading.Event())

    def write_many(self, requests: tuple[bytes, ...]) -> tuple[WriterResult, ...]:
        if not isinstance(requests, tuple):
            raise MycelError("invalid_input", "Summary requests must be a tuple of bytes.")
        for request in requests:
            self._validate_request(request)
        if not requests:
            return ()
        stopped = threading.Event()
        executor = ThreadPoolExecutor(max_workers=min(self.at_once, len(requests)),
                                      thread_name_prefix="mycel-summary")
        futures = []
        try:
            futures = [executor.submit(self._write, request, stopped) for request in requests]
            return tuple(future.result() for future in futures)
        except BaseException:
            stopped.set()
            raise
        finally:
            with _defer_cleanup_signals():
                executor.shutdown(wait=True, cancel_futures=True)

    def _write(self, request: bytes, stopped: threading.Event) -> WriterResult:
        while not self._slots.acquire(timeout=_POLL_SECONDS):
            _check_stopped(stopped)
        try:
            for attempt in (1, 2):
                _check_stopped(stopped)
                response, reason = self._attempt(request, stopped)
                if reason is None:
                    return WriterResult(response, None, attempt)
            return WriterResult(None, reason, 2)
        finally:
            self._slots.release()

    def _attempt(self, request: bytes, stopped: threading.Event) -> tuple[bytes | None, str | None]:
        try:
            # A new directory belongs to this attempt alone, including retries.
            with tempfile.TemporaryDirectory(prefix="mycel-summary-") as directory:
                return self._run(request, stopped, directory)
        except OSError:
            return None, "io_failure"

    def _run(self, request: bytes, stopped: threading.Event, directory: str) -> tuple[bytes | None, str | None]:
        _check_stopped(stopped)
        deadline = time.monotonic() + self._timeout
        try:
            home = Path.home()
            command = resolve_command(self.command, home=home, allow_path_search=True)
        except (ChildProcessFailure, OSError, ValueError):
            return None, "start_failed"
        # A changed-input guard is a caller lifecycle outcome, never a failed
        # subprocess start or an instruction to retry the same obsolete request.
        if self._before_launch is not None:
            self._before_launch()
        try:
            process = subprocess.Popen(command, shell=False, cwd=directory,
                                       env=safe_child_environment(home, Path(directory)),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, bufsize=0, close_fds=True,
                                       start_new_session=True)
        except (ChildProcessFailure, OSError, ValueError):
            return None, "start_failed"

        output = bytearray()
        stderr_size = 0
        sent = 0
        selector = None
        try:
            selector = selectors.DefaultSelector()
            for stream in (process.stdin, process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
            if request:
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map() or process.poll() is None:
                _check_stopped(stopped)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, "timeout"
                for key, _ in selector.select(min(_POLL_SECONDS, remaining)):
                    stream, kind = key.fileobj, key.data
                    try:
                        if kind == "stdin":
                            sent += os.write(stream.fileno(), memoryview(request)[sent:sent + 64 * 1024])
                            if sent == len(request):
                                selector.unregister(stream)
                                stream.close()
                            continue
                        limit = MAX_STDOUT_BYTES if kind == "stdout" else MAX_STDERR_BYTES
                        size = len(output) if kind == "stdout" else stderr_size
                        chunk = os.read(stream.fileno(), min(64 * 1024, limit + 1 - size))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                    elif len(chunk) > limit - size:
                        return None, "stdout_limit" if kind == "stdout" else "stderr_limit"
                    elif kind == "stdout":
                        output.extend(chunk)
                    else:
                        stderr_size += len(chunk)
            _check_stopped(stopped)
            process.wait()
            if process.returncode != 0:
                return None, "nonzero_exit"
            try:
                text = output.decode("utf-8")
            except UnicodeDecodeError:
                return None, "invalid_utf8"
            if not text.strip():
                return None, "empty_response"
            return bytes(output), None
        except OSError:
            return None, "io_failure"
        finally:
            try:
                # Completed commands can also leave background descendants.
                # The whole process group belongs to this attempt's lifetime.
                _end_process_group(process)
            finally:
                if selector is not None:
                    selector.close()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
