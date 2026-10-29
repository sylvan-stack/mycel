# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Disposable-store proofs for path-scoped undocumented code and freshness."""
from io import StringIO
from dataclasses import replace
import json
import os
from unittest.mock import patch

from mycel._capture import _Capture
from mycel._cli import parse, run
from mycel._errors import MycelError
from mycel._undocumented import handle_undocumented, normalize_paths, undocumented_from_store
try:
    from . import test_overview_cli as scope_fixtures
except ImportError:
    import test_overview_cli as scope_fixtures


import unittest

from mycel._freshness import Deadline
from mycel._undocumented import undocumented_from_store

try:
    from . import test_document_links as link_fixtures
    from . import test_freshness_store as freshness_fixtures
    pass
except ImportError:
    import test_document_links as link_fixtures
    import test_freshness_store as freshness_fixtures


class UndocumentedUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class UndocumentedStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.links = link_fixtures.DocumentLinksStoreTests()
        self.links.store_fixture = self.store_fixture
        self.links.setUp()
        self.base, self.settings = self.links.base, self.links.settings

    def report(self, connection, **options):
        options.setdefault('no_fresh', True)
        return undocumented_from_store(connection, self.settings, ('fixture',),
                                       deadline=Deadline.after(30), **options)


class UndocumentedFreshnessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = freshness_fixtures.FreshnessStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
