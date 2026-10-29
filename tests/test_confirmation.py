# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Confirmation's public writer through real, configured disposable stores."""
from hashlib import sha256
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._locks import operation_guard

import unittest

from mycel._verification import ConfirmationStore

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class ConfirmationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.ref = 'downstream:@artifact/answer.md#Answer'

    def confirm(self, connection, **options):
        return ConfirmationStore(connection).apply(self.base.settings, self.ref,
            settings_home=self.base.base, captured_at='2026-10-11T12:00:00Z', **options)

    def state(self, connection):
        state = self.fixture.state(connection)
        for table in ('mycel_relations', 'mycel_verifications', 'mycel_stale_reasons'):
            state[table] = connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
                'ORDER BY to_jsonb(t)::text').fetchall()
        return state


# Archived complete imports; restore needed names in their original scope, not at this file tail.
