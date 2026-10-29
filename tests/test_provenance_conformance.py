# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""One real-store public CLI flow across all five provenance capabilities.

Only provider transports/writers are service stand-ins. No production command
handler, canonical store boundary, relation or publication result is substituted.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import sys

from mycel._classification_payload import LABELS, ReviewerRequest
from mycel._classification_runner import ClassifyDependencies
from mycel._jev import JevResponse, route_response
from mycel._reviewer import ReviewerSuccess
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
try:
    from . import test_summary_build as summaries
except ImportError:
    import test_summary_build as summaries

import json
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run

try:
    from . import test_classify as classifiers
    pass
except ImportError:
    import test_classify as classifiers


class ProvenanceConformanceStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = classifiers.FiniteClassifyStoreTests()
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
        value = json.loads(output.getvalue())
        self.assertEqual(status, 0, value)
        return value

    def repository(self, reply, name):
        return next(row['result'] for row in reply['repositories'] if row['repository'] == name)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
