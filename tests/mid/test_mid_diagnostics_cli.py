
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_info_reports_all_settings_faults_without_echoing_values_or_accessing_services
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Info reports all settings faults without echoing values or accessing services.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_info_reports_all_settings_faults_without_echoing_values_or_accessing_services(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             config = root / 'config.toml'
#             for raw in (None, b'\xff', b'[broken',
#                         b'[providers]\napi_key="private-sentinel"\n'
#                         b'[embedding]\nmodel="private-sentinel"\ndimensions=true\n'
#                         b'[repos.sample]\nenabeld="private-sentinel"\n'):
#                 with self.subTest(raw=raw is None):
#                     if raw is not None:
#                         config.write_bytes(raw)
#                     snapshot = load_settings(path=config)
#                     before = {p.name: p.read_bytes() for p in root.iterdir()}
#                     with patch('mycel._database.store_connection') as database, \
#                             patch('mycel._credentials.Credentials.embedding_key') as embedding, \
#                             patch('mycel._credentials.Credentials.jev_key') as jev, \
#                             patch('mycel._safeguards.run_child') as child:
#                         status, reply = self.invoke(snapshot, ['info'])
#                     self.assertEqual(status, 0)
#                     self.assertEqual(reply['settings'], snapshot.report())
#                     self.assertEqual(reply['models'], {'state': 'settings'})
#                     self.assertNotIn('private-sentinel', json.dumps(reply))
#                     self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)
#                     for boundary in (database, embedding, jev, child):
#                         boundary.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_info_includes_configured_models_when_store_is_unavailable_without_model_credentials
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Info includes configured models when store is unavailable without model credentials.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_info_includes_configured_models_when_store_is_unavailable_without_model_credentials(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / 'config.toml'
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
#                               '[drifts]\nreview_command=["/absent-reviewer"]\n'
#                               'review_provider="fixture"\nreview_model="fixture-2026-10-01"\n'
#                               'review_revision="revision-1"\n')
#             snapshot = load_settings(path=config)
#             snapshot.require_valid()
#             before = config.read_bytes()
#             with patch('mycel._database.store_connection', side_effect=MycelError(
#                     'store_unavailable', 'The configured store is unavailable.')), \
#                     patch('mycel._credentials.Credentials.embedding_key') as embedding, \
#                     patch('mycel._credentials.Credentials.jev_key') as jev, \
#                     patch('mycel._safeguards.run_child') as child:
#                 status, reply = self.invoke(snapshot, ['info'])
#             self.assertEqual(status, 0)
#             self.assertEqual(reply['store']['error']['code'], 'store_unavailable')
#             self.assertEqual(reply['models']['embedding'], {'model': 'voyage-code-4', 'dimensions': 1024})
#             self.assertEqual(reply['models']['classification'], {'model': 'jev-1.13.0'})
#             self.assertEqual(reply['models']['reviewer'], {'configured': True, 'provider': 'fixture',
#                 'model': 'fixture-2026-10-01', 'revision': 'revision-1'})
#             self.assertEqual(config.read_bytes(), before)
#             for boundary in (embedding, jev, child):
#                 boundary.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_mixed_and_entirely_refused_scopes_keep_exact_individual_results
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Mixed and entirely refused scopes keep exact individual results.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_mixed_and_entirely_refused_scopes_keep_exact_individual_results(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / 'config.toml'
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
#                 '[repos.good]\nenabled=true\n[repos.busy]\nenabled=true\n[repos.disabled]\nenabled=false\n')
#             snapshot = load_settings(path=config)
#             touched = []
#             def operation(repository):
#                 touched.append(repository.name)
#                 if repository.name == 'busy':
#                     raise MycelError('busy', 'An operation already owns this repository.')
#                 return {'done': True}
#             handler = lambda invocation: for_repositories(invocation, operation, needs_folders=False)
#             for names in (('unknown',), ('unknown', 'disabled'), ('unknown', 'disabled', 'busy', 'good')):
#                 status, reply = self.invoke(snapshot, ['status', *[value for name in names for value in ('--repo', name)]],
#                     handlers={'status': handler})
#                 self.assertEqual(status, 1)
#                 self.assertEqual(set(reply), {'repositories'})
#                 entries = {row['repository']: row for row in reply['repositories']}
#                 self.assertEqual(set(entries), set(names))
#                 self.assertEqual(entries['unknown']['error']['code'], 'unknown_repository')
#                 if 'disabled' in names:
#                     self.assertEqual(entries['disabled']['error']['code'], 'refused')
#                 if 'busy' in names:
#                     self.assertEqual(entries['busy']['error']['code'], 'busy')
#                     self.assertEqual(entries['good']['result'], {'done': True})
#             self.assertEqual(touched, ['busy', 'good'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_removal_runs_each_literal_name_once_and_preserves_a_refused_member
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Removal runs each literal name once and preserves a refused member.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_removal_runs_each_literal_name_once_and_preserves_a_refused_member(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / 'config.toml'
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n')
#             snapshot = load_settings(path=config)
#             @contextmanager
#             def connected(invocation):
#                 yield object(), None
#             called = []
#             def remove(settings, name, *, build):
#                 self.assertIs(settings, snapshot)
#                 called.append(name)
#                 if name == 'busy':
#                     raise MycelError('busy', 'A repository mutation is running.')
#                 return {'repository': name, 'known': False, 'removed': {'documents': 1}}
#             with patch('mycel._cli.invocation_store', connected), \
#                     patch('mycel._repository_removal.RepositoryRemovalStore') as backend:
#                 backend.return_value.remove.side_effect = remove
#                 status, reply = self.invoke(snapshot, ['repos', 'remove', 'orphan space', 'busy', 'orphan space'])
#             self.assertEqual(status, 1)
#             self.assertEqual(called, ['orphan space', 'busy'])
#             self.assertEqual([row['repository'] for row in reply['repositories']], called)
#             self.assertEqual(reply['repositories'][0]['result']['repository'], 'orphan space')
#             self.assertEqual(reply['repositories'][1]['error']['code'], 'busy')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_removal_connection_close_failure_keeps_all_acknowledged_member_counts
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Removal connection close failure keeps all acknowledged member counts.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_removal_connection_close_failure_keeps_all_acknowledged_member_counts(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / 'config.toml'
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n')
#             snapshot = load_settings(path=config)
#             for failure, expected in ((MycelError('store_unavailable', 'The close failed.'), 1),
#                                       (KeyboardInterrupt(), 2)):
#                 @contextmanager
#                 def connected(invocation):
#                     yield object(), None
#                     raise failure
#                 with patch('mycel._cli.invocation_store', connected), \
#                         patch('mycel._repository_removal.RepositoryRemovalStore') as backend:
#                     backend.return_value.remove.return_value = {'removed': {'chunks': 7}}
#                     status, reply = self.invoke(snapshot, ['repos', 'remove', 'one', 'two'])
#                 self.assertEqual(status, expected)
#                 self.assertEqual(reply['countsState'], 'committed_prefix')
#                 self.assertEqual([row['result']['removed']['chunks'] for row in reply['repositories']], [7, 7])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_diagnostics_cli.py::DiagnosticsCliTests.test_interrupted_removal_keeps_committed_result_and_never_starts_later_names
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Interrupted removal keeps committed result and never starts later names.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_diagnostics_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_interrupted_removal_keeps_committed_result_and_never_starts_later_names(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / 'config.toml'
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n')
#             snapshot = load_settings(path=config)
#             @contextmanager
#             def connected(invocation):
#                 yield object(), None
#             committed = {'removed': {'chunks': 7}, 'stopped': 'interrupted',
#                          'countsState': 'committed_prefix',
#                          'error': {'code': 'refused', 'message': 'Stopped by the caller.'}}
#             with patch('mycel._cli.invocation_store', connected), \
#                     patch('mycel._repository_removal.RepositoryRemovalStore') as backend:
#                 backend.return_value.remove.return_value = committed
#                 status, reply = self.invoke(snapshot, ['repos', 'remove', 'one', 'two'])
#             self.assertEqual(status, 2)
#             backend.return_value.remove.assert_called_once_with(snapshot, 'one', build=current_build())
#             self.assertEqual(reply['repositories'][0]['result'], committed)
#             self.assertEqual(reply['repositories'][1], {'repository': 'two', 'error': committed['error']})
# LOW-TIER-SOURCE-END
# LOW-TIER-END
