"""Private summary staging and complete guarded tree replacement proofs."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._embedding_plan import document_place_line, plan_chunk
from mycel._evidence import EvidenceError
from mycel._generated import generated_capture
from mycel._locks import atomic_transaction, invocation_guard, operation_guard
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import GenerationMember, capture_generation
from mycel._summary_publication import SummaryPublicationStore, StagedSummaryEmbedding
from mycel._summary_request import SummarySection, plan_summary_requests
from mycel._summary_store import StoreSummaries

try:
    from . import test_generated as fixtures
except ImportError:
    import test_generated as fixtures


class SummaryPublicationStoreTests(unittest.TestCase):
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

    @proves('MYC-8.13', 'MYC-8.14', 'MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_private_levels_remain_invisible_then_publish_exact_reserved_versions_and_owned_pins_together(self):
        with self.base.connect() as connection, self.base.connect() as reader:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                leaf = self.staged(publisher, connection)
                upper = self.staged(publisher, connection, members=(leaf.member,), number='2/1', response=b'Upper whole text.')
                self.assertEqual(self.current(reader), [])
                self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_chunks WHERE id=ANY(%s::uuid[])',
                    ([leaf.member.chunk.identifier, upper.member.chunk.identifier],)).fetchone(), (0,))
                self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=ANY(%s)',
                    ([leaf.member.chunk.version, upper.member.chunk.version],)).fetchone(), (0,))
                self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
                resolver = SourceResolver.from_store(reader, self.base.settings)
                self.assertEqual(resolver.resolve(leaf.member.place.address, purpose='read').state, 'unresolved')
                values = (self.embedding(leaf), self.embedding(upper))
                def before_commit():
                    self.assertEqual(self.current(reader), [])
                    self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
                results, deleted = self.publish(publisher, values, callback=before_commit)
                self.assertEqual(deleted, 0)
                self.assertEqual([item.chunk_version for item in results], [leaf.member.chunk.version, upper.member.chunk.version])
                self.assertEqual(len(self.current(reader)), 2)
                for row in self.fixture.rows(connection):
                    capture, member = generated_capture(connection, row)
                    self.assertIn(row[2], {leaf.member.chunk.version, upper.member.chunk.version})
                    if row[2] == upper.member.chunk.version:
                        self.assertEqual(member['version'], leaf.member.chunk.version)
                        self.assertEqual(member['source']['hash'], leaf.member.chunk.snapshot_hash)
                publisher.release()
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                    "WHERE kind='summary_generation'").fetchone(), (0,))
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                    "WHERE kind='generated'").fetchone(), (2,))
                with StoreSummaries(reader, self.base.settings).snapshot(('fixture',)) as snapshot:
                    self.assertEqual(snapshot.status()['levels'], [{'level': 1, 'summaries': 1, 'stale': 0},
                                                                 {'level': 2, 'summaries': 1, 'stale': 0}])
                    self.assertEqual(snapshot.status()['builtAt'], fixtures.METADATA.built_at)

    @proves('MYC-8.15', 'MYC-8.26', kind='store')
    def test_empty_replacement_retains_set_metadata_and_removes_old_vectors_pins_and_permanent_owners_atomically(self):
        with self.base.connect() as connection, self.base.connect() as reader:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                first = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                leaf = self.staged(first, connection)
                self.publish(first, (self.embedding(leaf),))
                first.release()
                old = self.current(reader)
                metadata = replace(fixtures.METADATA, built_at='2026-10-14T14:00:00Z')
                second = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                def before_commit():
                    self.assertEqual(self.current(reader), old)
                results, deleted = self.publish(second, (), callback=before_commit, metadata=metadata)
                self.assertEqual((results, deleted), ((), 1))
                self.assertEqual(self.current(reader), [])
                self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
                self.assertEqual(reader.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='generated'").fetchone(), (0,))
                self.assertEqual(reader.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='generated'").fetchone(), (0,))
                with StoreSummaries(reader, self.base.settings).snapshot(('fixture',)) as snapshot:
                    self.assertEqual(snapshot.status()['builtAt'], metadata.built_at)
                    self.assertEqual(snapshot.status()['levels'], [])
                    self.assertEqual(snapshot.status()['numericalVersions'], dict(metadata.numerical_versions))

    @proves('MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_changed_disk_inputs_and_late_audit_failure_keep_complete_old_set_and_discard_private_evidence(self):
        with self.base.connect() as connection:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                first = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                self.publish(first, (self.embedding(self.staged(first, connection)),))
                first.release()
                old = self.current(connection)
                for failure in ('disk', 'audit', 'vector'):
                    with self.subTest(failure=failure):
                        publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                        leaf = self.staged(publisher, connection, response=b'Replacement summary.')
                        value = self.embedding(leaf)
                        source = self.fixture.fixture.source
                        original = source.read_bytes()
                        if failure == 'disk':
                            source.write_bytes(b'# Source\nChanged during calls.\n')
                        def callback():
                            if failure == 'audit':
                                raise RuntimeError('late audit failure')
                            if failure == 'vector':
                                connection.execute('DELETE FROM public.mycel_vectors')
                        with self.assertRaises((EvidenceError, RuntimeError)):
                            self.publish(publisher, (value,), callback=callback)
                        source.write_bytes(original)
                        publisher.discard()
                        self.assertEqual(self.current(connection), old)
                        self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                            "WHERE kind='summary_generation'").fetchone(), (0,))

    @proves('MYC-8.26', 'MYC-8.29', kind='store')
    def test_private_higher_request_requires_exact_same_invocation_response_and_never_accepts_foreign_stage(self):
        with self.base.connect() as connection:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                leaf = self.staged(publisher, connection)
                foreign = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                with self.assertRaises(EvidenceError):
                    self.staged(foreign, connection, members=(leaf.member,), number='2/1')
                connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (leaf.lease.owner_id,))
                with self.assertRaises(EvidenceError):
                    self.staged(publisher, connection, members=(leaf.member,), number='2/1')
                self.assertEqual(self.current(connection), [])
                publisher.discard()

    @proves('MYC-8.13', 'MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_identical_requests_have_distinct_actual_command_leases_and_publish_distinct_response_evidence(self):
        with self.base.connect() as connection:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                capture = self.fixture.capture(connection, 'fixture:@artifact/source.md#Source')
                leases = (publisher.retain_request(capture), publisher.retain_request(capture))
                self.assertNotEqual(leases[0].owner_id, leases[1].owner_id)
                self.assertEqual(leases[0].request_manifest, leases[1].request_manifest)
                stages = tuple(publisher.stage_response(lease, response,
                    place=SourceAddress('fixture', 'index', 'summaries', f'1/{number}'), level=1)
                    for number, (lease, response) in enumerate(zip(leases, (b'First produced response.', b'Second response.')), 1))
                self.publish(publisher, tuple(self.embedding(stage) for stage in stages))
                responses = {generated_capture(connection, row)[0].manifest.payload['response']['hash']
                             for row in self.fixture.rows(connection)}
                self.assertEqual(responses, {stage.member.chunk.snapshot_hash for stage in stages})
                publisher.release()

    @proves('MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_ingest_pass_contention_cannot_prevent_exact_private_lease_cleanup_or_replace_success_with_busy(self):
        with self.base.connect() as connection, self.base.connect() as ingester:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                staged = self.staged(publisher, connection)
                self.publish(publisher, (self.embedding(staged),))
                published = self.current(connection)
                with operation_guard(ingester, 'fixture', 'pass'):
                    publisher.release()
                    self.assertEqual(self.current(connection), published)
                    self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                        "WHERE kind='summary_generation'").fetchone(), (0,))
                interrupted = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                self.staged(interrupted, connection, response=b'Unpublished response.')
                with operation_guard(ingester, 'fixture', 'pass'):
                    interrupted.discard()
                self.assertEqual(self.current(connection), published)
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                    "WHERE kind='summary_generation'").fetchone(), (0,))

    @proves('MYC-8.15', 'MYC-8.26', 'MYC-8.29', kind='store')
    def test_private_owner_transfer_rolls_back_with_publication_and_confirmed_commit_cleanup_needs_no_sql(self):
        with self.base.connect() as connection:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                staged = self.staged(publisher, connection)
                with self.assertRaises(RuntimeError):
                    with self.fixture.fixture.guards(connection), atomic_transaction(connection):
                        publisher.publish_in_transaction((self.embedding(staged),), fixtures.METADATA,
                            guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                        publisher.verify_in_transaction()
                        publisher.release_in_transaction()
                        raise RuntimeError('outer commit cancelled')
                self.assertEqual(self.current(connection), [])
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                    "WHERE kind='summary_generation'").fetchone(), (1,))
                publisher.discard()
                second = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                staged = self.staged(second, connection)
                with self.fixture.fixture.guards(connection), atomic_transaction(connection):
                    second.publish_in_transaction((self.embedding(staged),), fixtures.METADATA,
                        guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                    second.verify_in_transaction()
                    second.release_in_transaction()
                second.confirm_release()
                with patch('mycel._summary_publication.checked_store', side_effect=AssertionError('committed cleanup touched SQL')):
                    second.release()
                self.assertEqual(len(self.current(connection)), 1)
