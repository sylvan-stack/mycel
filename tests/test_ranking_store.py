# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured current-disk graph and deterministic ranking acceptance."""
import math
import unittest
from dataclasses import replace
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._declared_refs import _raw
from mycel._settings import _defaults, _freeze

try:
    from . import test_retrieval_store as fixtures
    pass
except ImportError:
    import test_retrieval_store as fixtures


class RankingStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.RetrievalStoreTests()
        self.base.store_fixture = self.store_fixture
        self.query = (1.0,) + (0.0,) * 1023

    def settings(self, **kwargs):
        settings = self.base.settings(**kwargs)
        defaults = _defaults()[1]
        return replace(settings, values=_freeze({**settings.values, "repos": {
            name: {**defaults, **value} for name, value in settings.values["repos"].items()}}))

    def seed(self, connection, *, cosine=.8, embedded=True, **kwargs):
        result = self.base.seed(connection, **kwargs)
        if embedded:
            self.base.plan(connection, result[1], result[2], kwargs.get('source', 'body\n'),
                repository=kwargs.get('repository', 'fixture'),
                vectors=((cosine, math.sqrt(max(0, 1-cosine*cosine))),))
        return result

    def cite(self, connection, document, raw, *, kind='declared', anchor=None,
             location=None, syntax=None, pinned=None):
        version = document[2]
        if location is None:
            location = connection.execute('SELECT file_location FROM public.mycel_locations '
                                          'WHERE chunk_version=%s', (version,)).fetchone()[0]
        owned = connection.execute('SELECT kind,location FROM public.mycel_file_locations '
                                   'WHERE id=%s', (location,)).fetchone()
        state = {'declarationLocation': {'file': str(location), 'kind': owned[0], 'location': owned[1]},
                 'rawRef': _raw(raw)}
        if anchor:
            state['anchor'] = str(anchor)
        if syntax:
            state['syntaxFault'] = syntax
        identifier = uuid4()
        owner = connection.execute('SELECT repository FROM public.mycel_chunks WHERE id=%s',
                                   (document[1],)).fetchone()[0]
        connection.execute('INSERT INTO public.mycel_dependencies VALUES '
            '(%s,%s,%s,%s,%s,%s,%s,NULL)',
            (identifier, owner, version, raw, raw, kind, Jsonb(state)))
        if pinned is not None:
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (identifier, pinned))
        return identifier

    @staticmethod
    def entries(reply):
        return {entry.chunk.identifier: entry for entry in reply.results}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
