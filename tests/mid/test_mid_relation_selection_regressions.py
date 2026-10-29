"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_relation_selection_regressions as _support
# from test_relation_selection_regressions import (
#     CHUNK,
#     EvidenceStore,
#     FAMILY,
#     MycelError,
#     RelationSelectionRegressionStoreTests,
#     SOURCE,
#     SourceResolver,
#     fixtures,
#     unittest,
# )


# class RelationSelectionRegressionStoreTests(_support.RelationSelectionRegressionStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores
#     def test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores(self):
#         self.declare()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current(connection)
#             baseline = EvidenceStore(connection).read_baseline('fixture', original[5])
#             self.assertEqual(baseline.manifest.payload['selection'], 'family')
#             self.assertEqual([member['place']['name'] for member in baseline.manifest.payload['members']],
#                              ['Policy', 'Policy.apply'])
#             self.fixture.code.write_bytes(CHUNK)
#             self.fixture.publish(connection)
#             self.assert_observed(connection, original, baseline, current_kind='chunk', raw=CHUNK, removed=True)
#             self.fixture.code.write_bytes(FAMILY)
#             self.fixture.publish(connection)
#             self.assert_restored(connection, original, baseline)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member
#     def test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member(self):
#         self.declare(original=CHUNK)
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current(connection)
#             baseline = EvidenceStore(connection).read_baseline('fixture', original[5])
#             self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
#             self.assertEqual(len(baseline.manifest.payload['members']), 1)
#             self.fixture.code.write_bytes(FAMILY)
#             self.fixture.publish(connection)
#             self.assert_observed(connection, original, baseline, current_kind='family', raw=FAMILY)
#             self.fixture.code.write_bytes(CHUNK)
#             self.fixture.publish(connection)
#             self.assert_restored(connection, original, baseline)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin
#     def test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin(self):
#         self.accepted_edit_and_restoration(original_source=FAMILY, changed_source=CHUNK,
#             changed_kind='chunk', removed=True)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin
#     def test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin(self):
#         self.accepted_edit_and_restoration(original_source=CHUNK, changed_source=FAMILY,
#             changed_kind='family', removed=False)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant
#     def test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant(self):
#         original_guide = self.declare()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             previous = self.current(connection)
#             for raw, kind, removed in ((CHUNK, 'chunk', True), (FAMILY, 'family', False)):
#                 baseline = EvidenceStore(connection).read_baseline('fixture', previous[5])
#                 self.fixture.code.write_bytes(raw)
#                 self.fixture.publish(connection)
#                 self.assert_observed(connection, previous, baseline, current_kind=kind, raw=raw, removed=removed)
#                 reply = self.harness.confirm_hook(connection)
#                 self.assertEqual(reply.captured, 1)
#                 confirmed = self.current(connection)
#                 self.assertEqual(confirmed[:2], previous[:2])
#                 self.assertNotEqual(confirmed[5], previous[5])
#                 self.assertEqual(confirmed[3]['reasons'], [])
#                 self.assertEqual(EvidenceStore(connection).read_baseline('fixture', confirmed[5]).manifest.payload['selection'], kind)
#                 self.assertEqual(self.guide.read_bytes(), original_guide)
#                 self.fixture.publish(connection)
#                 self.assertEqual(self.reasons(connection, self.current(connection)), ())
#                 previous = self.current(connection)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant


raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
