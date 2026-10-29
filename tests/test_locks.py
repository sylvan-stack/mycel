# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""SQL protocol checks plus genuine disposable-store lock acceptance.

Scripted SQL never qualifies an MYC-6 store requirement. Store checks use the
gate's default product initializer and cannot run without a genuine fixture.
Only generated test databases are selected. The native backend may privately
read Mycel's store password when challenged; no paid provider key is acquired.
"""

import time
import unittest
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import pq

from mycel import _locks as locks
from mycel._coverage import require_check_database
from mycel._errors import MycelError
from mycel._store import require_store


class Rows:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class ScriptedConnection:
    """Protocol recorder only: intentionally not a PostgreSQL simulator."""

    def __init__(self):
        self.autocommit = True
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)
        self.closed = False
        self.registry = {}
        self.invocations = {}
        self.statements = []
        self.transactions = []
        self.held = Counter()
        self.busy = set()
        self.failure = None
        self.next_key = 1
        self.session = (42, datetime(2000, 1, 1, tzinfo=timezone.utc), uuid4())
        self.live_response = True

    @contextmanager
    def transaction(self):
        self.transactions.append("begin")
        saved = deepcopy((self.registry, self.invocations))
        self.info.transaction_status = pq.TransactionStatus.INTRANS
        try:
            yield
        except BaseException:
            self.registry, self.invocations = saved
            self.transactions.append("rollback")
            raise
        else:
            self.transactions.append("commit")
        finally:
            self.info.transaction_status = pq.TransactionStatus.IDLE

    def execute(self, statement, parameters=None):
        self.statements.append((statement, parameters))
        if self.failure and self.failure(statement, parameters):
            raise psycopg.errors.LockNotAvailable("public fixture failure")
        if statement.startswith("SET "):
            return Rows()
        if "pg_try_advisory_lock" in statement:
            marker = (parameters, "shared" if "lock_shared" in statement else "exclusive")
            okay = parameters not in self.busy
            if okay:
                self.held[marker] += 1
            return Rows((okay,))
        if "pg_advisory_unlock" in statement:
            marker = (parameters, "shared" if "unlock_shared" in statement else "exclusive")
            okay = self.held[marker] > 0
            if okay:
                self.held[marker] -= 1
            return Rows((okay,))
        if statement.startswith("SELECT key FROM public.mycel_lock_keys"):
            key = self.registry.get(parameters)
            return Rows(None if key is None else (key,))
        if statement.startswith("INSERT INTO public.mycel_lock_keys"):
            key = self.registry.setdefault(parameters, self.next_key)
            self.next_key += 1
            return Rows((key,))
        if statement.startswith("SELECT a.pid"):
            return Rows(self.session)
        if statement.startswith("INSERT INTO public.mycel_invocations"):
            if parameters[0] in self.invocations:
                return Rows()
            self.invocations[parameters[0]] = parameters
            return Rows((parameters[0],))
        if statement == locks._LIVENESS_SQL:
            return Rows((self.live_response,))
        raise AssertionError("Unexpected scripted SQL: " + statement)

    def close(self):
        self.closed = True
        self.held.clear()


class LockProtocolTests(unittest.TestCase):
    # These are check-declaration/protocol fixtures, never store acceptance.
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class LockStoreTests(unittest.TestCase):
    # No initialize_store override: the gate calls the product initializer.
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, "store_fixture"):
            self.fail("This acceptance check requires a genuine disposable store fixture.")
        self.assertIs(self.store_fixture.backend.real_store, True)
        require_check_database(self.store_fixture.database)

    @contextmanager
    def connect(self):
        fixture = self.store_fixture
        with fixture.backend.connection(fixture.database) as connection:
            self.assertEqual(connection.execute("SELECT pg_catalog.current_database()").fetchone()[0], fixture.database)
            require_store(connection)
            yield connection

    def busy(self, guard):
        started = time.monotonic()
        with self.assertRaises(MycelError) as raised:
            with guard:
                self.fail("conflicting guard was entered")
        self.assertEqual(raised.exception.code, "busy")
        self.assertLess(time.monotonic() - started, 0.5)



# Archived complete imports; restore needed names in their original scope, not at this file tail.
