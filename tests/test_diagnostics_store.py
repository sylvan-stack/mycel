# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Real-store info reporting retains every feature row and sequence."""
from io import StringIO
import json

from mycel._cli import run
from mycel._store import STORE_FORMAT
from test_refs import store_state

import unittest


class DiagnosticsStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
