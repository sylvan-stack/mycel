"""Bounded owned check processes; no product, provider or store imports."""
from __future__ import annotations

from contextlib import contextmanager
import math
import os
import signal
import subprocess
import sys
import threading
import time

from ._core import BuildError


class ProcessCancelled(KeyboardInterrupt):
    """Retain the caught signal while cleanup completes before cancellation."""
    def __init__(self, signum):
        super().__init__('A build check was cancelled.')
        self.signum = signum


def _cancel(number, handler, frame=None):
    # Preserve the caller's sticky deadline/custom cancellation exception.
    # Spawn-deferred delivery occurs after handle assignment inside the try.
    if callable(handler):
        handler(number, frame)
    raise ProcessCancelled(number)


@contextmanager
def _defer_cleanup_signals():
    pending, previous = [], {}
    def defer(number, _frame):
        pending.append(number)
    try:
        if threading.current_thread() is threading.main_thread():
            for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
                previous[number] = signal.getsignal(number)
                signal.signal(number, defer)
        yield
    finally:
        active_error = sys.exception()
        for number, handler in previous.items():
            signal.signal(number, handler)
        # Exception propagation skips code after try/finally. Delivery belongs
        # here, including when cleanup began with an ordinary active failure.
        if pending:
            try:
                _cancel(pending[0], previous[pending[0]])
            except BaseException as cancellation:
                cancellation.deferred_signals = list(pending)
                if active_error is not None:
                    raise cancellation from active_error
                raise


def group_absent(group):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def _end_group(process, *, grace=1.0):
    """Stop only the group created with this actual Popen handle."""
    for selected in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if group_absent(process.pid):
            process.wait(timeout=grace)
            return
        try:
            os.killpg(process.pid, selected)
        except ProcessLookupError:
            process.wait(timeout=grace)
            return
        until = time.monotonic() + grace
        try:
            process.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
        while time.monotonic() < until:
            if group_absent(process.pid):
                process.wait(timeout=grace)
                return
            time.sleep(min(0.01, max(0, until - time.monotonic())))
    process.wait(timeout=grace)
    if not group_absent(process.pid):
        raise BuildError('refused', 'A build check process group did not terminate.')


def end_group(process, *, grace=1.0):
    with _defer_cleanup_signals():
        _end_group(process, grace=grace)


@contextmanager
def owned_process(command, *, cwd=None, env=None, stdin=None):
    """Protect spawn/handle assignment and the complete owned lifecycle.

    Caught signals queue during Popen assignment rather than being ignored or
    masked in the child. Cancellation is raised inside the owned try after the
    handle is assigned. No guessed PID or group is used on an unknown launch.
    """
    if threading.current_thread() is not threading.main_thread():
        raise BuildError('refused', 'Build check supervision requires the main thread.')
    process, failure, cleanup_error = None, None, None
    previous, events = {}, []
    state = {'spawning': False, 'cleaning': False}
    actual = {'spawnAttempted': False, 'spawnConfirmed': False, 'pid': None,
              'processReaped': None, 'processGroupAbsent': None}
    def interrupted(number, _frame):
        deferred = state['spawning'] or state['cleaning']
        events.append({'signal': number, 'phase': 'spawn' if state['spawning'] else
                       'cleanup' if state['cleaning'] else 'running', 'delivered': not deferred})
        if not deferred:
            _cancel(number, previous[number], _frame)
    def deliver(event):
        event['delivered'] = True
        _cancel(event['signal'], previous[event['signal']])
    def execution_state():
        return {**actual, 'observedSignals': [event['signal'] for event in events],
                'observedSignalEvents': [dict(event) for event in events]}
    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
            previous[number] = signal.getsignal(number)
            signal.signal(number, interrupted)
        try:
            state['spawning'] = True
            try:
                actual['spawnAttempted'] = True
                process = subprocess.Popen(command, cwd=cwd, env=env, stdin=stdin,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                actual.update(spawnConfirmed=True, pid=process.pid)
            finally:
                state['spawning'] = False
            queued = next((event for event in events if not event['delivered']), None)
            if queued is not None:
                deliver(queued)
            yield process
        except BaseException as error:
            failure = error
            raise
        finally:
            state['cleaning'] = True
            if process is not None:
                try:
                    # The surrounding cleaning state already queues all three
                    # cancellation signals until these actual groups are gone.
                    _end_group(process)
                    actual.update(processReaped=process.returncode is not None,
                                  processGroupAbsent=True)
                except BaseException as error:
                    cleanup_error = error
                finally:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()
            actual.update(spawnOutcomeUnconfirmed=actual['spawnAttempted'] and not actual['spawnConfirmed'])
            for error in (failure, cleanup_error):
                if error is not None:
                    error.process_state = execution_state()
            # Deliver a newly deferred signal after reaping and pipe closure,
            # even if the body already has TimeoutExpired/BuildError in flight.
            # Already delivered events are never invoked a second time.
            queued = next((event for event in events if not event['delivered']), None)
            if queued is not None:
                try:
                    deliver(queued)
                except BaseException as error:
                    error.process_state = execution_state()
                    if cleanup_error is not None:
                        raise error from cleanup_error
                    if failure is not None:
                        raise error from failure
                    raise
            if cleanup_error is not None:
                raise cleanup_error
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_group(command, *, cwd=None, env=None, timeout=5400, input=None):
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= 5400):
        raise BuildError('invalid_input', 'Build checks need a positive deadline of at most 5400 seconds.')
    with owned_process(command, cwd=cwd, env=env,
                       stdin=subprocess.PIPE if input is not None else None) as process:
        output, errors = process.communicate(input=input, timeout=timeout)
        if not group_absent(process.pid):
            raise BuildError('refused', 'A completed check left a running process group.')
        return subprocess.CompletedProcess(command, process.returncode, output, errors)
