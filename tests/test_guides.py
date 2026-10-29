# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
import json
from pathlib import Path
import tempfile

from mycel._commands import help_reply
from mycel._errors import ErrorCode
from mycel._settings import load_settings

import unittest


class GuideTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
