# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Public pass identity details through the finite CLI and real-store boundary."""

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
