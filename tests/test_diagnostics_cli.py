# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Diagnostics stay available and repository refusals retain every member."""
from contextlib import contextmanager
from pathlib import Path
import tempfile

from mycel._cli import for_repositories, run
from mycel._build_identity import current_build
from mycel._errors import MycelError
from mycel._settings import load_settings


import json
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run


class DiagnosticsCliTests(unittest.TestCase):
    def invoke(self, snapshot, arguments, **kwargs):
        output, diagnostics = StringIO(), StringIO()
        with patch('mycel._cli.load_settings', return_value=snapshot):
            status = run(arguments, stdout=output, stderr=diagnostics, **kwargs)
        self.assertEqual(diagnostics.getvalue(), '')
        return status, json.loads(output.getvalue())


# Archived complete imports; restore needed names in their original scope, not at this file tail.
