# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real-store public summary publication across affected owner pass guards.

Writer/vector transports alone are local stand-ins. Canonical ingest, public
CLI handlers, generated publication, detection closure and peer locks are real.
"""
from contextlib import ExitStack
from io import StringIO
import json
import time
import unittest
from unittest.mock import patch

from mycel._cli import run
from mycel._locks import operation_guard
from mycel._settings import load_settings
from mycel._store import TABLES

try:
    from . import test_summary_build as summaries
except ImportError:
    import test_summary_build as summaries


class SummaryPublicationGuardsStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = summaries.SummaryBuildStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.downstream = self.base.base / 'downstream'
        self.disjoint = self.base.base / 'disjoint'
        self.downstream.mkdir(); self.disjoint.mkdir()
        (self.downstream / 'answer.md').write_text('---\nrole: authored\nsources: ["fixture:@artifact/note00.md#Part0"]\n---\n# Answer\nRetain its own natural source pin.\n')
        (self.disjoint / 'keep.md').write_text('# Keep\nIndependent untouched repository bytes.\n')
        self.base.config.write_text(self.base.config.read_text() +
            '\n[repos.downstream]\nenabled=true\nartifact_root=' + json.dumps(str(self.downstream)) +
            '\n[repos.disjoint]\nenabled=true\nartifact_root=' + json.dumps(str(self.disjoint)) + '\n')
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
        self.invoke('ingest', '--repo', 'downstream', '--repo', 'disjoint')
        with self.base.connect() as connection:
            self.assertGreater(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE repository='downstream'").fetchone()[0], 0)
            for repository in ('fixture', 'downstream', 'disjoint'):
                with operation_guard(connection, repository, 'pass'):
                    pass
        self.services = {'phase': None, 'probe': ('fixture', 'downstream')}
        self.observations = []
        self.last_service_at = None

    def invoke(self, *arguments, expected_status=0):
        output, diagnostic = StringIO(), StringIO()
        with patch('mycel._cli.load_settings', return_value=self.base.settings):
            status = run(arguments, stdout=output, stderr=diagnostic)
        value = json.loads(output.getvalue())
        self.assertEqual(diagnostic.getvalue(), '')
        self.assertEqual(status, expected_status, value)
        return value

    def service_callback(self, kind):
        def callback(_):
            # A different connection must acquire the actual pass locks while
            # either external-service interface is running.
            with self.base.connect() as peer, ExitStack() as held:
                for repository in self.services['probe']:
                    held.enter_context(operation_guard(peer, repository, 'pass'))
                self.observations.append((self.services['phase'], kind, self.services['probe']))
            self.last_service_at = time.monotonic()
        return callback

    def published_state(self, connection):
        names = ('mycel_chunks', 'mycel_chunk_versions', 'mycel_locations', 'mycel_generated_state',
                 'mycel_dependencies', 'mycel_edges', 'mycel_embedding_plans', 'mycel_embedding_parts',
                 'mycel_vectors', 'mycel_stale_reasons', 'mycel_drifts')
        return {name: connection.execute('SELECT to_jsonb(t),xmin::text FROM public.' + name +
            ' t ORDER BY to_jsonb(t)::text').fetchall() for name in names}

    def disjoint_state(self, connection):
        # Every canonical row carrying this repository, including its complete
        # evidence and state rows, retains both bytes and MVCC identity.
        return {table.name: connection.execute('SELECT to_jsonb(t),xmin::text FROM public.' + table.name +
            " t WHERE to_jsonb(t)->>'repository'='disjoint' ORDER BY to_jsonb(t)::text").fetchall()
            for table in TABLES}

    def busy_route(self, connection, action, phase):
        self.services.update(phase=phase, probe=('fixture',))
        self.last_service_at = None
        with self.base.connect() as peer, operation_guard(peer, 'downstream', 'pass'):
            before = self.published_state(connection)
            started = time.monotonic()
            reply = self.invoke('summaries', action, '--repo', 'fixture', expected_status=1)
            self.assertEqual(reply['error']['code'], 'busy')
            self.assertEqual(self.published_state(connection), before)
            self.assertLess(time.monotonic() - (self.last_service_at or started), 5)
        return reply

    def retry_with_disjoint_busy(self, connection, action, phase):
        self.services.update(phase=phase, probe=('fixture', 'downstream'))
        with self.base.connect() as peer, operation_guard(peer, 'disjoint', 'pass'):
            before = self.disjoint_state(connection)
            self.assertTrue(any(before.values()))
            reply = self.invoke('summaries', action, '--repo', 'fixture')
            self.assertEqual(self.disjoint_state(connection), before)
        return reply
