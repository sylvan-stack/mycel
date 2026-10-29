# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Local classification bookkeeping shares the caller's finite allowance."""
from contextlib import contextmanager, ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mycel._classification_local import reconcile_freshness, reconcile_local
from mycel._cli import Invocation, classification_store, parse
from mycel._deadline import deadline_guard
from mycel._errors import MycelError
from mycel._freshness import Deadline, FreshnessResult, FreshnessScope, RepositoryStatus
try:
    from .test_classification_store import ClassificationStoreFixture, AT
except ImportError:
    from test_classification_store import ClassificationStoreFixture, AT

import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    from .test_classification_store import ClassificationStoreFixture
except ImportError:
    from test_classification_store import ClassificationStoreFixture


def work(*sources):
    return {'id': 'drift', 'chunk': {'address': 'fixture:@artifact/guide.md#Guide'},
            'sources': [{'id': source, 'dependency': source, 'active': True} for source in sources]}


class LocalClassificationTests(unittest.TestCase):
    def no_models(self):
        stack = ExitStack()
        for target in ('mycel._jev.JevClient', 'mycel._reviewer.ReviewerClient',
                       'mycel._credentials.Credentials._keychain', 'subprocess.Popen'):
            stack.enter_context(patch(target, side_effect=AssertionError('Local reconciliation launched work.')))
        return stack


class ClassificationCliBoundaryTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class LocalClassificationStoreTests(ClassificationStoreFixture):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
