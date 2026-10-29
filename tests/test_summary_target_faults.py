# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured store proofs of generated-target faults and mutation refusal."""
import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._store import TABLES

try:
    from . import test_summary_build as builds
except ImportError:
    import test_summary_build as builds


class SummaryTargetFaultStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = builds.SummaryBuildStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def invoke(self, command, *arguments):
        output, diagnostics = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run([command, *arguments], stdout=output, stderr=diagnostics)
        self.assertEqual(diagnostics.getvalue(), '')
        return status, json.loads(output.getvalue())

    def state(self, connection):
        return {table.name: connection.execute(
            f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t ORDER BY to_jsonb(t)::text'
        ).fetchall() for table in TABLES}

    def disk_refs(self):
        status, reply = self.invoke('refs', '--repo', 'fixture', '--unresolved')
        self.assertEqual(status, 0, reply)
        return [row for row in reply['repositories'][0]['result']['refs']
                if row['location']['kind'] == 'disk']

    def ingest(self, *options):
        status, reply = self.invoke('ingest', '--repo', 'fixture', *options)
        self.assertEqual(status, 0, reply)
        return reply

    def prohibit_generation(self, stack):
        for target in ('mycel._summary_writer.SummaryWriter', 'mycel._embed.VoyageClient',
                       'mycel._credentials.Credentials.require_embedding_key',
                       'mycel._credentials.Credentials.jev_key'):
            stack.enter_context(patch(target, side_effect=AssertionError('fault operation called a provider')))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
