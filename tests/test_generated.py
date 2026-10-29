# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Successful publication, exact retained provenance and mechanical work proofs."""
import unittest
from uuid import uuid4

from mycel._generated import GeneratedPublicationStore
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import (
    GenerationEvidenceStore,
    GenerationMember,
    capture_generation,
)
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests
from mycel._summary_store import StoreSummaries, SummarySetMetadata

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


PROMPTS = SummaryPrompts(b'Instruction \r\n', b'Write complete summary: $sections', 'override')
METADATA = SummarySetMetadata('2026-10-12T12:00:00Z', 'mycel-summary-v1', None, {'numpy': '2.5.4', 'scipy': '1.18.1', 'scikit-learn': '1.9.1'})


class GeneratedStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def capture(self, connection, *addresses, owner='fixture', resolver=None):
        resolver = resolver or SourceResolver.from_store(connection, self.base.settings)
        members = tuple(resolver.resolve(address, purpose='read').selection.members[0] for address in addresses)
        sections = tuple(SummarySection(member, member.chunk.span[0] if member.chunk.span else 0) for member in members)
        request, = plan_summary_requests(sections, PROMPTS)
        return capture_generation(owner, tuple(GenerationMember(section.member, sent, position=section.position)
            for section, sent in zip(request.sections, request.sent_texts)), request=request.request,
            instruction=PROMPTS.instruction, task=PROMPTS.task, command=('fictional-writer', 'literal $(argument)'),
            prompt_profile=PROMPTS.profile)

    def lease(self, connection, invocation, capture, response=b' Complete summary \r\n\0end. '):
        store = GenerationEvidenceStore(connection)
        return store.retain_response(invocation, store.retain(invocation, capture), response)

    def publish(self, connection, invocation, lease, *, number='1/1', chunk_id=None, callback=None):
        publisher = GeneratedPublicationStore(connection)
        with self.fixture.guards(connection), atomic_transaction(connection):
            result = publisher.publish_in_transaction(self.base.settings, invocation, lease,
                chunk_id=chunk_id or uuid4(), place=SourceAddress(lease.repository, 'index', 'summaries', number),
                level=int(number.split('/')[0]), metadata=METADATA,
                guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
            if callback:
                callback(publisher, result)
            publisher.verify_in_transaction()
        return result

    def rows(self, connection):
        return connection.execute('SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,'
            'd.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d '
            'LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 '
            "WHERE d.kind='generated' ORDER BY d.id").fetchall()

    def state(self, connection):
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in (
            'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations', 'mycel_dependencies', 'mycel_edges',
            'mycel_generated_state', 'mycel_stale_reasons', 'mycel_evidence_owners', 'mycel_evidence_references',
            'mycel_snapshots', 'mycel_manifests', 'mycel_verifications', 'mycel_drifts', 'mycel_classification_work')}

    def work(self, connection, repository='fixture'):
        with StoreSummaries(connection, self.base.settings).snapshot((repository,)) as snapshot:
            return snapshot.status(), snapshot.regeneration_plan()

    def reasons(self, connection, result):
        return connection.execute('SELECT reason FROM public.mycel_stale_reasons WHERE chunk_version=%s '
            'ORDER BY reason::text', (result.chunk_version,)).fetchall()



# Archived complete imports; restore needed names in their original scope, not at this file tail.
