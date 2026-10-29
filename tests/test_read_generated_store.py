# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Exact reads of real generated summaries and their recursive source graph."""
import unittest
from contextlib import ExitStack
from uuid import uuid4

from mycel._generated import GeneratedPublicationStore
from mycel._locks import atomic_transaction, invocation_guard, operation_guard
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._store import checked_store
from mycel._summary_evidence import (
    GenerationEvidenceStore,
    GenerationMember,
    capture_generation,
)
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests
from mycel._summary_store import SummarySetMetadata

try:
    from . import test_freshness_store as fixtures
except ImportError:
    import test_freshness_store as fixtures


class GeneratedReadStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.FreshnessStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def publish(self, connection, member_address, number, response, *, owner='fixture'):
        settings = self.fixture.settings
        resolver = SourceResolver.from_store(connection, settings)
        member = resolver.resolve(member_address, purpose='read').selection.members[0]
        section = SummarySection(member, member.chunk.span[0] if member.chunk.span else 0)
        prompts = SummaryPrompts(b'Keep the complete governing content.\n',
                                b'Write a summary of $sections', 'fixture')
        request, = plan_summary_requests((section,), prompts)
        capture = capture_generation(owner, (GenerationMember(member, request.sent_texts[0],
            position=section.position),), request=request.request, instruction=prompts.instruction,
            task=prompts.task, command=('fictional-offline-writer',), prompt_profile=prompts.profile)
        with invocation_guard(connection) as invocation:
            evidence = GenerationEvidenceStore(connection)
            lease = evidence.retain_response(invocation, evidence.retain(invocation, capture), response)
            with ExitStack() as stack:
                stack.enter_context(checked_store(connection))
                guards = tuple(sorted(settings.values['repos']))
                for guarded_owner in guards:
                    stack.enter_context(operation_guard(connection, guarded_owner, 'pass'))
                with atomic_transaction(connection):
                    publisher = GeneratedPublicationStore(connection)
                    result = publisher.publish_in_transaction(settings, invocation, lease, chunk_id=uuid4(),
                        place=SourceAddress(owner, 'index', 'summaries', number),
                        level=int(number.split('/')[0]), guarded_repositories=guards,
                        metadata=SummarySetMetadata('2026-10-13T12:00:00Z', 'mycel-summary-v1', None,
                            {'numpy': '2.5.4', 'scipy': '1.18.1', 'scikit-learn': '1.9.1'}))
                    publisher.verify_in_transaction()
                return result

    @staticmethod
    def pins(connection):
        return connection.execute('SELECT d.id,d.dependant_version,d.baseline_owner,r.manifest_hash '
            'FROM public.mycel_dependencies d LEFT JOIN public.mycel_evidence_references r '
            'ON r.owner=d.baseline_owner AND r.ordinal=0 ORDER BY d.id').fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
