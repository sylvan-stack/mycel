# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Runner isolation checks do not qualify actual store acceptance."""

import unittest

from mycel._check_store import NativePostgresBackend
from mycel._coverage import PostgresBackend


class NativeCheckRunnerTests(unittest.TestCase):
    @staticmethod
    def backends(owner="owner"):
        address = "postgresql://fixture@localhost/" + owner
        return (NativePostgresBackend(address), PostgresBackend(address, psql="/fictional/psql"))



# Archived complete imports; restore needed names in their original scope, not at this file tail.
