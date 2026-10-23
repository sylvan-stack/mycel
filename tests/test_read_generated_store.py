"""Exact reads of real generated summaries and their recursive source graph."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch
from uuid import uuid4

from mycel._coverage import proves
from mycel._freshness import Deadline
from mycel._generated import GeneratedPublicationStore
from mycel._locks import atomic_transaction, invocation_guard, operation_guard
from mycel._read_store import read_from_store
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._store import checked_store
from mycel._summary_evidence import GenerationEvidenceStore, GenerationMember, capture_generation
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

    @proves('MYC-11.6', kind='store')
    def test_upper_summary_checks_generated_members_and_transitive_external_sources_without_regeneration(self):
        with self.fixture.base.connect() as connection:
            self.fixture.prepare(connection)
            lower = self.publish(connection, 'fixture:@artifact/driver.md#Driver', '1/1',
                                 b'Complete lower summary.\n')
            upper_text = 'Complete upper summary 雪.\n'
            upper = self.publish(connection, lower.place.address, '2/1', upper_text.encode())
            pins = self.pins(connection)
            outside = self.fixture.owned(connection, 'outside')
            self.fixture.glossary.write_bytes(b'# Glossary\nA substantive changed governing definition.\n')
            captures = []
            actual = fixtures._Capture.capture

            def record(capture):
                captures.append(capture.repository.name)
                return actual(capture)

            with patch.object(fixtures._Capture, 'capture', record), \
                    patch('mycel._summary_writer.SummaryWriter.write', side_effect=AssertionError('writer')), \
                    patch('mycel._embed.embed', side_effect=AssertionError('embedding')), \
                    patch.object(GeneratedPublicationStore, 'publish_in_transaction',
                                 side_effect=AssertionError('regeneration')):
                reply = read_from_store(connection, self.fixture.settings, upper.place.address,
                    deadline=Deadline.after(30), build=1)
            self.assertEqual(reply['id'], upper.chunk_id)
            self.assertEqual(reply['text'], upper_text)
            self.assertEqual(reply['origin'], 'summary')
            self.assertEqual(reply['root'], 'index')
            self.assertNotIn('file', reply)
            self.assertTrue(reply['stale'], reply)
            self.assertTrue(reply['freshness']['finished'], reply)
            self.assertTrue(reply['dependencyCheck']['complete'], reply)
            checks = {row['repository']: row for row in reply['freshness']['repositories']}
            self.assertTrue({'fixture', 'contract', 'glossary'}.issubset(captures))
            self.assertFalse({'outside', 'shared', 'disabled'}.intersection(captures))
            self.assertTrue({'fixture', 'contract', 'glossary'}.issubset(checks))
            self.assertTrue(all(checks[name]['state'] == 'done'
                                for name in ('fixture', 'contract', 'glossary')))
            self.assertGreater(checks['glossary']['ingested'], 0)
            self.assertEqual(reply['freshness']['ingested'], sum(row['ingested'] for row in checks.values()))
            self.assertTrue(any(reason['source']['repository'] == 'glossary'
                and any(place['address'] == lower.place.address for place in reason.get('via', ()))
                for reason in reply['staleReasons']), reply['staleReasons'])
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(self.fixture.owned(connection, 'outside'), outside)
            for publication, text in ((lower, b'Complete lower summary.\n'), (upper, upper_text.encode())):
                self.assertEqual(bytes(connection.execute('SELECT source_bytes FROM public.mycel_chunk_versions '
                    'WHERE id=%s', (publication.chunk_version,)).fetchone()[0]), text)

