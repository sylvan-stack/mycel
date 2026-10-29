# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""The real-repository checker must reject misleading public activity evidence."""
from copy import deepcopy
from pathlib import Path
import pstats
import runpy

try:
    from . import test_ingest_activity as fixtures
except ImportError:
    import test_ingest_activity as fixtures


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
