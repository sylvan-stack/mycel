# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Pure alias matching without weakening individual syntax faults."""
from dataclasses import replace
from itertools import permutations

from mycel._declared_refs import _raw
from mycel._dependency_application import RetainedDependencyResolver, _anchor, _match_declarations
from mycel._evidence import CaptureLocation, capture_baseline
from mycel._relations import _RelationRecord, _relation_syntax_faults
from mycel._resolver import SourceResolver
from mycel._source_refs import DeclaredSource, SourceAddress, parse_source_address
try:
    from . import test_reconciliation as fixtures
except ImportError:
    import test_reconciliation as fixtures

import unittest

try:
    pass
except ImportError:
    pass


class RelationOccurrenceAliasTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
