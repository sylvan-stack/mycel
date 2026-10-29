
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_initial_resolution_schedules_capture_without_claiming_captured_evidence
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Initial resolution schedules capture without claiming captured evidence.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_initial_resolution_schedules_capture_without_claiming_captured_evidence(self):
#         plan = self.plan((DependencyRequest('new', 'declared', self.declaration),), source=self.src)
#         decision = plan.decisions[0]
#         self.assertEqual((decision.action, decision.baseline, decision.source_state), ('capture', None, 'present'))
#         self.assertEqual(plan.role, 'derived')
#         self.assertEqual(plan.graph, (GraphEdge('source-chunk', 'answer', 'new'),))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_unresolved_first_reference_remains_visible_without_removed_baseline
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unresolved first reference remains visible without removed baseline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unresolved_first_reference_remains_visible_without_removed_baseline(self):
#         for absent in (None, 'away', 'deleted'):
#             plan = self.plan((DependencyRequest('new', 'declared', self.declaration, absent),))
#             decision = plan.decisions[0]
#             self.assertEqual((decision.action, decision.baseline, decision.source_state, decision.reasons),
#                              ('unresolved', None, 'unresolved', ()))
#             self.assertEqual(decision.fault, 'missing_file')
#             self.assertEqual(plan.role, 'unclassified')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_missing_previously_resolved_source_retains_every_baseline_and_governs_role
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Missing previously resolved source retains every baseline and governs role.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_previously_resolved_source_retains_every_baseline_and_governs_role(self):
#         old = self.record()
#         for state in ('away', 'deleted'):
#             decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration, state),), (old,)).decisions[0]
#             self.assertIs(decision.baseline, old.baseline)
#             self.assertEqual((decision.action, decision.source_state, decision.reasons), ('keep', state, ('source_removed',)))
#             self.assertEqual(decision.natural_place, old.natural_place)
#             self.assertEqual(decision.active_sources, ())
#             self.assertEqual(self.plan((DependencyRequest(old.identifier, 'declared', self.declaration, state),), (old,)).role, 'derived')
#         with self.assertRaises(ReconciliationError):
#             self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_recreation_joins_new_identifier_without_renewing_the_old_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Recreation joins new identifier without renewing the old pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recreation_joins_new_identifier_without_renewing_the_old_pin(self):
#         old = self.record()
#         recreated = document('source', 'source.md', '# Source\nNew source.\n', identifier='recreated', version=22)
#         decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=recreated).decisions[0]
#         self.assertEqual((decision.action, decision.active_sources, decision.reasons), ('keep', ('recreated',), ('source_changed',)))
#         self.assertIs(decision.baseline, old.baseline)
#         self.assertEqual(decision.baseline.identifier, old.baseline.identifier)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_source_changes_and_sibling_file_changes_do_not_authorize_repinning
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Source changes and sibling file changes do not authorize repinning.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_changes_and_sibling_file_changes_do_not_authorize_repinning(self):
#         old = self.record()
#         changed = document('source', 'source.md', '# Source\nChanged.\n', identifier='source-chunk', version=8)
#         decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=changed).decisions[0]
#         self.assertEqual(decision.action, 'keep')
#         self.assertIs(decision.baseline, old.baseline)
#         self.assertEqual(decision.reasons, ('source_changed',))
#         self.dep = replace(self.dep, source=self.dep.source + b'# Sibling\nNew text.\n',
#                            snapshot_hash=sha256(self.dep.source + b'# Sibling\nNew text.\n').hexdigest())
#         self.assertEqual(self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=changed).decisions[0].action, 'keep')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_disabled_and_unregistered_targets_keep_baseline_but_are_not_governing
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Disabled and unregistered targets keep baseline but are not governing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disabled_and_unregistered_targets_keep_baseline_but_are_not_governing(self):
#         old = self.record()
#         for enabled, registered, fault in ((False, True, 'disabled_repository'), (True, False, 'unregistered_repository')):
#             plan = plan_dependencies(member(self.dep), self.resolver(self.src, enabled=enabled, registered=registered),
#                 (DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), pin_version=1)
#             decision = plan.decisions[0]
#             self.assertEqual((decision.action, decision.source_state, decision.reasons, decision.fault),
#                              ('keep', 'ineligible', (), fault))
#             self.assertIs(decision.baseline, old.baseline)
#             self.assertEqual(plan.role, 'unclassified')
#             self.assertEqual(plan.graph, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_empty_file_and_empty_chunk_are_present_and_govern_role
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Empty file and empty chunk are present and govern role.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_empty_file_and_empty_chunk_are_present_and_govern_role(self):
#         empty = document('source', 'empty.md', '')
#         self.assertEqual(empty.chunks, ())
#         plan = self.plan((DependencyRequest('empty', 'declared', 'source:empty.md'),), source=empty)
#         self.assertEqual((plan.role, plan.graph, plan.decisions[0].source_state), ('derived', (), 'present'))
#         heading = document('source', 'source.md', '# Source\n')
#         self.assertEqual(self.plan((DependencyRequest('heading', 'declared', self.declaration),), source=heading).role, 'derived')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_declared_removal_never_removes_an_assertion_between_the_same_ends
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Declared removal never removes an assertion between the same ends.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_declared_removal_never_removes_an_assertion_between_the_same_ends(self):
#         declared, asserted = self.record(), self.record('asserted-link', 'asserted')
#         plan = self.plan((), (declared, asserted), source=self.src)
#         by_id = {decision.identifier: decision for decision in plan.decisions}
#         self.assertEqual(by_id[declared.identifier].action, 'release')
#         self.assertEqual(by_id[asserted.identifier].action, 'keep')
#         self.assertEqual(plan.graph, (GraphEdge('source-chunk', 'answer', 'asserted-link'),))
#         self.assertEqual(plan.role, 'derived')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_asserted_removal_is_selection_exact_and_leaves_declared_record
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Asserted removal is selection exact and leaves declared record.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_asserted_removal_is_selection_exact_and_leaves_declared_record(self):
#         declared, asserted = self.record(), self.record('asserted-link', 'asserted')
#         requests = (DependencyRequest(declared.identifier, 'declared', self.declaration),)
#         plan = self.plan(requests, (declared, asserted), source=self.src,
#                          remove_assertions=(AssertedRemoval(asserted.natural_place, 'chunk'),))
#         self.assertEqual({decision.identifier: decision.action for decision in plan.decisions},
#                          {'declared-link': 'keep', 'asserted-link': 'release'})
#         absent = AssertedRemoval(SourceAddress('source', 'artifact', 'other.md', 'Other'), 'chunk')
#         self.assertEqual(self.plan(requests, (declared, asserted), source=self.src, remove_assertions=(absent,)).decisions[-1].action, 'keep')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_asserted_removal_of_absent_source_requires_no_new_capture
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Asserted removal of absent source requires no new capture.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_asserted_removal_of_absent_source_requires_no_new_capture(self):
#         old = self.record('asserted-link', 'asserted')
#         request = DependencyRequest(old.identifier, 'asserted', self.declaration, 'deleted')
#         decision = self.plan((request,), (old,), remove_assertions=(AssertedRemoval(old.natural_place, 'chunk'),)).decisions[0]
#         self.assertEqual(decision.action, 'release')
#         self.assertIs(decision.baseline, old.baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_confirmation_withdraws_old_missing_source_but_refuses_new_fault_atomically
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Confirmation withdraws old missing source but refuses new fault atomically.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_confirmation_withdraws_old_missing_source_but_refuses_new_fault_atomically(self):
#         old = self.record()
#         request = DependencyRequest(old.identifier, 'declared', self.declaration, 'deleted')
#         plan = self.plan((request,), (old,), mode='confirm')
#         self.assertEqual((plan.decisions[0].action, plan.decisions[0].fault, plan.role), ('withdraw', 'missing_file', 'unclassified'))
#         for bad in ('source:unknown.md', 'bad ref', 'disabled:thing'):
#             with self.subTest(bad=bad), self.assertRaises(ReconciliationError) as caught:
#                 self.plan((request, DependencyRequest('bad', 'declared', bad)), (old,), mode='confirm')
#             self.assertEqual((caught.exception.status, caught.exception.dependencies), ('invalid_input', ('bad',)))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_authorized_confirmation_schedules_capture_and_identical_assertion_scan_is_noop
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Authorized confirmation schedules capture and identical assertion scan is noop.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_authorized_confirmation_schedules_capture_and_identical_assertion_scan_is_noop(self):
#         old = self.record('asserted-link', 'asserted')
#         observed = self.plan((), (old,), source=self.src)
#         confirmed = self.plan((), (old,), source=self.src, mode='confirm')
#         self.assertEqual((observed.decisions[0].action, confirmed.decisions[0].action), ('keep', 'capture'))
#         self.assertIs(confirmed.decisions[0].baseline, old.baseline)
#         with self.assertRaises(ReconciliationError):
#             self.plan((DependencyRequest('different-id', 'asserted', self.declaration),), (old,), source=self.src)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_exact_restoration_uses_that_versions_pin_and_rejects_the_later_pin
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Exact restoration uses that versions pin and rejects the later pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_restoration_uses_that_versions_pin_and_rejects_the_later_pin(self):
#         old = self.record()
#         self.dep = document('owner', 'answer.md', '# Answer\nChanged answer.\n', identifier='answer', version=2)
#         later = self.record()
#         self.dep = document('owner', 'answer.md', '# Answer\nAnswer body.\n', identifier='answer', version=1)
#         request = DependencyRequest(old.identifier, 'declared', self.declaration)
#         decision = self.plan((request,), (old,), source=self.src, mode='restore').decisions[0]
#         self.assertIs(decision.baseline, old.baseline)
#         self.assertEqual(decision.action, 'keep')
#         with self.assertRaises(ReconciliationError):
#             self.plan((request,), (later,), source=self.src, mode='restore')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_normalized_edit_and_heading_rename_inherit_instead_of_recapturing
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Normalized edit and heading rename inherit instead of recapturing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_normalized_edit_and_heading_rename_inherit_instead_of_recapturing(self):
#         old = self.record()
#         self.dep = document('owner', 'answer.md', '# Renamed\nAnswer\t body.\n', identifier='answer', version=2)
#         request = DependencyRequest(old.identifier, 'declared', self.declaration)
#         decision = self.plan((request,), (old,), source=self.src, mode='inherit', pin_version=1).decisions[0]
#         self.assertEqual(decision.action, 'inherit')
#         self.assertIs(decision.baseline, old.baseline)
#         with self.assertRaises(ReconciliationError):
#             self.plan((request,), (old,), source=self.src, mode='edit', pin_version=1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_substantive_edit_schedules_capture_or_withdraws_missing_and_never_confirms_a_normalized_edit
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Substantive edit schedules capture or withdraws missing and never confirms a normalized edit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_substantive_edit_schedules_capture_or_withdraws_missing_and_never_confirms_a_normalized_edit(self):
#         old = self.record()
#         self.dep = document('owner', 'answer.md', '# Answer\nSubstantive change.\n', identifier='answer', version=2)
#         request = DependencyRequest(old.identifier, 'declared', self.declaration)
#         self.assertEqual(self.plan((request,), (old,), source=self.src, mode='edit', pin_version=1).decisions[0].action, 'capture')
#         missing = replace(request, absent_state='away')
#         self.assertEqual(self.plan((missing,), (old,), mode='edit', pin_version=1).decisions[0].action, 'withdraw')
#         with self.assertRaises(ReconciliationError):
#             self.plan((request,), (old,), source=self.src, mode='inherit', pin_version=1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_missing_or_corrupt_baseline_can_never_be_treated_as_initial_resolution
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Missing or corrupt baseline can never be treated as initial resolution.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_or_corrupt_baseline_can_never_be_treated_as_initial_resolution(self):
#         request = DependencyRequest('previously-resolved', 'declared', self.declaration)
#         for status in ('baseline_missing', 'snapshot_corrupt', 'unsupported_comparison'):
#             with self.subTest(status=status), self.assertRaises(ReconciliationError) as caught:
#                 self.plan((request,), source=self.src, baseline_faults=(BaselineFault(request.identifier, status),))
#             self.assertEqual((caught.exception.status, caught.exception.dependencies), (status, (request.identifier,)))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_roles_recomputed_from_file_or_code_default_without_governing_dependencies
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Roles recomputed from file or code default without governing dependencies.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_roles_recomputed_from_file_or_code_default_without_governing_dependencies(self):
#         self.assertEqual(self.plan(file_role='authored').role, 'authored')
#         self.assertEqual(self.plan(file_role='derived').role, 'derived')
#         self.assertEqual(self.plan().role, 'unclassified')
#         self.dep = replace(self.dep, chunks=(replace(self.dep.chunks[0], kind='code', body=None, body_span=None,
#             comparison=exact_comparison(self.dep.chunks[0].source, 'code_text').as_dict()),))
#         self.assertEqual(self.plan().role, 'authored')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_whole_operation_refuses_self_cycle_and_cross_repository_cycle
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Whole operation refuses self cycle and cross repository cycle.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_whole_operation_refuses_self_cycle_and_cross_repository_cycle(self):
#         self_ref = DependencyRequest('self', 'declared', 'owner:answer.md#Answer')
#         with self.assertRaises(ReconciliationError) as caught:
#             self.plan((self_ref,), source=self.src)
#         self.assertEqual(caught.exception.cycle, ('answer', 'answer'))
#         request = DependencyRequest('new', 'declared', self.declaration)
#         graph = (GraphEdge('answer', 'intermediate', 'other'), GraphEdge('intermediate', 'source-chunk', 'other-2'))
#         with self.assertRaises(ReconciliationError) as caught:
#             self.plan((request,), source=self.src, graph=graph)
#         self.assertEqual(set(caught.exception.cycle[:-1]), {'answer', 'intermediate', 'source-chunk'})
#         self.assertEqual(caught.exception.cycle[0], caught.exception.cycle[-1])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_cycle_result_is_independent_of_insert_order_and_large_graph_is_iterative
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Cycle result is independent of insert order and large graph is iterative.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cycle_result_is_independent_of_insert_order_and_large_graph_is_iterative(self):
#         request = DependencyRequest('new', 'declared', self.declaration)
#         edges = (GraphEdge('answer', 'middle', 'a'), GraphEdge('middle', 'source-chunk', 'b'), GraphEdge('other', 'end', 'c'))
#         cycles = set()
#         for order in permutations(edges):
#             with self.assertRaises(ReconciliationError) as caught:
#                 self.plan((request,), source=self.src, graph=order)
#             cycles.add(caught.exception.cycle)
#         self.assertEqual(len(cycles), 1)
#         large = tuple(GraphEdge(str(index), str(index + 1), 'chain:' + str(index)) for index in range(2000))
#         self.assertEqual(len(self.plan(graph=large).graph), 2000)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_owned_graph_edges_are_replaced_and_other_kinds_are_preserved
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Owned graph edges are replaced and other kinds are preserved.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_owned_graph_edges_are_replaced_and_other_kinds_are_preserved(self):
#         old = self.record()
#         graph = (GraphEdge('source-chunk', 'answer', old.identifier), GraphEdge('answer', 'source-chunk', 'elsewhere'))
#         plan = self.plan((), (old,), graph=graph)
#         self.assertEqual(plan.graph, (graph[1],))
#         self.assertEqual(plan.decisions[0].action, 'release')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_file_selection_expands_every_current_chunk_for_cycle_check
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: File selection expands every current chunk for cycle check.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_file_selection_expands_every_current_chunk_for_cycle_check(self):
#         source = document('source', 'source.md', '# First\nFirst.\n# Second\nSecond.\n')
#         requests = (DependencyRequest('file', 'declared', 'source:source.md'),)
#         plan = self.plan(requests, source=source)
#         self.assertEqual(len(plan.graph), 2)
#         graph = (GraphEdge('answer', source.chunks[-1].identifier, 'back'),)
#         with self.assertRaises(ReconciliationError):
#             self.plan(requests, source=source, graph=graph)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_family_added_and_removed_members_keep_complete_old_baseline
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Family added and removed members keep complete old baseline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_family_added_and_removed_members_keep_complete_old_baseline(self):
#         initial = code('class C:\n    def first(self):\n        return 1\n\n    def second(self):\n        return 2\n')
#         old = self.record(source=initial, declaration='source:code.py#C')
#         before = old.baseline.canonical_bytes
#         changed = code('class C:\n    def first(self):\n        return 1\n\n    def third(self):\n        return 3\n')
#         request = DependencyRequest(old.identifier, 'declared', 'source:code.py#C')
#         decision = self.plan((request,), (old,), source=changed).decisions[0]
#         self.assertEqual(decision.action, 'keep')
#         self.assertEqual(decision.reasons, ('source_removed', 'source_changed'))
#         self.assertEqual(old.baseline.canonical_bytes, before)
#         self.assertIn('code:C.third', decision.active_sources)
#         self.assertNotIn('code:C.second', decision.active_sources)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_alias_spelling_keeps_identity_pin_original_declaration_and_natural_place
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Alias spelling keeps identity pin original declaration and natural place.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_alias_spelling_keeps_identity_pin_original_declaration_and_natural_place(self):
#         old = self.record()
#         request = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source')
#         decision = self.plan((request,), (old,), source=self.src).decisions[0]
#         self.assertEqual(decision.action, 'keep')
#         self.assertEqual(decision.declaration, request.declaration)
#         self.assertEqual(decision.baseline.payload['ref'], self.declaration)
#         self.assertEqual(decision.natural_place, old.natural_place)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_frozen_decisions_and_invalid_request_observations
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Frozen decisions and invalid request observations.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_frozen_decisions_and_invalid_request_observations(self):
#         plan = self.plan((DependencyRequest('new', 'declared', self.declaration),), source=self.src)
#         with self.assertRaises(FrozenInstanceError):
#             plan.role = 'authored'
#         with self.assertRaises(ReconciliationError):
#             self.plan((DependencyRequest('new', 'declared', self.declaration, 'deleted'),), source=self.src)
#         with self.assertRaises(ReconciliationError):
#             self.plan((DependencyRequest('same', 'declared', self.declaration), DependencyRequest('same', 'asserted', self.declaration)), source=self.src)
#         with self.assertRaises(ReconciliationError):
#             self.plan((DependencyRequest('bad', 'declared', 'bad ref', 'deleted'),))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_reusing_a_record_id_cannot_rebind_an_unrelated_selection
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Reusing a record id cannot rebind an unrelated selection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_reusing_a_record_id_cannot_rebind_an_unrelated_selection(self):
#         old = self.record()
#         unrelated = document('source', 'other.md', '# Other\nOther bytes.\n', identifier='unrelated')
#         resolver = SourceResolver(settings(), (self.dep, self.src, unrelated))
#         with self.assertRaises(ReconciliationError):
#             plan_dependencies(member(self.dep), resolver,
#                 (DependencyRequest(old.identifier, 'declared', 'source:other.md#Other'),), (old,), pin_version=1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_recognized_move_retains_natural_place_when_current_identity_is_the_same
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Recognized move retains natural place when current identity is the same.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recognized_move_retains_natural_place_when_current_identity_is_the_same(self):
#         old = self.record()
#         moved = document('source', 'moved.md', '# Source\nOld source.\n', identifier='source-chunk')
#         request = DependencyRequest(old.identifier, 'declared', 'source:moved.md#Source')
#         decision = self.plan((request,), (old,), source=moved).decisions[0]
#         self.assertEqual(decision.action, 'keep')
#         self.assertEqual(decision.natural_place, old.natural_place)
#         self.assertEqual(decision.current_selection.place.path, 'moved.md')
#         self.assertIs(decision.baseline, old.baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_unaffected_incoming_authoritative_graph_edge_governs_role
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unaffected incoming authoritative graph edge governs role.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unaffected_incoming_authoritative_graph_edge_governs_role(self):
#         incoming = GraphEdge('unaffected-source', 'answer', 'unaffected-generated')
#         self.assertEqual(self.plan(graph=(incoming,)).role, 'derived')
#         outgoing = GraphEdge('answer', 'other', 'outgoing')
#         self.assertEqual(self.plan(graph=(outgoing,)).role, 'unclassified')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_current_dependant_must_be_exactly_the_enabled_catalog_endpoint
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Current dependant must be exactly the enabled catalog endpoint.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_current_dependant_must_be_exactly_the_enabled_catalog_endpoint(self):
#         fake = document('owner', 'not-in-catalog.md', '# Fake\nFake.\n', identifier='fake')
#         resolver = self.resolver(self.src)
#         with self.assertRaises(ReconciliationError):
#             plan_dependencies(member(fake), resolver,
#                 (DependencyRequest('new', 'declared', self.declaration),), (), pin_version=1)
#         altered = replace(member(self.dep), chunk=replace(self.dep.chunks[0], version=99))
#         with self.assertRaises(ReconciliationError):
#             plan_dependencies(altered, resolver, (), (), pin_version=99)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_missing_disabled_and_malformed_rebinding_cannot_reuse_old_dependency_id
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Missing disabled and malformed rebinding cannot reuse old dependency id.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_disabled_and_malformed_rebinding_cannot_reuse_old_dependency_id(self):
#         old = self.record()
#         for declaration, state in (('source:other.md#Other', 'deleted'), ('unknown:source.md#Source', None), ('bad ref', None)):
#             with self.subTest(declaration=declaration), self.assertRaises(ReconciliationError):
#                 self.plan((DependencyRequest(old.identifier, 'declared', declaration, state),), (old,))
#         disabled = self.resolver(enabled=False)
#         with self.assertRaises(ReconciliationError):
#             plan_dependencies(member(self.dep), disabled,
#                 (DependencyRequest(old.identifier, 'declared', 'source:other.md#Other'),), (old,), pin_version=1)
#         equivalent = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source', 'deleted')
#         self.assertEqual(self.plan((equivalent,), (old,)).decisions[0].action, 'keep')
#         new = DependencyRequest('new-target', 'declared', 'source:other.md#Other', 'deleted')
#         plan = self.plan((new,), (old,))
#         self.assertEqual({decision.identifier: decision.action for decision in plan.decisions},
#                          {old.identifier: 'release', 'new-target': 'unresolved'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_recreated_anchor_can_move_again_without_replacing_audit_baseline
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Recreated anchor can move again without replacing audit baseline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recreated_anchor_can_move_again_without_replacing_audit_baseline(self):
#         old = self.record()
#         recreated = document('source', 'source.md', '# Source\nRecreated.\n', identifier='recreated')
#         request = DependencyRequest(old.identifier, 'declared', self.declaration)
#         reconnected = self.plan((request,), (old,), source=recreated).decisions[0]
#         retained = replace(old, retained_place=reconnected.current_selection.place, current_anchor='recreated',
#                            current_declaration=request.declaration)
#         moved = document('source', 'moved.md', '# Source\nRecreated.\n', identifier='recreated')
#         moved_request = replace(request, declaration='source:moved.md#Source')
#         decision = self.plan((moved_request,), (retained,), source=moved).decisions[0]
#         self.assertEqual(decision.action, 'keep')
#         self.assertEqual(decision.active_sources, ('recreated',))
#         self.assertIs(decision.baseline, old.baseline)
#         after_move = replace(retained, retained_place=decision.current_selection.place,
#                              current_declaration=moved_request.declaration)
#         gone = replace(moved_request, absent_state='deleted')
#         missing = self.plan((gone,), (after_move,)).decisions[0]
#         self.assertEqual(missing.natural_place.path, 'moved.md')
#         self.assertEqual(missing.baseline.payload['source']['path'], 'source.md')
#         self.assertEqual(missing.reasons, ('source_removed',))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_new_matching_id_cannot_displace_an_unaffected_graph_dependency
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: New matching id cannot displace an unaffected graph dependency.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_new_matching_id_cannot_displace_an_unaffected_graph_dependency(self):
#         existing_generated = GraphEdge('generated-source', 'answer', 'collision')
#         request = DependencyRequest('collision', 'declared', self.declaration)
#         with self.assertRaises(ReconciliationError):
#             self.plan((request,), source=self.src, graph=(existing_generated,))
#         different_dependant = GraphEdge('elsewhere', 'other-answer', 'collision')
#         with self.assertRaises(ReconciliationError):
#             self.plan((request,), source=self.src, graph=(different_dependant,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_ambiguity_report_retains_typed_candidates_without_replacing_baseline
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Ambiguity report retains typed candidates without replacing baseline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ambiguity_report_retains_typed_candidates_without_replacing_baseline(self):
#         old = self.record()
#         secondary_place = SourceAddress('source', 'code', 'source.md')
#         secondary = replace(self.src, identifier='secondary-file', primary=secondary_place, aliases=(secondary_place,))
#         resolver = SourceResolver(settings(), (self.dep, self.src, secondary))
#         decision = plan_dependencies(member(self.dep), resolver,
#             (DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), pin_version=1).decisions[0]
#         self.assertEqual((decision.action, decision.source_state, decision.fault), ('keep', 'unresolved', 'ambiguous_path'))
#         self.assertEqual(decision.resolution.candidate_count, 2)
#         self.assertEqual(decision.resolution.candidates,
#                          ('source:@artifact/source.md', 'source:@code/source.md'))
#         self.assertIs(decision.baseline, old.baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_binding_output_updates_current_anchor_without_mutating_audit
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Binding output updates current anchor without mutating audit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_binding_output_updates_current_anchor_without_mutating_audit(self):
#         old = self.record()
#         recreated = document('source', 'source.md', '# Source\nRecreated.\n', identifier='recreated')
#         request = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source')
#         decision = self.plan((request,), (old,), source=recreated).decisions[0]
#         self.assertEqual((decision.binding.place, decision.binding.anchor, decision.binding.declaration),
#                          (decision.current_selection.place, 'recreated', request.declaration))
#         self.assertEqual(old.baseline.payload['members'][0]['id'], 'source-chunk')
#         self.assertEqual(old.baseline.payload['ref'], self.declaration)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_reconciliation.py::ReconciliationTests.test_real_parser_code_kinds_without_governing_dependencies_are_authored
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Real parser code kinds without governing dependencies are authored.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_reconciliation.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_parser_code_kinds_without_governing_dependencies_are_authored(self):
#         parsed = code('import os\n\nclass C:\n    def method(self):\n        return 1\n\ndef function():\n    return 2\n')
#         owner_place = SourceAddress('owner', 'code', 'code.py')
#         owner_file = replace(parsed, identifier='owner-code-file', repository='owner',
#                              primary=owner_place, aliases=(owner_place,))
#         resolver = SourceResolver(settings(), (owner_file,))
#         kinds = set()
#         for index, chunk in enumerate(owner_file.chunks):
#             with self.subTest(kind=chunk.kind, name=chunk.name):
#                 kinds.add(chunk.kind)
#                 plan = plan_dependencies(member(owner_file, index), resolver, (), (), pin_version=chunk.version)
#                 self.assertEqual(plan.role, 'authored')
#                 self.assertEqual(plan.graph, ())
#         self.assertTrue({'class', 'method', 'function'} <= kinds)
#         self.assertEqual(self.plan().role, 'unclassified')
# LOW-TIER-SOURCE-END
# LOW-TIER-END
