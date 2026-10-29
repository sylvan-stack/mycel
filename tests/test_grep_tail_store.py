# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Actual normal top-five grep tails over disposable PostgreSQL.

Only ordinary query preparation is a controlled automatic-check stand-in.
Candidate/ranking/reply/metadata producers remain real and every row/xmin and
sequence is checked. Metadata-only no-fresh discovery is deliberately allowed.
"""
import io

from psycopg import pq
from mycel._cli import Invocation
from mycel._freshness import Deadline
from mycel._grep import append_tail, render_tail, search_tail
from mycel._safeguards import InvocationPolicy
from mycel._search import QueryEmbedding
from mycel._search_store import search_from_store

import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._store import TABLES, checked_store

try:
    from . import test_ranking_store as ranking_fixtures
except ImportError:
    import test_ranking_store as ranking_fixtures


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *arguments, **options):
        self.statements.append(str(statement))
        return self.connection.execute(statement, *arguments, **options)


def _state(connection):
    result = {table.name: connection.execute(
        f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t ORDER BY to_jsonb(t)::text').fetchall()
        for table in TABLES}
    sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename").fetchall()
    result['sequences'] = {name: connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone()
                           for name, in sequences}
    return result


@contextmanager
def _forbid_mutations_and_paid_work():
    with ExitStack() as stack:
        for target in (
            'mycel._freshness_store.StoreFreshnessAdapter.refresh',
            'mycel._capture._Capture.capture',
            'mycel._ingest.ingest',
            'mycel._activity.MutationActivity.session',
            'mycel._classification_store.ClassificationStore.prepare',
            'mycel._classification_store.ClassificationStore.apply',
            'mycel._classification_store.ClassificationStore.reuse',
            'mycel._summary_writer.SummaryWriter.write',
            'mycel._credentials.Credentials.embedding_key',
            'mycel._credentials.Credentials.jev_key',
            'mycel._voyage._https_request',
        ):
            stack.enter_context(patch(target, side_effect=AssertionError(target)))
        yield


class GrepTailStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.ranking = ranking_fixtures.RankingStoreTests()
        self.ranking.store_fixture = self.store_fixture
        self.ranking.setUp()
        self.base = self.ranking.base
        self.settings = self.ranking.settings(shared=({'repo': 'handbook', 'paths': ['selected']},))
        for repository in self.settings.values['repos'].values():
            for key in ('code_root', 'artifact_root'):
                if repository.get(key):
                    Path(repository[key]).mkdir(parents=True, exist_ok=True)

    def seed(self, connection, **options):
        value = self.ranking.seed(connection, **options)
        repository = options.get('repository', 'fixture')
        root = options.get('root', 'code')
        path = options.get('path', 'code.py')
        folder = Path(self.settings.values['repos'][repository]['code_root' if root == 'code' else 'artifact_root'])
        physical = folder / path
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_text(options.get('source', 'body\n'))
        return value

    def populated(self, connection):
        code = [self.seed(connection, path=f'src/needle{index}.py', name=f'Needle{index}',
                         source=f'needle implementation {index}\n', cosine=.8-index*.02)
                for index in range(8)]
        document = self.seed(connection, path='guide.md', root='artifact', kind='document',
            name='Guide', source='---\nstatus: heartwood\n---\n# Guide\nneedle explains implementation\n', cosine=.99)
        shared = self.seed(connection, repository='handbook', path='checkout-guide.md', root='code',
            kind='document', name='Shared', source='# Shared\nneedle shared explanation\n', cosine=.98,
            aliases=(('artifact', 'selected/shared.md'),))
        self.ranking.cite(connection, document, 'fixture:@code/src/needle0.py#Needle0')
        self.ranking.cite(connection, document, 'fixture:@code/src/needle1.py#Needle1')
        self.ranking.cite(connection, shared, 'fixture:@code/src/needle0.py#Needle0')
        reason = {'kind': 'source_changed', 'source': {'repository': 'fixture', 'root': 'code',
            'path': 'governor.py', 'name': 'Governor', 'address': 'fixture:@code/governor.py#Governor'}}
        connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,NULL,%s)',
                           (uuid4(), 'fixture', document[2], Jsonb(reason)))
        self.seed(connection, repository='handbook', path='outside.md', root='artifact',
                  kind='document', name='Outside', source='# Outside\nneedle\n', cosine=1.0)
        self.seed(connection, repository='disabled', path='hidden.py', name='Hidden',
                  source='needle\n', cosine=1.0)
        self.seed(connection, path='branch.py', name='Branch', source='needle\n', cosine=1.0,
                  location_kind='branch')
        return code, document, shared

    @contextmanager
    def connected_invocation(self, connection):
        @contextmanager
        def store(invocation):
            self.assertEqual(invocation.command, 'grep')
            self.assertEqual(invocation.repositories, ('fixture',))
            self.assertEqual(invocation.settings.values, self.settings.values)
            with checked_store(connection) as inspection:
                yield connection, inspection
        with patch('mycel._cli.invocation_store', store):
            yield


# Archived complete imports; restore needed names in their original scope, not at this file tail.
