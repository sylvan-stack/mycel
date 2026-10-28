"""Confirmation's public writer through real, configured disposable stores."""
import unittest

from mycel._verification import ConfirmationStore

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class ConfirmationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.ref = 'downstream:@artifact/answer.md#Answer'

    def confirm(self, connection, **options):
        return ConfirmationStore(connection).apply(self.base.settings, self.ref,
            settings_home=self.base.base, captured_at='2026-10-11T12:00:00Z', **options)

    def state(self, connection):
        state = self.fixture.state(connection)
        for table in ('mycel_relations', 'mycel_verifications', 'mycel_stale_reasons'):
            state[table] = connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
                'ORDER BY to_jsonb(t)::text').fetchall()
        return state

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_confirm_records_exact_dependency_and_related_snapshots_and_renewed_pins_atomically
#     def test_confirm_records_exact_dependency_and_related_snapshots_and_renewed_pins_atomically(self):
#         self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() +
#             b'\n<!-- related:\nfixture:@artifact/guide.md#Guide\n-->\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             old = self.fixture.dependencies(connection)[0][7]
#             self.fixture.source.write_bytes(b'# Source\nRevised governing source.\n')
#             self.fixture.publish(connection)
#             reply = self.confirm(connection, by='ana', how='check')
#             self.assertEqual((reply['by'], reply['how'], reply['at'], reply['current']),
#                 ('ana', 'check', '2026-10-11T12:00:00Z', True))
#             self.assertEqual(reply['textHash'], sha256(b'# Answer\nUnchanged dependant.\n\n<!-- related:\n'
#                 b'fixture:@artifact/guide.md#Guide\n-->\n').hexdigest())
#             self.assertEqual(reply['version'], reply['textHash'])
#             self.assertEqual(len(reply['baselineManifests']), 2)
#             self.assertEqual(len(reply['sources']), 2)
#             self.assertNotEqual(self.fixture.dependencies(connection)[0][7], old)
#             for manifest in reply['baselineManifests']:
#                 capture = EvidenceStore(connection).read_baseline('downstream', manifest)
#                 self.assertEqual(capture.manifest.payload['dependant']['snapshot'], reply['dependantSnapshot'])
#                 self.assertEqual(capture.manifest.payload['capturedAt'], reply['at'])
#             record, owner = connection.execute('SELECT record,evidence_owner FROM public.mycel_verifications '
#                 'WHERE id=%s', (reply['id'],)).fetchone()
#             self.assertEqual({selection['edgeKind'] for selection in record['selections']}, {'declared', 'related'})
#             refs = connection.execute('SELECT snapshot_hash,manifest_hash FROM public.mycel_evidence_references '
#                 'WHERE owner=%s ORDER BY ordinal', (owner,)).fetchall()
#             self.assertEqual({value[1] for value in refs if value[1]}, set(reply['baselineManifests']))
#             self.assertTrue(all(source['snapshot'].startswith('snapshot:') for source in reply['sources']))
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_confirm_records_exact_dependency_and_related_snapshots_and_renewed_pins_atomically

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_source_free_confirm_uses_login_read_defaults_and_does_not_mutate_files
#     def test_source_free_confirm_uses_login_read_defaults_and_does_not_mutate_files(self):
#         self.fixture.answer.write_bytes(b'# Answer\nIndependent statement.\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             before = self.fixture.answer.read_bytes()
#             with patch('mycel._verification.getpass.getuser', return_value='owner-login'):
#                 reply = self.confirm(connection)
#             self.assertEqual((reply['by'], reply['how'], reply['current']), ('owner-login', 'read', True))
#             self.assertEqual((reply['sources'], reply['baselineManifests']), ([], []))
#             self.assertEqual(self.fixture.answer.read_bytes(), before)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (1,))
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_source_free_confirm_uses_login_read_defaults_and_does_not_mutate_files

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_confirmation_retains_full_file_and_family_membership_with_every_exact_source
#     def test_confirmation_retains_full_file_and_family_membership_with_every_exact_source(self):
#         code = self.base.code / 'policy.py'
#         code.write_bytes(b'class Policy:\n    def apply(self):\n        return 1\n')
#         self.base.commit()
#         self.fixture.answer.write_bytes(b'---\nsources: ["fixture:@code/policy.py#Policy", '
#             b'"fixture:@artifact/source.md"]\n---\n# Answer\nReview complete file and family.\n'
#             b'\n<!-- related:\nfixture:@code/policy.py#Policy\n-->\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             reply = self.confirm(connection, by='ana')
#             self.assertEqual(len(reply['baselineManifests']), 3)
#             self.assertEqual(len(reply['sources']), 5)
#             record = connection.execute('SELECT record FROM public.mycel_verifications WHERE id=%s',
#                 (reply['id'],)).fetchone()[0]
#             checked = [EvidenceStore(connection).read_baseline('downstream', item['manifest']).manifest.payload
#                        for item in record['selections']]
#             self.assertEqual(sorted(value['selection'] for value in checked), ['family', 'family', 'file'])
#             whole = next(value for value in checked if value['selection'] == 'file')
#             self.assertEqual(whole['members'][0]['evidence']['hash'], sha256(self.fixture.source_bytes).hexdigest())
#             for source in reply['sources']:
#                 raw = connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
#                     ('downstream', source['hash'])).fetchone()[0]
#                 self.assertEqual(sha256(bytes(raw)).hexdigest(), source['hash'])
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_confirmation_retains_full_file_and_family_membership_with_every_exact_source

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_changed_since_ingest_dependant_or_source_refuses_without_publication_or_record
#     def test_changed_since_ingest_dependant_or_source_refuses_without_publication_or_record(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             before = self.state(connection)
#             answer = self.fixture.answer.read_bytes()
#             self.fixture.answer.write_bytes(answer.replace(b'Unchanged', b'Edited'))
#             with self.assertRaises(MycelError) as error:
#                 self.confirm(connection)
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertIn('changed_since_ingest', error.exception.message)
#             self.assertEqual(self.state(connection), before)
#             self.fixture.answer.write_bytes(answer)
#             self.fixture.source.write_bytes(b'# Source\nUnpublished source change.\n')
#             with self.assertRaises(MycelError) as error:
#                 self.confirm(connection)
#             self.assertIn('changed_since_ingest', error.exception.message)
#             self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_changed_since_ingest_dependant_or_source_refuses_without_publication_or_record

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_new_invalid_relation_rolls_back_earlier_dependency_repin
#     def test_new_invalid_relation_rolls_back_earlier_dependency_repin(self):
#         self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() +
#             b'\n<!-- related:\nfixture:@artifact/missing.md#Absent\n-->\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             self.fixture.source.write_bytes(b'# Source\nChanged before refused confirmation.\n')
#             self.fixture.publish(connection)
#             before = self.state(connection)
#             with self.assertRaises(MycelError) as error:
#                 self.confirm(connection)
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_new_invalid_relation_rolls_back_earlier_dependency_repin

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_deleted_declared_source_withdrawal_keeps_fault_and_independent_old_verification_evidence
#     def test_deleted_declared_source_withdrawal_keeps_fault_and_independent_old_verification_evidence(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             first = self.confirm(connection, by='ana')
#             source = first['sources'][0]
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             second = self.confirm(connection, by='ana')
#             self.assertFalse(second['current'])
#             self.assertEqual((second['sources'], second['baselineManifests']), ([], []))
#             self.assertIsNone(self.fixture.dependencies(connection)[0][6])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_ref_faults '
#                 "WHERE repository='downstream'").fetchone(), (1,))
#             row = connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
#                 ('downstream', source['hash'])).fetchone()
#             self.assertEqual(bytes(row[0]), self.fixture.source_bytes)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (2,))
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_deleted_declared_source_withdrawal_keeps_fault_and_independent_old_verification_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_source_change_rolls_back_pins_record_and_activity
#     def test_final_audit_callback_source_change_rolls_back_pins_record_and_activity(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             before = self.state(connection)
#             original = MutationActivity.record_in_transaction
#             def change_after_audit(activity, *args, **kwargs):
#                 result = original(activity, *args, **kwargs)
#                 self.fixture.source.write_bytes(b'# Source\nChanged during audit callback.\n')
#                 return result
#             with patch.object(MutationActivity, 'record_in_transaction', change_after_audit):
#                 with self.assertRaises(MycelError) as error:
#                     self.confirm(connection, build=1)
#             self.assertIn('changed_since_ingest', error.exception.message)
#             after = self.state(connection)
#             # The failed audit session may retain invocation liveness, but no
#             # feature or per-repository mutation activity row can survive.
#             self.assertEqual(after, before)
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_source_change_rolls_back_pins_record_and_activity

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_relation_withdrawal_rolls_back_complete_confirmation
#     def test_final_audit_callback_relation_withdrawal_rolls_back_complete_confirmation(self):
#         self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() +
#             b'\n<!-- related:\nfixture:@artifact/guide.md#Guide\n-->\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             before = self.state(connection)
#             original = MutationActivity.record_in_transaction
#             def withdraw_after_audit(activity, *args, **kwargs):
#                 result = original(activity, *args, **kwargs)
#                 connection.execute("DELETE FROM public.mycel_relations WHERE repository='downstream'")
#                 return result
#             with patch.object(MutationActivity, 'record_in_transaction', withdraw_after_audit):
#                 with self.assertRaises(MycelError) as error:
#                     self.confirm(connection, build=1)
#             self.assertIn('changed_since_ingest', error.exception.message)
#             self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_final_audit_callback_relation_withdrawal_rolls_back_complete_confirmation

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_required_busy_source_refuses_and_unrelated_busy_repository_does_not_block
#     def test_required_busy_source_refuses_and_unrelated_busy_repository_does_not_block(self):
#         unrelated = self.base.base / 'unrelated'
#         unrelated.mkdir()
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.unrelated]\nenabled=true\n'
#             'artifact_root="' + str(unrelated) + '"\n')
#         self.fixture.reload()
#         with self.base.connect() as connection, self.base.connect() as peer:
#             self.fixture.prepare(connection)
#             before = self.state(connection)
#             with operation_guard(peer, 'fixture', 'pass'):
#                 with self.assertRaises(MycelError) as error:
#                     self.confirm(connection)
#                 self.assertEqual(error.exception.code, 'busy')
#             self.assertEqual(self.state(connection), before)
#             with operation_guard(peer, 'unrelated', 'pass'):
#                 self.assertTrue(self.confirm(connection)['current'])
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_required_busy_source_refuses_and_unrelated_busy_repository_does_not_block

# TEST-TIER-DISABLED-BEGIN tests/test_confirmation.py::ConfirmationStoreTests.test_confirm_keeps_remaining_upstream_staleness_and_records_actual_build_reply
#     def test_confirm_keeps_remaining_upstream_staleness_and_records_actual_build_reply(self):
#         guide = self.base.artifact / 'guide.md'
#         guide.write_bytes(b'# Guide\nOriginal upstream fact.\n')
#         self.fixture.source.write_bytes(b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n' + self.fixture.source_bytes)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             guide.write_bytes(b'# Guide\nChanged upstream fact.\n')
#             self.fixture.publish(connection)
#             from mycel._staleness import MechanicalStalenessStore, detection_guards
#             from mycel._locks import atomic_transaction
#             with self.fixture.guards(connection), detection_guards(connection, self.base.settings, 'fixture') as guards:
#                 with atomic_transaction(connection):
#                     MechanicalStalenessStore(connection).apply_in_transaction(self.base.settings, 'fixture', guards)
#             reply = self.confirm(connection, build=1)
#             self.assertTrue(reply['current'])
#             reasons = connection.execute("SELECT reason FROM public.mycel_stale_reasons WHERE repository='downstream'").fetchall()
#             self.assertTrue(any(row[0]['kind'] == 'upstream_stale' for row in reasons))
#             entry = connection.execute("SELECT id FROM public.mycel_activity WHERE repository='downstream' AND kind='confirm'").fetchone()
#             self.assertEqual(activity_state(connection, entry[0])['counts'], reply)
# TEST-TIER-DISABLED-END tests/test_confirmation.py::ConfirmationStoreTests.test_confirm_keeps_remaining_upstream_staleness_and_records_actual_build_reply

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:2
# from hashlib import sha256
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:4
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:6
# from mycel._activity import MutationActivity, activity_state
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:7
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:8
# from mycel._evidence import EvidenceStore
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_confirmation.py:9
# from mycel._locks import operation_guard
# TEST-TIER-IMPORTS-END tests/test_confirmation.py:9
