"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_freshness as _support
# from test_freshness import (
#     Adapter,
#     Clock,
#     Deadline,
#     FreshnessDiscovery,
#     FreshnessScope,
#     FreshnessTests,
#     RefreshResult,
#     discovery,
#     run_freshness,
#     statuses,
#     unittest,
# )


# class FreshnessTests(_support.FreshnessTests):
# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_one_deadline_all_incomplete_states_and_exact_result_checks_keep_current_index_usable
#     def test_one_deadline_all_incomplete_states_and_exact_result_checks_keep_current_index_usable(self):
#         requirement = ChunkRequirement('driver', ('go', 1), ('driver', 'contract', 'glossary'))
#         known = discovery('driver', 'contract', 'glossary',
#             edges=(('driver', 'contract'), ('contract', 'glossary')),
#             requirements=(requirement,))
#         timed = Adapter(known, discover_cost=0.1, refresh_cost=0.15)
#         scope = FreshnessScope(('driver',), 'code')
#         limit = Deadline.after(0.5, clock=timed.clock)
#         result = run_freshness(scope, timed, deadline=limit)
#         self.assertEqual([name for name, _ in timed.events if name != 'discover'], ['glossary', 'contract'])
#         self.assertTrue(all(value is limit for value in timed.deadlines))
#         self.assertAlmostEqual(timed.events[1][1], 0.4)
#         self.assertAlmostEqual(timed.events[3][1], 0.15)
#         self.assertEqual(statuses(result)['driver'],
#             ('pending', 'The invocation freshness time limit was reached.', True))
#         self.assertFalse(result.finished)
#         self.assertFalse(result.complete_for_chunk('driver', ('go', 1)))
#         self.assertEqual(timed.read_index(result), (scope, timed.current_index))
#
#         # Initial dependency discovery consumes the same allowance. No file
#         # check or recursive discovery receives a replacement budget.
#         initial = Adapter(known, discover_cost=1)
#         first = self.run_check(initial, seconds=0.5)
#         self.assertEqual([name for name, _ in initial.events], ['discover'])
#         self.assertEqual({row.status for row in first.repositories}, {'pending'})
#         self.assertEqual(set(statuses(first)), {'driver', 'contract', 'glossary'})
#         self.assertFalse(first.discovery_complete)
#         self.assertEqual(initial.read_index(first)[1], initial.current_index)
#
#         # Every failure mode returns a report and leaves an independent result
#         # verified when its own exact dependency closure completed.
#         independent = ChunkRequirement('other', ('okay', 1), ('other',))
#         for state, failure in (
#             ('busy', MycelError('busy', 'A source repository has an active pass.')),
#             ('refused', MycelError('refused', 'Source capture cannot safely be ingested.')),
#             ('failed', RuntimeError('private exception text')),
#             ('pending', DeadlineExceeded()),
#         ):
#             with self.subTest(state=state):
#                 adapter = Adapter(discovery('driver', 'contract', 'other',
#                     edges=(('driver', 'contract'),), requirements=(
#                         replace(requirement, repositories=('driver', 'contract')), independent)),
#                     {'contract': [failure]})
#                 checked = self.run_check(adapter, FreshnessScope(('driver', 'other')))
#                 self.assertEqual(statuses(checked)['contract'][0], state)
#                 self.assertTrue(statuses(checked)['contract'][1])
#                 self.assertFalse(checked.finished)
#                 self.assertFalse(checked.complete_for_chunk('driver', ('go', 1)))
#                 self.assertTrue(checked.complete_for_chunk('other', ('okay', 1)))
#                 self.assertEqual(adapter.read_index(checked)[1], adapter.current_index)
#                 self.assertNotIn('private exception text', repr(checked))
#
#         # A completed file check alone cannot hide an unapplied dependant
#         # update; its files are never added to the scan frontier.
#         adapter = Adapter(known, {'glossary': [RefreshResult(dependency_updates=(
#             RepositoryUpdate('outside', 'pending', 'Its dependency update could not acquire its guard.'),))]})
#         partial = self.run_check(adapter)
#         self.assertEqual(statuses(partial)['outside'],
#             ('pending', 'Its dependency update could not acquire its guard.', False))
#         self.assertNotIn('outside', [name for name, _ in adapter.events if name != 'discover'])
#         self.assertFalse(partial.finished)
#         self.assertEqual(adapter.read_index(partial)[1], adapter.current_index)
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_one_deadline_all_incomplete_states_and_exact_result_checks_keep_current_index_usable

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_upstream_leaves_first_and_every_reread_keeps_original_scope
#     def test_upstream_leaves_first_and_every_reread_keeps_original_scope(self):
#         known = discovery('driver', 'contract', 'glossary',
#             edges=(('driver', 'contract'), ('contract', 'glossary')),
#             requirements=(ChunkRequirement('driver', ('go', 1), ('driver', 'contract', 'glossary')),))
#         adapter = Adapter(known)
#         scope = FreshnessScope(('driver',), 'code')
#         result = self.run_check(adapter, scope)
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'],
#                          ['glossary', 'contract', 'driver'])
#         self.assertTrue(all(value is scope for value in adapter.scopes))
#         self.assertIs(result.scope, scope)
#         self.assertTrue(result.finished)
#         self.assertTrue(result.complete_for_chunk('driver', ('go', 1)))
#         self.assertFalse(result.complete_for_chunk('driver', ('absent', 1)))
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_upstream_leaves_first_and_every_reread_keeps_original_scope

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_new_captured_sources_extend_recursively_before_retrying_the_owner
#     def test_new_captured_sources_extend_recursively_before_retrying_the_owner(self):
#         adapter = Adapter(discovery('driver'), {
#             'driver': [RefreshResult('pending', 'New upstream sources require checks.',
#                 discovered_repositories=('contract',), dependencies=(('driver', 'contract'),)), RefreshResult()],
#             'contract': [RefreshResult('pending', 'New upstream sources require checks.',
#                 discovered_repositories=('glossary',), dependencies=(('contract', 'glossary'),)), RefreshResult()],
#         })
#         adapter.discovery = lambda: (discovery('driver', 'contract', 'glossary',
#             edges=(('driver', 'contract'), ('contract', 'glossary'))) if 'driver' in adapter.applied
#             else discovery('driver'))
#         result = self.run_check(adapter)
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'],
#                          ['driver', 'contract', 'glossary', 'contract', 'driver'])
#         self.assertTrue(result.finished)
#         self.assertEqual(set(statuses(result)), {'driver', 'contract', 'glossary'})
#         self.assertTrue(all(row.scan_required for row in result.repositories))
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_new_captured_sources_extend_recursively_before_retrying_the_owner

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_a_removed_ref_stops_requiring_its_previously_busy_source
#     def test_a_removed_ref_stops_requiring_its_previously_busy_source(self):
#         adapter = Adapter(discovery('driver', 'contract', edges=(('driver', 'contract'),)),
#                           {'contract': [MycelError('busy', 'The old upstream is busy.')]})
#         adapter.discovery = lambda: (discovery('driver') if 'driver' in adapter.applied else
#             discovery('driver', 'contract', edges=(('driver', 'contract'),)))
#         result = self.run_check(adapter)
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'], ['contract', 'driver'])
#         self.assertEqual(set(statuses(result)), {'driver'})
#         self.assertTrue(result.finished)
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_a_removed_ref_stops_requiring_its_previously_busy_source

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_deferred_owner_retries_only_after_its_own_sources_made_progress
#     def test_deferred_owner_retries_only_after_its_own_sources_made_progress(self):
#         adapter = Adapter(discovery('driver', 'contract'), {
#             'driver': [RefreshResult('pending', 'Waiting for its explicit source.',
#                 discovered_repositories=('contract',), dependencies=(('driver', 'contract'),))],
#             'contract': [MycelError('busy', 'The source is busy.')],
#         })
#         result = self.run_check(adapter)
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'], ['driver', 'contract'])
#         self.assertFalse(result.finished)
#         self.assertEqual(statuses(result)['driver'][0], 'pending')
#         # An unsuccessful repository-level cycle cannot keep retrying itself.
#         cycle = Adapter(discovery('driver', 'contract',
#             edges=(('driver', 'contract'), ('contract', 'driver'))), {
#             'driver': [RefreshResult('pending', 'Waiting for source.',
#                 discovered_repositories=('contract',), dependencies=(('driver', 'contract'),))],
#             'contract': [RefreshResult('pending', 'Waiting for source.',
#                 discovered_repositories=('driver',), dependencies=(('contract', 'driver'),))],
#         })
#         cyclic = self.run_check(cycle)
#         self.assertEqual([name for name, _ in cycle.events if name != 'discover'], ['driver', 'contract'])
#         self.assertFalse(cyclic.finished)
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_deferred_owner_retries_only_after_its_own_sources_made_progress

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_no_fresh_reports_all_known_recursive_and_shared_suppliers_without_writes
#     def test_no_fresh_reports_all_known_recursive_and_shared_suppliers_without_writes(self):
#         adapter = Adapter(discovery('driver', 'contract', 'glossary', 'shared',
#             edges=(('driver', 'contract'), ('contract', 'glossary')),
#             requirements=(ChunkRequirement('driver', ('go', 1), ('driver', 'contract', 'glossary')),)))
#         result = self.run_check(adapter, no_fresh=True)
#         self.assertEqual([name for name, _ in adapter.events], ['discover'])
#         self.assertEqual(set(statuses(result)), {'driver', 'contract', 'glossary', 'shared'})
#         self.assertEqual({row.status for row in result.repositories}, {'pending'})
#         self.assertEqual({row.reason for row in result.repositories}, {'Freshness checking is disabled.'})
#         self.assertFalse(result.finished)
#         self.assertFalse(result.complete_for_chunk('driver', ('go', 1)))
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_no_fresh_reports_all_known_recursive_and_shared_suppliers_without_writes

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_expired_initial_discovery_still_reports_configured_shared_supplier_seeds
#     def test_expired_initial_discovery_still_reports_configured_shared_supplier_seeds(self):
#         adapter = Adapter(discovery('driver', 'shared'))
#         scope = FreshnessScope(('driver',), 'docs', ('shared',))
#         result = self.run_check(adapter, scope, seconds=0, no_fresh=True)
#         self.assertEqual(adapter.events, [])
#         self.assertEqual(set(statuses(result)), {'driver', 'shared'})
#         self.assertEqual({row.status for row in result.repositories}, {'pending'})
#         self.assertFalse(result.discovery_complete)
#         self.assertFalse(result.finished)
#         self.assertEqual(result.scope.repositories, ('driver',))
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_expired_initial_discovery_still_reports_configured_shared_supplier_seeds

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_faults_make_only_their_exact_result_closure_incomplete_after_finished_work
#     def test_faults_make_only_their_exact_result_closure_incomplete_after_finished_work(self):
#         fault = DependencyFault('contract', 'glossary:missing.md#Term', 'missing_file', ('contract', 2))
#         broken = ChunkRequirement('driver', ('go', 1), ('driver', 'contract'), (fault,))
#         unrelated = ChunkRequirement('driver', ('independent', 1), ('driver',))
#         adapter = Adapter(discovery('driver', 'contract',
#             edges=(('driver', 'contract'),), requirements=(broken, unrelated), faults=(fault,)))
#         result = self.run_check(adapter)
#         self.assertTrue(result.finished)
#         self.assertFalse(result.dependency_complete)
#         self.assertFalse(result.complete_for('driver'))
#         self.assertFalse(result.complete_for_chunk('driver', ('go', 1)))
#         self.assertTrue(result.complete_for_chunk('driver', ('independent', 1)))
#         self.assertEqual(result.faults, (fault,))
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_faults_make_only_their_exact_result_closure_incomplete_after_finished_work

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_recovery_of_dependency_updates_clears_pending_without_scanning_the_dependant
#     def test_recovery_of_dependency_updates_clears_pending_without_scanning_the_dependant(self):
#         adapter = Adapter(discovery('driver', 'contract', edges=(('driver', 'contract'),)), {
#             'contract': [RefreshResult(dependency_updates=(
#                 RepositoryUpdate('outside', 'pending', 'The dependant guard is busy.'),))],
#             'driver': [RefreshResult(dependency_updates=(RepositoryUpdate('outside'),))],
#         })
#         result = self.run_check(adapter)
#         self.assertTrue(result.finished)
#         self.assertEqual(statuses(result)['outside'], ('done', None, False))
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'], ['contract', 'driver'])
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_recovery_of_dependency_updates_clears_pending_without_scanning_the_dependant

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_owner_pass_clears_earlier_pending_update_and_preserves_its_current_pending_work
#     def test_owner_pass_clears_earlier_pending_update_and_preserves_its_current_pending_work(self):
#         requirement = ChunkRequirement('driver', ('go', 1), ('driver', 'contract'))
#         for current_pending in (False, True):
#             with self.subTest(current_pending=current_pending):
#                 current = (RepositoryUpdate('driver', 'pending', 'The current dependency update is incomplete.'),
#                            ) if current_pending else ()
#                 adapter = Adapter(discovery('driver', 'contract', edges=(('driver', 'contract'),),
#                     requirements=(requirement,)), {
#                     'contract': [RefreshResult(dependency_updates=(
#                         RepositoryUpdate('driver', 'pending', 'Its dirty file needs its own ingest pass.'),))],
#                     'driver': [RefreshResult(dependency_updates=current, ingested=True)],
#                 })
#                 result = self.run_check(adapter)
#                 self.assertEqual([name for name, _ in adapter.events if name != 'discover'],
#                                  ['contract', 'driver'])
#                 self.assertEqual(statuses(result)['driver'],
#                     ('pending', 'The current dependency update is incomplete.', True) if current_pending
#                     else ('done', None, True))
#                 self.assertEqual(result.finished, not current_pending)
#                 self.assertEqual(result.complete_for_chunk('driver', ('go', 1)), not current_pending)
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_owner_pass_clears_earlier_pending_update_and_preserves_its_current_pending_work

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_partial_discovery_keeps_new_known_sources_and_never_claims_completion
#     def test_partial_discovery_keeps_new_known_sources_and_never_claims_completion(self):
#         adapter = Adapter(discovery('driver', 'unresolved', complete=False,
#                                     reason='The invocation freshness time limit was reached.'))
#         result = self.run_check(adapter)
#         self.assertEqual(set(statuses(result)), {'driver', 'unresolved'})
#         self.assertEqual({row.status for row in result.repositories}, {'pending'})
#         self.assertFalse(result.finished)
#         self.assertFalse(result.complete_for('driver'))
#         self.assertEqual([name for name, _ in adapter.events], ['discover'])
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_partial_discovery_keeps_new_known_sources_and_never_claims_completion

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_discovery_failure_and_caller_interruption_preserve_current_index_fallback
#     def test_discovery_failure_and_caller_interruption_preserve_current_index_fallback(self):
#         for error in (RuntimeError('sensitive diagnostic'), MycelError('store_unavailable', 'Store read failed.'),
#                       KeyboardInterrupt()):
#             with self.subTest(error=type(error).__name__):
#                 adapter = Adapter(error)
#                 result = self.run_check(adapter)
#                 self.assertFalse(result.finished)
#                 self.assertEqual(statuses(result)['driver'][0], 'pending')
#                 self.assertEqual(adapter.read_index(result)[1], adapter.current_index)
#                 self.assertNotIn('sensitive diagnostic', repr(result))
#         adapter = Adapter(discovery('driver', 'contract'), {'driver': [KeyboardInterrupt()]})
#         result = self.run_check(adapter)
#         self.assertFalse(result.finished)
#         self.assertEqual([name for name, _ in adapter.events if name != 'discover'], ['driver'])
#         self.assertEqual({row.status for row in result.repositories}, {'pending'})
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_discovery_failure_and_caller_interruption_preserve_current_index_fallback

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_invalid_adapter_output_cannot_escape_into_a_successful_reply
#     def test_invalid_adapter_output_cannot_escape_into_a_successful_reply(self):
#         adapter = Adapter(discovery('driver'), {'driver': [RefreshResult('failed')]})
#         result = self.run_check(adapter)
#         self.assertEqual(statuses(result)['driver'][0], 'failed')
#         self.assertFalse(result.finished)
#         adapter = Adapter(discovery('driver'), {'driver': [RefreshResult(ingested=1)]})
#         result = self.run_check(adapter)
#         self.assertEqual(statuses(result)['driver'][0], 'failed')
#         self.assertFalse(result.finished)
#         adapter = Adapter(object())
#         result = self.run_check(adapter)
#         self.assertFalse(result.discovery_complete)
#         self.assertEqual(statuses(result)['driver'][0], 'pending')
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_invalid_adapter_output_cannot_escape_into_a_successful_reply

# TEST-TIER-DISABLED-BEGIN tests/test_freshness.py::FreshnessTests.test_scope_and_deadline_are_immutable_and_expiration_is_never_restarted
#     def test_scope_and_deadline_are_immutable_and_expiration_is_never_restarted(self):
#         scope = FreshnessScope(('driver',), 'docs')
#         with self.assertRaises(FrozenInstanceError):
#             scope.only = 'code'
#         for names in ([], (), ('driver', 'driver'), ('',), ('bad\0name',)):
#             with self.subTest(names=names), self.assertRaises(MycelError):
#                 FreshnessScope(names)
#         for only in ('unsupported', [], {}):
#             with self.subTest(only=only), self.assertRaises(MycelError):
#                 FreshnessScope(('driver',), only)
#         with self.assertRaises(MycelError):
#             FreshnessScope(('driver',), 'code', ('shared',))
#         clock = Clock()
#         limit = Deadline.after(0.5, clock=clock)
#         with self.assertRaises(FrozenInstanceError):
#             limit.expires_at = 1000
#         clock.advance(0.25)
#         self.assertAlmostEqual(limit.remaining(), 0.25)
#         clock.advance(0.25)
#         self.assertTrue(limit.cancelled())
#         with self.assertRaises(DeadlineExceeded):
#             limit.check()
#         for seconds in (-1, float('nan'), float('inf'), True, '1'):
#             with self.subTest(seconds=seconds), self.assertRaises(MycelError):
#                 Deadline.after(seconds, clock=clock)
# TEST-TIER-DISABLED-END tests/test_freshness.py::FreshnessTests.test_scope_and_deadline_are_immutable_and_expiration_is_never_restarted


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_freshness.py:2
# from dataclasses import FrozenInstanceError, replace
# TEST-TIER-IMPORTS-END tests/test_freshness.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_freshness.py:5
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_freshness.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_freshness.py:6
# from mycel._freshness import (ChunkRequirement, Deadline, DeadlineExceeded,
#     DependencyFault, FreshnessDiscovery, FreshnessScope, RefreshResult,
#     RepositoryUpdate, run_freshness)
# TEST-TIER-IMPORTS-END tests/test_freshness.py:6

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
