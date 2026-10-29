# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Direct offline relation reasons through the guarded mechanical detector."""
from unittest.mock import patch

from mycel._errors import MycelError
from mycel._evidence import CaptureLocation, EvidenceStore, capture_baseline
from mycel._locks import operation_guard
from mycel._relate import RelateStore
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._staleness import StaleEdge, StaleNode, StaleReason, compare_dependency, plan_staleness
try:
    from . import test_reconciliation as values
except ImportError:
    import test_reconciliation as values

import json
import unittest

from mycel._capture import capture_repository
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._store import checked_store

try:
    pass
    from . import test_retained_relations as fixtures
except ImportError:
    import test_retained_relations as fixtures


class RelationStalenessUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RelationStalenessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.helper = fixtures.RetainedRelationStoreTests()
        self.helper.store_fixture = self.store_fixture
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.fixture, self.base = self.helper.fixture, self.helper.base
        self.tail = self.base.base / 'tail'
        self.tail.mkdir()
        (self.tail / 'answer.md').write_bytes(b'---\nrole: authored\n'
            b'sources: ["downstream:@artifact/answer.md#Answer"]\n---\n# Tail\nLater unchanged claim.\n')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.tail]\nenabled=true\n'
                                    + 'artifact_root=' + json.dumps(str(self.tail)) + '\n')
        self.fixture.reload()

    def seed(self, connection):
        relation = self.helper.seed(connection)
        self.fixture.publish(connection, 'tail')
        self.assertEqual(self.reasons(connection), [])
        return relation

    def reasons(self, connection, owner=None):
        return connection.execute("""SELECT id,repository,chunk_version,dependency,reason,xmin::text
            FROM public.mycel_stale_reasons WHERE (%s::text IS NULL OR repository=%s)
            ORDER BY repository,reason::text""", (owner, owner)).fetchall()

    def publish(self, connection, *, reply_counts=None):
        # Exercise detector-owned foreign lock discovery without the producer's
        # broader guards. Relation creation/retention is already committed.
        with checked_store(connection):
            return LocatedCaptureStore(connection).apply(self.base.settings,
                capture_repository(self.base.settings, 'fixture'), reply_counts=reply_counts)

    def pins(self, connection):
        return connection.execute("""SELECT r.id,r.left_version,r.baseline_owner,e.manifest_hash
            FROM public.mycel_relations r JOIN public.mycel_evidence_references e
            ON e.owner=r.baseline_owner AND e.ordinal=0 WHERE r.repository='downstream' ORDER BY r.id""").fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
