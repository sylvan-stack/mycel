
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_verification_commands.py::VerificationCommandTests.test_real_confirm_dispatch_and_history_reply_with_explicit_and_default_voucher
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Real confirm dispatch and history reply with explicit and default voucher.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_verification_commands.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END
