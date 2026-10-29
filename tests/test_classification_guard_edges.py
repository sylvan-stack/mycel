# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Additional exact request and timer edges through disposable native stores."""

import unittest

try:
    from .test_classification_store import ClassificationStoreFixture
except ImportError:
    from test_classification_store import ClassificationStoreFixture


class ClassificationGuardEdgeStoreTests(ClassificationStoreFixture):
    check_kind = "store"



# Archived complete imports; restore needed names in their original scope, not at this file tail.
