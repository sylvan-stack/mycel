# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Evidence-only dependency refreshes remain scoped applied mutations."""
import unittest

try:
    from . import test_located_dependency_application as fixtures
except ImportError:
    import test_located_dependency_application as fixtures


class DependencyRefreshCollectionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedDependencyApplicationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base


# Archived complete imports; restore needed names in their original scope, not at this file tail.
