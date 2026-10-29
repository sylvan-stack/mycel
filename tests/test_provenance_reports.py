# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Public offline provenance reports over configured disposable PostgreSQL."""

import json
import os
import unittest
from contextlib import ExitStack, contextmanager
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._provenance_reports import handle_drifts, handle_stale, handle_status
from mycel._store import TABLES

try:
    from . import test_drift_lifecycle as fixtures
except ImportError:
    import test_drift_lifecycle as fixtures


HANDLERS = {'drifts': handle_drifts, 'stale': handle_stale, 'status': handle_status}


class ProvenanceReportUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class ProvenanceReportStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.helper = fixtures.DriftLifecycleStoreTests()
        self.helper.store_fixture = self.store_fixture
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.base, self.fixture = self.helper.base, self.helper.fixture

    def state(self, connection):
        rows = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}
        sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences WHERE schemaname='public'").fetchall()
        rows['sequences'] = tuple((name, connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone())
                                  for (name,) in sequences)
        return rows

    def no_work(self):
        stack = ExitStack()
        for target in ('mycel._capture.capture_repository', 'mycel._drift_store.DriftStore.reconcile',
                       'mycel._declared_refs.DeclaredRefStore.recheck',
                       'mycel._credentials.Credentials.embedding_key', 'mycel._credentials.Credentials.jev_key',
                       'mycel._locks.allocate_key', 'subprocess.Popen'):
            stack.enter_context(patch(target, side_effect=AssertionError('A report performed work: ' + target)))
        return stack

    def invoke(self, connection, command, *options, repositories=('downstream',)):
        @contextmanager
        def connected(credentials):
            self.assertEqual(credentials.store_target().address, self.base.settings.values['store']['address'])
            yield connection
        stdout, stderr = StringIO(), StringIO()
        arguments = [command, *options]
        for repository in repositories:
            arguments.extend(('--repo', repository))
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                patch('mycel._database.store_connection', connected):
            status = run(arguments, handlers=HANDLERS, stdout=stdout, stderr=stderr)
        self.assertEqual(stderr.getvalue(), '')
        return status, json.loads(stdout.getvalue())



# Archived complete imports; restore needed names in their original scope, not at this file tail.
