# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Runner isolation checks do not qualify actual store acceptance."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
import json
from types import SimpleNamespace
from unittest.mock import patch

from psycopg.errors import ObjectInUse
from mycel._coverage import CoverageError, PostgresBackend, disposable_store


import unittest

from mycel._check_store import NativePostgresBackend
from mycel._coverage import PostgresBackend


class NativeCheckRunnerTests(unittest.TestCase):
    @staticmethod
    def backends(owner="owner"):
        address = "postgresql://fixture@localhost/" + owner
        return (NativePostgresBackend(address), PostgresBackend(address, psql="/fictional/psql"))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
