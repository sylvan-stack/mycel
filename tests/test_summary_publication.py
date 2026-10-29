# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Private summary staging and complete guarded tree replacement proofs."""
from dataclasses import replace
from unittest.mock import patch

from mycel._evidence import EvidenceError
from mycel._generated import generated_capture
from mycel._locks import atomic_transaction, invocation_guard, operation_guard
from mycel._resolver import SourceResolver
from mycel._summary_publication import SummaryPublicationStore, StagedSummaryEmbedding
from mycel._summary_store import StoreSummaries

import unittest

from mycel._embedding_plan import document_place_line, plan_chunk
from mycel._locks import atomic_transaction
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import GenerationMember, capture_generation
from mycel._summary_publication import StagedSummaryEmbedding
from mycel._summary_request import SummarySection, plan_summary_requests

try:
    from . import test_generated as fixtures
except ImportError:
    import test_generated as fixtures


class SummaryPublicationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.GeneratedStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def staged(self, publisher, connection, *, members=None, number='1/1', response=b' Exact complete summary\r\n\0end. '):
        if members is None:
            capture = self.fixture.capture(connection, 'fixture:@artifact/source.md#Source',
                                           'fixture:@artifact/guide.md#Guide')
        else:
            sections = tuple(SummarySection(member, number) for number, member in enumerate(members))
            request, = plan_summary_requests(sections, fixtures.PROMPTS)
            capture = capture_generation('fixture', tuple(GenerationMember(section.member, sent,
                position=section.position) for section, sent in zip(request.sections, request.sent_texts)),
                request=request.request, instruction=fixtures.PROMPTS.instruction, task=fixtures.PROMPTS.task,
                command=('fictional-writer',), prompt_profile=fixtures.PROMPTS.profile)
        lease = publisher.retain_request(capture)
        return publisher.stage_response(lease, response, place=SourceAddress('fixture', 'index', 'summaries', number),
                                        level=int(number.split('/')[0]))

    def embedding(self, staged):
        chunk = staged.member.chunk
        plan = plan_chunk('fixture', chunk.identifier, str(chunk.version), chunk.source.decode(), kind='document',
            place_line=document_place_line(staged.member.place.path, staged.member.place.name),
            dimensions=self.base.settings.values['embedding']['dimensions'])
        vector = (0.125,) * plan.dimensions
        return StagedSummaryEmbedding(staged, plan, tuple(vector for _ in plan.parts))

    def publish(self, publisher, values, *, callback=None, metadata=fixtures.METADATA):
        with self.fixture.fixture.guards(publisher.connection), atomic_transaction(publisher.connection):
            result = publisher.publish_in_transaction(values, metadata,
                guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
            if callback:
                callback()
            publisher.verify_in_transaction()
        return result

    def current(self, connection):
        return connection.execute("SELECT c.id,v.id,v.source_bytes FROM public.mycel_chunks c "
            "JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id "
            "WHERE c.repository='fixture' AND c.kind='summary' AND l.kind='index' ORDER BY c.id").fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
