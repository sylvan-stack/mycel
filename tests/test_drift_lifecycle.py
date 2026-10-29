# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Exact, offline semantic-work lifecycle through configured disposable stores.

Classification replies are deterministic local stand-ins. These checks qualify
the work/evidence sink; provider execution and its protocols have other owners.
"""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch

from psycopg.types.json import Jsonb
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._locks import operation_guard
from mycel._relate import RelateStore
from mycel._resolver import SourceResolver
from mycel._verification import ConfirmationStore
try:
    from . import test_generated as generated
except ImportError:
    import test_generated as generated

import json
import unittest

from mycel._drift_store import DriftStore
from mycel._store import TABLES

try:
    from . import test_dependency_source_refresh as fixtures
    pass
except ImportError:
    import test_dependency_source_refresh as fixtures


AT = '2026-10-12T10:00:00Z'


class _FailAfterWrite:
    """Fail a real store operation after its first Drift update, inside the txn."""
    def __init__(self, connection):
        self.connection = connection
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        result = self.connection.execute(statement, *args, **kwargs)
        if not self.failed and 'UPDATE public.mycel_drifts' in statement:
            self.failed = True
            raise RuntimeError('Fictional drift publication failure.')
        return result


class DriftLifecycleStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.ref = 'downstream:@artifact/answer.md#Answer'
        self.extra = []
        for number in (2, 3):
            path = self.base.artifact / ('source' + str(number) + '.md')
            path.write_bytes(('# Source' + str(number) + '\nOriginal source ' + str(number) + '.\n').encode())
            self.extra.append(path)
        self.addresses = ('fixture:@artifact/source.md#Source',
                          'fixture:@artifact/source2.md#Source2',
                          'fixture:@artifact/source3.md#Source3')
        self.originals = {path: path.read_bytes() for path in (self.fixture.source, *self.extra)}
        self.write_answer(*self.addresses)
        self.base.commit()

    def write_answer(self, *sources, text='Unchanged dependant.', **metadata):
        values = {'role': 'authored', 'sources': list(sources), **metadata}
        head = '\n'.join(key + ': ' + json.dumps(value) for key, value in values.items())
        self.fixture.answer.write_bytes(('---\n' + head + '\n---\n# Answer\n' + text + '\n').encode())

    def prepare(self, connection):
        self.fixture.prepare(connection)
        return self.sync(connection)

    def change(self, connection, *numbers):
        paths = (self.fixture.source, *self.extra)
        for number in numbers or (1, 2, 3):
            path = paths[number - 1]
            path.write_bytes(path.read_bytes().replace(b'Original', b'Changed'))
        self.fixture.publish(connection)
        return self.sync(connection)

    def sync(self, connection):
        return DriftStore(connection).reconcile(self.base.settings, 'downstream', at=AT)

    def report(self, connection, **options):
        return DriftStore(connection).list('downstream', **options)

    def one(self, connection, **options):
        drifts = self.report(connection, **options)['drifts']
        self.assertEqual(len(drifts), 1, drifts)
        return drifts[0]

    def reason(self, drift, number=1, kind=None):
        values = [reason for reason in drift['sources']
                  if reason['source']['address'] == self.addresses[number - 1]
                  and (kind is None or reason['kind'] == kind)]
        self.assertEqual(len(values), 1, drift)
        return values[0]

    def record(self, connection, drift, reason, **options):
        return DriftStore(connection).record_classification(self.base.settings, drift['id'],
            reason['id'], reason['pairHash'], at=AT, **options)

    def support(self, connection, drift, reason):
        result = self.record(connection, drift, reason, judgement='still_supported')
        self.assertTrue(result['applied'], result)
        self.assertFalse(result['obsolete'], result)
        return result['drift']

    def immutable(self, connection):
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in
            ('mycel_dependencies', 'mycel_relations', 'mycel_edges', 'mycel_verifications')}

    def state(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    def stale(self, connection):
        return connection.execute("SELECT id,chunk_version,dependency,reason FROM public.mycel_stale_reasons "
            "WHERE repository='downstream' ORDER BY id").fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
