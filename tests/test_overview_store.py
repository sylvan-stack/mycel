# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured disposable-store proofs for index-only code projections."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

from mycel._embed import retained_contexts
from mycel._embedding_store import EmbeddingStore
from mycel._errors import MycelError
from mycel._freshness import Deadline
from mycel._locks import atomic_transaction, operation_guard, snapshot_transaction
from mycel._overview_store import OverviewStore
from mycel._read_store import read_from_store
from mycel._retrieval_store import StoreCandidates
from mycel._search_store import search_from_store
from mycel._settings import load_settings
from mycel._summary_store import StoreSummaries

import json
import math
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._credentials import Secret
from mycel._embedding_plan import load_tokenizer
from mycel._store import TABLES
from mycel._voyage import HTTPResult, VoyageClient

try:
    from . import test_ingest as fixtures
    from .fixtures import EmbeddingStandIn
except ImportError:
    import test_ingest as fixtures
    from fixtures import EmbeddingStandIn


class OverviewStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.IngestStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def write(self, path, source):
        file = self.base.code / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source)
        return file

    def ingest(self, *options):
        status, reply = self.fixture.invoke('--repo', 'fixture', *options)
        self.assertEqual(status, 0, reply)
        return reply['repositories']['fixture']

    def report(self, *options, repository='fixture'):
        output, error = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(['overview', '--repo', repository, *options], stdout=output, stderr=error)
        self.assertEqual((status, error.getvalue()), (0, ''))
        return json.loads(output.getvalue())

    def overview_rows(self, connection):
        return connection.execute("SELECT c.id,v.id,v.source_bytes,l.metadata,l.xmin::text,v.xmin::text,g.state "
            "FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id "
            "JOIN public.mycel_locations l ON l.chunk_version=v.id "
            "JOIN public.mycel_generated_state g ON g.chunk_id=c.id WHERE c.kind='overview' "
            "ORDER BY l.metadata->>'name'").fetchall()

    def state(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    def embed(self, *, fixed_cosines=False):
        service = EmbeddingStandIn(load_tokenizer().counts)
        def transport(body, key, **kwargs):
            request = json.loads(body)
            response = service.request(request)
            if fixed_cosines:
                for row, text in zip(response['data'], request['input'], strict=True):
                    cosine = .9 if text.startswith('overview › ') else .8 if ' (function)\n' in text else .7
                    row['embedding'] = [cosine, math.sqrt(1-cosine*cosine)] + [0.] * 1022
            return HTTPResult(200, json.dumps(response).encode())
        def client(credentials, policy, **kwargs):
            return VoyageClient(credentials, policy, _transport=transport, **kwargs)
        with patch('mycel._embed.VoyageClient', side_effect=client), \
                patch('mycel._credentials.Credentials.require_embedding_key', return_value=Secret('fixture-key')):
            self.ingest('--embed')
        self.assertTrue(service.attempts)
        return service


# Archived complete imports; restore needed names in their original scope, not at this file tail.
