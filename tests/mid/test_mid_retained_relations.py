
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_source_publication_retains_relation_away_deleted_and_recreated_pin_without_authority
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Source publication retains relation away deleted and recreated pin without authority.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_publication_retains_relation_away_deleted_and_recreated_pin_without_authority(self):
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             original = self.relation(connection, identifier)
#             baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
#             source_version = original[4]['selection']['members'][0]['version']
#             self.fixture.source.unlink()
#             self.fixture.publish(connection)
#             away = self.relation(connection, identifier)
#             self.assertEqual(away[:4] + away[5:], original[:4] + original[5:])
#             self.assertEqual((away[4]['sourceExistence'], away[4]['reasons']), ('away', ['source_removed']))
#             self.assertEqual(self.fixture.role(connection), 'authored')
#             self.assertEqual(self.fixture.edges(connection), [])
#             self.base.commit()
#             with MutationActivity(connection, build=1).session() as activity:
#                 deleted_result = self.fixture.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): deleted_result.counts,
#                     ('downstream', 'ingest'): deleted_result.counts['dependencyRepositories']['downstream']})
#             deleted = self.relation(connection, identifier)
#             self.assertEqual((deleted[4]['sourceExistence'], deleted[4]['reasons']), ('deleted', ['source_removed']))
#             self.assertEqual(deleted[4]['sourceAbsence']['place'], self.ref)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
#                 (source_version,)).fetchone(), (0,))
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), baseline)
#             counts = deleted_result.counts['dependencyRepositories']['downstream']
#             self.assertEqual(counts['relationsChanged'], 1)
#             entries = connection.execute("SELECT id FROM public.mycel_activity WHERE repository='downstream'").fetchall()
#             self.assertEqual(len(entries), 1)
#             self.assertEqual(activity_state(connection, entries[0][0])['counts'], counts)
#             stable = self.state(connection)
#             self.assertFalse(self.fixture.publish(connection).changed)
#             self.assertEqual(self.state(connection), stable)
#             self.fixture.source.write_bytes(self.fixture.source_bytes)
#             self.fixture.publish(connection)
#             recreated = self.relation(connection, identifier)
#             self.assertEqual(recreated[:4] + recreated[5:], original[:4] + original[5:])
#             self.assertEqual((recreated[4]['sourceExistence'], recreated[4]['reasons']), ('present', []))
#             self.assertNotEqual(recreated[4]['selection']['members'][0]['version'], source_version)
#             self.assertEqual(self.fixture.role(connection), 'authored')
#             self.fixture.source.write_bytes(b'# Source\nChanged recreated source.\n')
#             self.fixture.publish(connection)
#             changed = self.relation(connection, identifier)
#             self.assertEqual(changed[4]['reasons'], ['related_changed'])
#             self.assertEqual(changed[5], original[5])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_empty_relation_file_is_present_and_deleted_evidence_is_never_empty_substitution
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Empty relation file is present and deleted evidence is never empty substitution.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_empty_relation_file_is_present_and_deleted_evidence_is_never_empty_substitution(self):
#         self.fixture.source.write_bytes(b'')
#         self.base.commit()
#         self.ref = 'fixture:@artifact/source.md'
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             original = self.relation(connection, identifier)
#             self.assertEqual(original[4]['sourceExistence'], 'present')
#             self.assertEqual(original[4]['selection']['members'], [])
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             missing = self.relation(connection, identifier)
#             self.assertEqual(missing[4]['sourceExistence'], 'deleted')
#             self.assertEqual(missing[4]['sourceAbsence']['previousFileHash'], sha256(b'').hexdigest())
#             self.assertEqual(missing[5], original[5])
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.payload['pinnedHash'],
#                 sha256(b'').hexdigest())
#             self.fixture.source.write_bytes(b'')
#             self.fixture.publish(connection)
#             self.assertEqual(self.relation(connection, identifier)[4]['reasons'], [])
#             self.assertEqual(self.relation(connection, identifier)[5], original[5])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_confirmation_withdraws_missing_relation_baseline_and_keeps_declared_fault
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Confirmation withdraws missing relation baseline and keeps declared fault.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_confirmation_withdraws_missing_relation_baseline_and_keeps_declared_fault(self):
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             owner = self.relation(connection, identifier)[5]
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             reply = self.apply(connection, identifier, authorization='owner_confirmation')
#             current = self.relation(connection, identifier)
#             self.assertEqual(reply.released, 1)
#             self.assertIsNone(current[5])
#             self.assertEqual(current[4]['rawRef'], self.ref)
#             self.assertEqual(current[4]['resolution']['fault'], 'missing_file')
#             self.assertEqual(current[4]['reasons'], [])
#             self.assertEqual(current[4]['sourceState'], 'unresolved')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
#                 (owner,)).fetchone(), (0,))
#             self.assertEqual(self.fixture.role(connection), 'authored')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_substantive_edit_withdraws_missing_current_relation_without_changing_historical_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Substantive edit withdraws missing current relation without changing historical pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_substantive_edit_withdraws_missing_current_relation_without_changing_historical_pin(self):
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             original = self.relation(connection, identifier)
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Edited dependant.'))
#             result = self.fixture.publish(connection, 'downstream', collect=False)
#             relations = connection.execute('SELECT id,left_version,state,baseline_owner FROM public.mycel_relations '
#                 'ORDER BY left_version').fetchall()
#             self.assertEqual(len(relations), 2)
#             self.assertEqual(self.relation(connection, identifier), original)
#             current = next(row for row in relations if str(row[0]) != identifier)
#             self.assertIsNone(current[3])
#             self.assertEqual(current[2]['resolution']['fault'], 'missing_file')
#             self.assertEqual(current[2]['reasons'], [])
#             self.assertEqual(result.counts['relationsChanged'], 1)
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.identifier, baseline_id)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_same_capture_source_deletion_and_dependant_edit_withdraws_previously_present_relation
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Same capture source deletion and dependant edit withdraws previously present relation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_same_capture_source_deletion_and_dependant_edit_withdraws_previously_present_relation(self):
#         local = self.fixture.downstream / 'local.md'
#         local.write_bytes(b'# Local\nSame-repository source.\n')
#         self.ref = 'downstream:@artifact/local.md#Local'
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             previous = self.relation(connection, identifier)
#             self.assertEqual(previous[4]['sourceExistence'], 'present')
#             local.unlink()
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Edited dependant.'))
#             result = self.fixture.publish(connection, 'downstream', collect=False)
#             rows = connection.execute('SELECT id,left_version,state,baseline_owner FROM public.mycel_relations '
#                 'ORDER BY left_version').fetchall()
#             self.assertEqual(len(rows), 2)
#             self.assertEqual(self.relation(connection, identifier), previous)
#             current = next(row for row in rows if str(row[0]) != identifier)
#             self.assertIsNone(current[3])
#             self.assertEqual(current[2]['resolution']['fault'], 'missing_file')
#             self.assertEqual(current[2]['reasons'], [])
#             self.assertFalse(current[2]['everResolved'])
#             self.assertEqual(result.counts['relationsChanged'], 1)
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.identifier, baseline_id)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_removed_relation_family_member_preserves_complete_pin_and_direct_removed_reason
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Removed relation family member preserves complete pin and direct removed reason.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_removed_relation_family_member_preserves_complete_pin_and_direct_removed_reason(self):
#         code = self.base.code / 'policy.py'
#         code.write_bytes(b'class Policy:\n    def apply(self):\n        return 1\n')
#         self.base.commit()
#         self.ref = 'fixture:@code/policy.py#Policy'
#         with self.base.connect() as connection:
#             identifier, baseline_id = self.seed(connection)
#             previous = self.relation(connection, identifier)
#             self.assertEqual(len(previous[4]['selection']['members']), 2)
#             code.write_bytes(b'class Policy:\n    pass\n')
#             self.fixture.publish(connection)
#             current = self.relation(connection, identifier)
#             self.assertEqual(current[4]['reasons'], ['source_removed', 'related_changed'])
#             self.assertEqual(current[5], previous[5])
#             self.assertEqual(len(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.payload['members']), 2)
#             self.assertEqual(self.fixture.role(connection), 'authored')
#             self.assertEqual(self.fixture.edges(connection), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_retained_relations.py::RetainedRelationStoreTests.test_selected_relation_removal_and_late_foreign_change_are_guarded_and_atomic
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Selected relation removal and late foreign change are guarded and atomic.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_retained_relations.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_selected_relation_removal_and_late_foreign_change_are_guarded_and_atomic(self):
#         with self.base.connect() as connection:
#             declared, _ = self.seed(connection)
#             asserted, _ = self.seed(connection, ownership='asserted')
#             original = self.relation(connection, declared)
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             missing = self.relation(connection, declared)
#             self.apply(connection, asserted, remove=True)
#             self.assertIsNone(self.relation(connection, asserted))
#             self.assertEqual(self.relation(connection, declared), missing)
#             self.fixture.source.write_bytes(self.fixture.source_bytes)
#             before = self.state(connection)
#             with self.assertRaises(EvidenceError):
#                 self.apply(connection, declared, remove=True)
#             self.assertEqual(self.state(connection), before)
#             self.fixture.publish(connection)
#             self.fixture.source.write_bytes(b'# Source\nNew source.\n')
#             before = self.state(connection)
#             def late_change(repository, counts):
#                 self.fixture.answer.write_bytes(b'# Answer\nChanged during reply callback.\n')
#                 return counts
#             with self.assertRaises(EvidenceError):
#                 self.fixture.publish(connection, reply_counts=late_change)
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
