# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Complete public activity history over genuine read-only store snapshots."""
from contextlib import contextmanager
from io import StringIO
import json
from unittest.mock import patch
from uuid import uuid4

from mycel import _activity as activity
from mycel import _locks as locks
from mycel._cli import parse, run
from mycel._errors import MycelError
from mycel._source_refs import SourceAddress


import unittest

from mycel._activity_reader import activity_from_store

try:
    from .test_activity_retention import _History
except ImportError:
    from test_activity_retention import _History


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **options):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **options)


class ActivityHistoryUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class ActivityHistoryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.history = _History(self.store_fixture)

    def read(self, connection, names=('fixture',), **options):
        return activity_from_store(connection, self.history.settings, names, **options)

    @staticmethod
    def ids(reply):
        return [int(entry['id']) for entry in reply['entries']]


# Archived complete imports; restore needed names in their original scope, not at this file tail.
