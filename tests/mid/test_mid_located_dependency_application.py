
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_real_producer_initial_pins_and_exact_activity_commit_and_noop_is_quiet
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Real producer initial pins and exact activity commit and noop is quiet.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_producer_initial_pins_and_exact_activity_commit_and_noop_is_quiet(self):
#         with self.base.connect() as connection:
#             with MutationActivity(connection, build=1).session() as activity:
#                 result = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): result.counts})
#             rows = self.current(connection)
#             self.assertEqual(set(rows), {'disk', 'branch'})
#             self.assertEqual(result.counts['pinsCaptured'], 2)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 2)
#             entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
#             self.assertEqual(activity_state(connection, entry)['counts'], result.counts)
#             before = self.base.state(connection)
#             with MutationActivity(connection, build=1).session() as activity:
#                 repeated = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): repeated.counts})
#             self.assertFalse(repeated.changed)
#             self.assertEqual(self.base.state(connection), before)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_normalized_edit_inherits_own_pin_and_substantive_edit_captures_current_source
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Normalized edit inherits own pin and substantive edit captures current source.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_normalized_edit_inherits_own_pin_and_substantive_edit_captures_current_source(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             original = self.current(connection)
#             old_manifest = self.manifest(connection, original['disk'])
#             path = self.base.artifact / 'guide.md'
#             (self.base.artifact / 'source.md').write_bytes(b'# Source\nNew source.\n# Other\nOther body.\n')
#             path.write_bytes(path.read_bytes().replace(b'Plain body.', b'Plain   body.'))
#             inherited = self.publish(connection)
#             rows = self.current(connection)
#             self.assertEqual(inherited.counts['pinsInherited'], 1)
#             self.assertNotEqual(rows['disk'][1], original['disk'][1])
#             self.assertEqual(rows['branch'], original['branch'])
#             self.assertEqual(self.manifest(connection, rows['disk'])['pinnedHash'], old_manifest['pinnedHash'])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0], 3)
#             path.write_bytes(path.read_bytes().replace(b'Plain   body.', b'Substantive changed body.'))
#             edited = self.publish(connection)
#             rows = self.current(connection)
#             self.assertEqual(edited.counts['pinsCaptured'], 1)
#             self.assertNotEqual(self.manifest(connection, rows['disk'])['pinnedHash'], old_manifest['pinnedHash'])
#             self.assertEqual(rows['branch'], original['branch'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_qualified_alias_change_keeps_baseline_and_immutable_audit_spelling
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Qualified alias change keeps baseline and immutable audit spelling.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_qualified_alias_change_keeps_baseline_and_immutable_audit_spelling(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             original = self.current(connection)
#             path = self.base.artifact / 'guide.md'
#             path.write_bytes(path.read_bytes().replace(b'fixture:@artifact/source.md', b'fixture:source.md'))
#             result = self.publish(connection)
#             rows = self.current(connection)
#             self.assertEqual(rows['disk'][0:3], original['disk'][0:3])
#             self.assertEqual(rows['disk'][4:], original['disk'][4:])
#             self.assertEqual(_text(rows['disk'][3]['rawRef']), 'fixture:source.md#Source')
#             self.assertEqual((result.counts['pinsCaptured'], result.counts['pinsInherited']), (0, 0))
#             self.assertEqual(rows['branch'], original['branch'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_restored_exact_disk_version_uses_its_own_old_pin_after_newer_edit
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Restored exact disk version uses its own old pin after newer edit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_restored_exact_disk_version_uses_its_own_old_pin_after_newer_edit(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             original = self.current(connection)
#             path = self.base.artifact / 'guide.md'
#             original_bytes = path.read_bytes()
#             (self.base.artifact / 'source.md').write_bytes(b'# Source\nNew source.\n# Other\nOther body.\n')
#             path.write_bytes(original_bytes.replace(b'Plain body.', b'Edited dependant.'))
#             self.publish(connection)
#             later = self.current(connection)
#             self.assertNotEqual(later['disk'][6], original['disk'][6])
#             path.write_bytes(original_bytes)
#             result = self.publish(connection)
#             restored = self.current(connection)
#             self.assertEqual(restored['disk'][0:3], original['disk'][0:3])
#             self.assertEqual(restored['disk'][4:], original['disk'][4:])
#             self.assertEqual((result.counts['pinsCaptured'], result.counts['pinsInherited']), (0, 0))
#             self.assertEqual(restored['branch'], original['branch'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_recognized_source_move_updates_current_binding_without_renewing_audit_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Recognized source move updates current binding without renewing audit pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recognized_source_move_updates_current_binding_without_renewing_audit_pin(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             original = self.current(connection)
#             (self.base.artifact / 'source.md').rename(self.base.artifact / 'moved.md')
#             result = self.publish(connection)
#             moved = self.current(connection)
#             self.assertEqual(moved['disk'][0:3], original['disk'][0:3])
#             self.assertEqual(moved['disk'][4:], original['disk'][4:])
#             self.assertEqual(moved['disk'][3]['resolution']['place'], 'fixture:@artifact/moved.md#Source')
#             self.assertEqual(self.manifest(connection, moved['disk'])['source']['path'], 'source.md')
#             self.assertEqual((result.counts['pinsCaptured'], result.counts['pinsInherited']), (0, 0))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_missing_source_retains_pin_until_substantive_dependant_edit_withdraws_it
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Missing source retains pin until substantive dependant edit withdraws it.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_source_retains_pin_until_substantive_dependant_edit_withdraws_it(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             original = self.current(connection)
#             (self.base.artifact / 'source.md').unlink()
#             self.publish(connection)
#             removed = self.current(connection)
#             self.assertEqual(removed['disk'][4], original['disk'][4])
#             self.assertEqual(removed['disk'][3]['sourceState'], 'source_removed')
#             path = self.base.artifact / 'guide.md'
#             path.write_bytes(path.read_bytes().replace(b'Plain body.', b'Changed body after removal.'))
#             self.publish(connection)
#             current = self.current(connection)
#             self.assertIsNone(current['disk'][4])
#             self.assertEqual(current['disk'][3]['resolution']['fault'], 'missing_file')
#             self.assertEqual(current['branch'], original['branch'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_cycle_and_late_audit_failure_roll_back_all_policy_and_capture_rows
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Cycle and late audit failure roll back all policy and capture rows.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cycle_and_late_audit_failure_roll_back_all_policy_and_capture_rows(self):
#         with self.base.connect() as connection:
#             before = self.base.state(connection)
#             with MutationActivity(connection, build=1).session() as activity:
#                 with patch.object(activity, '_details', side_effect=RuntimeError('fixture audit failure')):
#                     with self.assertRaises(RuntimeError):
#                         self.publish(connection, activity=activity)
#                 self.assertEqual(self.base.state(connection), before)
#                 activity.finish('failed', error={'code': 'internal', 'message': 'fixture failed'})
#             (self.base.artifact / 'source.md').write_bytes(
#                 b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Source\nSource cycle.\n')
#             with self.assertRaises(ReconciliationError) as error:
#                 self.publish(connection)
#             self.assertEqual(error.exception.status, 'dependency_cycle')
#             self.assertEqual(self.base.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_collect_dead_exact_version_after_policy_preserves_other_locations_and_current_pins
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Collect dead exact version after policy preserves other locations and current pins.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_collect_dead_exact_version_after_policy_preserves_other_locations_and_current_pins(self):
#         with self.base.connect() as connection:
#             self.publish(connection, collect=True)
#             original = self.current(connection)
#             path = self.base.artifact / 'guide.md'
#             path.write_bytes(path.read_bytes().replace(b'Plain body.', b'Plain   body.'))
#             self.publish(connection, collect=True)
#             inherited = self.current(connection)['disk']
#             path.write_bytes(path.read_bytes().replace(b'Plain   body.', b'Final substantive text.'))
#             result = self.publish(connection, collect=True)
#             current = self.current(connection)
#             self.assertEqual(result.counts['collected']['versions'], 1)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
#                 (inherited[1],)).fetchone()[0], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
#                 (inherited[4],)).fetchone()[0], 0)
#             self.assertEqual(current['branch'], original['branch'])
#             self.assertIsNotNone(current['disk'][4])
#             self.assertEqual(self.manifest(connection, current['disk'])['dependantVersion'], str(current['disk'][1]))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_complete_acyclic_declaration_reversal_does_not_depend_on_file_order
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Complete acyclic declaration reversal does not depend on file order.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_acyclic_declaration_reversal_does_not_depend_on_file_order(self):
#         (self.base.artifact / 'a.md').write_bytes(b'# A\nAlpha.\n')
#         (self.base.artifact / 'z.md').write_bytes(
#             b'---\nsources: ["fixture:@artifact/a.md#A"]\n---\n# Z\nZulu.\n')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.publish(connection)
#             (self.base.artifact / 'a.md').write_bytes(
#                 b'---\nsources: ["fixture:@artifact/z.md#Z"]\n---\n# A\nAlpha.\n')
#             (self.base.artifact / 'z.md').write_bytes(b'# Z\nZulu.\n')
#             result = self.publish(connection)
#             self.assertEqual(result.counts['dependenciesReleased'], 1)
#             self.assertEqual(result.counts['pinsCaptured'], 1)
#             rows = connection.execute("""SELECT c.metadata->>'name',d.declaration,l.kind
#                 FROM public.mycel_dependencies d JOIN public.mycel_chunk_versions c ON c.id=d.dependant_version
#                 JOIN public.mycel_file_locations l ON l.id=(d.state->'declarationLocation'->>'file')::uuid
#                 WHERE d.kind='declared' AND l.kind='disk' ORDER BY d.declaration""").fetchall()
#             self.assertTrue(any(name=='A' and declaration=='fixture:@artifact/z.md#Z' for name,declaration,_ in rows))
#             self.assertFalse(any(name=='Z' and declaration=='fixture:@artifact/a.md#A' for name,declaration,_ in rows))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_stale_foreign_source_or_recreated_missing_path_refuses_complete_owner_change
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Stale foreign source or recreated missing path refuses complete owner change.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_stale_foreign_source_or_recreated_missing_path_refuses_complete_owner_change(self):
#         foreign = self.base.base / 'foreign'
#         foreign.mkdir()
#         foreign_file = foreign / 'source.md'
#         foreign_file.write_bytes(b'# Source\nForeign source.\n')
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.foreign]\nenabled=true\nartifact_root="' + str(foreign) + '"\n')
#         self.base.settings = load_settings(path=self.base.config, home=self.base.base)
#         path = self.base.artifact / 'guide.md'
#         path.write_bytes(path.read_bytes().replace(b'fixture:@artifact/source.md', b'foreign:@artifact/source.md'))
#         self.base.commit()
#         with self.base.connect() as connection:
#             LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'foreign'))
#             self.publish(connection)
#             before = self.base.state(connection)
#             original = path.read_bytes()
#             foreign_file.write_bytes(b'# Source\nUnindexed foreign change.\n')
#             path.write_bytes(original.replace(b'Plain body.', b'Edit requiring new source.'))
#             from mycel._evidence import EvidenceError
#             with self.assertRaises(EvidenceError) as error:
#                 self.publish(connection)
#             self.assertEqual(error.exception.status, 'changed_since_ingest')
#             self.assertEqual(self.base.state(connection), before)
#             path.write_bytes(original)
#             foreign_file.unlink()
#             LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'foreign'),
#                                                  confirm_empty=True)
#             foreign_file.write_bytes(b'# Source\nRecreated but unindexed.\n')
#             before = self.base.state(connection)
#             path.write_bytes(original.replace(b'Plain body.', b'Edit after apparent deletion.'))
#             with self.assertRaises(EvidenceError) as error:
#                 self.publish(connection)
#             self.assertEqual(error.exception.status, 'changed_since_ingest')
#             self.assertEqual(self.base.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_recreated_unindexed_foreign_raw_path_cannot_hide_behind_a_retained_move
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Recreated unindexed foreign raw path cannot hide behind a retained move.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recreated_unindexed_foreign_raw_path_cannot_hide_behind_a_retained_move(self):
#         foreign = self.base.base / 'foreign-move'
#         foreign.mkdir()
#         source = foreign / 'source.md'
#         source.write_bytes(b'# Source\nForeign original.\n')
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.foreign]\nenabled=true\nartifact_root="' + str(foreign) + '"\n')
#         self.base.settings = load_settings(path=self.base.config, home=self.base.base)
#         path = self.base.artifact / 'guide.md'
#         path.write_bytes(path.read_bytes().replace(b'fixture:@artifact/source.md', b'foreign:@artifact/source.md'))
#         self.base.commit()
#         with self.base.connect() as connection:
#             LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'foreign'))
#             self.publish(connection)
#             source.rename(foreign / 'moved.md')
#             LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'foreign'))
#             path.write_bytes(path.read_bytes().replace(b'Plain body.', b'Plain   body.'))
#             self.publish(connection)
#             moved = self.current(connection)['disk']
#             self.assertEqual(moved[3]['resolution']['place'], 'foreign:@artifact/moved.md#Source')
#             before = self.base.state(connection)
#             source.write_bytes(b'# Source\nRecreated source.\n')
#             path.write_bytes(path.read_bytes().replace(b'Plain   body.', b'Edited dependant.'))
#             from mycel._evidence import EvidenceError
#             with MutationActivity(connection, build=1).session() as activity:
#                 with self.assertRaises(EvidenceError) as error:
#                     self.publish(connection, activity=activity)
#                 self.assertEqual(error.exception.status, 'changed_since_ingest')
#                 self.assertEqual(self.base.state(connection), before)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
#                 activity.finish('failed', error={'code': 'invalid_input', 'message': 'Source changed.'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_dependency_application.py::LocatedDependencyApplicationStoreTests.test_unindexed_foreign_legacy_path_collision_refuses_repin_and_complete_owner_publication
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unindexed foreign legacy path collision refuses repin and complete owner publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_dependency_application.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unindexed_foreign_legacy_path_collision_refuses_repin_and_complete_owner_publication(self):
#         foreign = self.base.base / 'foreign-collision'
#         code, artifact = foreign / 'code', foreign / 'artifact'
#         code.mkdir(parents=True)
#         artifact.mkdir()
#         (artifact / 'source.md').write_bytes(b'# Source\nOriginal foreign source.\n')
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.foreign]\nenabled=true\ncode_root="' +
#             str(code) + '"\nartifact_root="' + str(artifact) + '"\n')
#         self.base.settings = load_settings(path=self.base.config, home=self.base.base)
#         path = self.base.artifact / 'guide.md'
#         path.write_bytes(path.read_bytes().replace(b'fixture:@artifact/source.md', b'foreign:source.md'))
#         self.base.commit()
#         with self.base.connect() as connection:
#             LocatedCaptureStore(connection).apply(self.base.settings, capture_repository(self.base.settings, 'foreign'))
#             self.publish(connection)
#             original = self.current(connection)['disk']
#             self.assertEqual(original[3]['resolution']['place'], 'foreign:@artifact/source.md#Source')
#             before = self.base.state(connection)
#             (code / 'source.md').write_bytes(b'# Source\nNew unindexed colliding source.\n')
#             path.write_bytes(path.read_bytes().replace(b'Plain body.', b'Edited dependant against colliding path.'))
#             from mycel._evidence import EvidenceError
#             with MutationActivity(connection, build=1).session() as activity:
#                 with self.assertRaises(EvidenceError) as error:
#                     self.publish(connection, activity=activity)
#                 self.assertEqual(error.exception.status, 'changed_since_ingest')
#                 self.assertEqual(self.base.state(connection), before)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
#                 activity.finish('failed', error={'code': 'invalid_input', 'message': 'Source changed.'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END
