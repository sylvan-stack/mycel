
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_ingest_activity.py::PublicIngestActivityStoreTests.test_public_ingest_history_and_detail_match_exact_reply_and_quiet_pass_is_silent
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public ingest history and detail match exact reply and quiet pass is silent.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ingest_activity.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_ingest_history_and_detail_match_exact_reply_and_quiet_pass_is_silent(self):
#         code = self.base.code / 'answer.py'
#         code.write_bytes(b'def answer():\n    return 42\n')
#         self.assertEqual(self.history(), [])
#         reply = self.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
#         entries = self.history()
#         self.assertEqual(len(entries), 1)
#         entry = entries[0]
#         self.assertEqual((entry['repository'], entry['kind'], entry['startedBy'],
#                           entry['build'], entry['outcome']),
#                          ('fixture', 'ingest', 'command', '1a', 'done'))
#         self.assertEqual(entry['counts'], reply)
#         self.assertLessEqual(entry['startedAt'], entry['endedAt'])
#         detail = self.invoke('activity', '--entry', entry['id'])['entries'][0]
#         self.assertEqual({key: detail[key] for key in entry}, entry)
#         self.assertTrue({('code', 'answer.py'), ('artifact', 'guide.md')} <=
#                         {(f['root'], f['path']) for f in detail['files']})
#         self.assertTrue(all(f['change'] == 'added' for f in detail['files']))
#         self.assertTrue({'answer', 'Guide'} <= {d['name'] for d in detail['decisions']})
#         self.assertTrue(any(d['name'] == 'answer' and d['decision'] == 'new'
#                             for d in detail['decisions']), detail['decisions'])
#         quiet = self.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
#         self.assertFalse(quiet['changed'])
#         self.assertEqual(self.history(), entries)
#         self.assertEqual(self.invoke('activity', '--entry', entry['id'])['entries'][0], detail)
#         code.write_bytes(b'def answer():\n    return 43\n')
#         edited = self.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
#         latest, original = self.history()
#         self.assertEqual(original, entry)
#         self.assertNotEqual(latest['invocation'], entry['invocation'])
#         self.assertEqual(latest['counts'], edited)
#         edit_detail = self.invoke('activity', '--entry', latest['id'])['entries'][0]
#         self.assertIn({'root': 'code', 'path': 'answer.py', 'location': 'disk', 'change': 'changed'},
#                       edit_detail['files'])
#         self.assertIn('edited', {d['decision'] for d in edit_detail['decisions']})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ingest_activity.py::PublicIngestActivityStoreTests.test_public_audit_failure_rolls_back_publication_and_missing_identity_never_downgrades
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public audit failure rolls back publication and missing identity never downgrades.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ingest_activity.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_audit_failure_rolls_back_publication_and_missing_identity_never_downgrades(self):
#         self.identity.unlink()
#         missing = self.invoke('ingest', '--repo', 'fixture', status=1)
#         self.assertEqual(missing['error']['code'], 'internal')
#         self.assertEqual(self.history(), [])
#         self.identity.write_bytes(b'{"schemaVersion":1,"build":26}\n')
#         with self.base.connect() as connection:
#             connection.execute("CREATE FUNCTION public.reject_fixture_activity() RETURNS trigger "
#                 "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture audit write failure'; END $$")
#             connection.execute('CREATE TRIGGER reject_fixture_activity BEFORE INSERT ON '
#                 'public.mycel_activity FOR EACH ROW EXECUTE FUNCTION public.reject_fixture_activity()')
#         refused = self.invoke('ingest', '--repo', 'fixture', status=1)
#         self.assertEqual(refused['repositories'][0]['error']['code'], 'internal')
#         self.assertEqual(self.history(), [])
#         with self.base.connect() as connection:
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone()[0], 0)
#             connection.execute('DROP TRIGGER reject_fixture_activity ON public.mycel_activity')
#             connection.execute('DROP FUNCTION public.reject_fixture_activity()')
#         reply = self.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
#         entries = self.history()
#         self.assertEqual(len(entries), 1)
#         self.assertEqual(entries[0]['counts'], reply)
#         self.assertEqual(entries[0]['outcome'], 'done')
# LOW-TIER-SOURCE-END
# LOW-TIER-END
