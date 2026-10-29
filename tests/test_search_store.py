# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Real-store search replies with exact scope, coverage and dependency marks."""
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb
from mycel._capture import _Capture
from mycel._embedding_plan import PlanningError
from mycel._freshness import (ChunkRequirement, Deadline, DependencyFault, FreshnessResult,
                              FreshnessScope)
from mycel._locks import operation_guard
from mycel._search_store import _fault_records, _readable_file, search_from_store
from mycel._settings import _defaults, _freeze, load_settings
from mycel._source_refs import SourceAddress
from mycel._store import checked_store

import unittest

from mycel._freshness import Deadline
from mycel._search_store import search_from_store

try:
    from . import test_freshness_store as freshness_fixtures
    from . import test_ranking_store as ranking_fixtures
except ImportError:
    import test_freshness_store as freshness_fixtures
    import test_ranking_store as ranking_fixtures


class SearchFileTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class SearchStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = ranking_fixtures.RankingStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()

    def search(self, connection, query='needle', names=('fixture',), **options):
        options.setdefault('deadline', Deadline.after(30))
        options.setdefault('no_fresh', True)
        settings = options.pop('settings', self.base.settings())
        return search_from_store(connection, settings, query, names, **options)


class SearchFreshnessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = freshness_fixtures.FreshnessStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

    def search(self, connection, query='dependant unrelated', **options):
        options.setdefault('deadline', Deadline.after(30))
        return search_from_store(connection, self.base.settings, query, ('fixture',),
                                 only='docs', build=1, **options)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
