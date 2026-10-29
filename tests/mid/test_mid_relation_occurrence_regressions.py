
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_confirmation_refuses_malformed_occurrence_without_renewing_valid_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Confirmation refuses malformed occurrence without renewing valid pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_relation_occurrence_regressions.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_confirmation_refuses_malformed_occurrence_without_renewing_valid_pin(self):
#         self.guide.write_bytes(self.mixed())
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current_pins(connection)
#             self.assertEqual(set(original), {'declared'})
#             self.fixture.source.write_bytes(b'# Source\nChanged source requires a new comparison.\n')
#             self.fixture.publish(connection)
#             current = self.current_pins(connection)
#             self.assertEqual(self.pin_identities(current), self.pin_identities(original))
#             self.assertEqual(current['declared'][3]['reasons'], ['related_changed'])
#             location, version = connection.execute("""SELECT file_location,chunk_version FROM public.mycel_locations
#                 WHERE kind='disk' AND metadata->>'name'='Guide'""").fetchone()
#             inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
#             before = store_state(connection)
#             with self.assertRaises(MycelError) as error:
#                 with self.fixture.guards(connection), atomic_transaction(connection):
#                     RelationApplicationStore(connection).apply_in_transaction(self.base.settings,
#                         str(location), version, mode='confirm', captured_at='2026-10-11T10:00:00Z',
#                         reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None))
#                     inputs.verify()
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(store_state(connection), before)
#             self.assert_mixed_reports()
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(original))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_valid_duplicates_share_one_pin_and_invalid_only_duplicates_have_no_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Valid duplicates share one pin and invalid only duplicates have no pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_relation_occurrence_regressions.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_valid_duplicates_share_one_pin_and_invalid_only_duplicates_have_no_pin(self):
#         valid = ('---\nrole: authored\n---\n# Guide\nBody.\n<!-- related:\n' + SOURCE + '\n  ' +
#                  SOURCE + '  \n-->\n').encode()
#         self.guide.write_bytes(valid)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             first = self.current_pins(connection)
#             self.assertEqual(set(first), {'declared'})
#             refs = self.reports()
#             self.assertEqual(len(refs), 2)
#             self.assertTrue(all(ref['fault'] is None and ref['baselineStatus'] == 'retained' for ref in refs))
#             self.assertEqual(len({ref['id'] for ref in refs}), 1)
#             self.assertEqual(self.reports(unresolved=True), [])
#             repeated = self.fixture.publish(connection)
#             self.assertEqual(repeated.counts['relationPinsCaptured'], 0)
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(first))
#             invalid = ('---\nrole: authored\n---\n# Guide\nBody.\n<!-- related:\n' + SOURCE + '\n  ' +
#                        SOURCE + '  \n').encode()
#             self.publish_guide(connection, invalid)
#             self.assertEqual(self.current_pins(connection), {})
#             refs = self.reports()
#             self.assertEqual(len(refs), 2)
#             self.assertTrue(all(ref['fault'] == 'not_a_ref' for ref in refs))
#             self.assertEqual(self.reports(unresolved=True), refs)
#             self.assertTrue(all(row[4] is None for row in self.current_rows(connection)))
#             retained = connection.execute("""SELECT r.id,r.left_version,r.baseline_owner,e.manifest_hash
#                 FROM public.mycel_relations r JOIN public.mycel_evidence_references e
#                 ON e.owner=r.baseline_owner AND e.ordinal=0 WHERE r.id=%s""", (first['declared'][0],)).fetchone()
#             self.assertEqual(retained, (first['declared'][0], first['declared'][1],
#                                        first['declared'][4], first['declared'][5]))
#             self.assertIn(self.fixture.source_bytes,
#                           [blob.source for blob in self.baseline(connection, first['declared']).snapshots])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_mixed_occurrences_preserve_independent_pins_through_edit_inheritance_and_known_restore
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Mixed occurrences preserve independent pins through edit inheritance and known restore.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_relation_occurrence_regressions.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_mixed_occurrences_preserve_independent_pins_through_edit_inheritance_and_known_restore(self):
#         original = self.mixed()
#         self.guide.write_bytes(original)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             RelateStore(connection).apply(self.base.settings, DEPENDANT, SOURCE,
#                 captured_at='2026-10-11T10:00:00Z', settings_home=self.base.base)
#             first = self.current_pins(connection)
#             self.assertEqual(set(first), {'declared', 'asserted'})
#             first_hashes = {kind: self.baseline(connection, row).manifest.payload['pinnedHash']
#                             for kind, row in first.items()}
#             self.assertNotEqual(first['declared'][4], first['asserted'][4])
#             self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
#             inherited = self.publish_guide(connection, self.mixed('Original   dependant.'))
#             equivalent = self.current_pins(connection)
#             self.assertEqual(set(equivalent), {'declared', 'asserted'})
#             self.assertEqual(inherited.counts['relationPinsInherited'], 2)
#             self.assertNotEqual(equivalent['declared'][1], first['declared'][1])
#             for kind, row in equivalent.items():
#                 self.assertEqual(self.baseline(connection, row).manifest.payload['pinnedHash'], first_hashes[kind])
#                 self.assertEqual(row[3]['reasons'], ['related_changed'])
#             self.assert_mixed_reports()
#             edited = self.publish_guide(connection, self.mixed('Edited dependant.'))
#             repinned = self.current_pins(connection)
#             self.assertEqual(edited.counts['relationPinsCaptured'], 2)
#             for kind, row in repinned.items():
#                 self.assertNotEqual(self.baseline(connection, row).manifest.payload['pinnedHash'], first_hashes[kind])
#                 self.assertEqual(row[3]['reasons'], [])
#             self.assert_mixed_reports()
#             restored = self.publish_guide(connection, original)
#             current = self.current_pins(connection)
#             self.assertEqual((restored.counts['relationPinsCaptured'], restored.counts['relationPinsInherited']), (0, 0))
#             self.assertEqual(self.pin_identities(current), self.pin_identities(first))
#             self.assertTrue(all(row[3]['reasons'] == ['related_changed'] for row in current.values()))
#             self.assert_mixed_reports()
#             before = store_state(connection)
#             assertion = RelateStore(connection).apply(self.base.settings, DEPENDANT, SOURCE,
#                 captured_at='2026-10-11T10:10:00Z', settings_home=self.base.base)
#             self.assertFalse(assertion['changed'])
#             self.assertEqual(store_state(connection), before)
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(first))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
