"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_drift_lifecycle as _support
# from test_drift_lifecycle import (
#     AT,
#     DriftLifecycleStoreTests,
#     DriftStore,
#     TABLES,
#     _FailAfterWrite,
#     fixtures,
#     json,
#     unittest,
# )


# class DriftLifecycleStoreTests(_support.DriftLifecycleStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_three_changed_sources_are_one_exact_version_drift_and_repeat_observation_is_stable
#     def test_three_changed_sources_are_one_exact_version_drift_and_repeat_observation_is_stable(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.assertEqual(self.report(connection)['drifts'], [])
#             self.change(connection)
#             drift = self.one(connection)
#             selected = SourceResolver.from_store(connection, self.base.settings).resolve(self.ref).selection.members[0]
#             self.assertEqual(drift['version'], sha256(selected.chunk.source).hexdigest())
#             self.assertEqual((drift['state'], drift['current']), ('open', True))
#             self.assertEqual({source['source']['address'] for source in drift['sources']}, set(self.addresses))
#             self.assertEqual(len({source['id'] for source in drift['sources']}), 3)
#             self.assertTrue(all(source['active'] and source['kind'] == 'source_changed'
#                 and source['link'] == 'declared' and source['classification']['status'] == 'pending_jev'
#                 for source in drift['sources']))
#             stable = self.state(connection)
#             self.sync(connection)
#             self.assertEqual(self.one(connection), drift)
#             self.assertEqual(self.state(connection), stable)
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_three_changed_sources_are_one_exact_version_drift_and_repeat_observation_is_stable

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_pending_uncertain_error_and_review_states_keep_work_and_jev_evidence
#     def test_pending_uncertain_error_and_review_states_keep_work_and_jev_evidence(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             ConfirmationStore(connection).apply(self.base.settings, self.ref, by='owner', captured_at=AT)
#             self.change(connection)
#             drift = self.one(connection)
#             immutable, stale = self.immutable(connection), self.stale(connection)
#             first = self.reason(drift)
#             jev = {'stage': 'jev', 'status': 'complete', 'judgement': 'insufficient_evidence',
#                 'provider': 'typesafe', 'model': 'jev-1.13.0', 'inputHash': first['pairHash'],
#                 'probabilities': {'needs_review': .4, 'insufficient_evidence': .5, 'still_supported': .1},
#                 'confidence': .25}
#             routed = self.record(connection, drift, first, status='needs_llm_review', evidence={'jev': jev})['drift']
#             self.assertTrue(self.reason(routed)['active'])
#             self.assertEqual(self.reason(routed)['classification']['status'], 'needs_llm_review')
#             self.assertEqual(self.reason(routed)['classification']['evidence']['jev'], jev)
#             review = {'stage': 'review', 'status': 'complete', 'judgement': 'needs_review',
#                 'provider': 'fictional', 'model': 'review-model-v1', 'inputHash': first['pairHash'],
#                 'rationale': 'The changed source requires checking.'}
#             reviewed = self.record(connection, routed, self.reason(routed), judgement='needs_review',
#                 evidence={'review': review})['drift']
#             evidence = self.reason(reviewed)['classification']['evidence']
#             self.assertEqual(evidence, {'jev': jev, 'review': review})
#             self.record(connection, reviewed, self.reason(reviewed, 2), judgement='insufficient_evidence')
#             self.record(connection, reviewed, self.reason(reviewed, 3), status='error',
#                 evidence={'error': {'kind': 'provider_result_invalid'}})
#             final = self.one(connection)
#             self.assertEqual(self.reason(final)['classification']['judgement'], 'needs_review')
#             self.assertEqual(self.reason(final, 2)['classification']['judgement'], 'insufficient_evidence')
#             self.assertEqual(self.reason(final, 3)['classification']['status'], 'error')
#             self.assertTrue(all(reason['active'] for reason in final['sources']))
#             self.assertEqual(self.immutable(connection), immutable)
#             self.assertEqual([(row[:3], {k: v for k, v in row[3].items() if k != 'classification'})
#                               for row in self.stale(connection)],
#                              [(row[:3], {k: v for k, v in row[3].items() if k != 'classification'}) for row in stale])
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_pending_uncertain_error_and_review_states_keep_work_and_jev_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_still_supported_closes_only_exact_pairs_and_preserves_staleness_pins_and_verifications
#     def test_still_supported_closes_only_exact_pairs_and_preserves_staleness_pins_and_verifications(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             ConfirmationStore(connection).apply(self.base.settings, self.ref, by='owner', captured_at=AT)
#             self.change(connection)
#             drift = self.one(connection)
#             immutable, stale = self.immutable(connection), self.stale(connection)
#             for number in (1, 2):
#                 drift = self.support(connection, drift, self.reason(drift, number))
#                 self.assertEqual(drift['state'], 'open')
#             self.assertEqual([reason['source']['address'] for reason in drift['sources'] if reason['active']],
#                              [self.addresses[2]])
#             drift = self.support(connection, drift, self.reason(drift, 3))
#             self.assertEqual((drift['state'], drift['closed']['because']), ('closed', 'still_supported'))
#             self.assertEqual(self.report(connection)['drifts'], [])
#             self.assertEqual(self.one(connection, closed=True), drift)
#             self.assertEqual(self.immutable(connection), immutable)
#             self.assertEqual({row[0] for row in self.stale(connection)}, {row[0] for row in stale})
#             self.assertEqual({row[3]['kind'] for row in self.stale(connection)}, {'source_changed'})
#             self.assertTrue(all(row[3]['classification']['judgement'] == 'still_supported'
#                                 for row in self.stale(connection)))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_still_supported_closes_only_exact_pairs_and_preserves_staleness_pins_and_verifications

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_away_then_deleted_source_are_distinct_and_keep_complete_pinned_before_evidence
#     def test_away_then_deleted_source_are_distinct_and_keep_complete_pinned_before_evidence(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             original = self.fixture.dependencies(connection)
#             original = next(row for row in original if row[3] == self.addresses[0])
#             baseline = EvidenceStore(connection).read_baseline('downstream', original[7])
#             self.fixture.source.unlink()
#             self.fixture.publish(connection)
#             self.sync(connection)
#             away = self.reason(self.one(connection))
#             self.assertEqual(away['kind'], 'source_removed')
#             self.assertEqual(away['classification']['reason'], 'source_away')
#             self.assertTrue(away['active'])
#             self.base.commit()
#             self.fixture.publish(connection)
#             self.sync(connection)
#             removed = self.reason(self.one(connection))
#             self.assertEqual(removed['kind'], 'source_removed')
#             self.assertNotEqual(removed['classification'].get('reason'), 'source_away')
#             self.assertEqual(removed['classification']['status'], 'pending_jev')
#             retained = EvidenceStore(connection).read_baseline('downstream', original[7])
#             self.assertEqual(retained, baseline)
#             self.assertIn(self.fixture.source_bytes, [snapshot.source for snapshot in retained.snapshots])
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_away_then_deleted_source_are_distinct_and_keep_complete_pinned_before_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_live_read_failure_keeps_error_work_and_cannot_be_treated_as_removal_or_support
#     def test_live_read_failure_keeps_error_work_and_cannot_be_treated_as_removal_or_support(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             immutable = self.immutable(connection)
#             with patch('mycel._staleness.capture_repository', side_effect=MycelError('invalid_input',
#                     'Fictional file read failure.')):
#                 self.sync(connection)
#                 failed = self.one(connection)
#                 first = self.reason(failed)
#                 self.assertEqual(first['kind'], 'source_changed')
#                 self.assertEqual(first['classification']['status'], 'error')
#                 self.assertEqual(first['classification']['reason'], 'read_failed')
#                 result = self.record(connection, failed, first, judgement='still_supported')
#                 self.assertTrue(result['drift']['sources'][0]['active'])
#                 self.assertEqual(result['drift']['sources'][0]['classification']['status'], 'error')
#             self.assertEqual(self.one(connection)['state'], 'open')
#             self.assertEqual(self.immutable(connection), immutable)
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_live_read_failure_keeps_error_work_and_cannot_be_treated_as_removal_or_support

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_new_source_input_invalidates_prior_support_and_retains_attempt_history
#     def test_new_source_input_invalidates_prior_support_and_retains_attempt_history(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             first = self.one(connection)
#             old = deepcopy(self.reason(first))
#             supported = self.support(connection, first, old)
#             self.assertEqual(supported['state'], 'closed')
#             self.fixture.source.write_bytes(b'# Source\nA newer changed governing source.\n')
#             self.fixture.publish(connection)
#             self.sync(connection)
#             newest = self.one(connection)
#             current = self.reason(newest)
#             self.assertNotEqual(current['pairHash'], old['pairHash'])
#             self.assertEqual(current['classification']['status'], 'pending_jev')
#             self.assertTrue(current['active'])
#             outcome = self.record(connection, first, old, judgement='still_supported')
#             self.assertFalse(outcome['applied'])
#             self.assertTrue(outcome['obsolete'])
#             records = self.report(connection, closed=True, all_versions=True)['drifts']
#             encoded = json.dumps(records, sort_keys=True)
#             self.assertIn(old['pairHash'], encoded)
#             self.assertIn('still_supported', encoded)
#             self.assertEqual(self.one(connection)['state'], 'open')
#             supported = self.support(connection, newest, current)
#             self.assertEqual(supported['state'], 'closed')
#             # Comparison-equivalent current bytes remain semantically exact
#             # new evidence even though they keep the same mechanical reason.
#             self.fixture.source.write_bytes(self.fixture.source.read_bytes().replace(b'source.', b'source.   '))
#             self.fixture.publish(connection)
#             self.sync(connection)
#             formatted = self.reason(self.one(connection))
#             self.assertNotEqual(formatted['pairHash'], current['pairHash'])
#             self.assertTrue(formatted['active'])
#             self.assertEqual(formatted['classification']['status'], 'pending_jev')
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_new_source_input_invalidates_prior_support_and_retains_attempt_history

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_error_and_pending_results_cannot_supply_support_and_listing_is_read_only
#     def test_error_and_pending_results_cannot_supply_support_and_listing_is_read_only(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             first = self.reason(drift)
#             before = self.state(connection)
#             for status in ('pending_debounce', 'pending_jev', 'error'):
#                 with self.assertRaises(MycelError) as error:
#                     self.record(connection, drift, first, status=status, judgement='still_supported')
#                 self.assertEqual(error.exception.code, 'invalid_input')
#             self.report(connection, closed=True, all_versions=True)
#             self.assertEqual(self.state(connection), before)
#             pending = self.record(connection, drift, first, status='pending_debounce')['drift']
#             self.assertEqual(self.reason(pending)['classification']['status'], 'pending_debounce')
#             self.assertTrue(self.reason(pending)['active'])
#             self.assertEqual(pending['state'], 'open')
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_error_and_pending_results_cannot_supply_support_and_listing_is_read_only

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_standalone_declarations_open_ref_fault_without_a_guessed_link
#     def test_malformed_standalone_declarations_open_ref_fault_without_a_guessed_link(self):
#         self.fixture.answer.write_bytes(b'---\nrole: authored\nsources: ["not a ref"]\n---\n'
#                                        b'# Answer\nUnchanged dependant.\n')
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             faults = connection.execute("SELECT id,fault FROM public.mycel_ref_faults WHERE repository='downstream'").fetchall()
#             self.assertTrue(faults)
#             # A standalone parser fault is a supported persisted input. Produce
#             # its diagnostic normally, then remove only the unpinned stub to
#             # exercise the projector independently of any live link record.
#             self.assertTrue(all(row[6] is None for row in self.fixture.dependencies(connection)))
#             connection.execute("DELETE FROM public.mycel_dependencies WHERE repository='downstream'")
#             self.sync(connection)
#             self.assertEqual(self.fixture.dependencies(connection), [])
#             drift = self.one(connection)
#             active = [source for source in drift['sources'] if source['active']]
#             self.assertEqual(len(active), 1)
#             self.assertEqual((active[0]['kind'], active[0]['classification']['status']), ('ref_fault', 'error'))
#             inactive = [source for source in drift['sources'] if not source['active']]
#             self.assertTrue(inactive)
#             self.assertTrue(all(source['kind'] == 'ref_fault' and source['closed']['because'] == 'ref_removed'
#                                 for source in inactive))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_standalone_declarations_open_ref_fault_without_a_guessed_link

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_related_pair_support_preserves_same_source_authority_work_and_independent_pin
#     def test_related_pair_support_preserves_same_source_authority_work_and_independent_pin(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             relation = RelateStore(connection).apply(self.base.settings, self.ref, self.addresses[0],
#                 captured_at=AT, settings_home=self.base.base)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             immutable = self.immutable(connection)
#             self.assertEqual(len(drift['sources']), 2)
#             authority = self.reason(drift, kind='source_changed')
#             related = self.reason(drift, kind='related_changed')
#             self.assertNotEqual(authority['id'], related['id'])
#             self.assertEqual(related['link'], 'related')
#             drift = self.support(connection, drift, related)
#             self.assertEqual(drift['state'], 'open')
#             self.assertTrue(self.reason(drift, kind='source_changed')['active'])
#             self.assertFalse(self.reason(drift, kind='related_changed')['active'])
#             self.assertEqual(self.immutable(connection), immutable)
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', relation['baselineManifest'])
#                 .manifest.payload['kind'], 'related')
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_related_pair_support_preserves_same_source_authority_work_and_independent_pin

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_duplicate_occurrence_cannot_hide_behind_valid_pair_support
#     def test_malformed_duplicate_occurrence_cannot_hide_behind_valid_pair_support(self):
#         # Valid and malformed related occurrences remain distinct diagnostics
#         # even when both name the same natural source selection.
#         self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() +
#             b'\n<!-- related: fixture:@artifact/source.md#Source -->\n'
#             b'<!-- related:\n  fixture:@artifact/source.md#Source  \n')
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             faults = [source for source in drift['sources'] if source['kind'] == 'ref_fault']
#             self.assertTrue(faults)
#             valid = self.reason(drift, kind='related_changed')
#             supported = self.support(connection, drift, valid)
#             self.assertEqual(supported['state'], 'open')
#             self.assertTrue(any(source['kind'] == 'ref_fault' and source['active'] for source in supported['sources']))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_duplicate_occurrence_cannot_hide_behind_valid_pair_support

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason
#     def test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason(self):
#         guide = self.base.artifact / 'guide.md'
#         self.fixture.source.write_bytes(b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n'
#                                        + self.fixture.source_bytes)
#         self.write_answer(*self.addresses, 'absent:@artifact/missing.md#Missing')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             guide.write_bytes(b'# Guide\nChanged upstream authority.\n')
#             self.extra[0].write_bytes(b'# Source2\nChanged direct source.\n')
#             self.fixture.publish(connection)
#             self.sync(connection)
#             drift = self.one(connection)
#             self.assertIn('upstream_stale', {reason['kind'] for reason in drift['sources']})
#             self.assertIn('ref_fault', {reason['kind'] for reason in drift['sources']})
#             direct = self.reason(drift, 2, 'source_changed')
#             drift = self.support(connection, drift, direct)
#             protected = [reason for reason in drift['sources'] if reason['kind'] in {'ref_fault', 'upstream_stale'}]
#             self.assertTrue(protected)
#             for reason in protected:
#                 result = self.record(connection, drift, reason, judgement='still_supported')
#                 saved = next(value for value in result['drift']['sources'] if value['id'] == reason['id'])
#                 self.assertTrue(saved['active'])
#                 self.assertEqual(saved['classification']['status'], 'error')
#                 self.assertNotIn('judgement', saved['classification'])
#             self.assertEqual(self.one(connection)['state'], 'open')
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_supported_direct_pair_cannot_suppress_ref_fault_or_upstream_stale_reason

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_source_restoration_ref_withdrawal_and_dependant_edit_close_only_answered_work
#     def test_source_restoration_ref_withdrawal_and_dependant_edit_close_only_answered_work(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             pins = self.fixture.pins(self.fixture.dependencies(connection))
#             self.change(connection)
#             self.fixture.source.write_bytes(self.originals[self.fixture.source])
#             self.fixture.publish(connection)
#             self.sync(connection)
#             restored = self.one(connection)
#             self.assertFalse(self.reason(restored)['active'])
#             self.assertTrue(self.reason(restored, 2)['active'])
#             self.assertEqual(self.fixture.pins(self.fixture.dependencies(connection)), pins)
#             self.write_answer(self.addresses[0], self.addresses[2])
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             remaining = self.one(connection)
#             self.assertFalse(self.reason(remaining, 2)['active'])
#             self.assertEqual(self.reason(remaining, 2)['closed']['because'], 'ref_removed')
#             self.assertTrue(self.reason(remaining, 3)['active'])
#             self.extra[1].write_bytes(b'# Source3\nAnother source change after the dependant edit.\n')
#             self.fixture.publish(connection)
#             self.sync(connection)
#             opened = self.one(connection)
#             self.write_answer(self.addresses[0], self.addresses[2], text='The owner repaired the dependant claim.')
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             self.assertEqual(self.report(connection)['drifts'], [])
#             self.assertTrue(any(drift['id'] == opened['id'] and drift['closed']['because'] == 'edited'
#                 for drift in self.report(connection, closed=True, all_versions=True)['drifts']))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_source_restoration_ref_withdrawal_and_dependant_edit_close_only_answered_work

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_explicit_confirmation_closes_answered_work_and_links_its_exact_verification
#     def test_explicit_confirmation_closes_answered_work_and_links_its_exact_verification(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection)
#             opened = self.one(connection)
#             record = ConfirmationStore(connection).apply(self.base.settings, self.ref, by='owner', captured_at=AT)
#             self.assertEqual(self.report(connection)['drifts'], [])
#             closed = self.one(connection, closed=True)
#             self.assertEqual((closed['id'], closed['closed']['because']), (opened['id'], 'confirmed'))
#             self.assertEqual(closed['closed']['verification'], record)
#             self.assertEqual(self.stale(connection), [])
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_explicit_confirmation_closes_answered_work_and_links_its_exact_verification

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_heartwood_and_external_generated_declarations_close_exempt_work
#     def test_heartwood_and_external_generated_declarations_close_exempt_work(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             original = self.one(connection)
#             self.write_answer(*self.addresses, status='heartwood')
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             self.assertEqual(self.report(connection)['drifts'], [])
#             history = self.report(connection, closed=True, all_versions=True)['drifts']
#             self.assertTrue(any(drift['id'] == original['id'] and drift['closed']['because'] == 'heartwood'
#                                 for drift in history))
#             self.write_answer(*self.addresses)
#             self.fixture.publish(connection, 'downstream')
#             self.extra[0].write_bytes(b'# Source2\nLater meaningful source edit.\n')
#             self.fixture.publish(connection)
#             self.sync(connection)
#             original = self.one(connection)
#             self.write_answer(*self.addresses, generated=True)
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             history = self.report(connection, closed=True, all_versions=True)['drifts']
#             self.assertTrue(any(drift['id'] == original['id'] and drift['closed']['because'] == 'generated'
#                                 for drift in history))
#             self.assertEqual(self.report(connection)['drifts'], [])
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_heartwood_and_external_generated_declarations_close_exempt_work

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_off_disk_version_is_inactive_and_last_location_removal_keeps_closed_evidence_history
#     def test_off_disk_version_is_inactive_and_last_location_removal_keeps_closed_evidence_history(self):
#         (self.fixture.downstream / 'keep.md').write_bytes(b'# Keep\nIndependent surviving document.\n')
#         self.base.git('init', '--initial-branch=dependant-main', cwd=self.fixture.downstream)
#         self.base.commit(cwd=self.fixture.downstream)
#         self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
#             '[repos.downstream]\nenabled=true\ncode_root=' + json.dumps(str(self.fixture.downstream))))
#         self.fixture.reload()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             opened = self.one(connection)
#             self.fixture.answer.unlink()
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             self.assertEqual(self.report(connection)['drifts'], [])
#             inactive = self.one(connection, all_versions=True)
#             self.assertEqual((inactive['id'], inactive['current'], inactive['state']), (opened['id'], False, 'open'))
#             self.assertTrue(inactive['locations'])
#             self.assertTrue(any(location['kind'] == 'branch' for location in inactive['locations']))
#             self.base.commit(cwd=self.fixture.downstream)
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             removed = self.one(connection, closed=True, all_versions=True)
#             self.assertEqual((removed['id'], removed['closed']['because']), (opened['id'], 'version_removed'))
#             self.assertEqual(removed['version'], opened['version'])
#             snapshots = connection.execute('SELECT s.bytes FROM public.mycel_snapshots s '
#                 'JOIN public.mycel_evidence_references e ON e.repository=s.repository AND e.snapshot_hash=s.hash '
#                 'JOIN public.mycel_drifts d ON d.evidence_owner=e.owner WHERE d.id=%s', (removed['id'],)).fetchall()
#             self.assertTrue(any(b'Unchanged dependant.' in bytes(row[0]) for row in snapshots))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks WHERE id=%s',
#                 (removed['chunkId'],)).fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_off_disk_version_is_inactive_and_last_location_removal_keeps_closed_evidence_history

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification
#     def test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification(self):
#         with self.base.connect() as connection, self.base.connect() as peer:
#             self.prepare(connection)
#             self.change(connection, 1)
#             opened = self.one(connection)
#             with operation_guard(peer, 'downstream', 'pass'):
#                 with self.assertRaises(MycelError) as error:
#                     self.sync(connection)
#                 self.assertEqual(error.exception.code, 'busy')
#             self.sync(connection)
#             self.assertEqual(self.one(connection), opened)
#             before = self.state(connection)
#             failing = _FailAfterWrite(connection)
#             with self.assertRaises((RuntimeError, MycelError)):
#                 self.record(failing, opened, self.reason(opened), judgement='still_supported')
#             self.assertTrue(failing.failed)
#             self.assertEqual(self.state(connection), before)
#
#             def annotations():
#                 return connection.execute("SELECT id,reason,xmin::text FROM public.mycel_stale_reasons "
#                     "WHERE repository='downstream' ORDER BY id").fetchall()
#
#             source_bytes = self.fixture.source.read_bytes()
#             native_write = DriftStore._write
#
#             def obsolete_support(drift, evidence):
#                 edited = False
#                 def late_write(store, *args, **kwargs):
#                     nonlocal edited
#                     value = native_write(store, *args, **kwargs)
#                     if not edited:
#                         edited = True
#                         self.fixture.source.write_bytes(source_bytes + b'Late physical input change.\n')
#                     return value
#                 previous = annotations()
#                 with patch.object(DriftStore, '_write', late_write):
#                     result = self.record(connection, drift, self.reason(drift),
#                         judgement='still_supported', evidence=evidence)
#                 self.assertTrue(edited)
#                 self.assertFalse(result['applied'], result)
#                 self.assertTrue(result['obsolete'], result)
#                 self.assertEqual(annotations(), previous)
#                 latest = self.one(connection)
#                 self.assertTrue(self.reason(latest)['active'])
#                 attempts = [item for item in latest['history'] if item.get('evidence') == evidence]
#                 self.assertEqual(len(attempts), 1)
#                 self.assertTrue(attempts[0]['obsolete'])
#                 archived = [item['source'] for item in latest['history'] if item.get('because') == 'input_changed'
#                     and item['source']['pairHash'] == self.reason(drift)['pairHash']]
#                 self.assertTrue(archived)
#                 self.assertEqual(archived[-1]['classification'], self.reason(drift)['classification'])
#
#             # An obsolete attempt may not create an annotation, or replace one
#             # that an earlier exact-input answer already committed.
#             self.assertTrue(all('classification' not in row[1] for row in annotations()))
#             obsolete_support(opened, {'jev': {'case': 'late-first-answer'}})
#             self.fixture.source.write_bytes(source_bytes)
#             self.sync(connection)
#             current = self.one(connection)
#             committed = self.record(connection, current, self.reason(current), judgement='insufficient_evidence',
#                 evidence={'jev': {'case': 'committed-earlier-answer'}})
#             self.assertTrue(committed['applied'], committed)
#             self.assertEqual(annotations()[0][1]['classification']['evidence'],
#                              {'jev': {'case': 'committed-earlier-answer'}})
#             obsolete_support(committed['drift'], {'jev': {'case': 'late-replacement-answer'}})
#
#             self.fixture.source.write_bytes(source_bytes)
#             self.sync(connection)
#             current = self.one(connection)
#             before = self.state(connection)
#             native_publish = DriftStore._publish_classification
#             def late_publish(store, *args, **kwargs):
#                 value = native_publish(store, *args, **kwargs)
#                 self.fixture.source.write_bytes(source_bytes + b'Publication-time physical input change.\n')
#                 return value
#             with patch.object(DriftStore, '_publish_classification', late_publish):
#                 with self.assertRaises(MycelError) as error:
#                     self.record(connection, current, self.reason(current), judgement='still_supported',
#                         evidence={'jev': {'case': 'publication-time-answer'}})
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_busy_peer_cannot_duplicate_open_work_and_failure_rolls_back_classification

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_normalized_formatting_and_recognized_rename_carry_unresolved_work_without_confirmation
#     def test_normalized_formatting_and_recognized_rename_carry_unresolved_work_without_confirmation(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             original = self.one(connection)
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(
#                 b'Unchanged dependant.', b'Unchanged dependant.   '))
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             carried = self.one(connection)
#             self.assertEqual(carried['state'], 'open')
#             self.assertTrue(any(source['active'] for source in carried['sources']))
#             self.assertEqual({source['classification']['status'] for source in carried['sources'] if source['active']},
#                              {'pending_jev'})
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_verifications").fetchone(), (0,))
#             self.assertTrue(self.stale(connection))
#             renamed = self.fixture.downstream / 'renamed.md'
#             self.fixture.answer.rename(renamed)
#             self.fixture.answer = renamed
#             self.fixture.publish(connection, 'downstream')
#             self.sync(connection)
#             carried = self.one(connection)
#             self.assertTrue(any(source['active'] for source in carried['sources']))
#             self.assertEqual({source['classification']['status'] for source in carried['sources'] if source['active']},
#                              {'pending_jev'})
#             self.assertEqual(carried['chunk']['path'], 'renamed.md')
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_verifications").fetchone(), (0,))
#             self.assertTrue(self.stale(connection))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_normalized_formatting_and_recognized_rename_carry_unresolved_work_without_confirmation

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_generated_summary_is_regeneration_work_with_no_semantic_drift
#     def test_generated_summary_is_regeneration_work_with_no_semantic_drift(self):
#         helper = generated.GeneratedStoreTests()
#         helper.fixture, helper.base = self.fixture, self.base
#         from mycel._locks import invocation_guard
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             with invocation_guard(connection) as invocation:
#                 capture = helper.capture(connection, self.addresses[0], owner='fixture')
#                 summary = helper.publish(connection, invocation, helper.lease(connection, invocation, capture))
#             self.change(connection, 1)
#             reply = self.report(connection)
#             self.assertEqual(len(reply['drifts']), 1)
#             self.assertTrue(all(drift['chunk']['address'] != summary.place.address for drift in reply['drifts']))
#             work, = DriftStore(connection).list('fixture')['regeneration']
#             self.assertEqual((work['place']['path'], work['place']['name']),
#                              (summary.place.path, summary.place.name))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_classification_work w '
#                 'JOIN public.mycel_dependencies d ON d.id=w.dependency WHERE d.kind=\'generated\'').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_generated_summary_is_regeneration_work_with_no_semantic_drift

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_external_generated_disk_source_still_opens_its_authored_dependants_work
#     def test_external_generated_disk_source_still_opens_its_authored_dependants_work(self):
#         self.fixture.source.write_bytes(b'---\ngenerated: true\n---\n' + self.fixture.source_bytes)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             first = self.reason(drift)
#             self.assertEqual((first['kind'], first['classification']['status']), ('source_changed', 'pending_jev'))
#             self.assertTrue(first['active'])
#             self.assertEqual(DriftStore(connection).list('fixture')['drifts'], [])
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_external_generated_disk_source_still_opens_its_authored_dependants_work

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_open_work_is_refused_without_duplicate_or_partial_mutation
#     def test_malformed_open_work_is_refused_without_duplicate_or_partial_mutation(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             connection.execute("UPDATE public.mycel_drifts SET state=state-'schema' WHERE id=%s", (drift['id'],))
#             before = self.state(connection)
#             for action in (lambda: self.sync(connection), lambda: self.report(connection)):
#                 with self.assertRaises(MycelError) as error:
#                     action()
#                 self.assertEqual(error.exception.code, 'store_format')
#                 self.assertEqual(self.state(connection), before)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_drifts WHERE closed_at IS NULL")
#                 .fetchone(), (1,))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_malformed_open_work_is_refused_without_duplicate_or_partial_mutation

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_recognized_schema_corrupt_source_state_is_refused_without_suppressing_or_duplicating_work
#     def test_recognized_schema_corrupt_source_state_is_refused_without_suppressing_or_duplicating_work(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.change(connection, 1)
#             drift = self.one(connection)
#             original, = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s', (drift['id'],)).fetchone()
#             for field, value in (('status', 'unrecognized'), ('active', 'false'), ('pairHash', 'invalid')):
#                 corrupt = deepcopy(original)
#                 if field == 'status':
#                     corrupt['sources'][0]['classification']['status'] = value
#                 else:
#                     corrupt['sources'][0][field] = value
#                 connection.execute('UPDATE public.mycel_drifts SET state=%s WHERE id=%s', (Jsonb(corrupt), drift['id']))
#                 before = self.state(connection)
#                 for action in (lambda: self.sync(connection), lambda: self.report(connection),
#                         lambda: self.record(connection, drift, self.reason(drift), judgement='still_supported')):
#                     with self.assertRaises(MycelError) as error:
#                         action()
#                     self.assertEqual(error.exception.code, 'store_format')
#                     self.assertEqual(self.state(connection), before)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_drifts WHERE closed_at IS NULL')
#                     .fetchone(), (1,))
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_recognized_schema_corrupt_source_state_is_refused_without_suppressing_or_duplicating_work

# TEST-TIER-DISABLED-BEGIN tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_family_changed_pair_support_leaves_removed_member_work_active
#     def test_family_changed_pair_support_leaves_removed_member_work_active(self):
#         worker = self.base.code / 'worker.py'
#         worker.write_bytes(b'class Worker:\n    def old(self):\n        return 1\n'
#                            b'    def keep(self):\n        return 2\n')
#         self.write_answer('fixture:@code/worker.py#Worker')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             worker.write_bytes(b'class Worker:\n    def keep(self):\n        return 2\n')
#             self.fixture.publish(connection)
#             self.sync(connection)
#             drift = self.one(connection)
#             self.assertEqual({source['kind'] for source in drift['sources']}, {'source_changed', 'source_removed'})
#             changed = next(source for source in drift['sources'] if source['kind'] == 'source_changed')
#             supported = self.support(connection, drift, changed)
#             removed = next(source for source in supported['sources'] if source['kind'] == 'source_removed')
#             self.assertEqual(removed['source']['name'], 'Worker.old')
#             self.assertTrue(removed['active'])
#             self.assertEqual(removed['classification']['status'], 'pending_jev')
#             self.assertEqual(supported['state'], 'open')
# TEST-TIER-DISABLED-END tests/test_drift_lifecycle.py::DriftLifecycleStoreTests.test_family_changed_pair_support_leaves_removed_member_work_active


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:6
# from copy import deepcopy
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:6

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:7
# from hashlib import sha256
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:10
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:12
# from psycopg.types.json import Jsonb
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:15
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:15

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:16
# from mycel._evidence import EvidenceStore
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:17
# from mycel._locks import operation_guard
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:18
# from mycel._relate import RelateStore
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:18

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:19
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:19

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:21
# from mycel._verification import ConfirmationStore
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:21

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:25
#     from . import test_generated as generated
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:25

# TEST-TIER-IMPORTS-BEGIN tests/test_drift_lifecycle.py:28
#     import test_generated as generated
# TEST-TIER-IMPORTS-END tests/test_drift_lifecycle.py:28

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
