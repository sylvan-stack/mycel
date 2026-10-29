# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""The real-repository checker must reject misleading public activity evidence."""

import unittest

try:
    pass
except ImportError:
    pass


class RealActivityCheckStoreTests(unittest.TestCase):
    check_kind = "store"


class RealProviderIsolationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
