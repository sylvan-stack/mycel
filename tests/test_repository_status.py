# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public repository inventory and offline coverage on disposable PostgreSQL."""
from dataclasses import replace
from types import SimpleNamespace

from psycopg import pq
from mycel._embed import retained_contexts
from mycel._embedding_plan import load_tokenizer
from mycel._embedding_store import EmbeddingStore
from mycel._errors import MycelError
from mycel._locks import operation_guard
from mycel._provenance_reports import ProvenanceReports, handle_status
from mycel._repository_status import RepositoryReports
from mycel._settings import load_settings
from mycel._voyage import PartFailure, PartIdentity, VectorWrite


import json
import os
import unittest
from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._provenance_reports import handle_status

try:
    from . import test_located_reconciliation as fixtures
    from . import test_provenance_reports as provenance_fixtures
except ImportError:
    import test_located_reconciliation as fixtures
    import test_provenance_reports as provenance_fixtures


class RepositoryStatusUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RepositoryStatusStoreTests(unittest.TestCase):
    check_kind = "store"

    state = provenance_fixtures.ProvenanceReportStoreTests.state
    no_work = provenance_fixtures.ProvenanceReportStoreTests.no_work

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

    def invoke(self, connection, *arguments):
        @contextmanager
        def connected(_credentials):
            yield connection
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                patch('mycel._database.store_connection', connected):
            status = run(['status', *arguments], handlers={'status': handle_status}, stdout=stdout, stderr=stderr)
        self.assertEqual(stderr.getvalue(), '')
        return status, json.loads(stdout.getvalue())


# Archived complete imports; restore needed names in their original scope, not at this file tail.
