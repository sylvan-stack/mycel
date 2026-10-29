# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Actual confirmation and history dispatch over configured disposable stores."""
from io import StringIO
import json
import unittest
from unittest.mock import patch

from mycel._cli import run

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class VerificationCommandTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def invoke(self, *arguments):
        output, diagnostic = StringIO(), StringIO()
        with patch('mycel._cli.load_settings', return_value=self.base.settings), \
                patch('mycel._build_identity.current_build', return_value=None):
            status = run(arguments, stdout=output, stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(), '')
        return status, json.loads(output.getvalue())
