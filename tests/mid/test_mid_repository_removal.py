"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_repository_removal as _support
from test_repository_removal import (CollectionStore ,RepositoryRemovalStore ,patch)


class RepositoryRemovalStoreTests(_support.RepositoryRemovalStoreTests):


# TEST-TIER-BEGIN tests/test_repository_removal.py::RepositoryRemovalStoreTests.test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards
    def test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards(self):
        with self.connect() as connection, self.connect() as peer:
            self.seed(connection, 'fixture', complete=True)
            before = self.state(connection)
            actual = CollectionStore.remove_repository_in_transaction
            def fail(store, *args, **kwargs):
                actual(store, *args, **kwargs)
                raise RuntimeError('Fixture failure after repository deletion.')
            with patch.object(CollectionStore, 'remove_repository_in_transaction', fail):
                with self.assertRaises(RuntimeError):
                    RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
            self.assertEqual(self.state(connection), before)
            reply = RepositoryRemovalStore(peer).remove(self.settings, 'fixture')
            self.assertEqual(reply['removed']['chunks'], 3)
# TEST-TIER-END tests/test_repository_removal.py::RepositoryRemovalStoreTests.test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_removal_counts_complete_owned_state_and_preserves_files_and_foreign_rows
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Removal counts complete owned state and preserves files and foreign rows.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_removal_counts_complete_owned_state_and_preserves_files_and_foreign_rows(self):
#         with self.connect() as connection:
#             other_dependency, _ = self.seed(connection, 'other', complete=True)
#             foreign = self.state(connection)
#             _, version = self.seed(connection, 'fixture', complete=True)
#             connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (other_dependency, version))
#             before_files = self.files()
#             reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#             self.assertEqual(reply, {'repository': 'fixture', 'known': True, 'removed': {
#                 'documents': 1, 'chunks': 3, 'versions': 3, 'vectors': 1, 'edges': 2,
#                 'evidenceBlobs': 6, 'evidenceManifests': 1, 'drifts': 2, 'verifications': 1}})
#             self.assertEqual(self.state(connection), foreign)
#             self.assertEqual(self.files(), before_files)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_disabled_forgotten_and_receipt_only_repository_owners_are_removable
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disabled forgotten and receipt only repository owners are removable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disabled_forgotten_and_receipt_only_repository_owners_are_removable(self):
#         with self.connect() as connection:
#             for known, enabled in ((True, False), (False, False)):
#                 with self.subTest(known=known):
#                     self.configure(known=known, enabled=enabled)
#                     self.seed(connection, 'fixture')
#                     reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                     self.assertIs(reply['known'], known)
#                     self.assertEqual(reply['removed']['documents'], 1)
#                     self.assertTrue(all(not rows for rows in self.state(connection).values()))
#             connection.execute('INSERT INTO public.mycel_embedding_receipts (id,repository,model,dimensions,payload) '
#                 'VALUES (%s,\'fixture\',\'voyage-code-4\',1024,%s)', (uuid4(), b'receipt without source'))
#             reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#             self.assertFalse(reply['known'])
#             self.assertTrue(all(count == 0 for count in reply['removed'].values()))
#             self.assertTrue(all(not rows for rows in self.state(connection).values()))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_every_active_operation_and_evidence_mutation_refuses_without_feature_changes
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Every active operation and evidence mutation refuses without feature changes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_every_active_operation_and_evidence_mutation_refuses_without_feature_changes(self):
#         with self.connect() as connection, self.connect() as peer:
#             self.seed(connection, 'fixture')
#             for guard in [*(lambda operation=operation: operation_guard(peer, 'fixture', operation)
#                            for operation in ('pass', 'embed', 'classify', 'summaries')),
#                           lambda: mutation_guard(peer, 'fixture')]:
#                 with guard():
#                     before = self.state(connection)
#                     with self.assertRaises(MycelError) as error:
#                         RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                     self.assertEqual(error.exception.code, 'busy')
#                     self.assertEqual(self.state(connection), before)
#             with structure_guard(peer, exclusive=True):
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                 self.assertEqual(error.exception.code, 'busy')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_live_lease_and_running_activity_prevent_removal_until_the_invocation_ends
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Live lease and running activity prevent removal until the invocation ends.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_live_lease_and_running_activity_prevent_removal_until_the_invocation_ends(self):
#         with self.connect() as connection, self.connect() as peer:
#             self.seed(connection, 'fixture')
#             with invocation_guard(peer) as invocation:
#                 owner = self.owner(peer, 'fixture', 'classification_lease', 'live lease', invocation=invocation.id)
#                 before = self.state(connection)
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                 self.assertEqual(error.exception.code, 'busy')
#                 self.assertEqual(self.state(connection), before)
#                 peer.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s', (owner,))
#                 peer.execute('INSERT INTO public.mycel_activity '
#                     '(repository,invocation,index_generation,kind,trigger,build,started_at,counts) '
#                     'VALUES (\'fixture\',%s,%s,\'classify\',\'command\',1,clock_timestamp(),\'{}\')',
#                     (invocation.id, invocation.index_generation))
#                 before = self.state(connection)
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                 self.assertEqual(error.exception.code, 'busy')
#                 self.assertEqual(self.state(connection), before)
#             RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#             self.assertTrue(all(not rows for rows in self.state(connection).values()))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_busy_foreign_dependant_blocks_edge_cascade_without_partial_removal
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Busy foreign dependant blocks edge cascade without partial removal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_busy_foreign_dependant_blocks_edge_cascade_without_partial_removal(self):
#         with self.connect() as connection, self.connect() as peer:
#             foreign, _ = self.seed(connection, 'other')
#             _, source = self.seed(connection, 'fixture')
#             connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (foreign, source))
#             with operation_guard(peer, 'other', 'pass'):
#                 before = self.state(connection)
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#                 self.assertEqual(error.exception.code, 'busy')
#                 self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_configured_empty_repository_is_noop_and_unknown_absent_name_is_refused
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Configured empty repository is noop and unknown absent name is refused.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_configured_empty_repository_is_noop_and_unknown_absent_name_is_refused(self):
#         with self.connect() as connection:
#             reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#             self.assertTrue(all(count == 0 for count in reply['removed'].values()))
#             before = self.state(connection)
#             with self.assertRaises(MycelError) as error:
#                 RepositoryRemovalStore(connection).remove(self.settings, 'forgotten')
#             self.assertEqual(error.exception.code, 'unknown_repository')
#             self.assertEqual(self.state(connection), before)
#             self.configure(enabled=False)
#             with self.assertRaises(MycelError) as error:
#                 RepositoryRemovalStore(connection).remove(load_settings(path=self.config, home=self.root), '\0')
#             self.assertEqual(error.exception.code, 'invalid_input')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_settings_change_before_commit_rolls_back_the_whole_removal
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Settings change before commit rolls back the whole removal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_settings_change_before_commit_rolls_back_the_whole_removal(self):
#         with self.connect() as connection:
#             self.seed(connection, 'fixture')
#             before = self.state(connection)
#             actual = CollectionStore.remove_repository_in_transaction
#             def change_settings(store, *args, **kwargs):
#                 result = actual(store, *args, **kwargs)
#                 self.configure(enabled=False)
#                 return result
#             with patch.object(CollectionStore, 'remove_repository_in_transaction', change_settings):
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture')
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_numbered_removal_records_exact_global_activity_and_audit_failure_rolls_back
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Numbered removal records exact global activity and audit failure rolls back.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_numbered_removal_records_exact_global_activity_and_audit_failure_rolls_back(self):
#         with self.connect() as connection:
#             self.seed(connection, 'fixture', complete=True)
#             before = self.state(connection)
#             with patch.object(MutationActivity, 'record_in_transaction',
#                               side_effect=MycelError('internal', 'Fixture audit failure.')):
#                 with self.assertRaises(MycelError):
#                     RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
#             self.assertEqual(self.state(connection), before)
#             reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
#             rows = connection.execute('SELECT repository,kind,outcome,counts FROM public.mycel_activity').fetchall()
#             self.assertEqual(rows, [(None, 'remove', 'done', reply)])
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
#                 'WHERE repository=\'fixture\'').fetchone())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_activity_close_failure_preserves_committed_counts_and_reports_error
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Activity close failure preserves committed counts and reports error.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_activity_close_failure_preserves_committed_counts_and_reports_error(self):
#         with self.connect() as connection:
#             self.seed(connection, 'fixture')
#             with patch.object(MutationActivity, 'finish',
#                               side_effect=MycelError('internal', 'Fixture activity close failure.')):
#                 reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
#             self.assertEqual(reply['removed']['documents'], 1)
#             self.assertEqual(reply['countsState'], 'committed_prefix')
#             self.assertEqual(reply['error']['code'], 'internal')
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
#                 'WHERE repository=\'fixture\'').fetchone())
#             audit = connection.execute('SELECT repository,kind,counts FROM public.mycel_activity').fetchall()
#             self.assertEqual(audit, [(None, 'remove', {key: value for key, value in reply.items()
#                 if key not in {'error', 'countsState'}})])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalStoreTests.test_interrupt_after_commit_preserves_removed_counts_and_reports_interruption
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Interrupt after commit preserves removed counts and reports interruption.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_interrupt_after_commit_preserves_removed_counts_and_reports_interruption(self):
#         with self.connect() as connection:
#             self.seed(connection, 'fixture')
#             with patch.object(MutationActivity, 'finish', side_effect=KeyboardInterrupt):
#                 reply = RepositoryRemovalStore(connection).remove(self.settings, 'fixture', build=1)
#             self.assertEqual(reply['removed']['documents'], 1)
#             self.assertEqual(reply['countsState'], 'committed_prefix')
#             self.assertEqual(reply['stopped'], 'interrupted')
#             self.assertEqual(reply['error']['code'], 'refused')
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_repository_state '
#                 'WHERE repository=\'fixture\'').fetchone())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalEvidenceStoreTests.test_removed_source_keeps_dependant_baseline_and_projects_missing_source_without_writing
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Removed source keeps dependant baseline and projects missing source without writing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_removed_source_keeps_dependant_baseline_and_projects_missing_source_without_writing(self):
#         try:
#             from . import test_dependency_source_refresh as fixtures
#         except ImportError:
#             import test_dependency_source_refresh as fixtures
#         fixture = fixtures.DependencySourceRefreshStoreTests()
#         fixture.store_fixture = self.store_fixture
#         fixture.setUp()
#         self.addCleanup(fixture.doCleanups)
#         with fixture.base.connect() as connection:
#             fixture.prepare(connection)
#             dependency = fixture.dependencies(connection)[0]
#             baseline = EvidenceStore(connection).read_baseline('downstream', dependency[7])
#             owned_tables = [table for table in TABLES if any(column.name == 'repository' for column in table.columns)]
#             def foreign():
#                 return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
#                     'WHERE repository=\'downstream\' ORDER BY to_jsonb(t)::text').fetchall() for table in owned_tables}
#             before = foreign()
#             reply = RepositoryRemovalStore(connection).remove(fixture.base.settings, 'fixture')
#             self.assertGreater(reply['removed']['edges'], 0)
#             self.assertEqual(foreign(), before)
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', dependency[7]), baseline)
#             resolver = SourceResolver.from_store(connection, fixture.base.settings)
#             self.assertEqual(resolver.resolve(dependency[3]).fault, 'missing_file')
#             read = read_from_store(connection, fixture.base.settings, 'downstream:@artifact/answer.md#Answer',
#                 no_fresh=True, deadline=Deadline.after(30))
#             self.assertEqual(read['dependencyCheck']['faults'][0]['fault'], 'not_found')
#             self.assertEqual(read['dependencyCheck']['faults'][0]['ref'], dependency[3])
#             self.assertEqual(foreign(), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_removal.py::RepositoryRemovalEvidenceStoreTests.test_repin_and_evidence_collection_roll_back_together_and_keep_protected_history
# Reason: Narrower case removed from this family after retaining test_failure_after_cascading_deletion_rolls_back_every_feature_row_and_releases_guards. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Repin and evidence collection roll back together and keep protected history.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_removal.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repin_and_evidence_collection_roll_back_together_and_keep_protected_history(self):
#         try:
#             from . import test_dependency_source_refresh as fixtures
#         except ImportError:
#             import test_dependency_source_refresh as fixtures
#         fixture = fixtures.DependencySourceRefreshStoreTests()
#         fixture.store_fixture = self.store_fixture
#         fixture.setUp()
#         self.addCleanup(fixture.doCleanups)
#         with fixture.base.connect() as connection:
#             fixture.prepare(connection)
#             ConfirmationStore(connection).apply(fixture.base.settings, 'downstream:@artifact/answer.md#Answer',
#                 by='owner', captured_at='2026-10-09T12:00:00Z')
#             protected_id = fixture.dependencies(connection)[0][7]
#             protected = EvidenceStore(connection).read_baseline('downstream', protected_id)
#             fixture.source.write_bytes(b'# Source\nChanged source for authorized repin.\n')
#             fixture.publish(connection)
#             orphan = b'Wholly unreferenced disposable evidence.'
#             orphan_hash = sha256(orphan).hexdigest()
#             connection.execute('INSERT INTO public.mycel_snapshots VALUES (\'downstream\',%s,%s,\'{}\')',
#                 (orphan_hash, orphan))
#             def contents():
#                 return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
#                     'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
#                     if table.name not in {'mycel_store', 'mycel_lock_keys', 'mycel_invocations'}}
#             before = contents()
#             actual = EvidenceStore._collect
#             def fail_after_collection(store, repository):
#                 actual(store, repository)
#                 self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
#                     'WHERE repository=\'downstream\' AND hash=%s', (orphan_hash,)).fetchone())
#                 self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_manifests '
#                     'WHERE repository=\'downstream\' AND hash=%s', (protected_id,)).fetchone())
#                 raise RuntimeError('Fixture failure after new capture, repin and evidence collection.')
#             with patch.object(EvidenceStore, '_collect', fail_after_collection):
#                 with self.assertRaises(RuntimeError):
#                     fixture.apply_assertions(connection, mode='confirm')
#             self.assertEqual(contents(), before)
#             fixture.apply_assertions(connection, mode='confirm')
#             self.assertNotEqual(fixture.dependencies(connection)[0][7], protected_id)
#             self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
#                 'WHERE repository=\'downstream\' AND hash=%s', (orphan_hash,)).fetchone())
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', protected_id), protected)
#             RepositoryRemovalStore(connection).remove(fixture.base.settings, 'fixture')
#             self.assertEqual(EvidenceStore(connection).read_baseline('downstream', protected_id), protected)
#             RepositoryRemovalStore(connection).remove(fixture.base.settings, 'downstream')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_references').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
