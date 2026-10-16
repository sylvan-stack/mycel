"""Invocation-owned freshness deadline through nested readers and transactions.

The context is empty for ordinary commands. Cleanup can suspend it briefly to
release an owned lock even after search has exhausted its work allowance.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import math

from psycopg import pq
from psycopg.errors import QueryCanceled

_DEADLINE = ContextVar('mycel_operation_deadline', default=None)


def current_deadline():
    return _DEADLINE.get()


def check_deadline():
    deadline = current_deadline()
    if deadline is not None:
        deadline.check()


def deadline_seconds(maximum):
    deadline = current_deadline()
    if deadline is None:
        return maximum
    deadline.check()
    return min(maximum, deadline.remaining())


@contextmanager
def deadline_guard(deadline):
    token = _DEADLINE.set(deadline)
    try:
        check_deadline()
        yield
    finally:
        _DEADLINE.reset(token)


@contextmanager
def deadline_suspended():
    token = _DEADLINE.set(None)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


class DeadlineConnection:
    """Clamp every SQL statement to the remaining invocation allowance.

    All product changes still use the original connection's transactions. Local
    timeouts disappear at transaction end. Autocommit readers and advisory
    operations restore their prior timeout, including on cancellation.
    """
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def execute(self, query, params=None, **kwargs):
        deadline = current_deadline()
        if deadline is None:
            return self._connection.execute(query, params, **kwargs)
        deadline.check()
        local = self._connection.info.transaction_status != pq.TransactionStatus.IDLE
        previous = None
        if not local:
            previous = self._connection.execute("SHOW statement_timeout").fetchone()[0]
        deadline.check()
        milliseconds = max(1, math.floor(deadline.remaining() * 1000))
        if local:
            # SET leaves transaction characteristics selectable; a SELECT of
            # set_config here would precede SET TRANSACTION and take a snapshot.
            self._connection.execute(f"SET LOCAL statement_timeout = '{milliseconds}ms'")
        else:
            self._connection.execute("SELECT pg_catalog.set_config('statement_timeout', %s, false)",
                                     (f'{milliseconds}ms',))
        try:
            # Reading and setting the timeout are part of the same allowance;
            # neither can authorize a new statement after it has expired.
            deadline.check()
            # A successful autocommit advisory acquisition must reach its
            # owner's finally block before an expired deadline can raise.
            return self._connection.execute(query, params, **kwargs)
        except QueryCanceled as error:
            # Translate our statement cap before ordinary store boundaries
            # can turn it into a store failure. Millisecond rounding can fire
            # just before the absolute monotonic expiry.
            if error.diag.message_primary == 'canceling statement due to statement timeout':
                from ._freshness import DeadlineExceeded
                raise DeadlineExceeded() from None
            deadline.check()
            raise
        finally:
            if previous is not None and not self._connection.closed:
                self._connection.execute("SELECT pg_catalog.set_config('statement_timeout', %s, false)",
                                         (previous,))
