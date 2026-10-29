# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Finite exact-read command syntax and Build capability description."""
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from mycel._cli import parse, run
from mycel._commands import COMMANDS, help_reply
from mycel._errors import MycelError


import unittest


class ReadCliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
