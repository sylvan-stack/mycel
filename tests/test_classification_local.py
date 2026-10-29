# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Local classification bookkeeping shares the caller's finite allowance."""
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
