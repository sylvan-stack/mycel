"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_activity_retention as _support
# from test_activity_retention import (
#     ActivityRetentionStore,
#     ActivityRetentionStoreTests,
#     Jsonb,
#     TABLES,
#     _History,
#     _freeze,
#     activity,
#     checked_store,
#     load_settings,
#     locks,
#     nullcontext,
#     replace,
#     unittest,
#     uuid4,
# )


# class ActivityRetentionStoreTests(_support.ActivityRetentionStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_opening_keeps_exact_newest_thousand_independently_for_two_repositories_and_globals
#     def test_opening_keeps_exact_newest_thousand_independently_for_two_repositories_and_globals(self):
#         with self.history.connect() as connection:
#             self.history.repositories(connection, 'fixture', 'other')
#             groups = {owner: self.history.seed(connection, owner, 1000)
#                       for owner in ('fixture', 'other', None)}
#             for identifiers in groups.values():
#                 self.history.details(connection, identifiers[0])
#                 self.history.details(connection, identifiers[-1])
#             with activity.MutationActivity(connection, build=31).session() as audit:
#                 for owner in ('fixture', 'other', None):
#                     kind = 'remove' if owner is None else 'ingest'
#                     audit.apply(owner, kind, self.history.mutation(owner))
#                     survivors = self.history.ids(connection, owner)
#                     self.assertEqual(len(survivors), 1000)
#                     self.assertEqual(set(survivors[1:]), set(groups[owner][1:]))
#                     self.assertGreater(survivors[0], groups[owner][-1])
#                     for untouched in groups.keys() - {owner}:
#                         self.assertGreaterEqual(len(self.history.ids(connection, untouched)), 1000)
#                 audit.finish('done')
#             for owner, identifiers in groups.items():
#                 self.assertEqual(len(self.history.ids(connection, owner)), 1000)
#                 for table in ('mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications'):
#                     self.assertEqual(connection.execute(f'SELECT count(*) FROM public.{table} WHERE activity=%s',
#                                                         (identifiers[0],)).fetchone(), (0,))
#                     self.assertEqual(connection.execute(f'SELECT count(*) FROM public.{table} WHERE activity=%s',
#                                                         (identifiers[-1],)).fetchone(), (1,))
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_opening_keeps_exact_newest_thousand_independently_for_two_repositories_and_globals

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_only_exact_live_invocations_survive_the_limit_and_closed_protection_eventually_expires
#     def test_only_exact_live_invocations_survive_the_limit_and_closed_protection_eventually_expires(self):
#         with self.history.connect() as owner, self.history.connect() as writer:
#             self.history.repositories(owner, 'fixture')
#             with activity.MutationActivity(owner, build=31).session() as live:
#                 live.apply('fixture', 'ingest', self.history.mutation('fixture'))
#                 identifier = self.history.ids(owner, 'fixture')[0]
#                 owner.execute("UPDATE public.mycel_activity SET started_at='2000-01-01' WHERE id=%s", (identifier,))
#                 dead, = self.history.seed(owner, 'fixture', 1, open_entry=True, at='1999-01-01T00:00:00Z')
#                 recent = self.history.seed(owner, 'fixture', 1000)
#                 # A repository operation lock cannot supply the dead entry's
#                 # invocation key, PID, backend start time and generation.
#                 with locks.operation_guard(owner, 'fixture', 'pass'):
#                     removed = self.prune(writer, 'fixture')
#                 self.assertIn(dead, removed)
#                 self.assertEqual(set(self.history.ids(writer, 'fixture')), {*recent, identifier})
#                 live.finish('done')
#                 self.assertIn(identifier, self.history.ids(writer, 'fixture'))
#                 self.assertTrue(locks.invocation_is_live(writer, live.invocation))
#             self.assertEqual(len(self.history.ids(writer, 'fixture')), 1001)
#             with activity.MutationActivity(writer, build=31).session() as next_writer:
#                 next_writer.apply('fixture', 'embed', self.history.mutation('fixture'))
#             survivors = self.history.ids(writer, 'fixture')
#             self.assertEqual(len(survivors), 1000)
#             self.assertNotIn(identifier, survivors)
#             self.assertNotIn(recent[0], survivors)
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_only_exact_live_invocations_survive_the_limit_and_closed_protection_eventually_expires

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact
#     def test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact(self):
#         with self.history.connect() as connection:
#             self.history.repositories(connection, 'fixture')
#             fixtures = removal_fixtures.RepositoryRemovalStoreTests()
#             chunk, version = fixtures.chunk(connection, 'fixture')
#             baseline = fixtures.owner(connection, 'fixture', 'baseline', 'retention-baseline')
#             dependency = uuid4()
#             connection.execute('INSERT INTO public.mycel_dependencies VALUES '
#                 '(%s,%s,%s,%s,%s,\'asserted\',\'{}\',%s)',
#                 (dependency, 'fixture', version, 'fixture:@artifact/source.md#Source',
#                  'fixture:@artifact/source.md#Source', baseline))
#             verification = fixtures.owner(connection, 'fixture', 'verification', 'retention-verification')
#             connection.execute('INSERT INTO public.mycel_verifications VALUES (%s,%s,%s,clock_timestamp(),\'{}\',%s)',
#                                (uuid4(), 'fixture', chunk, verification))
#             classifier = fixtures.owner(connection, 'fixture', 'classification', 'retention-classifier')
#             connection.execute('INSERT INTO public.mycel_classification_work VALUES (%s,%s,%s,NULL,\'{}\',%s)',
#                                (uuid4(), 'fixture', dependency, classifier))
#             drift_owner = fixtures.owner(connection, 'fixture', 'drift', 'retention-classification-bundle')
#             bundle = uuid4()
#             connection.execute('INSERT INTO public.mycel_drifts VALUES '
#                 '(%s,%s,%s,clock_timestamp(),clock_timestamp(),\'{}\',%s)',
#                 (bundle, 'fixture', version, drift_owner))
#             identifiers = self.history.seed(connection, 'fixture', 1000)
#             self.history.details(connection, identifiers[0], bundle=str(bundle))
#             evidence_tables = tuple(table for table in TABLES if table.name in {
#                 'mycel_snapshots', 'mycel_manifests', 'mycel_evidence_owners', 'mycel_evidence_references',
#                 'mycel_dependencies', 'mycel_verifications', 'mycel_classification_work', 'mycel_drifts'})
#             before = self.history.state(connection, tables=evidence_tables)
#             with activity.MutationActivity(connection, build=31).session() as audit:
#                 audit.apply('fixture', 'embed', self.history.mutation('fixture'))
#             self.assertNotIn(identifiers[0], self.history.ids(connection, 'fixture'))
#             self.assertEqual(self.history.state(connection, tables=evidence_tables), before)
#             for table in ('mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications'):
#                 self.assertEqual(connection.execute(f'SELECT count(*) FROM public.{table}').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions
#     def test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions(self):
#         with self.history.connect() as connection:
#             self.history.repositories(connection, 'fixture')
#             old = self.history.seed(connection, 'fixture', 1000)
#             actual = ActivityRetentionStore.prune_in_transaction
#
#             def fail_after_prune(store, repository):
#                 actual(store, repository)
#                 raise MycelError('internal', 'The retention transaction failed.')
#
#             with activity.MutationActivity(connection, build=31).session() as audit:
#                 # The caller's removal-protection identity is allocated
#                 # outside its feature transaction and remains reusable.
#                 with locks.mutation_guard(connection, 'fixture'):
#                     pass
#                 before = self.history.state(connection)
#                 with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
#                     with self.assertRaises(MycelError) as error:
#                         audit.apply('fixture', 'ingest', self.history.mutation('fixture',
#                             files=(activity.FileChange('code', 'same.py', 'disk', 'changed'),)))
#                 self.assertEqual(error.exception.code, 'internal')
#                 self.assertEqual(self.history.state(connection), before)
#                 audit.apply('fixture', 'ingest', self.history.mutation('fixture'))
#                 opened = self.history.ids(connection, 'fixture')[0]
#                 connection.execute("UPDATE public.mycel_activity SET started_at='1999-01-01' WHERE id=%s", (opened,))
#                 self.history.seed(connection, 'fixture', 2, at='2002-01-01T00:00:00Z')
#                 before = self.history.state(connection)
#                 with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
#                     with self.assertRaises(MycelError) as error:
#                         audit.finish('done', counts={('fixture', 'ingest'): {'applied': 7}})
#                 self.assertEqual(error.exception.code, 'internal')
#                 self.assertEqual(self.history.state(connection), before)
#                 audit.finish('done', counts={('fixture', 'ingest'): {'applied': 7}})
#                 self.assertEqual(len(self.history.ids(connection, 'fixture')), 1001)
#                 self.assertEqual(activity.activity_state(connection, opened)['counts'], {'applied': 7})
#             self.assertNotIn(old[0], self.history.ids(connection, 'fixture'))
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_concurrent_group_writers_refuse_without_partial_feature_or_prune_then_retry
#     def test_concurrent_group_writers_refuse_without_partial_feature_or_prune_then_retry(self):
#         with self.history.connect() as first, self.history.connect() as second:
#             self.history.repositories(first, 'fixture')
#             self.history.seed(first, 'fixture', 1000)
#             raw = b'An independent feature write must roll back with its audit.'
#             receipt = uuid4()
#
#             def second_write(connection):
#                 # Returned embedding receipts deliberately have no repository
#                 # FK. This reaches the activity group guard rather than
#                 # blocking earlier on a feature table's parent-row FK check.
#                 connection.execute('INSERT INTO public.mycel_embedding_receipts '
#                     '(id,repository,model,dimensions,payload) VALUES (%s,\'fixture\',\'voyage-code-4\',1024,%s)',
#                     (receipt, raw))
#                 return activity.AppliedMutation(True, {'applied': 1})
#
#             with activity.MutationActivity(first, build=31).session() as left, \
#                     activity.MutationActivity(second, build=31).session() as right:
#                 with locks.mutation_guard(first, 'fixture'), locks.atomic_transaction(first):
#                     left.record_in_transaction('fixture', 'ingest', activity.AppliedMutation(True, {'applied': 1}))
#                     with self.assertRaises(MycelError) as error:
#                         right.apply('fixture', 'embed', second_write)
#                     self.assertEqual(error.exception.code, 'internal')
#                     self.assertIsNone(second.execute('SELECT 1 FROM public.mycel_embedding_receipts WHERE id=%s', (receipt,)).fetchone())
#                     self.assertEqual(len(self.history.ids(second, 'fixture')), 1000)
#                 right.apply('fixture', 'embed', second_write)
#                 self.assertEqual(len(self.history.ids(second, 'fixture')), 1000)
#                 with checked_store(first), locks.atomic_transaction(first):
#                     ActivityRetentionStore(first).guard_in_transaction('fixture')
#                     with self.assertRaises(MycelError) as closing:
#                         right.finish('done')
#                     self.assertEqual(closing.exception.code, 'internal')
#                     self.assertEqual(second.execute('SELECT outcome,ended_at FROM public.mycel_activity '
#                         'WHERE invocation=%s', (right.invocation.id,)).fetchone(), (None, None))
#                 right.finish('done')
#                 left.finish('done')
#             self.assertEqual(len(self.history.ids(first, 'fixture')), 1000)
#             self.assertIsNotNone(first.execute('SELECT 1 FROM public.mycel_embedding_receipts WHERE id=%s', (receipt,)).fetchone())
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_concurrent_group_writers_refuse_without_partial_feature_or_prune_then_retry

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups
#     def test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups(self):
#         with self.history.connect() as holder, self.history.connect() as writer:
#             self.history.repositories(holder, 'fixture', 'other')
#             groups = {owner: self.history.seed(holder, owner, 1001) for owner in ('fixture', 'other', None)}
#             parent_values = holder.execute('SELECT to_jsonb(t) FROM public.mycel_repository_state t '
#                                            'ORDER BY repository').fetchall()
#             store_values = holder.execute('SELECT to_jsonb(t) FROM public.mycel_store t').fetchall()
#             lock_values = holder.execute('SELECT * FROM public.mycel_lock_keys ORDER BY key').fetchall()
#             sequence_values = self.history.state(holder, tables=(), sequences=True)
#             for owner in ('fixture', None):
#                 with checked_store(holder), locks.atomic_transaction(holder):
#                     if owner is None:
#                         holder.execute('SELECT singleton FROM public.mycel_store WHERE singleton=true FOR KEY SHARE')
#                     else:
#                         holder.execute('SELECT repository FROM public.mycel_repository_state '
#                                        'WHERE repository=%s FOR KEY SHARE', (owner,))
#                     with checked_store(writer), locks.atomic_transaction(writer):
#                         # A wrong lock upgrade must fail this proof promptly,
#                         # rather than leaving its peer waiting for our exit.
#                         writer.execute("SET LOCAL lock_timeout='20ms'")
#                         deleted = ActivityRetentionStore(writer).prune_in_transaction(owner)
#                     self.assertEqual(set(deleted), {groups[owner][0]})
#                     self.assertEqual(len(self.history.ids(writer, owner)), 1000)
#             with checked_store(holder), locks.atomic_transaction(holder):
#                 ActivityRetentionStore(holder).guard_in_transaction('fixture')
#                 with checked_store(writer), locks.atomic_transaction(writer):
#                     deleted = ActivityRetentionStore(writer).prune_in_transaction('other')
#                 self.assertEqual(set(deleted), {groups['other'][0]})
#                 # Global history is another independent writer group.
#                 with checked_store(writer), locks.atomic_transaction(writer):
#                     self.assertEqual(ActivityRetentionStore(writer).prune_in_transaction(None), ())
#             self.assertEqual(holder.execute('SELECT to_jsonb(t) FROM public.mycel_repository_state t '
#                 'ORDER BY repository').fetchall(), parent_values)
#             self.assertEqual(holder.execute('SELECT to_jsonb(t) FROM public.mycel_store t').fetchall(), store_values)
#             self.assertEqual(holder.execute('SELECT * FROM public.mycel_lock_keys ORDER BY key').fetchall(), lock_values)
#             self.assertEqual(self.history.state(holder, tables=(), sequences=True), sequence_values)
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry
#     def test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry(self):
#         with self.history.connect() as stale, self.history.connect() as peer:
#             self.history.repositories(stale, 'fixture')
#             old = self.history.seed(stale, 'fixture', 1000)
#             left_receipt, peer_receipt = uuid4(), uuid4()
#
#             def write_receipt(connection, identifier, payload):
#                 # No parent FK or parent feature update: the retained group's
#                 # row-version change must come from the activity writer.
#                 connection.execute('INSERT INTO public.mycel_embedding_receipts '
#                     '(id,repository,model,dimensions,payload) VALUES (%s,\'fixture\',\'voyage-code-4\',1024,%s)',
#                     (identifier, payload))
#                 return activity.AppliedMutation(True, {'applied': 1})
#
#             committed = None
#             with activity.MutationActivity(stale, build=31).session() as left, \
#                     activity.MutationActivity(peer, build=31).session() as right:
#                 with self.assertRaises(MycelError) as failure:
#                     with locks.mutation_guard(stale, 'fixture'), locks.atomic_transaction(stale):
#                         stale.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
#                         stale.execute("SET LOCAL lock_timeout='20ms'")
#                         self.assertEqual(set(self.history.ids(stale, 'fixture')), set(old))
#                         right.apply('fixture', 'embed',
#                             lambda connection: write_receipt(connection, peer_receipt, b'peer committed feature'))
#                         right.finish('done')
#                         committed = self.history.state(peer)
#                         # The old snapshot still contains the pruned row and
#                         # cannot see the peer's newly opened/closed activity.
#                         self.assertEqual(set(self.history.ids(stale, 'fixture')), set(old))
#                         result = write_receipt(stale, left_receipt, b'must roll back with stale audit')
#                         left.record_in_transaction('fixture', 'ingest', result)
#                 self.assertEqual(failure.exception.code, 'internal')
#                 self.assertIsNotNone(committed)
#                 self.assertEqual(self.history.state(peer), committed)
#                 self.assertIsNone(peer.execute('SELECT 1 FROM public.mycel_embedding_receipts WHERE id=%s',
#                                                (left_receipt,)).fetchone())
#                 self.assertEqual(peer.execute('SELECT count(*) FROM public.mycel_activity WHERE invocation=%s',
#                                               (left.invocation.id,)).fetchone(), (0,))
#                 left.apply('fixture', 'ingest',
#                     lambda connection: write_receipt(connection, left_receipt, b'fresh retry committed feature'))
#                 left.finish('done')
#             survivors = self.history.ids(peer, 'fixture')
#             self.assertEqual(len(survivors), 1000)
#             self.assertNotIn(old[0], survivors)
#             self.assertNotIn(old[1], survivors)
#             self.assertEqual(peer.execute('SELECT payload FROM public.mycel_embedding_receipts WHERE id=%s',
#                                           (left_receipt,)).fetchone()[0], b'fresh retry committed feature')
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_actual_numbered_initialization_prunes_global_history_atomically_with_dimension_change
#     def test_actual_numbered_initialization_prunes_global_history_atomically_with_dimension_change(self):
#         with self.history.connect() as connection:
#             old = self.history.seed(connection, None, 1000)
#             self.history.details(connection, old[0])
#             actual = ActivityRetentionStore.prune_in_transaction
#
#             def fail_after_prune(store, repository):
#                 actual(store, repository)
#                 raise MycelError('internal', 'The init retention transaction failed.')
#
#             before = self.history.state(connection)
#             with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
#                 with self.assertRaises(MycelError):
#                     initialize_store(connection, dimensions=2048, build=31,
#                                      address=self.store_fixture.backend.address(self.store_fixture.database))
#             # Invocation protocol identities may be allocated before a schema
#             # transaction; the feature schema and all activity remain exact.
#             after = self.history.state(connection)
#             for name in before.keys() - {'mycel_invocations', 'mycel_lock_keys'}:
#                 self.assertEqual(after[name], before[name], name)
#             self.assertEqual(require_store(connection).dimensions, 1024)
#             initialize_store(connection, dimensions=2048, build=31,
#                              address=self.store_fixture.backend.address(self.store_fixture.database))
#             self.assertEqual(require_store(connection).dimensions, 2048)
#             identifiers = self.history.ids(connection, None)
#             self.assertEqual(len(identifiers), 1000)
#             self.assertNotIn(old[0], identifiers)
#             self.assertEqual(activity.activity_state(connection, identifiers[0])['kind'], 'init')
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_actual_numbered_initialization_prunes_global_history_atomically_with_dimension_change

# TEST-TIER-DISABLED-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_numbered_repository_removal_deletes_its_history_and_retains_foreign_evidence_and_global_limit
#     def test_numbered_repository_removal_deletes_its_history_and_retains_foreign_evidence_and_global_limit(self):
#         fixture = removal_fixtures.RepositoryRemovalStoreTests()
#         fixture.store_fixture = self.store_fixture
#         fixture.setUp()
#         self.addCleanup(fixture.doCleanups)
#         with fixture.connect() as connection:
#             fixture.seed(connection, 'fixture', complete=True)
#             fixture.seed(connection, 'other', complete=True)
#             owned = self.history.ids(connection, 'fixture')
#             other_activity = self.history.ids(connection, 'other')
#             foreign_details = {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
#                 'WHERE activity=ANY(%s) ORDER BY to_jsonb(t)::text', (other_activity,)).fetchall()
#                 for table in ('mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications')}
#             foreign = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
#                        "WHERE to_jsonb(t)->>'repository'='other' ORDER BY to_jsonb(t)::text").fetchall()
#                        for table in TABLES}
#             old = self.history.seed(connection, None, 1000)
#             self.history.details(connection, old[0])
#             before = self.history.state(connection)
#             actual = ActivityRetentionStore.prune_in_transaction
#
#             def fail_after_prune(store, repository):
#                 actual(store, repository)
#                 raise MycelError('internal', 'The removal retention transaction failed.')
#
#             with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
#                 with self.assertRaises(MycelError) as error:
#                     RepositoryRemovalStore(connection).remove(fixture.settings, 'fixture', build=31)
#             self.assertEqual(error.exception.code, 'internal')
#             after = self.history.state(connection)
#             for name in before.keys() - {'mycel_invocations', 'mycel_lock_keys'}:
#                 self.assertEqual(after[name], before[name], name)
#             reply = RepositoryRemovalStore(connection).remove(fixture.settings, 'fixture', build=31)
#             self.assertNotIn('error', reply)
#             self.assertEqual(self.history.ids(connection, 'fixture'), [])
#             for table in ('mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications'):
#                 self.assertEqual(connection.execute(f'SELECT count(*) FROM public.{table} WHERE activity=ANY(%s)',
#                                                     (owned,)).fetchone(), (0,))
#             for table in TABLES:
#                 self.assertEqual(connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
#                     "WHERE to_jsonb(t)->>'repository'='other' ORDER BY to_jsonb(t)::text").fetchall(),
#                     foreign[table.name], table.name)
#             for table, expected in foreign_details.items():
#                 self.assertEqual(connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
#                     'WHERE activity=ANY(%s) ORDER BY to_jsonb(t)::text', (other_activity,)).fetchall(), expected)
#             globals_ = self.history.ids(connection, None)
#             self.assertEqual(len(globals_), 1000)
#             self.assertNotIn(old[0], globals_)
#             removal = activity.activity_state(connection, globals_[0])
#             self.assertIsNone(removal['repository'])
#             self.assertEqual((removal['kind'], removal['outcome'], removal['counts']), ('remove', 'done', reply))
# TEST-TIER-DISABLED-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_numbered_repository_removal_deletes_its_history_and_retains_foreign_evidence_and_global_limit


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:6
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:6

# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:14
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:14

# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:15
# from mycel._repository_removal import RepositoryRemovalStore
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:15

# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:17
# from mycel._store import TABLES, checked_store, initialize_store, require_store
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:20
#     from . import test_repository_removal as removal_fixtures
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:20

# TEST-TIER-IMPORTS-BEGIN tests/test_activity_retention.py:22
#     import test_repository_removal as removal_fixtures
# TEST-TIER-IMPORTS-END tests/test_activity_retention.py:22

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
