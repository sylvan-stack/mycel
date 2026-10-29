"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_verification_history as _support
from test_verification_history import (
    CollectionStore,
    ConfirmationStore,
    EvidenceError,
    Jsonb,
    LocatedCaptureStore,
    MycelError,
    VerificationHistoryStoreTests,
    VerificationReader,
    capture_repository,
    deepcopy,
    fixtures,
    patch,
    sha256,
    snapshot_transaction,
    store,
    unittest,
    validate_verification_record,
)


class VerificationHistoryStoreTests(_support.VerificationHistoryStoreTests):
# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_old_exact_version_collects_but_history_and_owned_evidence_survive_and_exact_text_return_applies
    def test_old_exact_version_collects_but_history_and_owned_evidence_survive_and_exact_text_return_applies(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            original = self.confirm(connection)
            stored = self.records(connection)
            old = stored[0][4]['dependant']['versionId']
            self.path.write_bytes(b'# Guide\nChanged text.\n')
            self.publish(connection)
            self.assertEqual(connection.execute('SELECT id FROM public.mycel_chunk_versions WHERE id=%s', (old,)).fetchall(), [])
            self.assertEqual(self.records(connection), stored)
            validate_verification_record(connection, stored[0])
            self.assertEqual(self.report(connection)['verifications'], [])
            history = self.report(connection, history=True)['verifications']
            self.assertEqual(history, [{**original, 'current': False}])
            self.path.write_bytes(b'# Guide\nOriginal text.\n')
            self.publish(connection)
            self.assertEqual(self.report(connection)['verifications'], [original])
            self.assertNotEqual(connection.execute('SELECT id FROM public.mycel_chunk_versions WHERE snapshot_hash=%s',
                                                   (original['textHash'],)).fetchone()[0], old)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_old_exact_version_collects_but_history_and_owned_evidence_survive_and_exact_text_return_applies

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_branch_switch_selects_only_newest_record_for_resulting_exact_dependant_version
    def test_branch_switch_selects_only_newest_record_for_resulting_exact_dependant_version(self):
        self.helper.initialize(raw=b'# Guide\nOriginal text.\n')
        with self.helper.connect() as connection:
            self.publish(connection)
            first = self.confirm(connection)
            self.helper.git('checkout', '-b', 'other-verification')
            self.path.write_bytes(b'# Guide\nAlternate branch text.\n')
            self.helper.commit()
            self.publish(connection)
            second = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertEqual(self.report(connection)['verifications'], [second])
            self.helper.git('checkout', 'fixture-main')
            self.publish(connection)
            self.assertEqual(self.report(connection)['verifications'], [first])
            self.assertEqual(self.report(connection, history=True)['verifications'],
                             [{**second, 'current': False}, first])
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_branch_switch_selects_only_newest_record_for_resulting_exact_dependant_version

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_branch_only_dependency_and_relation_faults_do_not_invalidate_shared_current_disk_version
    def test_branch_only_dependency_and_relation_faults_do_not_invalidate_shared_current_disk_version(self):
        from io import StringIO
        import os
        from mycel._cli import run
        raw = (b'# Guide\nSame dependant text in both branches.\n\n'
               b'<!-- sources:\nfixture:@artifact/source.md#Source\n-->\n\n'
               b'<!-- related:\nfixture:@artifact/source.md#Source\n-->\n')
        self.helper.initialize(raw=raw)
        source = self.artifact / 'source.md'
        source.write_bytes(b'# Source\nCurrent disk source.\n')
        self.helper.commit()
        self.helper.git('checkout', '-b', 'missing-source')
        source.unlink()
        self.helper.commit()
        self.helper.git('checkout', 'fixture-main')
        output = StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.helper.config)}):
            status = run(['ingest', '--repo', 'fixture'], stdout=output, stderr=StringIO())
        self.assertEqual(status, 0, output.getvalue())
        with self.helper.connect() as connection:
            faults = connection.execute("""SELECT f.chunk_version,coalesce(d.state,r.state)->'declarationLocation'
                FROM public.mycel_ref_faults f
                LEFT JOIN public.mycel_dependencies d ON d.id=f.id
                LEFT JOIN public.mycel_relations r ON r.id=f.id ORDER BY f.id""").fetchall()
            self.assertEqual(len(faults), 2)
            self.assertTrue(all(location['kind'] == 'branch' for _, location in faults))
            current = self.confirm(connection)
            exact = self.records(connection)[0][4]['dependant']['versionId']
            self.assertTrue(all(version == exact for version, _ in faults))
            self.assertTrue(current['current'])
            self.assertEqual(len(current['baselineManifests']), 2)
            self.assertEqual(self.report(connection)['verifications'], [current])
            self.assertEqual(self.report(connection, history=True)['verifications'], [current])
            # Current disk faults retain their original invalidating behavior.
            source.unlink()
            with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.helper.config)}):
                self.assertEqual(run(['ingest', '--repo', 'fixture'], stdout=StringIO(), stderr=StringIO()), 0)
            withdrawn = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertFalse(withdrawn['current'])
            self.assertEqual(self.report(connection)['verifications'], [])
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_branch_only_dependency_and_relation_faults_do_not_invalidate_shared_current_disk_version

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_family_selection_member_addition_and_removal_invalidate_unchanged_dependant
    def test_family_selection_member_addition_and_removal_invalidate_unchanged_dependant(self):
        from mycel._relate import RelateStore
        self.path.write_bytes(b'# Guide\nFamily guide.\n\n<!-- sources:\nfixture:@code/worker.py#Worker\n-->\n')
        code = self.helper.code / 'worker.py'
        original = b'class Worker:\n    def first(self):\n        return 1\n'
        code.write_bytes(original)
        with self.helper.connect() as connection:
            self.publish(connection)
            # The same spelling names a full dependency family and an asserted
            # relation header; one selection must not narrow the other.
            RelateStore(connection).apply(self.settings, self.ref, 'fixture:@code/worker.py#Worker',
                                         settings_home=self.helper.base)
            first = self.confirm(connection)
            self.assertEqual(len(first['sources']), 3)
            self.assertEqual(self.report(connection)['verifications'], [first])
            selections = self.records(connection)[0][4]['selections']
            self.assertEqual([(item['edgeKind'], item['endpoint'], len(item['members'])) for item in selections],
                             [('declared', False, 2), ('related', True, 1)])
            code.write_bytes(original + b'    def second(self):\n        return 2\n')
            self.publish(connection)
            self.assertEqual(self.report(connection)['verifications'], [])
            second = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertEqual(len(second['sources']), 4)
            self.assertEqual(self.report(connection)['verifications'], [second])
            code.write_bytes(original)
            self.publish(connection)
            self.assertEqual(self.report(connection)['verifications'], [])
            self.assertTrue(all(not item['current'] for item in self.report(connection, history=True)['verifications']))
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_family_selection_member_addition_and_removal_invalidate_unchanged_dependant

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_related_source_text_change_ineligible_inputs_and_relation_assertion_are_checked
    def test_related_source_text_change_ineligible_inputs_and_relation_assertion_are_checked(self):
        from io import StringIO
        import os
        from mycel._cli import run
        from mycel._relate import RelateStore
        self.path.write_bytes(b'# Guide\nRelated guide.\n')
        source = self.artifact / 'source.md'
        source.write_bytes(b'# Source\nOriginal source.\n')
        with self.helper.connect() as connection:
            self.publish(connection)
            first = self.confirm(connection)
            RelateStore(connection).apply(self.settings, self.ref, 'fixture:@artifact/source.md#Source',
                                         settings_home=self.helper.base)
            self.assertEqual(self.report(connection)['verifications'], [])
            second = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertEqual(self.report(connection)['verifications'], [second])
            row = connection.execute("SELECT id,left_version,baseline_owner,state FROM public.mycel_relations "
                "WHERE state->'declarationLocation'->>'kind'='disk'").fetchone()
            record = deepcopy(self.records(connection))
            moved = self.artifact / 'moved.md'
            source.rename(moved)
            def policy_ingest():
                output = StringIO()
                with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.helper.config)}):
                    status = run(['ingest', '--repo', 'fixture'], stdout=output, stderr=StringIO())
                self.assertEqual(status, 0, output.getvalue())
            policy_ingest()
            after = connection.execute("SELECT id,left_version,baseline_owner,state FROM public.mycel_relations "
                "WHERE state->'declarationLocation'->>'kind'='disk'").fetchone()
            self.assertEqual(after[:3], row[:3])
            self.assertEqual(after[3]['anchor'], row[3]['anchor'])
            self.assertEqual(after[3]['rawRef'], row[3]['rawRef'])
            self.assertEqual(after[3]['resolution']['place'], 'fixture:@artifact/moved.md#Source')
            self.assertEqual(after[3]['reasons'], [])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_ref_faults').fetchone(), (0,))
            self.assertEqual(self.records(connection), record)
            self.assertEqual(self.report(connection)['verifications'], [second])
            self.assertEqual(self.report(connection, history=True)['verifications'], [second, {**first, 'current': False}])
            source = moved
            source.write_bytes(b'# Source\nChanged relation source.\n')
            policy_ingest()
            self.assertEqual(self.report(connection)['verifications'], [])
            self.assertFalse(self.report(connection, history=True)['verifications'][0]['current'])
            self.assertEqual(self.records(connection)[0][4]['chunkId'], first['chunkId'])
            source.write_bytes(b'# Source\nOriginal source.\n')
            self.publish(connection)
            self.assertEqual(self.report(connection)['verifications'], [second])
            self.helper.config.write_text(self.helper.config.read_text().replace('enabled=true', 'enabled=false'))
            from mycel._settings import load_settings
            disabled = load_settings(path=self.helper.config, home=self.helper.base)
            before = self.state(connection)
            with store.checked_store(connection), snapshot_transaction(connection):
                reply = VerificationReader(connection, disabled).list_in_transaction('fixture', history=True)
            self.assertTrue(all(not item['current'] for item in reply['verifications']))
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_related_source_text_change_ineligible_inputs_and_relation_assertion_are_checked

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_default_newest_exact_record_history_deterministic_and_empty_are_read_only
    def test_default_newest_exact_record_history_deterministic_and_empty_are_read_only(self):
        with self.helper.connect() as connection:
            before = self.state(connection)
            self.assertEqual(self.report(connection), {'repository': 'fixture', 'verifications': []})
            self.assertEqual(self.state(connection), before)
            self.publish(connection)
            first = self.confirm(connection)
            second = self.confirm(connection, at='2026-10-11T12:00:01Z')
            before = self.state(connection)
            self.assertEqual(self.report(connection)['verifications'], [second])
            self.assertEqual(self.report(connection, history=True)['verifications'], [second, {**first, 'current': False}])
            self.assertEqual(self.state(connection), before)
            # Address ordering takes precedence over newer timestamps; tied
            # exact-version records use record ID descending.
            (self.artifact / 'alpha.md').write_bytes(b'# Zulu\nZulu text.\n\n# Alpha\nAlpha text.\n')
            (self.helper.code / 'notes.py').write_bytes(b'def notes():\n    return 1\n')
            self.publish(connection)
            zulu = self.confirm(connection, ref='fixture:@artifact/alpha.md#Zulu', at='2026-10-11T12:00:04Z')
            alpha_record = self.confirm(connection, ref='fixture:@artifact/alpha.md#Alpha', at='2026-10-11T12:00:03Z')
            code = self.confirm(connection, ref='fixture:@code/notes.py#notes', at='2026-10-11T12:00:05Z')
            tied = self.confirm(connection, at='2026-10-11T12:00:01Z')
            winner, loser = sorted((second, tied), key=lambda item: item['id'], reverse=True)
            before = self.state(connection)
            self.assertEqual(self.report(connection)['verifications'], [alpha_record, zulu, winner, code])
            self.assertEqual(self.report(connection, history=True)['verifications'],
                [alpha_record, zulu, winner, {**loser, 'current': False}, {**first, 'current': False}, code])
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_default_newest_exact_record_history_deterministic_and_empty_are_read_only

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_changed_missing_uningested_and_corrupt_inputs_are_never_current_and_reporting_never_writes
    def test_changed_missing_uningested_and_corrupt_inputs_are_never_current_and_reporting_never_writes(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            original = self.confirm(connection)
            stored = self.records(connection)
            self.path.write_bytes(b'# Guide\nUningested text.\n')
            before = self.state(connection)
            self.assertEqual(self.report(connection)['verifications'], [])
            self.assertFalse(self.report(connection, history=True)['verifications'][0]['current'])
            self.assertEqual(self.state(connection), before)
            self.path.unlink()
            self.assertEqual(self.report(connection)['verifications'], [])
            self.path.write_bytes(b'# Guide\nOriginal text.\n')
            connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s', (stored[0][5],))
            before = self.state(connection)
            self.assertEqual(self.report(connection)['verifications'], [])
            self.assertEqual(self.report(connection, history=True)['verifications'], [{**original, 'current': False}])
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_changed_missing_uningested_and_corrupt_inputs_are_never_current_and_reporting_never_writes

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_new_assertion_and_removed_assertion_invalidate_same_dependant_text
    def test_new_assertion_and_removed_assertion_invalidate_same_dependant_text(self):
        from mycel._derive import DeriveStore
        self.path.write_bytes(b'# Guide\nOriginal text.\n')
        (self.artifact / 'source.md').write_bytes(b'# Source\nSource text.\n')
        source = 'fixture:@artifact/source.md#Source'
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            DeriveStore(connection).apply(self.settings, self.ref, source, settings_home=self.helper.base)
            self.assertEqual(self.report(connection)['verifications'], [])
            second = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertEqual(self.report(connection)['verifications'], [second])
            DeriveStore(connection).apply(self.settings, self.ref, source, remove=True, settings_home=self.helper.base)
            self.assertEqual(self.report(connection)['verifications'], [])
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_new_assertion_and_removed_assertion_invalidate_same_dependant_text

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_withdrawn_deleted_declared_source_keeps_fault_and_history_noncurrent
    def test_withdrawn_deleted_declared_source_keeps_fault_and_history_noncurrent(self):
        self.path.write_bytes(b'# Guide\nOriginal text.\n\n<!-- sources:\nfixture:@artifact/source.md#Source\n-->\n')
        source = self.artifact / 'source.md'
        source.write_bytes(b'# Source\nSource text.\n')
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            source.unlink()
            self.publish(connection)
            final = self.confirm(connection, at='2026-10-11T12:00:01Z')
            self.assertFalse(final['current'])
            self.assertEqual(self.report(connection)['verifications'], [])
            self.assertTrue(all(not item['current'] for item in self.report(connection, history=True)['verifications']))
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_withdrawn_deleted_declared_source_keeps_fault_and_history_noncurrent

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_logical_chunk_deletion_releases_only_its_verification_and_preserves_shared_source_evidence
    def test_logical_chunk_deletion_releases_only_its_verification_and_preserves_shared_source_evidence(self):
        self.path.write_bytes(b'# Guide\nOriginal text.\n\n<!-- sources:\nfixture:@artifact/source.md#Source\n-->\n')
        source = self.artifact / 'source.md'
        source.write_bytes(b'# Source\nSource text.\n')
        with self.helper.connect() as connection:
            self.publish(connection)
            original = self.confirm(connection)
            surviving = self.confirm(connection, ref='fixture:@artifact/source.md#Source')
            history_owner = next(row[5] for row in self.records(connection) if str(row[0]) == original['id'])
            self.path.unlink()
            self.publish(connection)
            self.assertEqual(self.report(connection, history=True)['verifications'], [surviving])
            self.assertIsNone(connection.execute('SELECT id FROM public.mycel_evidence_owners WHERE id=%s', (history_owner,)).fetchone())
            self.assertIsNotNone(connection.execute('SELECT hash FROM public.mycel_snapshots WHERE hash=%s',
                                                   (surviving['textHash'],)).fetchone())
            source.unlink()
            self.publish(connection)
            self.assertEqual(self.records(connection), [])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), (0,))
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_logical_chunk_deletion_releases_only_its_verification_and_preserves_shared_source_evidence

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_late_collection_failure_rolls_back_versions_chunks_history_owners_and_evidence
    def test_late_collection_failure_rolls_back_versions_chunks_history_owners_and_evidence(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            before = self.state(connection)
            self.path.unlink()
            with self.assertRaises(RuntimeError):
                self.publish(connection, fail=True)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_late_collection_failure_rolls_back_versions_chunks_history_owners_and_evidence

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_empty_and_valid_predecessors_migrate_preserving_record_evidence_and_generation
    def test_empty_and_valid_predecessors_migrate_preserving_record_evidence_and_generation(self):
        with self.helper.connect() as connection:
            self.predecessor(connection)
            empty = store.initialize_store(connection, dimensions=1024)
            self.assertEqual((empty.before.format, empty.after.format), (1, store.STORE_FORMAT))
            self.path.write_bytes(b'# Guide\nOriginal text.\n\n<!-- sources:\nfixture:@artifact/source.md#Source\n-->\n')
            (self.artifact / 'source.md').write_bytes(b'# Source\nExact checked source.\n')
            self.publish(connection)
            original = self.confirm(connection)
            stored = self.records(connection)
            generation = store.require_store(connection).index_generation
            self.predecessor(connection)
            migrated = store.initialize_store(connection, dimensions=1024)
            self.assertEqual(migrated.after.index_generation, generation)
            self.assertEqual(self.records(connection), stored)
            self.assertEqual(self.report(connection)['verifications'], [original])
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_empty_and_valid_predecessors_migrate_preserving_record_evidence_and_generation

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_migration_refuses_unknown_incomplete_cross_repo_hash_and_public_version_without_partial_ddl
    def test_migration_refuses_unknown_incomplete_cross_repo_hash_and_public_version_without_partial_ddl(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            stored = deepcopy(self.records(connection)[0][4])
            self.predecessor(connection)
            corruptions = [{}, {**stored, 'schema': 'unknown'}, {**stored, 'version': '1'},
                           {**stored, 'textHash': '0' * 64}, {**stored, 'by': ''},
                           {**stored, 'chunkId': '00000000-0000-0000-0000-000000000000'},
                           {**stored, 'chunk': {**stored['chunk'], 'repository': 'foreign',
                                               'address': 'foreign:@artifact/guide.md#Guide'}},
                           {**stored, 'dependant': {**stored['dependant'], 'comparisonHash': '0' * 64}}]
            for record in corruptions:
                connection.execute('UPDATE public.mycel_verifications SET record=%s', (Jsonb(record),))
                with self.assertRaises(MycelError) as raised:
                    store.initialize_store(connection, dimensions=1024)
                self.assertEqual(raised.exception.code.value, 'store_format')
                self.assertEqual(connection.execute('SELECT format FROM public.mycel_store').fetchone(), (1,))
                columns = connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name='mycel_verifications'").fetchall()
                self.assertIn(('chunk_version',), columns)
                self.assertNotIn(('chunk_id',), columns)
            connection.execute('UPDATE public.mycel_verifications SET record=%s', (Jsonb(stored),))
            store.initialize_store(connection, dimensions=1024)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_migration_refuses_unknown_incomplete_cross_repo_hash_and_public_version_without_partial_ddl

# TEST-TIER-BEGIN tests/test_verification_history.py::VerificationHistoryStoreTests.test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration
    def test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration(self):
        with self.helper.connect() as connection:
            self.publish(connection)
            self.confirm(connection)
            self.predecessor(connection)
            before = self.state(connection)
            migration = store.MIGRATIONS[1]
            def failed(current):
                migration.apply(current)
                raise RuntimeError('deliberate migration validation failure')
            with patch.object(store, 'MIGRATIONS', {1: store.Migration(failed, migration.validate),
                                                    **{number: step for number, step in store.MIGRATIONS.items() if number > 1}}):
                with self.assertRaises(RuntimeError):
                    store.initialize_store(connection, dimensions=1024)
            self.assertEqual(self.state(connection), before)
            with patch('mycel._activity.record_initialization', side_effect=MycelError('internal', 'deliberate audit failure')):
                with self.assertRaises(MycelError):
                    store.initialize_store(connection, dimensions=1024, build=1,
                                           address=self.store_fixture.backend.address(self.store_fixture.database))
            self.assertEqual(self.state(connection), before)
            store.initialize_store(connection, dimensions=1024)
# TEST-TIER-END tests/test_verification_history.py::VerificationHistoryStoreTests.test_midstep_and_numbered_build_audit_failure_roll_back_the_complete_migration
