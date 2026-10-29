# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Report-only overview argument and scope boundaries."""
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

from mycel._cli import parse, run
from mycel._errors import MycelError
from mycel._overview import handle_overview, overview_repository


import json
import tempfile
import unittest
from pathlib import Path

from mycel._settings import load_settings


class OverviewCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config.toml"
        self.config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
            '[organizations.team]\nroot=' + json.dumps(str(self.root / "team")) + '\n'
            '[repos.example]\nenabled=true\ncode_root=' +
            json.dumps(str(self.root / "team" / "example")) + '\n'
            '[repos.disabled]\nenabled=false\ncode_root=' +
            json.dumps(str(self.root / "disabled")) + '\n')
        self.settings = load_settings(path=self.config, home=self.root)
        self.settings.require_valid()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
