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

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_complete_removal_atomically_drops_set_metadata_vectors_pins_and_only_unowned_evidence
#     def test_complete_removal_atomically_drops_set_metadata_vectors_pins_and_only_unowned_evidence(self):
#         with self.base.connect() as connection, self.base.connect() as reader:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 summaries = self.prepare(connection, invocation, parent=True)
#                 response_hash = summaries[0].member.chunk.snapshot_hash
#                 independent = uuid4()
#                 connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
#                     (independent, 'fixture', 'manual', str(independent)))
#                 connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
#                     (independent, 'fixture', response_hash))
#                 downstream = connection.execute("SELECT id,baseline_owner,state FROM public.mycel_dependencies "
#                     "WHERE repository='downstream' ORDER BY id").fetchall()
#                 old = self.fixture.current(reader)
#                 store = SummaryLifecycleStore(connection, self.base.settings, invocation, 'fixture')
#                 with self.fixture.fixture.fixture.guards(connection), atomic_transaction(connection):
#                     removed, changed = store.remove_in_transaction(guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
#                     self.assertEqual((removed, changed), (2, True))
#                     self.assertEqual(self.fixture.current(reader), old)
#                     store.verify_in_transaction()
#                 self.assertEqual(self.fixture.current(reader), [])
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks WHERE id=%s',
#                     (summary_set_identifier('fixture'),)).fetchone(), (0,))
#                 self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='generated'").fetchone(), (0,))
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
#                 self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='generated'").fetchone(), (0,))
#                 self.assertEqual(connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
#                     ('fixture', response_hash)).fetchone(), (summaries[0].member.chunk.source,))
#                 self.assertEqual(connection.execute('SELECT id FROM public.mycel_evidence_owners WHERE id=%s',
#                     (independent,)).fetchone(), (independent,))
#                 self.assertEqual(connection.execute("SELECT id,baseline_owner,state FROM public.mycel_dependencies "
#                     "WHERE repository='downstream' ORDER BY id").fetchall(), downstream)
#                 with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
#                     self.assertNotIn('builtAt', snapshot.status())
#                     self.assertEqual(snapshot.status()['levels'], [])
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_complete_removal_atomically_drops_set_metadata_vectors_pins_and_only_unowned_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_removal_without_command_or_model_credentials_records_one_done_audit_and_empty_removal_is_normal_noop
#     def test_removal_without_command_or_model_credentials_records_one_done_audit_and_empty_removal_is_normal_noop(self):
#         with self.base.connect() as connection:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 self.prepare(connection, invocation)
#             self.assertFalse(self.base.settings.values['summaries'].get('command'))
#             with patch('mycel._summary_lifecycle.current_build', return_value=31), \
#                     patch('mycel._summary_writer.SummaryWriter', side_effect=AssertionError('writer started')), \
#                     patch('mycel._summary_build.Credentials', side_effect=AssertionError('model credentials requested')), \
#                     patch('mycel._summary_build.capture_repository', side_effect=AssertionError('disk captured')):
#                 result = self.remove(connection)
#                 self.assertEqual((result.status, result.value), (0, {'repository': 'fixture', 'removed': 1}))
#                 rows = connection.execute("SELECT outcome,counts FROM public.mycel_activity WHERE kind='summaries_remove'").fetchall()
#                 self.assertEqual(rows, [('done', result.value)])
#                 no_op = self.remove(connection)
#                 self.assertEqual((no_op.status, no_op.value), (0, {'repository': 'fixture', 'removed': 0}))
#                 self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='summaries_remove'").fetchone(), (1,))
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_removal_without_command_or_model_credentials_records_one_done_audit_and_empty_removal_is_normal_noop

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_summary_and_pass_contention_and_interruption_refuse_without_partial_removal
#     def test_summary_and_pass_contention_and_interruption_refuse_without_partial_removal(self):
#         with self.base.connect() as connection, self.base.connect() as other:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 self.prepare(connection, invocation)
#             original = self.state(connection)
#             for operation in ('summaries', 'pass'):
#                 with self.subTest(operation=operation), operation_guard(other, 'fixture', operation):
#                     with self.assertRaises(MycelError) as error:
#                         self.remove(connection)
#                     self.assertEqual(error.exception.code, 'busy')
#                 self.assertEqual(self.state(connection), original)
#             def interrupted():
#                 raise KeyboardInterrupt
#             with self.assertRaises(KeyboardInterrupt):
#                 self.remove(connection, before=interrupted)
#             self.assertEqual(self.state(connection), original)
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 store = SummaryLifecycleStore(connection, self.base.settings, invocation, 'fixture')
#                 with self.assertRaises(RuntimeError):
#                     with self.fixture.fixture.fixture.guards(connection), atomic_transaction(connection):
#                         store.remove_in_transaction(guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
#                         raise RuntimeError('late audit failed')
#                 self.assertEqual(self.state(connection), original)
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_summary_and_pass_contention_and_interruption_refuse_without_partial_removal

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_empty_set_metadata_removal_succeeds_and_corrupt_sentinel_refuses_without_deleting_other_chunk
#     def test_empty_set_metadata_removal_succeeds_and_corrupt_sentinel_refuses_without_deleting_other_chunk(self):
#         with self.base.connect() as connection:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 self.prepare(connection, invocation)
#                 empty = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
#                 self.fixture.publish(empty, ())
#                 empty.release()
#             self.assertEqual(self.remove(connection).value, {'repository': 'fixture', 'removed': 0})
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks WHERE id=%s',
#                 (summary_set_identifier('fixture'),)).fetchone(), (0,))
#             self.assertEqual(self.remove(connection).value, {'repository': 'fixture', 'removed': 0})
#             connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,%s)',
#                 (summary_set_identifier('fixture'), 'fixture', 'overview', Jsonb({})))
#             original = self.state(connection)
#             with self.assertRaises(MycelError) as error:
#                 self.remove(connection)
#             self.assertEqual(error.exception.code, 'store_format')
#             self.assertEqual(self.state(connection), original)
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_empty_set_metadata_removal_succeeds_and_corrupt_sentinel_refuses_without_deleting_other_chunk

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_post_commit_audit_close_faults_and_interruption_keep_acknowledged_removal_count
#     def test_post_commit_audit_close_faults_and_interruption_keep_acknowledged_removal_count(self):
#         from mycel._activity import MutationActivity
#         for failure in ('finish', 'close', 'signal'):
#             with self.subTest(failure=failure), self.base.connect() as connection:
#                 with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                     self.prepare(connection, invocation)
#                 original_finish = MutationActivity.finish
#                 def finish(activity, *args, **kwargs):
#                     original_finish(activity, *args, **kwargs)
#                     if failure == 'signal':
#                         raise KeyboardInterrupt
#                     if failure == 'finish':
#                         raise MycelError('internal', 'Final audit acknowledgement failed.')
#                 @contextmanager
#                 def guard(*args):
#                     with operation_guard(*args) as value:
#                         yield value
#                     if failure == 'close' and args[2] == 'summaries':
#                         raise MycelError('store_unavailable', 'Final connection close failed.')
#                 with patch('mycel._summary_lifecycle.current_build', return_value=31), \
#                         patch('mycel._summary_lifecycle.operation_guard', side_effect=guard), \
#                         patch.object(MutationActivity, 'finish', finish):
#                     result = self.remove(connection)
#                 self.assertEqual(result.status, 2 if failure == 'signal' else 1)
#                 self.assertEqual(result.value['removed'], 1)
#                 self.assertEqual(result.value['countsState'], 'committed_prefix')
#                 self.assertEqual(self.fixture.current(connection), [])
#                 self.assertEqual(connection.execute("SELECT counts->>'removed',outcome FROM public.mycel_activity "
#                     "WHERE kind='summaries_remove' ORDER BY id DESC LIMIT 1").fetchone(), ('1', 'done'))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_post_commit_audit_close_faults_and_interruption_keep_acknowledged_removal_count

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_settings_change_in_removal_audit_rolls_back_complete_set_and_audit
#     def test_settings_change_in_removal_audit_rolls_back_complete_set_and_audit(self):
#         from mycel._activity import MutationActivity
#         with self.base.connect() as connection:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 self.prepare(connection, invocation)
#             original = self.state(connection)
#             config = self.base.config.read_bytes()
#             original_record = MutationActivity.record_in_transaction
#             def record(activity, *args, **kwargs):
#                 original_record(activity, *args, **kwargs)
#                 self.base.config.write_bytes(config + b'\n[summaries]\nat_once=1\n')
#             try:
#                 with patch('mycel._summary_lifecycle.current_build', return_value=31), \
#                         patch.object(MutationActivity, 'record_in_transaction', record), self.assertRaises(MycelError):
#                     self.remove(connection)
#             finally:
#                 self.base.config.write_bytes(config)
#             self.assertEqual(self.state(connection), original)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='summaries_remove'").fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_settings_change_in_removal_audit_rolls_back_complete_set_and_audit

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_reserved_renewal_publishes_current_vectors_and_pins_in_place_atomically_releasing_old_owner
#     def test_reserved_renewal_publishes_current_vectors_and_pins_in_place_atomically_releasing_old_owner(self):
#         with self.base.connect() as connection, self.base.connect() as reader:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 lower, upper = self.prepare(connection, invocation, parent=True)
#                 owners = connection.execute("SELECT DISTINCT baseline_owner FROM public.mycel_dependencies WHERE dependant_version=%s",
#                     (lower.member.chunk.version,)).fetchall()
#                 self.fixture.fixture.fixture.source.write_bytes(b'# Source\nNew source body.\n')
#                 self.fixture.fixture.fixture.publish(connection)
#                 lower, upper = self.summaries(connection)
#                 store, lease, plan, vectors = self.renewal(connection, invocation, lower)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
#                     (int(plan.chunk_version),)).fetchone(), (0,))
#                 old = self.fixture.current(reader)
#                 with self.fixture.fixture.fixture.guards(connection), atomic_transaction(connection):
#                     result = store.publish_in_transaction(lower, lease, plan, vectors,
#                         guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
#                     self.assertEqual(self.fixture.current(reader), old)
#                     store.verify_in_transaction()
#                 renewed, parent = self.summaries(connection)
#                 self.assertEqual(renewed.member.chunk.identifier, lower.member.chunk.identifier)
#                 self.assertEqual(renewed.member.place, lower.member.place)
#                 self.assertEqual(renewed.member.chunk.version, int(plan.chunk_version))
#                 self.assertEqual(renewed.member.chunk.source, b'New complete response.')
#                 self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE dependant_version=%s AND kind='generated'",
#                     (lower.member.chunk.version,)).fetchone(), (0,))
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=ANY(%s::uuid[])',
#                     ([owner for owner, in owners],)).fetchone(), (0,))
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p ON p.id=v.plan_id '
#                     'WHERE p.chunk_version=%s', (result.chunk_version,)).fetchone(), (len(plan.parts),))
#                 with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
#                     self.assertEqual(snapshot._generated_stale, frozenset({parent.member.chunk.identifier}))
#                 connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (lease.owner_id,))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_reserved_renewal_publishes_current_vectors_and_pins_in_place_atomically_releasing_old_owner

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_withdrawal_of_memberless_summary_preserves_parent_pins_and_recomposes_source_removed
#     def test_withdrawal_of_memberless_summary_preserves_parent_pins_and_recomposes_source_removed(self):
#         with self.base.connect() as connection:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 lower, upper = self.prepare(connection, invocation, parent=True)
#                 self.base.artifact.joinpath('independent.md').write_bytes(b'# Independent\nUnrelated surviving document.\n')
#                 self.fixture.fixture.fixture.source.unlink()
#                 self.fixture.fixture.fixture.base.artifact.joinpath('guide.md').unlink()
#                 self.base.commit()
#                 self.fixture.fixture.fixture.publish(connection)
#                 lower, upper = self.summaries(connection)
#                 old_upper = connection.execute("SELECT declaration,state,baseline_owner FROM public.mycel_dependencies WHERE dependant_version=%s",
#                     (upper.member.chunk.version,)).fetchall()
#                 store = SummaryLifecycleStore(connection, self.base.settings, invocation, 'fixture')
#                 with self.fixture.fixture.fixture.guards(connection), atomic_transaction(connection):
#                     self.assertEqual(store.delete_in_transaction(lower,
#                         guarded_repositories=tuple(sorted(self.base.settings.values['repos']))), 1)
#                     store.verify_in_transaction()
#                 self.assertEqual(connection.execute("SELECT declaration,state,baseline_owner FROM public.mycel_dependencies WHERE dependant_version=%s",
#                     (upper.member.chunk.version,)).fetchall(), old_upper)
#                 with StoreSummaries(connection, self.base.settings).snapshot(('fixture',)) as snapshot:
#                     self.assertEqual(snapshot.regeneration_plan()['remove'][0]['address'], upper.member.place.address)
#                     self.assertEqual(snapshot._generated_stale, frozenset({upper.member.chunk.identifier}))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_withdrawal_of_memberless_summary_preserves_parent_pins_and_recomposes_source_removed

# TEST-TIER-DISABLED-BEGIN tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_changed_exact_inputs_and_late_vector_tampering_roll_back_text_vectors_and_pins
#     def test_changed_exact_inputs_and_late_vector_tampering_roll_back_text_vectors_and_pins(self):
#         with self.base.connect() as connection:
#             with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
#                 summary, = self.prepare(connection, invocation)
#                 for failure in ('inputs', 'vectors', 'audit_disk'):
#                     with self.subTest(failure=failure):
#                         store, lease, plan, vectors = self.renewal(connection, invocation, summary)
#                         original = self.state(connection)
#                         source = self.fixture.fixture.fixture.source
#                         original_source = source.read_bytes()
#                         if failure == 'inputs':
#                             source.write_bytes(b'# Source\nDisk changed during generation.\n')
#                         with self.assertRaises((EvidenceError, MycelError)):
#                             with self.fixture.fixture.fixture.guards(connection), atomic_transaction(connection):
#                                 store.publish_in_transaction(summary, lease, plan, vectors,
#                                     guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
#                                 if failure == 'audit_disk':
#                                     activity = MutationActivity(connection, build=31)
#                                     activity.invocation = invocation
#                                     activity.record_in_transaction('fixture', 'summaries_regenerate', AppliedMutation(True, {'written': 1}))
#                                     source.write_bytes(b'# Source\nDisk changed after audit.\n')
#                                 else:
#                                     connection.execute('DELETE FROM public.mycel_vectors WHERE plan_id IN '
#                                         '(SELECT id FROM public.mycel_embedding_plans WHERE chunk_version=%s)', (int(plan.chunk_version),))
#                                 store.verify_in_transaction()
#                         source.write_bytes(original_source)
#                         self.assertEqual(self.state(connection), original)
#                         self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='summaries_regenerate'").fetchone(), (0,))
#                         connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (lease.owner_id,))
# TEST-TIER-DISABLED-END tests/test_summary_lifecycle.py::SummaryLifecycleStoreTests.test_changed_exact_inputs_and_late_vector_tampering_roll_back_text_vectors_and_pins


if __name__ == '__main__':
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:2
# from contextlib import contextmanager
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:4
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:5
# from uuid import uuid4
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:7
# from psycopg.types.json import Jsonb
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:9
# from mycel._activity import AppliedMutation, MutationActivity
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:9
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:12
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:13
# from mycel._evidence import EvidenceError
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:14
# from mycel._locks import atomic_transaction, invocation_guard, operation_guard
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_lifecycle.py:17
# from mycel._summary_store import StoreSummaries, summary_set_identifier
# TEST-TIER-IMPORTS-END tests/test_summary_lifecycle.py:17
