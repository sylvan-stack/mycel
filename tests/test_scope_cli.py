# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Scope and repository reports through the CLI's JSON boundary."""
from pathlib import Path
import tempfile

from mycel._cli import for_repositories, run
from mycel._errors import MycelError


import json
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run


class ScopeCliTests(unittest.TestCase):
    def invoke(self, config, arguments, *, handlers=None):
        output = StringIO()
        with patch.dict("os.environ", {"MYCEL_CONFIG": str(config)}):
            status = run(arguments, handlers=handlers, stdout=output, stderr=StringIO())
        return status, json.loads(output.getvalue())


# Archived complete imports; restore needed names in their original scope, not at this file tail.
