# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""MYC-D37 permits only the prescribed settings data, without scope coupling."""
import ast
import re
import tempfile

from mycel._errors import MycelError
from mycel._scope import RepositoryLocations
from mycel._settings import load_settings

import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class NamedExceptionTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
