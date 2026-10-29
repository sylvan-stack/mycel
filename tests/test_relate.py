# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured exact relation creation, ownership, guards and edit acceptance."""
import unittest

from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._locks import atomic_transaction
from mycel._relate import RelateStore
from mycel._relations import RelationApplicationStore

try:
    from . import test_derive as fixtures
except ImportError:
    import test_derive as fixtures


class RelateCliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RelateStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DeriveStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.dependant, self.ref = self.fixture.dependant, self.fixture.ref
        self.guide = self.base.artifact / 'guide.md'

    def rows(self, connection):
        return connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash,r.xmin::text FROM public.mycel_relations r LEFT JOIN public.mycel_evidence_references e
            ON e.owner=r.baseline_owner AND e.ordinal=0 ORDER BY r.id""").fetchall()

    def state(self, connection):
        return self.fixture.state(connection), connection.execute('SELECT to_jsonb(r),xmin::text '
            'FROM public.mycel_relations r ORDER BY r.id').fetchall(), connection.execute('SELECT to_jsonb(r),xmin::text '
            'FROM public.mycel_stale_reasons r ORDER BY r.id').fetchall()

    def relate(self, connection, source=None, dependant=None, **kwargs):
        return RelateStore(connection).apply(self.base.settings, dependant or self.dependant, source or self.ref,
            build=0xDA, settings_home=self.base.base, captured_at='2026-10-10T10:00:00Z', **kwargs)

    def confirm_hook(self, connection):
        location, version = connection.execute("""SELECT l.file_location,l.chunk_version FROM public.mycel_locations l
            WHERE l.kind='disk' AND l.metadata->>'name'='Guide'""").fetchone()
        inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            result = RelationApplicationStore(connection).apply_in_transaction(self.base.settings, str(location), version,
                mode='confirm', captured_at='2026-10-10T11:00:00Z',
                reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None))
            inputs.verify()
        return result


# Archived complete imports; restore needed names in their original scope, not at this file tail.
