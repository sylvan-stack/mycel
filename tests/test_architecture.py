# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
import ast
import json
import tomllib

from mycel._commands import help_reply

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
