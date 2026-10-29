# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Writer-triggered activity retention against the configured disposable store."""

import unittest
from contextlib import nullcontext
from dataclasses import replace
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel import _activity as activity
from mycel import _locks as locks
from mycel._activity_retention import ActivityRetentionStore
from mycel._settings import _freeze, load_settings
from mycel._store import TABLES, checked_store

try:
    pass
except ImportError:
    pass


class _History:
    """Retained rows are fixture data; behavior uses real public writer paths."""

    def __init__(self, fixture):
        self.fixture = fixture
        settings = load_settings(path=fixture.settings_file)
        names = ('fixture', 'other', 'empty', 'disabled')
        self.settings = replace(settings, values=_freeze({**settings.values, 'repos': {
            name: {'enabled': name != 'disabled', 'code_subdirs': [],
                   'code_root': str(fixture.root / 'work' / name),
                   'artifact_root': str(fixture.root / 'documents' / name)} for name in names},
            'organizations': {'team': {'root': str(fixture.root / 'work'),
                                      'artifact_root': str(fixture.root / 'team-documents')}}}))

    def connect(self):
        return self.fixture.backend.connection(self.fixture.database)

    @staticmethod
    def repositories(connection, *names):
        for name in names:
            connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') "
                               'ON CONFLICT DO NOTHING', (name,))

    @staticmethod
    def seed(connection, repository, count, *, kind=None, at='2001-01-01T00:00:00Z',
             step='0 seconds', open_entry=False, invocation=None):
        if invocation is None:
            with locks.invocation_guard(connection) as retained:
                pass
        else:
            retained = invocation
        kind = kind or ('init' if repository is None else 'ingest')
        return [row[0] for row in connection.execute("""INSERT INTO public.mycel_activity
            (repository,invocation,index_generation,kind,trigger,build,started_at,ended_at,outcome,counts)
            SELECT %s,%s,%s,%s,'command',31,
                %s::timestamptz+n*%s::interval,
                CASE WHEN %s THEN NULL ELSE %s::timestamptz+n*%s::interval END,
                %s,jsonb_build_object('ordinal',n)
            FROM generate_series(1,%s) AS n RETURNING id""",
            (repository, retained.id, retained.index_generation, kind, at, step,
             open_entry, at, step, None if open_entry else 'done', count)).fetchall()]

    @staticmethod
    def ids(connection, repository):
        return [row[0] for row in connection.execute('SELECT id FROM public.mycel_activity '
            'WHERE repository IS NOT DISTINCT FROM %s ORDER BY started_at DESC,id DESC',
            (repository,)).fetchall()]

    @staticmethod
    def details(connection, identifier, *, bundle='retained-classification-bundle'):
        connection.execute("INSERT INTO public.mycel_activity_files VALUES (%s,0,'code','same.py','disk','changed')",
                           (identifier,))
        connection.execute("INSERT INTO public.mycel_identity_decisions VALUES "
            "(%s,0,'artifact','same.py','topic',%s,'renamed','Before','After')", (identifier, uuid4()))
        connection.execute('INSERT INTO public.mycel_activity_classifications VALUES (%s,0,%s,%s,%s)',
            (identifier, bundle, 'fixture:@code/same.py#After', 'needs_review'))

    @staticmethod
    def state(connection, *, tables=TABLES, sequences=False):
        result = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                  'ORDER BY to_jsonb(t)::text').fetchall() for table in tables}
        if sequences:
            names = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
                                       "WHERE schemaname='public' ORDER BY sequencename").fetchall()
            result['sequences'] = {name: connection.execute(
                'SELECT last_value,is_called FROM public."' + name + '"').fetchone() for name, in names}
        return result

    @staticmethod
    def mutation(repository, counts=None, **details):
        def write(connection):
            value = {'applied': 1} if counts is None else counts
            if repository is not None:
                connection.execute('UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository=%s',
                                   (Jsonb(value), repository))
            return activity.AppliedMutation(True, value, **details)
        return write


class ActivityRetentionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.history = _History(self.store_fixture)

    def prune(self, connection, repository):
        guard = locks.mutation_guard(connection, repository) if repository is not None else nullcontext()
        with checked_store(connection), guard, locks.atomic_transaction(connection):
            retained = ActivityRetentionStore(connection)
            retained.guard_in_transaction(repository)
            return retained.prune_in_transaction(repository)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
