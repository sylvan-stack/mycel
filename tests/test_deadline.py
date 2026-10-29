# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Invocation deadlines reach safe child boundaries and leave fallback reads usable."""
import unittest
from types import SimpleNamespace

from psycopg import pq


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Connection:
    def __init__(self, *, in_transaction=False):
        self.info = SimpleNamespace(transaction_status=(pq.TransactionStatus.INTRANS
            if in_transaction else pq.TransactionStatus.IDLE))
        self.closed = False
        self.queries = []

    def execute(self, query, params=None, **kwargs):
        self.queries.append((query, params, kwargs))
        if query == 'SHOW statement_timeout':
            return SimpleNamespace(fetchone=lambda: ('17s',))
        if query == 'fixture failure':
            raise RuntimeError('query failed')
        return SimpleNamespace(fetchall=lambda: [('existing indexed result',)])


class DeadlineBoundaryTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
