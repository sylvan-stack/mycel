
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_read_generated_store.py::GeneratedReadStoreTests.test_upper_summary_checks_generated_members_and_transitive_external_sources_without_regeneration
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Upper summary checks generated members and transitive external sources without regeneration.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_read_generated_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_upper_summary_checks_generated_members_and_transitive_external_sources_without_regeneration(self):
#         with self.fixture.base.connect() as connection:
#             self.fixture.prepare(connection)
#             lower = self.publish(connection, 'fixture:@artifact/driver.md#Driver', '1/1',
#                                  b'Complete lower summary.\n')
#             upper_text = 'Complete upper summary 雪.\n'
#             upper = self.publish(connection, lower.place.address, '2/1', upper_text.encode())
#             pins = self.pins(connection)
#             outside = self.fixture.owned(connection, 'outside')
#             self.fixture.glossary.write_bytes(b'# Glossary\nA substantive changed governing definition.\n')
#             captures = []
#             actual = fixtures._Capture.capture
#
#             def record(capture):
#                 captures.append(capture.repository.name)
#                 return actual(capture)
#
#             with patch.object(fixtures._Capture, 'capture', record), \
#                     patch('mycel._summary_writer.SummaryWriter.write', side_effect=AssertionError('writer')), \
#                     patch('mycel._embed.embed', side_effect=AssertionError('embedding')), \
#                     patch.object(GeneratedPublicationStore, 'publish_in_transaction',
#                                  side_effect=AssertionError('regeneration')):
#                 reply = read_from_store(connection, self.fixture.settings, upper.place.address,
#                     deadline=Deadline.after(30), build=1)
#             self.assertEqual(reply['id'], upper.chunk_id)
#             self.assertEqual(reply['text'], upper_text)
#             self.assertEqual(reply['origin'], 'summary')
#             self.assertEqual(reply['root'], 'index')
#             self.assertNotIn('file', reply)
#             self.assertTrue(reply['stale'], reply)
#             self.assertTrue(reply['freshness']['finished'], reply)
#             self.assertTrue(reply['dependencyCheck']['complete'], reply)
#             checks = {row['repository']: row for row in reply['freshness']['repositories']}
#             self.assertTrue({'fixture', 'contract', 'glossary'}.issubset(captures))
#             self.assertFalse({'outside', 'shared', 'disabled'}.intersection(captures))
#             self.assertTrue({'fixture', 'contract', 'glossary'}.issubset(checks))
#             self.assertTrue(all(checks[name]['state'] == 'done'
#                                 for name in ('fixture', 'contract', 'glossary')))
#             self.assertGreater(checks['glossary']['ingested'], 0)
#             self.assertEqual(reply['freshness']['ingested'], sum(row['ingested'] for row in checks.values()))
#             self.assertTrue(any(reason['source']['repository'] == 'glossary'
#                 and any(place['address'] == lower.place.address for place in reason.get('via', ()))
#                 for reason in reply['staleReasons']), reply['staleReasons'])
#             self.assertEqual(self.pins(connection), pins)
#             self.assertEqual(self.fixture.owned(connection, 'outside'), outside)
#             for publication, text in ((lower, b'Complete lower summary.\n'), (upper, upper_text.encode())):
#                 self.assertEqual(bytes(connection.execute('SELECT source_bytes FROM public.mycel_chunk_versions '
#                     'WHERE id=%s', (publication.chunk_version,)).fetchone()[0]), text)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
