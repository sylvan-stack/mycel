"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_verification_commands as _support
# from test_verification_commands import (
#     StringIO,
#     VerificationCommandTests,
#     fixtures,
#     json,
#     patch,
#     run,
#     unittest,
# )


# class VerificationCommandTests(_support.VerificationCommandTests):
# TEST-TIER-DISABLED-BEGIN tests/test_verification_commands.py::VerificationCommandTests.test_real_confirm_dispatch_and_history_reply_with_explicit_and_default_voucher
#     def test_real_confirm_dispatch_and_history_reply_with_explicit_and_default_voucher(self):
#         self.fixture.answer.write_bytes(b'# Answer\nIndependent statement.\n')
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             with patch('mycel._verification.getpass.getuser', return_value='owner-login'):
#                 status, first = self.invoke('confirm', 'downstream:@artifact/answer.md#Answer')
#             self.assertEqual((status, first['by'], first['how'], first['current']),
#                              (0, 'owner-login', 'read', True))
#             expected = {'id', 'chunk', 'chunkId', 'version', 'textHash', 'dependantSnapshot',
#                         'baselineManifests', 'sources', 'by', 'how', 'at', 'current'}
#             self.assertEqual(set(first), expected)
#             status, second = self.invoke('confirm', 'downstream:@artifact/answer.md#Answer',
#                                         '--by', 'ana', '--how', 'check')
#             self.assertEqual((status, second['by'], second['how']), (0, 'ana', 'check'))
#             self.assertNotEqual(first['id'], second['id'])
#             before = self.fixture.state(connection)
#             records = connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_verifications r ORDER BY id').fetchall()
#             status, current = self.invoke('verifications', '--repo', 'downstream')
#             self.assertEqual(status, 0)
#             self.assertEqual(current, {'repository': 'downstream', 'verifications': [second]})
#             status, history = self.invoke('verifications', '--repo', 'downstream', '--history')
#             self.assertEqual(status, 0)
#             self.assertEqual([r['id'] for r in history['verifications']], [second['id'], first['id']])
#             self.assertEqual([r['current'] for r in history['verifications']], [True, False])
#             self.assertEqual(self.fixture.state(connection), before)
#             self.assertEqual(connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_verifications r ORDER BY id').fetchall(), records)
# TEST-TIER-DISABLED-END tests/test_verification_commands.py::VerificationCommandTests.test_real_confirm_dispatch_and_history_reply_with_explicit_and_default_voucher


raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
