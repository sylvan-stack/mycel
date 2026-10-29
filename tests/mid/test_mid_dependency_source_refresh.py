"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_dependency_source_refresh as _support
from test_dependency_source_refresh import (
    AssertedRemoval,
    DependencyApplicationStore,
    DependencySourceRefreshStoreTests,
    EvidenceError,
    EvidenceStore,
    ExitStack,
    LocatedCaptureStore,
    LocatedDependencyProducer,
    MutationActivity,
    PinInputs,
    RetainedDependencyResolver,
    SourceAddress,
    SourceResolver,
    activity_state,
    atomic_transaction,
    capture_repository,
    checked_store,
    fixtures,
    json,
    load_settings,
    operation_guard,
    patch,
    replace,
    sha256,
    unittest,
)


class DependencySourceRefreshStoreTests(_support.DependencySourceRefreshStoreTests):
# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_only_away_and_restoration_preserve_foreign_pin_and_role
    def test_source_only_away_and_restoration_preserve_foreign_pin_and_role(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            original_answer = self.answer.read_bytes()
            self.source.unlink()
            result = self.publish(connection)
            missing = self.dependencies(connection)
            self.assertEqual(self.pins(missing), self.pins(before))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')
            state = missing[0][5]
            self.assertEqual((state['sourceState'], state['sourceExistence'], state['reasons']),
                             ('source_removed', 'away', ['source_removed']))
            self.assertEqual(state['sourceAbsence']['state'], 'away')
            self.assertEqual(state['sourceAbsence']['place'], 'fixture:@artifact/source.md#Source')
            self.assertIsInstance(state['sourceAbsence']['previousFileHash'], str)
            self.assertEqual(state['sourceAbsence']['observedAt'], '2026-10-09T11:00:00Z')
            counts = result.counts['dependencyRepositories']['downstream']
            self.assertEqual((counts['pinsCaptured'], counts['pinsInherited'], counts['refsChanged']), (0, 0, 1))
            stable = self.state(connection)
            self.assertFalse(self.publish(connection).changed)
            self.assertEqual(self.state(connection), stable)
            self.source.write_bytes(b'# Source\nChanged restored source.\n')
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual((restored[0][5]['sourceState'], restored[0][5]['sourceExistence'],
                              restored[0][5]['reasons']), ('present', 'present', ['source_changed']))
            self.assertEqual(len(self.edges(connection)), 1)
            self.assertEqual(self.answer.read_bytes(), original_answer)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_only_away_and_restoration_preserve_foreign_pin_and_role

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_last_location_deletion_and_recreation_keep_exact_dependant_owned_evidence
    def test_last_location_deletion_and_recreation_keep_exact_dependant_owned_evidence(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            old_source = self.edges(connection)[0][1]
            baseline = EvidenceStore(connection).read_baseline('downstream', before[0][7])
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            missing = self.dependencies(connection)
            self.assertEqual(self.pins(missing), self.pins(before))
            self.assertEqual(missing[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(missing[0][5]['sourceAbsence']['state'], 'deleted')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_source,)).fetchone(), (0,))
            retained = EvidenceStore(connection).read_baseline('downstream', before[0][7])
            self.assertEqual(retained.manifest, baseline.manifest)
            self.assertIn(self.source_bytes, [blob.source for blob in retained.snapshots])
            self.source.write_bytes(self.source_bytes)
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual(restored[0][5]['reasons'], [])
            self.assertNotEqual(self.edges(connection)[0][1], old_source)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_last_location_deletion_and_recreation_keep_exact_dependant_owned_evidence

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_pass_retries_never_resolved_foreign_declaration
    def test_source_pass_retries_never_resolved_foreign_declaration(self):
        self.source.unlink()
        self.base.commit()
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.assertIsNone(before[0][6])
            self.assertEqual(before[0][5]['sourceState'], 'unresolved')
            self.source.write_bytes(self.source_bytes)
            result = self.publish(connection)
            resolved = self.dependencies(connection)
            self.assertEqual(resolved[0][0:4], before[0][0:4])
            self.assertIsNotNone(resolved[0][6])
            self.assertEqual(resolved[0][5]['sourceState'], 'present')
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['pinsCaptured'], 1)
            self.assertEqual(self.role(connection), 'derived')
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_pass_retries_never_resolved_foreign_declaration

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_disabled_foreign_owner_is_unchanged_by_source_publication
    def test_disabled_foreign_owner_is_unchanged_by_source_publication(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            edges = self.edges(connection)
            self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
                                                                            '[repos.downstream]\nenabled=false'))
            self.reload()
            self.source.write_bytes(b'# Source\nChange while owner disabled.\n')
            result = self.publish(connection)
            self.assertEqual(self.dependencies(connection), before)
            self.assertEqual(self.edges(connection), edges)
            self.assertNotIn('downstream', result.counts.get('dependencyRepositories', {}))
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_disabled_foreign_owner_is_unchanged_by_source_publication

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_settings_only_source_disable_and_enable_recheck_unchanged_captures
    def test_settings_only_source_disable_and_enable_recheck_unchanged_captures(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=true',
                                                                            '[repos.fixture]\nenabled=false'))
            self.reload()
            invalid = self.publish(connection, 'downstream')
            disabled = self.dependencies(connection)
            self.assertTrue(invalid.changed)
            self.assertEqual(self.pins(disabled), self.pins(before))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(disabled[0][5]['sourceExistence'], 'ineligible')
            self.assertEqual(disabled[0][5]['resolution']['state'], 'invalid')
            self.assertEqual(self.role(connection), 'authored')
            self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=false',
                                                                            '[repos.fixture]\nenabled=true'))
            self.reload()
            result = self.publish(connection)
            recovered = self.dependencies(connection)
            self.assertEqual(self.pins(recovered), self.pins(before))
            self.assertEqual(recovered[0][5]['sourceExistence'], 'present')
            self.assertEqual(recovered[0][5]['reasons'], [])
            self.assertEqual(len(self.edges(connection)), 1)
            self.assertEqual(self.role(connection), 'derived')
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['refsChanged'], 1)
            stable = self.state(connection)
            self.publish(connection)
            self.assertEqual(self.state(connection), stable)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_settings_only_source_disable_and_enable_recheck_unchanged_captures

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_empty_file_selection_survives_deletion_and_recreation_without_chunk_edges
    def test_empty_file_selection_survives_deletion_and_recreation_without_chunk_edges(self):
        self.source.write_bytes(b'')
        self.base.commit()
        self.answer.write_bytes(self.answer.read_bytes().replace(b'source.md#Source', b'source.md'))
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            removed = self.dependencies(connection)
            self.assertEqual(self.pins(removed), self.pins(before))
            self.assertEqual(removed[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(removed[0][5]['sourceAbsence']['previousFileHash'], sha256(b'').hexdigest())
            self.assertEqual(self.role(connection), 'derived')
            self.source.write_bytes(b'')
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual((restored[0][5]['sourceExistence'], restored[0][5]['reasons']), ('present', []))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_empty_file_selection_survives_deletion_and_recreation_without_chunk_edges

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_removed_foreign_branch_refuses_an_away_observation
    def test_unindexed_removed_foreign_branch_refuses_an_away_observation(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.unlink()
            self.publish(connection)
            self.assertEqual(self.dependencies(connection)[0][5]['sourceExistence'], 'away')
            before = self.state(connection)
            self.base.git('checkout', '--detach')
            self.base.git('branch', '--delete', '--force', 'fixture-main')
            self.assertFalse(self.source.exists())
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_removed_foreign_branch_refuses_an_away_observation

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_new_foreign_branch_file_refuses_a_deleted_observation
    def test_unindexed_new_foreign_branch_file_refuses_a_deleted_observation(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            self.assertEqual(self.dependencies(connection)[0][5]['sourceExistence'], 'deleted')
            before = self.state(connection)
            self.base.git('checkout', '-b', 'hidden-source')
            self.source.write_bytes(b'# Source\nNew source held by another local branch.\n')
            self.base.commit()
            self.base.git('checkout', 'fixture-main')
            self.assertFalse(self.source.exists())
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_new_foreign_branch_file_refuses_a_deleted_observation

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_recreation_of_deleted_moved_source_refuses_original_declaration
    def test_unindexed_recreation_of_deleted_moved_source_refuses_original_declaration(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            moved = self.base.artifact / 'moved.md'
            self.source.rename(moved)
            self.base.commit()
            self.publish(connection)
            moved_rows = self.dependencies(connection)
            self.assertEqual(self.pins(moved_rows), self.pins(before))
            self.assertEqual(moved_rows[0][4], 'fixture:@artifact/moved.md#Source')
            moved.unlink()
            self.base.commit()
            self.publish(connection)
            removed = self.dependencies(connection)
            self.assertEqual(removed[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(removed[0][5]['sourceAbsence']['place'], 'fixture:@artifact/moved.md#Source')
            stable = self.state(connection)
            moved.write_bytes(b'# Source\nRecreated current natural place without ingest.\n')
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), stable)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_unindexed_recreation_of_deleted_moved_source_refuses_original_declaration

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner
    def test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.state(connection)
            original_answer = self.answer.read_bytes()
            self.source.write_bytes(b'# Source\nChanged source requiring observation.\n')
            actual = DependencyApplicationStore.apply_in_transaction

            def mutate_after_foreign_application(store, *args, **kwargs):
                reply = actual(store, *args, **kwargs)
                owner = store.connection.execute("""SELECT f.repository FROM public.mycel_file_locations l
                    JOIN public.mycel_file_versions v ON v.id=l.file_version
                    JOIN public.mycel_files f ON f.id=v.file_id WHERE l.id=%s""", (args[1],)).fetchone()[0]
                if owner == 'downstream':
                    self.answer.write_bytes(original_answer.replace(b'Unchanged dependant.', b'Changed during pass.'))
                return reply

            with patch.object(DependencyApplicationStore, 'apply_in_transaction', mutate_after_foreign_application):
                with self.assertRaises(EvidenceError) as caught:
                    self.publish(connection)
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
            self.answer.write_bytes(original_answer)
            with MutationActivity(connection, build=1).session() as activity:
                with patch.object(activity, '_details', side_effect=RuntimeError('late audit failure')):
                    with self.assertRaises(RuntimeError):
                        self.publish(connection, activity=activity)
                self.assertEqual(self.state(connection), before)
                activity.finish('failed', error={'code': 'internal', 'message': 'fixture failed'})
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_change_in_reply_callback_refuses_all_prospective_rows
    def test_foreign_change_in_reply_callback_refuses_all_prospective_rows(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.state(connection)
            original_answer = self.answer.read_bytes()
            self.source.write_bytes(b'# Source\nChanged source for late reply guard.\n')

            def late_change(repository, counts):
                self.answer.write_bytes(original_answer.replace(b'Unchanged dependant.', b'Late changed dependant.'))
                return counts

            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, reply_counts=late_change)
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_foreign_change_in_reply_callback_refuses_all_prospective_rows

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_and_foreign_activity_share_one_commit_and_owner_counts
    def test_source_and_foreign_activity_share_one_commit_and_owner_counts(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged source with foreign activity.\n')
            with MutationActivity(connection, build=1).session() as activity:
                result = self.publish(connection, activity=activity)
                foreign_counts = result.counts['dependencyRepositories']['downstream']
                activity.finish('done', counts={('fixture', 'ingest'): result.counts,
                                                ('downstream', 'ingest'): foreign_counts})
            rows = connection.execute('SELECT id,repository,invocation FROM public.mycel_activity ORDER BY repository').fetchall()
            self.assertEqual([row[1] for row in rows], ['downstream', 'fixture'])
            self.assertEqual(rows[0][2], rows[1][2])
            foreign = activity_state(connection, rows[0][0])
            self.assertEqual(foreign['counts'], foreign_counts)
            self.assertEqual(foreign['files'], [])
            self.assertEqual(foreign['decisions'], [])
            self.assertEqual(activity_state(connection, rows[1][0])['counts'], result.counts)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_source_and_foreign_activity_share_one_commit_and_owner_counts

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_two_source_only_changes_keep_foreign_cumulative_reply_and_activity_counts
    def test_two_source_only_changes_keep_foreign_cumulative_reply_and_activity_counts(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            committed, previewed = {}, {}

            def add(previous, local):
                # Repository reply portions and current stale/pending state
                # are snapshots; processing counters accumulate per pass.
                return {key: value if key in {'dependencyRepositories', 'stale', 'stalePending'} else
                        add(previous.get(key, {}), value) if isinstance(value, dict) else
                        previous.get(key, 0) + value for key, value in local.items()}

            def cumulative(repository, local):
                value = add(committed.get(repository, {}), local)
                previewed[repository] = value
                return value

            with MutationActivity(connection, build=1).session() as activity:
                for text in (b'First source change.', b'Second source change.'):
                    self.source.write_bytes(b'# Source\n' + text + b'\n')
                    result = self.publish(connection, activity=activity, reply_counts=cumulative)
                    committed = dict(previewed)
                    self.assertEqual(result.counts['dependencyRepositories']['downstream'], committed['downstream'])
                self.assertEqual(committed['downstream']['refsChecked'], 2)
                self.assertEqual(committed['downstream']['refsChanged'], 2)
                self.assertEqual(committed['downstream']['pinsCaptured'], 0)
                self.assertEqual(committed['downstream']['staleChecked'], 2)
                self.assertEqual(committed['downstream']['staleChanged'], 1)
                self.assertEqual(committed['downstream']['staleReasons'], 2)
                self.assertEqual(committed['downstream']['stale'], 1)
                self.assertEqual(committed['fixture']['stalePending'], [])
                entries = connection.execute('SELECT id,repository FROM public.mycel_activity ORDER BY repository').fetchall()
                self.assertEqual([row[1] for row in entries], ['downstream', 'fixture'])
                for identifier, repository in entries:
                    self.assertEqual(activity_state(connection, identifier)['counts'], committed[repository])
                activity.finish('done', counts={(repository, 'ingest'): counts for repository, counts in committed.items()})
            for identifier, repository in entries:
                self.assertEqual(activity_state(connection, identifier)['counts'], committed[repository])
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_two_source_only_changes_keep_foreign_cumulative_reply_and_activity_counts

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_collection_only_unchanged_pass_reports_and_audits_its_feature_mutation
    def test_collection_only_unchanged_pass_reports_and_audits_its_feature_mutation(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            old_version = before[0][1]
            self.answer.write_bytes(self.answer.read_bytes().replace(b'Unchanged dependant.', b'Substantive dependant edit.'))
            self.publish(connection, 'downstream', collect=False)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_version,)).fetchone(), (1,))
            with MutationActivity(connection, build=1).session() as activity:
                result = self.publish(connection, 'downstream', activity=activity)
                self.assertTrue(result.changed)
                self.assertEqual(result.counts['collected']['versions'], 1)
                activity.finish('done', counts={('downstream', 'ingest'): result.counts})
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_version,)).fetchone(), (0,))
            entry = connection.execute('SELECT id,repository FROM public.mycel_activity').fetchone()
            self.assertEqual(entry[1], 'downstream')
            self.assertEqual(activity_state(connection, entry[0])['counts'], result.counts)
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_collection_only_unchanged_pass_reports_and_audits_its_feature_mutation

# TEST-TIER-BEGIN tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_declared_and_asserted_same_source_survive_each_others_removal
    def test_declared_and_asserted_same_source_survive_each_others_removal(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.apply_assertions(connection, assertions=('fixture:@artifact/source.md#Source',))
            both = self.dependencies(connection)
            self.assertEqual({row[2] for row in both}, {'declared', 'asserted'})
            self.assertEqual(len(self.edges(connection)), 2)
            declared = next(row for row in both if row[2] == 'declared')
            self.apply_assertions(connection, remove_assertions=(AssertedRemoval(
                SourceAddress('fixture', 'artifact', 'source.md', 'Source'), 'chunk'),))
            self.assertEqual(self.pins(self.dependencies(connection)), self.pins([declared]))
            self.apply_assertions(connection, assertions=('fixture:@artifact/source.md#Source',))
            asserted = next(row for row in self.dependencies(connection) if row[2] == 'asserted')
            self.answer.write_bytes(b'---\nrole: authored\n---\n# Answer\nUnchanged dependant.\n')
            self.publish(connection, 'downstream')
            self.assertEqual(self.pins(self.dependencies(connection)), self.pins([asserted]))
            self.assertEqual(self.role(connection), 'derived')
            self.apply_assertions(connection, remove_assertions=(AssertedRemoval(
                SourceAddress('fixture', 'artifact', 'source.md', 'Source'), 'chunk'),))
            self.assertEqual(self.dependencies(connection), [])
            self.assertEqual(self.role(connection), 'authored')
# TEST-TIER-END tests/test_dependency_source_refresh.py::DependencySourceRefreshStoreTests.test_declared_and_asserted_same_source_survive_each_others_removal
