# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Additional exact request and timer edges through disposable native stores."""
from datetime import timedelta
from hashlib import sha256
import json
import os

from psycopg.types.json import Jsonb
from mycel._classification_store import ClassificationStore
from mycel._relate import RelateStore
from mycel._resolver import SourceResolver
try:
    from .test_classification_store import ClassificationStoreFixture, AT, NOW
except ImportError:
    from test_classification_store import ClassificationStoreFixture, AT, NOW


import unittest

try:
    from .test_classification_store import ClassificationStoreFixture
except ImportError:
    from test_classification_store import ClassificationStoreFixture


class ClassificationGuardEdgeStoreTests(ClassificationStoreFixture):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
