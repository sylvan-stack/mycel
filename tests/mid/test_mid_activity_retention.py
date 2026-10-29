"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_activity_retention as _support
from test_activity_retention import (ActivityRetentionStore ,MycelError ,TABLES ,activity ,checked_store ,locks ,patch ,removal_fixtures ,uuid4)


class ActivityRetentionStoreTests(_support.ActivityRetentionStoreTests):


# TEST-TIER-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact
    def test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture')
            fixtures = removal_fixtures.RepositoryRemovalStoreTests()
            chunk, version = fixtures.chunk(connection, 'fixture')
            baseline = fixtures.owner(connection, 'fixture', 'baseline', 'retention-baseline')
            dependency = uuid4()
            connection.execute('INSERT INTO public.mycel_dependencies VALUES '
                '(%s,%s,%s,%s,%s,\'asserted\',\'{}\',%s)',
                (dependency, 'fixture', version, 'fixture:@artifact/source.md#Source',
                 'fixture:@artifact/source.md#Source', baseline))
            verification = fixtures.owner(connection, 'fixture', 'verification', 'retention-verification')
            connection.execute('INSERT INTO public.mycel_verifications VALUES (%s,%s,%s,clock_timestamp(),\'{}\',%s)',
                               (uuid4(), 'fixture', chunk, verification))
            classifier = fixtures.owner(connection, 'fixture', 'classification', 'retention-classifier')
            connection.execute('INSERT INTO public.mycel_classification_work VALUES (%s,%s,%s,NULL,\'{}\',%s)',
                               (uuid4(), 'fixture', dependency, classifier))
            drift_owner = fixtures.owner(connection, 'fixture', 'drift', 'retention-classification-bundle')
            bundle = uuid4()
            connection.execute('INSERT INTO public.mycel_drifts VALUES '
                '(%s,%s,%s,clock_timestamp(),clock_timestamp(),\'{}\',%s)',
                (bundle, 'fixture', version, drift_owner))
            identifiers = self.history.seed(connection, 'fixture', 1000)
            self.history.details(connection, identifiers[0], bundle=str(bundle))
            evidence_tables = tuple(table for table in TABLES if table.name in {
                'mycel_snapshots', 'mycel_manifests', 'mycel_evidence_owners', 'mycel_evidence_references',
                'mycel_dependencies', 'mycel_verifications', 'mycel_classification_work', 'mycel_drifts'})
            before = self.history.state(connection, tables=evidence_tables)
            with activity.MutationActivity(connection, build=31).session() as audit:
                audit.apply('fixture', 'embed', self.history.mutation('fixture'))
            self.assertNotIn(identifiers[0], self.history.ids(connection, 'fixture'))
            self.assertEqual(self.history.state(connection, tables=evidence_tables), before)
            for table in ('mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications'):
                self.assertEqual(connection.execute(f'SELECT count(*) FROM public.{table}').fetchone(), (0,))
# TEST-TIER-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_pruning_all_attached_detail_leaves_baseline_verification_and_classifier_evidence_exact

# TEST-TIER-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions
    def test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions(self):
        with self.history.connect() as connection:
            self.history.repositories(connection, 'fixture')
            old = self.history.seed(connection, 'fixture', 1000)
            actual = ActivityRetentionStore.prune_in_transaction

            def fail_after_prune(store, repository):
                actual(store, repository)
                raise MycelError('internal', 'The retention transaction failed.')

            with activity.MutationActivity(connection, build=31).session() as audit:
                # The caller's removal-protection identity is allocated
                # outside its feature transaction and remains reusable.
                with locks.mutation_guard(connection, 'fixture'):
                    pass
                before = self.history.state(connection)
                with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
                    with self.assertRaises(MycelError) as error:
                        audit.apply('fixture', 'ingest', self.history.mutation('fixture',
                            files=(activity.FileChange('code', 'same.py', 'disk', 'changed'),)))
                self.assertEqual(error.exception.code, 'internal')
                self.assertEqual(self.history.state(connection), before)
                audit.apply('fixture', 'ingest', self.history.mutation('fixture'))
                opened = self.history.ids(connection, 'fixture')[0]
                connection.execute("UPDATE public.mycel_activity SET started_at='1999-01-01' WHERE id=%s", (opened,))
                self.history.seed(connection, 'fixture', 2, at='2002-01-01T00:00:00Z')
                before = self.history.state(connection)
                with patch.object(ActivityRetentionStore, 'prune_in_transaction', fail_after_prune):
                    with self.assertRaises(MycelError) as error:
                        audit.finish('done', counts={('fixture', 'ingest'): {'applied': 7}})
                self.assertEqual(error.exception.code, 'internal')
                self.assertEqual(self.history.state(connection), before)
                audit.finish('done', counts={('fixture', 'ingest'): {'applied': 7}})
                self.assertEqual(len(self.history.ids(connection, 'fixture')), 1001)
                self.assertEqual(activity.activity_state(connection, opened)['counts'], {'applied': 7})
            self.assertNotIn(old[0], self.history.ids(connection, 'fixture'))
# TEST-TIER-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_late_open_and_close_prune_failures_rollback_feature_rows_audits_and_deletions


# TEST-TIER-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups
    def test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups(self):
        with self.history.connect() as holder, self.history.connect() as writer:
            self.history.repositories(holder, 'fixture', 'other')
            groups = {owner: self.history.seed(holder, owner, 1001) for owner in ('fixture', 'other', None)}
            parent_values = holder.execute('SELECT to_jsonb(t) FROM public.mycel_repository_state t '
                                           'ORDER BY repository').fetchall()
            store_values = holder.execute('SELECT to_jsonb(t) FROM public.mycel_store t').fetchall()
            lock_values = holder.execute('SELECT * FROM public.mycel_lock_keys ORDER BY key').fetchall()
            sequence_values = self.history.state(holder, tables=(), sequences=True)
            for owner in ('fixture', None):
                with checked_store(holder), locks.atomic_transaction(holder):
                    if owner is None:
                        holder.execute('SELECT singleton FROM public.mycel_store WHERE singleton=true FOR KEY SHARE')
                    else:
                        holder.execute('SELECT repository FROM public.mycel_repository_state '
                                       'WHERE repository=%s FOR KEY SHARE', (owner,))
                    with checked_store(writer), locks.atomic_transaction(writer):
                        # A wrong lock upgrade must fail this proof promptly,
                        # rather than leaving its peer waiting for our exit.
                        writer.execute("SET LOCAL lock_timeout='20ms'")
                        deleted = ActivityRetentionStore(writer).prune_in_transaction(owner)
                    self.assertEqual(set(deleted), {groups[owner][0]})
                    self.assertEqual(len(self.history.ids(writer, owner)), 1000)
            with checked_store(holder), locks.atomic_transaction(holder):
                ActivityRetentionStore(holder).guard_in_transaction('fixture')
                with checked_store(writer), locks.atomic_transaction(writer):
                    deleted = ActivityRetentionStore(writer).prune_in_transaction('other')
                self.assertEqual(set(deleted), {groups['other'][0]})
                # Global history is another independent writer group.
                with checked_store(writer), locks.atomic_transaction(writer):
                    self.assertEqual(ActivityRetentionStore(writer).prune_in_transaction(None), ())
            self.assertEqual(holder.execute('SELECT to_jsonb(t) FROM public.mycel_repository_state t '
                'ORDER BY repository').fetchall(), parent_values)
            self.assertEqual(holder.execute('SELECT to_jsonb(t) FROM public.mycel_store t').fetchall(), store_values)
            self.assertEqual(holder.execute('SELECT * FROM public.mycel_lock_keys ORDER BY key').fetchall(), lock_values)
            self.assertEqual(self.history.state(holder, tables=(), sequences=True), sequence_values)
# TEST-TIER-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_group_guards_remain_compatible_with_peer_fk_key_share_and_other_groups

# TEST-TIER-BEGIN tests/test_activity_retention.py::ActivityRetentionStoreTests.test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry
    def test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry(self):
        with self.history.connect() as stale, self.history.connect() as peer:
            self.history.repositories(stale, 'fixture')
            old = self.history.seed(stale, 'fixture', 1000)
            left_receipt, peer_receipt = uuid4(), uuid4()

            def write_receipt(connection, identifier, payload):
                # No parent FK or parent feature update: the retained group's
                # row-version change must come from the activity writer.
                connection.execute('INSERT INTO public.mycel_embedding_receipts '
                    '(id,repository,model,dimensions,payload) VALUES (%s,\'fixture\',\'voyage-code-4\',1024,%s)',
                    (identifier, payload))
                return activity.AppliedMutation(True, {'applied': 1})

            committed = None
            with activity.MutationActivity(stale, build=31).session() as left, \
                    activity.MutationActivity(peer, build=31).session() as right:
                with self.assertRaises(MycelError) as failure:
                    with locks.mutation_guard(stale, 'fixture'), locks.atomic_transaction(stale):
                        stale.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                        stale.execute("SET LOCAL lock_timeout='20ms'")
                        self.assertEqual(set(self.history.ids(stale, 'fixture')), set(old))
                        right.apply('fixture', 'embed',
                            lambda connection: write_receipt(connection, peer_receipt, b'peer committed feature'))
                        right.finish('done')
                        committed = self.history.state(peer)
                        # The old snapshot still contains the pruned row and
                        # cannot see the peer's newly opened/closed activity.
                        self.assertEqual(set(self.history.ids(stale, 'fixture')), set(old))
                        result = write_receipt(stale, left_receipt, b'must roll back with stale audit')
                        left.record_in_transaction('fixture', 'ingest', result)
                self.assertEqual(failure.exception.code, 'internal')
                self.assertIsNotNone(committed)
                self.assertEqual(self.history.state(peer), committed)
                self.assertIsNone(peer.execute('SELECT 1 FROM public.mycel_embedding_receipts WHERE id=%s',
                                               (left_receipt,)).fetchone())
                self.assertEqual(peer.execute('SELECT count(*) FROM public.mycel_activity WHERE invocation=%s',
                                              (left.invocation.id,)).fetchone(), (0,))
                left.apply('fixture', 'ingest',
                    lambda connection: write_receipt(connection, left_receipt, b'fresh retry committed feature'))
                left.finish('done')
            survivors = self.history.ids(peer, 'fixture')
            self.assertEqual(len(survivors), 1000)
            self.assertNotIn(old[0], survivors)
            self.assertNotIn(old[1], survivors)
            self.assertEqual(peer.execute('SELECT payload FROM public.mycel_embedding_receipts WHERE id=%s',
                                          (left_receipt,)).fetchone()[0], b'fresh retry committed feature')
# TEST-TIER-END tests/test_activity_retention.py::ActivityRetentionStoreTests.test_stale_repeatable_snapshot_refuses_after_peer_commit_and_rolls_back_feature_then_fresh_retry
