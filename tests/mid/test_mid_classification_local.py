"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_classification_local as _support
# from test_classification_local import (
#     ClassificationCliBoundaryTests,
#     ClassificationStoreFixture,
#     ExitStack,
#     LocalClassificationStoreTests,
#     LocalClassificationTests,
#     patch,
#     unittest,
#     work,
# )


# class LocalClassificationTests(_support.LocalClassificationTests):
# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_local_pending_inputs_call_no_model_credential_or_child_and_never_apply
#     def test_local_pending_inputs_call_no_model_credential_or_child_and_never_apply(self):
#         prepared = SimpleNamespace(decision=object(), status='pending_debounce')
#         with self.no_models(), patch('mycel._classification_local.DriftStore') as drifts, \
#                 patch('mycel._classification_local.ClassificationStore') as stores:
#             drifts.return_value.list.return_value = {'drifts': [work('first', 'second')]}
#             stores.return_value.prepare.return_value = prepared
#             stores.return_value.reuse.return_value = None
#             result = reconcile_local(object(), SimpleNamespace(values={'repos': {}}), 'fixture')
#             self.assertEqual((result['pairs'], result['pendingDebounce'], result['reused']), (2, 2, 0))
#             self.assertTrue(result['complete'])
#             stores.return_value.apply.assert_not_called()
#             stores.return_value.stage.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_local_pending_inputs_call_no_model_credential_or_child_and_never_apply

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_existing_deadline_prevents_store_work_without_creating_another_allowance
#     def test_existing_deadline_prevents_store_work_without_creating_another_allowance(self):
#         clock = lambda: 20.0
#         with patch('mycel._classification_local.DriftStore') as drifts, \
#                 patch('mycel._classification_local.ClassificationStore') as stores:
#             adapter = SimpleNamespace(connection=object(), settings=object(), activity=None, counts={})
#             scope = FreshnessScope(('fixture',))
#             result = FreshnessResult(scope, (RepositoryStatus('fixture', 'done'),), (), True, True, ())
#             returned = reconcile_freshness(adapter, result, deadline=Deadline(20, clock))
#             self.assertIs(returned, result)
#             self.assertEqual(adapter.classification_checks['fixture']['reason'], 'time_limit')
#             self.assertFalse(adapter.classification_checks['fixture']['complete'])
#             drifts.assert_not_called()
#             stores.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_existing_deadline_prevents_store_work_without_creating_another_allowance

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_budget_expiry_retains_checked_prefix_and_does_not_prepare_another_pair
#     def test_budget_expiry_retains_checked_prefix_and_does_not_prepare_another_pair(self):
#         clock = [0.0]
#         prepared = SimpleNamespace(decision=object(), status='pending_jev')
#         def prepare(*_args, **_kwargs):
#             clock[0] = 5.0
#             return prepared
#         with self.no_models(), patch('mycel._classification_local.DriftStore') as drifts, \
#                 patch('mycel._classification_local.ClassificationStore') as stores:
#             drifts.return_value.list.return_value = {'drifts': [work('first', 'second')]}
#             stores.return_value.prepare.side_effect = prepare
#             stores.return_value.reuse.return_value = None
#             with deadline_guard(Deadline(4.0, lambda: clock[0])):
#                 result = reconcile_local(object(), SimpleNamespace(values={'repos': {}}), 'fixture')
#             self.assertEqual((result['pairs'], result['pendingJev']), (1, 1))
#             self.assertFalse(result['complete'])
#             self.assertEqual(result['reason'], 'time_limit')
#             self.assertEqual(stores.return_value.prepare.call_count, 1)
#             stores.return_value.apply.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_budget_expiry_retains_checked_prefix_and_does_not_prepare_another_pair

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_unchecked_upstreams_do_no_reconciliation_and_preserve_incomplete_freshness
#     def test_unchecked_upstreams_do_no_reconciliation_and_preserve_incomplete_freshness(self):
#         adapter = SimpleNamespace(connection=object(), settings=object(), activity=None, counts={})
#         scope = FreshnessScope(('fixture',))
#         result = FreshnessResult(scope, (RepositoryStatus('fixture', 'pending', 'busy'),),
#                                 (), False, True, ('fixture',))
#         with self.no_models(), patch('mycel._classification_local.reconcile_local') as reconcile:
#             returned = reconcile_freshness(adapter, result, deadline=Deadline(10, lambda: 0))
#         self.assertIs(returned, result)
#         reconcile.assert_not_called()
#         self.assertEqual(adapter.classification_checks['fixture'],
#                          {'checked': False, 'complete': False, 'reason': 'sources_unchecked'})
#         self.assertFalse(returned.complete_for('fixture'))
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_unchecked_upstreams_do_no_reconciliation_and_preserve_incomplete_freshness

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_guarded_cache_application_keeps_obsolete_effect_out_of_reused_count
#     def test_guarded_cache_application_keeps_obsolete_effect_out_of_reused_count(self):
#         prepared = SimpleNamespace(decision=object(), status='pending_jev',
#                                    bundle=SimpleNamespace(evidence_hash='bundle'))
#         with self.no_models(), patch('mycel._classification_local.DriftStore') as drifts, \
#                 patch('mycel._classification_local.ClassificationStore') as stores:
#             drifts.return_value.list.return_value = {'drifts': [work('first')]}
#             stores.return_value.prepare.return_value = prepared
#             stores.return_value.reuse.return_value = {'judgement': 'still_supported', 'evidence': {'jev': 'retained'}}
#             stores.return_value.apply.return_value = {'applied': False, 'obsolete': True}
#             result = reconcile_local(object(), SimpleNamespace(values={'repos': {}}), 'fixture')
#             self.assertEqual(result['reused'], 0)
#             self.assertIs(stores.return_value.apply.call_args.args[1], prepared)
#             self.assertEqual(stores.return_value.apply.call_args.kwargs['evidence'], {'jev': 'retained'})
#             self.assertTrue(callable(stores.return_value.apply.call_args.kwargs['_audit']))
#             stores.return_value.stage.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_guarded_cache_application_keeps_obsolete_effect_out_of_reused_count

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_current_complete_cache_is_read_without_reapplying_a_judgement
#     def test_current_complete_cache_is_read_without_reapplying_a_judgement(self):
#         prepared = SimpleNamespace(decision=object(), status='pending_jev', input_hash='exact-input')
#         drift = work('first')
#         drift['sources'][0]['classification'] = {
#             'status': 'complete', 'inputHash': 'exact-input', 'judgement': 'needs_review'}
#         with self.no_models(), patch('mycel._classification_local.DriftStore') as drifts, \
#                 patch('mycel._classification_local.ClassificationStore') as stores:
#             drifts.return_value.list.return_value = {'drifts': [drift]}
#             stores.return_value.prepare.return_value = prepared
#             stores.return_value.reuse.return_value = drift['sources'][0]['classification']
#             result = reconcile_local(object(), SimpleNamespace(values={'repos': {}}), 'fixture')
#             self.assertEqual((result['reused'], result['pendingJev']), (0, 0))
#             stores.return_value.apply.assert_not_called()
#             stores.return_value.stage.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_current_complete_cache_is_read_without_reapplying_a_judgement

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationTests.test_search_and_read_share_original_deadline_and_skipped_reads_do_not_reconcile
#     def test_search_and_read_share_original_deadline_and_skipped_reads_do_not_reconcile(self):
#         from mycel._search_store import _run_search_freshness
#         from mycel._read_store import _run_read_freshness
#         scope = FreshnessScope(('fixture',))
#         freshness = FreshnessResult(scope, (RepositoryStatus('fixture', 'done'),), (), True, True, ())
#         deadline = Deadline(10, lambda: 0)
#         with self.no_models(), patch('mycel._classification_local.reconcile_local',
#                 return_value={'checked': True, 'complete': True, 'reused': 0}) as reconcile, \
#                 patch('mycel._search_store.current_build', return_value=None), \
#                 patch('mycel._read_store.current_build', return_value=None), \
#                 patch('mycel._search_store.StoreFreshnessAdapter') as search_adapter, \
#                 patch('mycel._read_store.StoreReadFreshnessAdapter') as read_adapter, \
#                 patch('mycel._search_store.run_freshness', return_value=freshness) as search_run, \
#                 patch('mycel._read_store.run_freshness', return_value=freshness) as read_run:
#             for factory in (search_adapter, read_adapter):
#                 factory.return_value.connection = object()
#                 factory.return_value.settings = object()
#                 factory.return_value.activity = None
#                 factory.return_value.counts = {}
#             for skipped in (False, True):
#                 _run_search_freshness(object(), object(), scope, deadline=deadline, no_fresh=skipped, build=None)
#                 _run_read_freshness(object(), object(), scope, 'fixture:@artifact/guide.md#Guide',
#                                    None, None, deadline=deadline, no_fresh=skipped, build=None)
#             self.assertEqual(reconcile.call_count, 2)
#             self.assertTrue(all(call.kwargs['deadline'] is deadline for call in search_run.call_args_list))
#             self.assertTrue(all(call.kwargs['deadline'] is deadline for call in read_run.call_args_list))
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationTests.test_search_and_read_share_original_deadline_and_skipped_reads_do_not_reconcile



# class ClassificationCliBoundaryTests(_support.ClassificationCliBoundaryTests):
# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::ClassificationCliBoundaryTests.test_final_audit_failure_and_later_interrupt_preserve_committed_repository_replies
#     def test_final_audit_failure_and_later_interrupt_preserve_committed_repository_replies(self):
#         from mycel._classify import handle_classify
#         settings = SimpleNamespace(values={'drifts': {'seconds': 30}})
#         repositories = [SimpleNamespace(name=name, require_folders=Mock()) for name in ('first', 'second')]
#         completed = {'repository': 'first', 'status': 0, 'completed': 2, 'incomplete': False}
#         activity = Mock()
#         activity.finish.side_effect = MycelError('store_unavailable', 'The audit could not be finalized.')
#         with patch('mycel._classify.RepositoryLocations') as locations, \
#                 patch('mycel._build_identity.current_build', return_value=None), \
#                 patch('mycel._classify.run_classification', return_value=completed):
#             locations.return_value.resolve_scope.return_value = repositories
#             reply = handle_classify(Invocation('classify', settings=settings),
#                                     _store=(object(), None), _activity=activity)
#         self.assertEqual(reply.status, 1)
#         self.assertEqual(reply.value['countsState'], 'committed_prefix')
#         self.assertEqual([entry['result']['completed'] for entry in reply.value['repositories']], [2, 2])
#         with patch('mycel._classify.RepositoryLocations') as locations, \
#                 patch('mycel._build_identity.current_build', return_value=None), \
#                 patch('mycel._classify.run_classification', side_effect=[completed, KeyboardInterrupt()]):
#             locations.return_value.resolve_scope.return_value = repositories
#             reply = handle_classify(Invocation('classify', settings=settings), _store=(object(), None))
#         self.assertEqual(reply.status, 2)
#         entries = {entry['repository']: entry for entry in reply.value['repositories']}
#         self.assertEqual(entries['first']['result']['completed'], 2)
#         self.assertEqual(entries['second']['error']['code'], 'refused')
# TEST-TIER-DISABLED-END tests/test_classification_local.py::ClassificationCliBoundaryTests.test_final_audit_failure_and_later_interrupt_preserve_committed_repository_replies

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::ClassificationCliBoundaryTests.test_dry_run_reaches_the_store_as_every_command_and_takes_no_model_credential
#     def test_dry_run_reaches_the_store_as_every_command_and_takes_no_model_credential(self):
#         from mycel._credentials import Secret
#         settings = SimpleNamespace(values={'store': {'address': 'postgresql://fixture@127.0.0.1/test'},
#                                           'embedding': {'dimensions': 1024}}, require_valid=Mock())
#         connection = object()
#         for challenged in (False, True):
#             purposes = []
#             def keychain(credentials, purpose, **_limits):
#                 purposes.append(purpose)
#                 return Secret('fictional-store-password')
#             @contextmanager
#             def connect(target, **_limits):
#                 self.assertIsNone(target.store_target().password)
#                 if challenged:
#                     password = target.store_target(password_requested=True).password
#                     self.assertEqual(password.reveal(), 'fictional-store-password')
#                 for model_credential in (target.jev_key, target.embedding_key):
#                     with self.assertRaises(MycelError) as refused:
#                         model_credential()
#                     self.assertEqual(refused.exception.code, 'refused')
#                 yield connection
#             @contextmanager
#             def checked(opened, **_options):
#                 self.assertIs(opened, connection)
#                 yield 'inspection'
#             with self.subTest(challenged=challenged), patch('mycel._database.store_connection', connect), \
#                     patch('mycel._store.checked_store', checked), \
#                     patch('mycel._credentials.Credentials._keychain', keychain), patch('subprocess.Popen') as child:
#                 with classification_store(Invocation('classify', settings=settings), dry_run=True) as store:
#                     self.assertEqual(store, (connection, 'inspection'))
#                 # The store item is read only when the store asks for a password.
#                 self.assertEqual(purposes, ['store'] if challenged else [])
#                 child.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_classification_local.py::ClassificationCliBoundaryTests.test_dry_run_reaches_the_store_as_every_command_and_takes_no_model_credential

# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::ClassificationCliBoundaryTests.test_classify_and_drift_options_are_preserved_and_invalid_caps_stop_before_work
#     def test_classify_and_drift_options_are_preserved_and_invalid_caps_stop_before_work(self):
#         invocation = parse(['classify', '--all', '--k', '3', '--dry-run'])
#         self.assertEqual((invocation.all_repositories, invocation.arguments), (True, ('--k', '3', '--dry-run')))
#         listing = parse(['drifts', '--repo', 'fixture', '--closed', '--all-versions'])
#         self.assertEqual(listing.arguments, ('--closed', '--all-versions'))
#         for arguments in (['classify', '--k', '0'], ['classify', '--k', '-1'],
#                           ['classify', 'extra'], ['stale', 'extra'], ['status', 'extra']):
#             with self.subTest(arguments=arguments), self.assertRaises(MycelError):
#                 parse(arguments)
# TEST-TIER-DISABLED-END tests/test_classification_local.py::ClassificationCliBoundaryTests.test_classify_and_drift_options_are_preserved_and_invalid_caps_stop_before_work



# class LocalClassificationStoreTests(_support.LocalClassificationStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_classification_local.py::LocalClassificationStoreTests.test_local_reads_preserve_waiting_review_errors_and_refuse_malformed_retained_metadata
#     def test_local_reads_preserve_waiting_review_errors_and_refuse_malformed_retained_metadata(self):
#         from copy import deepcopy
#         from psycopg.types.json import Jsonb
#         from mycel._classification_store import ClassificationStore
#         with self.base.connect() as connection:
#             prepared = self.prepare(connection)
#             writer = ClassificationStore(connection)
#             writer.drifts.record_classification(self.base.settings, prepared.drift_id, prepared.reason_id,
#                 prepared.pair_hash, status='needs_llm_review', evidence={'jev': {'inputHash': prepared.input_hash}},
#                 canonical_input_hash=prepared.input_hash, at=AT)
#             waiting = writer.prepare(self.base.settings, prepared.drift_id, prepared.reason_id, at=AT, reconcile=True)
#             self.assertEqual(waiting.status, 'needs_llm_review')
#             counts = reconcile_local(connection, self.base.settings, 'downstream', at=AT)
#             self.assertEqual((counts['needsLlmReview'], counts['pendingJev']), (1, 0))
#             writer.drifts.record_classification(self.base.settings, prepared.drift_id, prepared.reason_id,
#                 prepared.pair_hash, status='error', evidence={'reason': 'authentication'},
#                 canonical_input_hash=prepared.input_hash, at=AT)
#             counts = reconcile_local(connection, self.base.settings, 'downstream', at=AT)
#             self.assertEqual((counts['unresolved'], counts['pendingJev']), (1, 0))
#             state = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s',
#                                        (prepared.drift_id,)).fetchone()[0]
#             source = next(source for source in state['sources'] if source['id'] == prepared.reason_id)
#             self.assertEqual((source['classification']['status'], source['classification']['reason']),
#                              ('error', 'authentication'))
#             for field, value in (('classificationRequests', []), ('classificationObservations', []),
#                                   ('classificationRequests', {prepared.input_hash: []}),
#                                   ('classificationObservations', {'bad-identity': {}})):
#                 with self.subTest(field=field, value=value):
#                     corrupt = deepcopy(state)
#                     corrupt[field] = value
#                     connection.execute('UPDATE public.mycel_drifts SET state=%s WHERE id=%s',
#                                        (Jsonb(corrupt), prepared.drift_id))
#                     with self.assertRaises(MycelError) as fault:
#                         writer.prepare(self.base.settings, prepared.drift_id, prepared.reason_id,
#                                        at=AT, reconcile=True)
#                     self.assertEqual(fault.exception.code, 'store_format')
#                     retained = connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s',
#                                                   (prepared.drift_id,)).fetchone()[0]
#                     self.assertEqual(retained, corrupt)
#                     connection.execute('UPDATE public.mycel_drifts SET state=%s WHERE id=%s',
#                                        (Jsonb(state), prepared.drift_id))
# TEST-TIER-DISABLED-END tests/test_classification_local.py::LocalClassificationStoreTests.test_local_reads_preserve_waiting_review_errors_and_refuse_malformed_retained_metadata


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:2
# from contextlib import contextmanager, ExitStack
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:3
# from types import SimpleNamespace
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:5
# from unittest.mock import Mock, patch
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:7
# from mycel._classification_local import reconcile_freshness, reconcile_local
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:8
# from mycel._cli import Invocation, classification_store, parse
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:9
# from mycel._deadline import deadline_guard
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:10
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:11
# from mycel._freshness import Deadline, FreshnessResult, FreshnessScope, RepositoryStatus
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:14
#     from .test_classification_store import ClassificationStoreFixture, AT
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:14

# TEST-TIER-IMPORTS-BEGIN tests/test_classification_local.py:16
#     from test_classification_store import ClassificationStoreFixture, AT
# TEST-TIER-IMPORTS-END tests/test_classification_local.py:16

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
