"""Successful publication, exact retained provenance and mechanical work proofs."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._evidence import EvidenceError
from mycel._generated import GeneratedPublicationStore, generated_capture
from mycel._locks import atomic_transaction, invocation_guard, operation_guard
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import GenerationEvidenceStore, GenerationMember, capture_generation
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests
from mycel._summary_store import StoreSummaries, SummarySetMetadata
from mycel._verification import ConfirmationStore

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

    @proves('MYC-7.21', 'MYC-7.22', 'MYC-7.29', kind='store')
    def test_success_publishes_complete_response_and_separate_generated_pins_with_permanent_exact_evidence(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            capture = self.capture(connection, 'fixture:@artifact/source.md#Source',
                                   'fixture:@artifact/guide.md#Guide')
            response = ' Complete answer 雪🙂\r\n\0end. '.encode()
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, capture, response)
                self.assertEqual(self.rows(connection), [])
                result = self.publish(connection, invocation, lease)
                rows = self.rows(connection)
                self.assertEqual(len(rows), 2)
                for row in rows:
                    retained, member = generated_capture(connection, row)
                    self.assertEqual(retained, capture.with_response(response))
                    self.assertEqual(row[7], result.evidence_owner)
                    self.assertEqual(row[3], member['place']['address'])
                self.assertEqual(connection.execute('SELECT source_bytes FROM public.mycel_chunk_versions WHERE id=%s',
                    (result.chunk_version,)).fetchone()[0], response)
                # Same ends can coexist under every ownership kind. Ordinary
                # assertion/declaration writers never manufacture generated pins.
                for kind in ('declared', 'asserted'):
                    identifier = uuid4()
                    connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
                        (identifier, 'fixture', result.chunk_version, rows[0][3], rows[0][4], kind, Jsonb({})))
                    connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)',
                        (identifier, capture.manifest.payload['members'][0]['version']))
                self.assertEqual(connection.execute('SELECT kind FROM public.mycel_dependencies WHERE dependant_version=%s '
                    'ORDER BY kind', (result.chunk_version,)).fetchall(), [('asserted',), ('declared',), ('generated',), ('generated',)])
            # A permanent owner has no invocation liveness FK and keeps every
            # byte independently when the temporary request lease is removed.
            connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (lease.owner_id,))
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            for row in self.rows(connection):
                retained, _ = generated_capture(connection, row)
                self.assertEqual(retained, capture.with_response(response))
            self.assertEqual(connection.execute('SELECT invocation FROM public.mycel_evidence_owners WHERE id=%s',
                (result.evidence_owner,)).fetchone(), (None,))

    @proves('MYC-7.21', 'MYC-7.22', kind='store')
    def test_file_and_command_cannot_create_generated_edges_and_generated_confirm_is_refused(self):
        self.fixture.answer.write_bytes(b'---\ngenerated: true\n---\n# Answer\nExternal generated file.\n')
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.assertEqual(self.rows(connection), [])
            capture = self.capture(connection, 'fixture:@artifact/source.md#Source')
            with invocation_guard(connection) as invocation:
                result = self.publish(connection, invocation, self.lease(connection, invocation, capture))
            before = self.state(connection)
            for address in (result.place.address, 'downstream:@artifact/answer.md#Answer'):
                with self.assertRaises(MycelError) as error:
                    ConfirmationStore(connection).apply(self.base.settings, address)
                self.assertEqual(error.exception.code, 'refused')
            from mycel._derive import DeriveStore
            from mycel._relate import RelateStore
            for store in (DeriveStore(connection), RelateStore(connection)):
                with self.assertRaises(MycelError) as error:
                    store.apply(self.base.settings, result.place.address, 'fixture:@artifact/source.md#Source')
                self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.22', 'MYC-7.29', kind='store')
    def test_unfinished_cancelled_inactive_forged_and_failed_publications_leave_no_live_text_or_pins(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            capture = self.capture(connection, 'fixture:@artifact/source.md#Source')
            with invocation_guard(connection) as invocation:
                unfinished = GenerationEvidenceStore(connection).retain(invocation, capture)
                before = self.state(connection)
                with self.assertRaises(EvidenceError):
                    self.publish(connection, invocation, unfinished)
                self.assertEqual(self.state(connection), before)
                lease = self.lease(connection, invocation, capture)
                before = self.state(connection)
                for forged in (replace(lease, owner_id=uuid4()), replace(lease, request_manifest='0' * 64)):
                    with self.assertRaises(EvidenceError):
                        self.publish(connection, invocation, forged)
                    self.assertEqual(self.state(connection), before)
                def cancelled(publisher, result):
                    raise KeyboardInterrupt()
                with self.assertRaises(KeyboardInterrupt):
                    self.publish(connection, invocation, lease, callback=cancelled)
                self.assertEqual(self.state(connection), before)
                def failed(publisher, result):
                    connection.execute('SELECT 1/0')
                with self.assertRaises(MycelError):
                    self.publish(connection, invocation, lease, callback=failed)
                self.assertEqual(self.state(connection), before)
            with self.assertRaises(EvidenceError):
                self.publish(connection, invocation, lease)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.22', 'MYC-7.29', kind='store')
    def test_changed_disk_or_ingested_member_and_late_settings_or_source_changes_roll_back_publication(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            capture = self.capture(connection, 'fixture:@artifact/source.md#Source')
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, capture)
                before = self.state(connection)
                self.fixture.source.write_bytes(b'# Source\nChanged unpublished text.\n')
                with self.assertRaises(EvidenceError) as error:
                    self.publish(connection, invocation, lease)
                self.assertEqual(error.exception.status, 'inputs_changed')
                self.assertEqual(self.state(connection), before)
                self.fixture.source.write_bytes(self.fixture.source_bytes)
                def late_source(publisher, result):
                    self.fixture.source.write_bytes(b'# Source\nChanged during audit.\n')
                with self.assertRaises((EvidenceError, MycelError)):
                    self.publish(connection, invocation, lease, callback=late_source)
                self.assertEqual(self.state(connection), before)
                self.fixture.source.write_bytes(self.fixture.source_bytes)
                config = self.base.config.read_bytes()
                def late_settings(publisher, result):
                    self.base.config.write_bytes(config + b'\n[summaries]\nat_once=2\n')
                with self.assertRaises(MycelError):
                    self.publish(connection, invocation, lease, callback=late_settings)
                self.assertEqual(self.state(connection), before)
                self.base.config.write_bytes(config)
                self.fixture.source.write_bytes(b'# Source\nChanged indexed text.\n')
                self.fixture.publish(connection)
                before = self.state(connection)
                with self.assertRaises(EvidenceError) as error:
                    self.publish(connection, invocation, lease)
                self.assertEqual(error.exception.status, 'inputs_changed')
                self.assertEqual(self.state(connection), before)

    @proves('MYC-7.22', 'MYC-7.29', kind='store')
    def test_corrupt_request_response_or_final_owner_and_member_rows_cannot_publish_partial_text(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            capture = self.capture(connection, 'fixture:@artifact/source.md#Source')
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, capture)
                descriptor = capture.manifest.payload['request']
                connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 1, 'bytes': 0, 'encoding': 'utf-8'}), 'fixture', descriptor['hash']))
                before = self.state(connection)
                with self.assertRaises(EvidenceError):
                    self.publish(connection, invocation, lease)
                self.assertEqual(self.state(connection), before)
                connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 1, 'bytes': descriptor['bytes'], 'encoding': 'utf-8'}), 'fixture', descriptor['hash']))
                before = self.state(connection)
                def corrupt_owner(publisher, result):
                    connection.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s',
                        ('wrong owner identity', result.evidence_owner))
                with self.assertRaises((EvidenceError, MycelError)):
                    self.publish(connection, invocation, lease, callback=corrupt_owner)
                self.assertEqual(self.state(connection), before)
                def missing_member(publisher, result):
                    connection.execute('DELETE FROM public.mycel_dependencies WHERE dependant_version=%s',
                        (result.chunk_version,))
                with self.assertRaises((EvidenceError, MycelError)):
                    self.publish(connection, invocation, lease, callback=missing_member)
                self.assertEqual(self.state(connection), before)

    @proves('MYC-7.23', 'MYC-7.29', kind='store')
    def test_mechanical_generated_levels_propagate_and_report_regeneration_with_zero_semantic_work(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'downstream:@artifact/answer.md#Answer', owner='downstream')))
                upper = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, lower.place.address, owner='downstream'), b'Higher exact summary.'), number='2/1')
            before = self.rows(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged governing source.\n')
            with patch('mycel._summaries.generate_summary_requests', side_effect=AssertionError('writer forbidden')), \
                    patch('mycel._voyage._https_request', side_effect=AssertionError('provider forbidden')):
                self.fixture.publish(connection)
                status, plan = self.work(connection, 'downstream')
            self.assertEqual([row[0]['kind'] for row in self.reasons(connection, lower)], ['upstream_stale'])
            reason, = [row[0] for row in self.reasons(connection, upper)]
            self.assertEqual(reason['kind'], 'upstream_stale')
            self.assertEqual([place['address'] for place in reason['via']],
                ['downstream:@artifact/answer.md#Answer', lower.place.address])
            self.assertEqual([level['stale'] for level in status['levels']], [1, 1])
            self.assertEqual([place['address'] for place in plan['write']], [lower.place.address, upper.place.address])
            self.assertEqual(plan['work'][1]['conditionalOn'][0]['address'], lower.place.address)
            self.assertEqual(self.rows(connection), before)
            self.assertEqual(connection.execute('SELECT (SELECT count(*) FROM public.mycel_drifts '
                'WHERE dependant_version=ANY(%s)),(SELECT count(*) FROM public.mycel_classification_work w '
                'JOIN public.mycel_dependencies d ON d.id=w.dependency WHERE d.kind=\'generated\')',
                ([lower.chunk_version, upper.chunk_version],)).fetchone(), (0, 0))
            # Confirmation answers the authored node's direct reason only and
            # recomposes every generated descendant in the same transaction.
            ConfirmationStore(connection).apply(self.base.settings, 'downstream:@artifact/answer.md#Answer')
            self.assertEqual(self.reasons(connection, lower), [])
            self.assertEqual(self.reasons(connection, upper), [])
            self.assertEqual(self.rows(connection), before)

    @proves('MYC-7.23', 'MYC-7.29', kind='store')
    def test_direct_generated_body_comparison_removal_rejoin_and_summary_of_summaries_are_coherent(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')))
                upper = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, lower.place.address), b'Parent.'), number='2/1')
            pins = self.rows(connection)
            self.fixture.source.write_bytes(b'# Renamed source\nOriginal governing source.   \n')
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower), [])
            self.assertEqual([level['stale'] for level in self.work(connection)[0]['levels']], [0, 0])
            self.fixture.source.write_bytes(b'# Renamed source\nSubstantive body change.\n')
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower)[0][0]['kind'], 'source_changed')
            self.assertEqual(self.reasons(connection, upper)[0][0]['kind'], 'upstream_stale')
            self.assertEqual([level['stale'] for level in self.work(connection)[0]['levels']], [1, 1])
            # Restore the original logical address before last-location deletion;
            # a deliberately renamed declaration's retained anchor is separate.
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.fixture.publish(connection)
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower)[0][0]['kind'], 'source_removed')
            self.assertEqual(self.work(connection)[1]['remove'][0]['address'], lower.place.address)
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower), [])
            self.assertEqual(self.reasons(connection, upper), [])
            self.assertEqual(self.rows(connection), pins)

    @proves('MYC-7.22', 'MYC-7.23', 'MYC-7.29', kind='store')
    def test_stale_generated_member_blocks_new_parent_and_corrupt_pin_keeps_existing_marks_pending(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')))
                parent_lease = self.lease(connection, invocation, self.capture(connection, lower.place.address), b'Parent.')
                self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
                self.fixture.publish(connection)
                before = self.state(connection)
                with self.assertRaises(EvidenceError) as error:
                    self.publish(connection, invocation, parent_lease, number='2/1')
                self.assertEqual(error.exception.status, 'stale_member')
                self.assertEqual(self.state(connection), before)
            marks = self.reasons(connection, lower)
            row, = self.rows(connection)
            connection.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s',
                ('broken permanent identity', row[7]))
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            result = self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower), marks)
            self.assertIn('snapshot_corrupt', json.dumps(dict(result.counts)))
            self.assertEqual(self.work(connection)[0]['levels'][0]['stale'], 1)

    @proves('MYC-7.21', 'MYC-7.22', 'MYC-7.29', kind='store')
    def test_invalid_places_cross_owner_requests_and_final_output_location_changes_are_atomic_refusals(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, self.capture(connection, 'fixture:@artifact/source.md#Source'))
                before = self.state(connection)
                for number in ('1/0', '1/notinteger', '6/1', '01/1', '1/01'):
                    with self.assertRaises(EvidenceError):
                        self.publish(connection, invocation, lease, number=number)
                    self.assertEqual(self.state(connection), before)
                foreign = self.lease(connection, invocation,
                    self.capture(connection, 'downstream:@artifact/answer.md#Answer'))
                before = self.state(connection)
                with self.assertRaises(EvidenceError) as error:
                    self.publish(connection, invocation, foreign)
                self.assertEqual(error.exception.status, 'invalid_input')
                self.assertEqual(self.state(connection), before)
                for mutation in (
                        lambda result: connection.execute('DELETE FROM public.mycel_locations WHERE chunk_version=%s',
                            (result.chunk_version,)),
                        lambda result: connection.execute('UPDATE public.mycel_locations SET metadata=%s WHERE chunk_version=%s',
                            (Jsonb({'path': 'summaries', 'name': '1/2', 'level': 1}), result.chunk_version)),
                        lambda result: connection.execute('DELETE FROM public.mycel_edges WHERE dependency IN '
                            '(SELECT id FROM public.mycel_dependencies WHERE dependant_version=%s)', (result.chunk_version,))):
                    with self.assertRaises((EvidenceError, MycelError)):
                        self.publish(connection, invocation, lease, callback=lambda publisher, result: mutation(result))
                    self.assertEqual(self.state(connection), before)

    @proves('MYC-7.23', 'MYC-7.29', kind='store')
    def test_final_secondary_request_evidence_change_rolls_back_detection_and_source_publication(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lease = self.lease(connection, invocation, self.capture(connection, 'fixture:@artifact/source.md#Source'))
                self.publish(connection, invocation, lease)
            self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
            before = self.state(connection)
            from mycel._staleness import MechanicalStalenessStore
            verify = MechanicalStalenessStore.verify_in_transaction
            def changed_request(detector, settings, guards):
                connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 99}), 'fixture', lease.request_manifest))
                verify(detector, settings, guards)
            with patch.object(MechanicalStalenessStore, 'verify_in_transaction', changed_request), self.assertRaises(MycelError):
                self.fixture.publish(connection)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.22', 'MYC-7.29', kind='store')
    def test_same_response_regeneration_repins_only_generated_rows_and_releases_unreferenced_previous_owner(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                first = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')))
                sibling = uuid4()
                connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
                    (sibling, 'fixture', first.chunk_version, 'literal', 'literal', 'asserted', Jsonb({})))
                self.fixture.source.write_bytes(b'# Source\nUpdated source.\n')
                self.fixture.publish(connection)
                second = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')), chunk_id=__import__('uuid').UUID(first.chunk_id))
                self.assertEqual(second.chunk_version, first.chunk_version)
                self.assertNotEqual(second.evidence_owner, first.evidence_owner)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
                    (first.evidence_owner,)).fetchone(), (0,))
                self.assertEqual(connection.execute('SELECT kind FROM public.mycel_dependencies WHERE id=%s',
                    (sibling,)).fetchone(), ('asserted',))
                self.assertEqual(self.reasons(connection, second), [])

    @proves('MYC-7.23', 'MYC-7.29', kind='store')
    def test_busy_generated_owner_is_pending_without_partial_marks_and_retry_propagates(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'downstream:@artifact/answer.md#Answer', owner='downstream')))
            self.fixture.source.write_bytes(b'# Source\nChanged governing source.\n')
            from mycel._capture import capture_repository
            from mycel._located_dependencies import LocatedDependencyProducer
            from mycel._located_reconciliation import LocatedCaptureStore
            from mycel._store import checked_store
            from mycel._staleness import MechanicalStalenessStore, detection_guards
            # The source producer cannot acquire its explicit dependency owner
            # while busy; mechanical observation also preserves generated marks.
            with self.base.connect() as other, operation_guard(other, 'downstream', 'pass'):
                with checked_store(connection), operation_guard(connection, 'fixture', 'pass'):
                    with detection_guards(connection, self.base.settings, 'fixture') as guards:
                        with atomic_transaction(connection):
                            detector = MechanicalStalenessStore(connection)
                            _, _, pending = detector.apply_in_transaction(self.base.settings, 'fixture', guards)
                            detector.verify_in_transaction(self.base.settings, guards)
                self.assertTrue(any(item['chunk']['address'] == lower.place.address for item in pending))
                self.assertEqual(self.reasons(connection, lower), [])
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower)[0][0]['kind'], 'upstream_stale')

    @proves('MYC-7.22', 'MYC-7.23', 'MYC-7.29', kind='store')
    def test_one_transaction_composes_multiple_outputs_and_regeneration_repropagates_same_or_changed_response(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                first_lease = self.lease(connection, invocation, self.capture(connection, 'fixture:@artifact/source.md#Source'))
                second_lease = self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/guide.md#Guide'), b'Independent sibling.')
                publisher = GeneratedPublicationStore(connection)
                with self.fixture.guards(connection), atomic_transaction(connection):
                    def publish(lease, number):
                        return publisher.publish_in_transaction(self.base.settings, invocation, lease,
                            chunk_id=uuid4(), place=SourceAddress('fixture', 'index', 'summaries', number),
                            level=int(number.split('/')[0]), metadata=METADATA,
                            guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                    first = publish(first_lease, '1/1')
                    second = publish(second_lease, '1/2')
                    prospective = SourceResolver.from_transaction(connection, self.base.settings,
                        guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                    capture = self.capture(connection, first.place.address, second.place.address, resolver=prospective)
                    evidence = GenerationEvidenceStore(connection)
                    upper_lease = evidence.retain_in_transaction(invocation, capture)
                    upper_lease = evidence.retain_response_in_transaction(invocation, upper_lease, b'Upper.')
                    upper = publish(upper_lease, '2/1')
                    publisher.verify_in_transaction()
                self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
                self.fixture.publish(connection)
                self.assertEqual(self.reasons(connection, upper)[0][0]['kind'], 'upstream_stale')
                from uuid import UUID
                renewed = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')), chunk_id=UUID(first.chunk_id))
                self.assertEqual(self.reasons(connection, renewed), [])
                self.assertEqual(self.reasons(connection, upper), [])
                with invocation_guard(connection) as next_invocation:
                    changed = self.publish(connection, next_invocation, self.lease(connection, next_invocation,
                        self.capture(connection, 'fixture:@artifact/source.md#Source'), b'Different produced summary.'),
                        chunk_id=UUID(first.chunk_id))
                self.assertNotEqual(changed.chunk_version, first.chunk_version)
                self.assertEqual(self.reasons(connection, upper)[0][0]['kind'], 'source_changed')
                self.assertEqual(self.reasons(connection, upper)[0][0]['edge'], 'generated')

    @proves('MYC-7.22', 'MYC-7.29', kind='store')
    def test_corrupt_or_missing_lower_generated_state_blocks_parent_without_a_stored_stale_mark(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower_lease = self.lease(connection, invocation, self.capture(connection, 'fixture:@artifact/source.md#Source'))
                lower = self.publish(connection, invocation, lower_lease)
                parent = self.lease(connection, invocation, self.capture(connection, lower.place.address), b'Parent.')
                self.assertEqual(self.reasons(connection, lower), [])
                connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 99}), 'fixture', lower_lease.request_manifest))
                before = self.state(connection)
                with self.assertRaises(EvidenceError) as error:
                    self.publish(connection, invocation, parent, number='2/1')
                self.assertEqual(error.exception.status, 'stale_member')
                self.assertEqual(self.state(connection), before)
                connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 1, 'protocol': 'mycel-summary-generation-v1'}), 'fixture', lower_lease.request_manifest))
                connection.execute('DELETE FROM public.mycel_generated_state WHERE chunk_id=%s', (lower.chunk_id,))
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    self.publish(connection, invocation, parent, number='2/1')
                self.assertEqual(error.exception.code, 'store_format')
                self.assertEqual(self.state(connection), before)

    @proves('MYC-7.23', 'MYC-7.29', kind='store')
    def test_generated_state_membership_corruption_refuses_reports_and_final_state_change_rolls_back_detection(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with invocation_guard(connection) as invocation:
                lower = self.publish(connection, invocation, self.lease(connection, invocation,
                    self.capture(connection, 'fixture:@artifact/source.md#Source')))
            state = connection.execute('SELECT state FROM public.mycel_generated_state WHERE chunk_id=%s',
                (lower.chunk_id,)).fetchone()[0]
            bad = {**state, 'members': []}
            connection.execute('UPDATE public.mycel_generated_state SET state=%s WHERE chunk_id=%s',
                (Jsonb(bad), lower.chunk_id))
            with self.assertRaises(MycelError) as error:
                self.work(connection)
            self.assertEqual(error.exception.code, 'store_format')
            with invocation_guard(connection) as invocation:
                parent = self.lease(connection, invocation, self.capture(connection, lower.place.address), b'Parent.')
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    self.publish(connection, invocation, parent, number='2/1')
                self.assertEqual(error.exception.code, 'store_format')
                self.assertEqual(self.state(connection), before)
            connection.execute('UPDATE public.mycel_generated_state SET state=%s WHERE chunk_id=%s',
                (Jsonb(state), lower.chunk_id))
            self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
            before = self.state(connection)
            from mycel._staleness import MechanicalStalenessStore
            verify = MechanicalStalenessStore.verify_in_transaction
            def late_state(detector, settings, guards):
                connection.execute('UPDATE public.mycel_generated_state SET state=%s WHERE chunk_id=%s',
                    (Jsonb(bad), lower.chunk_id))
                verify(detector, settings, guards)
            with patch.object(MechanicalStalenessStore, 'verify_in_transaction', late_state), self.assertRaises(MycelError):
                self.fixture.publish(connection)
            self.assertEqual(self.state(connection), before)
            self.fixture.publish(connection)
            marks = self.reasons(connection, lower)
            connection.execute('UPDATE public.mycel_generated_state SET state=%s WHERE chunk_id=%s',
                (Jsonb({**state, 'level': 2}), lower.chunk_id))
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            result = self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection, lower), marks)
            self.assertIn('snapshot_corrupt', json.dumps(dict(result.counts)))
            with self.assertRaises(MycelError) as error:
                self.work(connection)
            self.assertEqual(error.exception.code, 'store_format')


if __name__ == '__main__':
    unittest.main()
