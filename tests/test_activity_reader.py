# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public pass identity details through the finite CLI and real-store boundary."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from mycel._activity import AppliedMutation, FileChange, IdentityChange, MutationActivity
from mycel._cli import Invocation, run
from mycel._activity_reader import handle_activity
from mycel._errors import MycelError
from mycel._settings import load_settings


import json
import unittest
from io import StringIO

from mycel._cli import run
from mycel._store import TABLES


def invoke(arguments):
    output, diagnostics = StringIO(), StringIO()
    status = run(arguments, stdout=output, stderr=diagnostics)
    return status, json.loads(output.getvalue()), diagnostics.getvalue()


def state(connection):
    return {table.name: tuple(sorted(connection.execute(
        'SELECT * FROM public."' + table.name + '"').fetchall(), key=repr)) for table in TABLES}


class ActivityReaderTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class ActivityReaderStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
