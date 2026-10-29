# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Quiet-period fixtures; store producers prove the owned store claims."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from mycel._errors import MycelError

import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

from mycel._classification_eligibility import classification_eligibility, observe_input

NOW = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
FILE = 'fixture:@artifact/guide.md'


class ClassificationEligibilityTests(unittest.TestCase):
    def setUp(self):
        boundary = ExitStack()
        self.addCleanup(boundary.close)
        for target in ('time.sleep', 'subprocess.Popen', 'threading.Timer', 'threading.Thread.start'):
            boundary.enter_context(patch(target, side_effect=AssertionError(
                'Quiet-period observations must finish without sleeping or starting a worker.')))

    def file(self, version='first', *, observed=NOW, modified=None, previous=None, **kwargs):
        return observe_input(FILE, version, observed_at=observed,
                             modified_at=modified, previous=previous, **kwargs)

    def eligible(self, observation, *, at=NOW, seconds=300):
        return classification_eligibility((observation,), at=at, debounce_seconds=seconds)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
