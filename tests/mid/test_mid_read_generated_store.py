"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_read_generated_store as _support
# from test_read_generated_store import (
#     ExitStack,
#     GeneratedPublicationStore,
#     GeneratedReadStoreTests,
#     GenerationEvidenceStore,
#     GenerationMember,
#     SourceAddress,
#     SourceResolver,
#     SummaryPrompts,
#     SummarySection,
#     SummarySetMetadata,
#     atomic_transaction,
#     capture_generation,
#     checked_store,
#     fixtures,
#     invocation_guard,
#     operation_guard,
#     plan_summary_requests,
#     unittest,
#     uuid4,
# )


# class GeneratedReadStoreTests(_support.GeneratedReadStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_read_generated_store.py::GeneratedReadStoreTests.test_upper_summary_checks_generated_members_and_transitive_external_sources_without_regeneration
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
# TEST-TIER-DISABLED-END tests/test_read_generated_store.py::GeneratedReadStoreTests.test_upper_summary_checks_generated_members_and_transitive_external_sources_without_regeneration


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_read_generated_store.py:4
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_read_generated_store.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_read_generated_store.py:7
# from mycel._freshness import Deadline
# TEST-TIER-IMPORTS-END tests/test_read_generated_store.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_read_generated_store.py:10
# from mycel._read_store import read_from_store
# TEST-TIER-IMPORTS-END tests/test_read_generated_store.py:10

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
