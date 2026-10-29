# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Current-store proofs for the complete, query-independent document relation."""
from uuid import uuid4

from psycopg.types.json import Jsonb
from mycel._declared_refs import DeclaredRefStore
from mycel._search_store import search_from_store
try:
    from . import test_declared_refs as declared_fixtures
except ImportError:
    import test_declared_refs as declared_fixtures


import unittest

from mycel._freshness import Deadline
from mycel._read_store import read_from_store

try:
    pass
    from . import test_ranking_store as ranking_fixtures
    from . import test_read_store as read_fixtures
except ImportError:
    import test_ranking_store as ranking_fixtures
    import test_read_store as read_fixtures


class DocumentLinksStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.ranking = ranking_fixtures.RankingStoreTests()
        self.ranking.store_fixture = self.store_fixture
        self.ranking.setUp()
        self.base = self.ranking.base
        self.settings = self.ranking.settings()
        self.reads = read_fixtures.ReadStoreTests()
        self.reads.store_fixture = self.store_fixture
        self.reads.setUp()
        self.reads.settings = self.settings

    def read(self, connection, identifier):
        return read_from_store(connection, self.settings, identifier=str(identifier),
                               deadline=Deadline.after(30), no_fresh=True)

    def seed(self, connection, **options):
        return self.base.seed(connection, **options)

    def cite(self, connection, dependant, source, **options):
        return self.ranking.cite(connection, dependant, source, **options)

    @staticmethod
    def signatures(reply):
        return {(link['section']['address'], link['direction'], link['edge'])
                for link in reply['documents']}

    @staticmethod
    def make_historical(connection, file_id):
        connection.execute("UPDATE public.mycel_locations SET kind='branch',location='old' "
            'WHERE file_location IN (SELECT fl.id FROM public.mycel_file_locations fl '
            'JOIN public.mycel_file_versions fv ON fv.id=fl.file_version WHERE fv.file_id=%s)', (file_id,))
        connection.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old' "
            'WHERE file_version IN (SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', (file_id,))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
