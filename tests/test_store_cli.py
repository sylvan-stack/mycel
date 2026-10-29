# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Command integration with stand-ins; these do not qualify SQL acceptance."""
from contextlib import contextmanager

from mycel._errors import MycelError
from mycel._store import InitResult, StoreInspection, STORE_FORMAT


import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings


class StoreCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "config.toml"
        self.address = "postgresql://fixture@localhost/private_fixture?sslmode=disable"
        self.path.write_text('[store]\naddress=' + json.dumps(self.address) + '\n[embedding]\ndimensions=256\n')
        self.snapshot = load_settings(path=self.path)

    def invoke(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with patch("mycel._cli.load_settings", return_value=self.snapshot):
            status = run(arguments, stdout=out, stderr=err)
        return status, json.loads(out.getvalue()), err.getvalue()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
