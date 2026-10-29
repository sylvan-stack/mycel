# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""MYC-D37 permits only the prescribed settings data, without scope coupling."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class NamedExceptionTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
