# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""The native store boundary with only private, injected connections."""
from io import StringIO
from functools import partial
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch

import psycopg
from psycopg import conninfo, pq
from mycel._database import _native_connect, _without_libpq_environment, store_connection


import unittest

from mycel._credentials import Secret, StoreTarget
from mycel._errors import MycelError

SENTINEL = "private-password-not-for-output"
ADDRESS = "postgresql://fixture@127.0.0.1:6543/fixture"


class FakePGconn:
    def __init__(self, needs_password=False):
        self.needs_password = needs_password
        self.finished = False

    def finish(self):
        self.finished = True


class FakeConnection:
    def __init__(self):
        self.closed = False
        self.pgconn = FakePGconn()

    def close(self):
        self.closed = True


class FakeCredentials:
    def __init__(self, address=ADDRESS, password=SENTINEL):
        self.address = address
        self.password = password
        self.requests = []
        self.budgets = []

    def store_target(self, *, password_requested=False, timeout_seconds=None, cancelled=None):
        self.requests.append(password_requested)
        self.budgets.append(timeout_seconds)
        password = Secret(self.password) if password_requested and self.password is not None else None
        return StoreTarget(self.address, password)


class DatabaseTests(unittest.TestCase):
    def assert_unavailable(self, function):
        with self.assertRaises(MycelError) as raised:
            function()
        self.assertEqual(raised.exception.code, "store_unavailable")
        self.assertNotIn(SENTINEL, str(raised.exception))
        self.assertNotIn(ADDRESS, str(raised.exception))
        return raised.exception


# Archived complete imports; restore needed names in their original scope, not at this file tail.
