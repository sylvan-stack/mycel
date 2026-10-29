# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured real-store proofs for summary withdrawal and guarded renewal."""
import unittest

from mycel._cli import Invocation
from mycel._embedding_plan import document_place_line, plan_chunk
from mycel._summary_lifecycle import SummaryLifecycleStore, remove_summaries
from mycel._summary_publication import SummaryPublicationStore
from mycel._summary_store import StoreSummaries

try:
    from . import test_summary_publication as fixtures
except ImportError:
    import test_summary_publication as fixtures


class SummaryLifecycleStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.SummaryPublicationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def prepare(self, connection, invocation, *, parent=False):
        self.fixture.fixture.fixture.prepare(connection)
        publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
        leaf = self.fixture.staged(publisher, connection)
        stages = [leaf]
        if parent:
            stages.append(self.fixture.staged(publisher, connection, members=(leaf.member,),
                number='2/1', response=b'Parent output.'))
        self.fixture.publish(publisher, tuple(self.fixture.embedding(stage) for stage in stages))
        publisher.release()
        return self.summaries(connection)

    def summaries(self, connection):
        with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
            return snapshot._summaries

    def remove(self, connection, *, before=None):
        invocation = Invocation('summaries', repositories=('fixture',), arguments=('remove',), settings=self.base.settings)
        return remove_summaries(invocation, _store=(connection, None), _before_publish=before)

    def renewal(self, connection, invocation, summary, response=b'New complete response.'):
        generated = self.fixture.fixture
        capture = generated.capture(connection, 'fixture:@artifact/source.md#Source', 'fixture:@artifact/guide.md#Guide')
        lease = generated.lease(connection, invocation, capture, response)
        store = SummaryLifecycleStore(connection, self.base.settings, invocation, 'fixture')
        version = store.reserve_response(summary, lease)
        plan = plan_chunk('fixture', summary.member.chunk.identifier, str(version), response.decode(), kind='document',
            place_line=document_place_line('summaries', summary.member.place.name),
            dimensions=self.base.settings.values['embedding']['dimensions'])
        return store, lease, plan, tuple((0.25,) * plan.dimensions for _ in plan.parts)

    def state(self, connection):
        return {table: connection.execute(f'SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
            for table in ('mycel_chunks', 'mycel_chunk_versions', 'mycel_locations', 'mycel_dependencies', 'mycel_edges',
                          'mycel_generated_state', 'mycel_embedding_plans', 'mycel_embedding_parts', 'mycel_vectors',
                          'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_snapshots', 'mycel_manifests')}



# Archived complete imports; restore needed names in their original scope, not at this file tail.
