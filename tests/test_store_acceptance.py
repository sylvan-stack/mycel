# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Product-store acceptance requires a real per-check disposable database."""
from contextlib import contextmanager
import io
import json
import socket
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings


import unittest
from hashlib import sha256
from uuid import uuid4

import psycopg

from mycel import _store as store
from mycel._errors import MycelError


class RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **kwargs)

    def transaction(self, *args, **kwargs):
        return self.connection.transaction(*args, **kwargs)


class ProductStoreTests(unittest.TestCase):
    check_kind = "store"

    def connection(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def error(self, code, action):
        with self.assertRaises(MycelError) as error:
            action()
        self.assertEqual(error.exception.code.value, code)


class EmptyProductStoreTests(unittest.TestCase):
    check_kind = "store"

    initialize_store = staticmethod(lambda backend, settings_file: None)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
