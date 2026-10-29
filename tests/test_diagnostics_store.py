# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real-store info reporting retains every feature row and sequence."""
import unittest


class DiagnosticsStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
