"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_disk_reconciliation as _support
from test_disk_reconciliation import (
    DiskCaptureStore,
    DiskReconciliationStoreTests,
    GitFileMove,
    Jsonb,
    MutationActivity,
    MycelError,
    Path,
    SourceResolver,
    activity_state,
    capture_repository,
    json,
    load_settings,
    os,
    patch,
    replace,
    require_check_database,
    shutil,
    subprocess,
    tempfile,
    unittest,
    uuid4,
)


class DiskReconciliationStoreTests(_support.DiskReconciliationStoreTests):
# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_effective_settings_change_before_or_after_handoff_or_reply_counts_refuses_disk_publication
    def test_effective_settings_change_before_or_after_handoff_or_reply_counts_refuses_disk_publication(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nComplete body.\n')
        original = self.config.read_text()
        captured = capture_repository(self.settings, 'fixture')
        with self.connect() as connection:
            before = self.state(connection)
            for stage in ('captured', 'handoff', 'reply_counts'):
                with self.subTest(stage=stage):
                    def change_settings():
                        self.config.write_text(original.replace('enabled=true', 'enabled=false'))

                    def handoff(conn, file):
                        change_settings()

                    def reply_counts(repository, counts):
                        change_settings()
                        return counts

                    if stage == 'captured':
                        change_settings()
                    try:
                        with MutationActivity(connection, build=1).session() as activity:
                            with self.assertRaises(MycelError) as error:
                                DiskCaptureStore(connection).apply(self.settings, captured, activity=activity,
                                    file_handoff=handoff if stage == 'handoff' else None,
                                    reply_counts=reply_counts if stage == 'reply_counts' else None)
                            self.assertEqual(error.exception.code, 'invalid_input')
                            self.assertEqual(self.state(connection), before)
                            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                            activity.finish('failed', error={'code': 'invalid_input', 'message': 'Settings changed.'})
                    finally:
                        self.config.write_text(original)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_effective_settings_change_before_or_after_handoff_or_reply_counts_refuses_disk_publication

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication
    def test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication(self):
        path = self.artifact / 'guide.md'
        original = b'# Guide\nComplete body.\n'
        path.write_bytes(original)
        captured = capture_repository(self.settings, 'fixture')
        with self.connect() as connection:
            before = self.state(connection)
            for stage in ('handoff', 'reply_counts'):
                with self.subTest(stage=stage):
                    def change_file():
                        path.write_bytes(b'# Guide\nChanged after the last guarded source observation.\n')

                    def handoff(conn, file):
                        change_file()

                    def reply_counts(repository, counts):
                        change_file()
                        return counts

                    try:
                        with MutationActivity(connection, build=1).session() as activity:
                            with self.assertRaises(MycelError) as error:
                                DiskCaptureStore(connection).apply(self.settings, captured, activity=activity,
                                    file_handoff=handoff if stage == 'handoff' else None,
                                    reply_counts=reply_counts if stage == 'reply_counts' else None)
                            self.assertEqual(error.exception.code, 'invalid_input')
                            self.assertEqual(self.state(connection), before)
                            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                            activity.finish('failed', error={'code': 'invalid_input', 'message': 'Source changed.'})
                    finally:
                        path.write_bytes(original)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_file_change_after_last_handoff_or_reply_counts_rolls_back_disk_publication

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_complete_capture_applies_one_overlap_identity_stable_primary_and_noop
    def test_complete_capture_applies_one_overlap_identity_stable_primary_and_noop(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nComplete body.\n')
        with self.connect() as connection:
            first = self.apply(connection)
            file = first.files[0]
            self.assertEqual(file.binding.primary.address, 'fixture:@artifact/guide.md')
            selected = self.disk(connection)
            by_code = self.disk(connection, 'fixture:@code/docs/guide.md#Guide')
            self.assertEqual(selected.members[0].chunk.identifier, file.chunk_versions[0][0])
            self.assertEqual(by_code.members[0].chunk.identifier, selected.members[0].chunk.identifier)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 1)
            before = self.state(connection)
            with MutationActivity(connection, build=1).session() as audit:
                same = self.apply(connection, activity=audit)
                self.assertFalse(same.changed)
                self.assertEqual(same.counts['chunks']['unchanged'], 1)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                audit.finish('done')
            self.assertEqual(self.state(connection), before)
            self.assertEqual(same.files[0].binding, file.binding)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_complete_capture_applies_one_overlap_identity_stable_primary_and_noop

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_previous_primary_remains_valid_when_fresh_discovery_would_choose_another_alias
    def test_previous_primary_remains_valid_when_fresh_discovery_would_choose_another_alias(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nStable place.\n')
        settings = self.configure(code=self.artifact, artifact=self.code)
        with self.connect() as connection:
            first_capture = capture_repository(settings, 'fixture')
            first = DiskCaptureStore(connection).apply(settings, first_capture).files[0]
            self.assertEqual(first.binding.primary.address, 'fixture:@code/guide.md')
            settings = self.configure(code=self.artifact, artifact=self.artifact)
            current_capture = capture_repository(settings, 'fixture', previous=first_capture)
            fresh_capture = capture_repository(settings, 'fixture')
            self.assertNotEqual(current_capture.disk.files[0].primary, fresh_capture.disk.files[0].primary)
            current = DiskCaptureStore(connection).apply(settings, current_capture).files[0]
            self.assertEqual(current.binding.primary.address, first.binding.primary.address)
            self.assertEqual(current.binding.identifier, first.binding.identifier)
            self.assertEqual(current.chunk_versions, first.chunk_versions)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_previous_primary_remains_valid_when_fresh_discovery_would_choose_another_alias

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_distinct_files_with_equal_bytes_paths_or_new_names_do_not_merge
    def test_distinct_files_with_equal_bytes_paths_or_new_names_do_not_merge(self):
        raw = b'# Guide\nIdentical body.\n'
        (self.code / 'guide.md').write_bytes(raw)
        (self.artifact / 'guide.md').write_bytes(raw)
        with self.connect() as connection:
            first = self.apply(connection)
            ids = {item.binding.identifier for item in first.files}
            chunks = {item.chunk_versions[0][0] for item in first.files}
            self.assertEqual(len(ids), 2)
            self.assertEqual(len(chunks), 2)
            fault = SourceResolver.from_store(connection, self.settings).resolve('fixture:guide.md#Guide')
            self.assertEqual(fault.fault, 'ambiguous_path')
            self.assertEqual(fault.candidates, ('fixture:@artifact/guide.md', 'fixture:@code/guide.md'))
            old = self.disk(connection)
            # Copy/unlink has neither the old physical identity nor checked Git
            # rename evidence. Equal complete bytes never establish a move.
            temporary = self.artifact / 'new.md'
            temporary.write_bytes(raw)
            (self.artifact / 'guide.md').unlink()
            second = self.apply(connection)
            new = self.disk(connection, 'fixture:@artifact/new.md#Guide')
            self.assertNotEqual(new.file.identifier, old.file.identifier)
            self.assertNotEqual(new.members[0].chunk.identifier, old.members[0].chunk.identifier)
            self.assertEqual(len(second.retired_locations), 1)
            self.assertEqual(SourceResolver.from_store(connection, self.settings).resolve_retained(
                'fixture:@artifact/guide.md#Guide', old.members[0].chunk.identifier).fault, 'missing_file')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_distinct_files_with_equal_bytes_paths_or_new_names_do_not_merge

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_inode_changing_atomic_save_preserves_identity_and_changes_exact_version
    def test_inode_changing_atomic_save_preserves_identity_and_changes_exact_version(self):
        path = self.artifact / 'guide.md'
        path.write_bytes(b'# Guide\nOriginal body.\n')
        with self.connect() as connection:
            first = self.apply(connection).files[0]
            inode = path.stat().st_ino
            temporary = self.artifact / 'replacement.tmp'
            temporary.write_bytes(b'# Guide\nEdited body.\n')
            temporary.replace(path)
            self.assertNotEqual(path.stat().st_ino, inode)
            with MutationActivity(connection, build=1).session() as audit:
                second = self.apply(connection, activity=audit,
                    reply_counts=lambda _, local: {**local, 'reply': 'exact'})
                audit.finish('done', counts={('fixture', 'ingest'): {**second.counts, 'reply': 'exact'}})
            changed = second.files[0]
            self.assertEqual(changed.binding.identifier, first.binding.identifier)
            self.assertEqual(changed.chunk_versions[0][0], first.chunk_versions[0][0])
            self.assertNotEqual(changed.chunk_versions[0][1], first.chunk_versions[0][1])
            self.assertEqual(changed.identity.decisions[0].reason, 'edited')
            self.assertEqual(changed.identity.decisions[0].pin_decision, 'requires_authorized_capture')
            self.assertEqual(self.disk(connection).members[0].chunk.source, b'# Guide\nEdited body.\n')
            entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
            detail = activity_state(connection, entry)
            self.assertEqual(detail['counts'], {**second.counts, 'reply': 'exact'})
            self.assertEqual([item['decision'] for item in detail['decisions']], ['edited'])
            self.assertEqual(detail['files'][0]['change'], 'changed')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_inode_changing_atomic_save_preserves_identity_and_changes_exact_version

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_physical_move_reserves_old_identity_before_a_reused_original_path
    def test_physical_move_reserves_old_identity_before_a_reused_original_path(self):
        path = self.artifact / 'guide.md'
        path.write_bytes(b'# Guide\nOriginal file.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            path.rename(self.artifact / 'moved.md')
            path.write_bytes(b'# Other\nDifferent physical file.\n')
            self.apply(connection)
            moved = self.disk(connection, 'fixture:@artifact/moved.md#Guide')
            reused = self.disk(connection, 'fixture:@artifact/guide.md#Other')
            self.assertEqual(moved.file.identifier, original.binding.identifier)
            self.assertEqual(moved.members[0].chunk.identifier, original.chunk_versions[0][0])
            self.assertNotEqual(reused.file.identifier, original.binding.identifier)
            self.assertNotEqual(reused.members[0].chunk.identifier, original.chunk_versions[0][0])
            self.assertEqual(SourceResolver.from_store(connection, self.settings).resolve_retained(
                'fixture:@artifact/guide.md#Guide', original.chunk_versions[0][0]).fault, 'missing_name')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_physical_move_reserves_old_identity_before_a_reused_original_path

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_root_retarget_creates_new_identity_and_retains_branch_binding
    def test_root_retarget_creates_new_identity_and_retains_branch_binding(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nSame body.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            branch_location = uuid4()
            connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                (branch_location, original.binding.version, 'branch', 'retained-main', Jsonb({})))
            for identifier, version in original.chunk_versions:
                connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                    (uuid4(), version, branch_location, 'branch', 'retained-main', Jsonb({})))
            other_code = self.base / 'other-code'
            other_artifact = other_code / 'docs'
            other_artifact.mkdir(parents=True)
            (other_artifact / 'guide.md').write_bytes(b'# Guide\nSame body.\n')
            settings = self.configure(code=other_code, artifact=other_artifact)
            current = self.apply(connection, settings).files[0]
            self.assertNotEqual(current.binding.identifier, original.binding.identifier)
            self.assertNotEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertEqual(self.disk(connection, settings=settings).file.identifier, current.binding.identifier)
            retained = SourceResolver.from_store(connection, settings, kind='branch', location='retained-main')
            self.assertEqual(retained.resolve('fixture:@artifact/guide.md#Guide').selection.file.identifier,
                             original.binding.identifier)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 2)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_root_retarget_creates_new_identity_and_retains_branch_binding

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_branch_only_chunk_is_removed_from_disk_once_and_partial_old_binding_is_preserved
    def test_branch_only_chunk_is_removed_from_disk_once_and_partial_old_binding_is_preserved(self):
        path = self.artifact / 'guide.md'
        path.write_bytes(b'# Guide\nDisk body.\n# Away\nRetained branch body.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            branch = self.retain_branch(connection, original, metadata={'root': 'artifact', 'custom': 'kept'})
            path.write_bytes(b'# Guide\nDisk body.\n')
            second = self.apply(connection)
            self.assertEqual(second.counts['chunks']['removed'], 1)
            metadata = connection.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s', (branch,)).fetchone()[0]
            self.assertEqual(metadata['root'], 'artifact')
            self.assertEqual(metadata['path'], 'guide.md')
            self.assertEqual(metadata['custom'], 'kept')
            self.assertIn({'root': 'code', 'path': 'docs/guide.md'}, metadata['aliases'])
            before = self.state(connection)
            with MutationActivity(connection, build=1).session() as audit:
                third = self.apply(connection, activity=audit)
                self.assertFalse(third.changed)
                self.assertEqual(third.counts['chunks']['removed'], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                audit.finish('done')
            self.assertEqual(self.state(connection), before)
            retained = SourceResolver.from_store(connection, self.settings, kind='branch', location='retained-main')
            self.assertEqual(retained.resolve('fixture:@artifact/guide.md#Away').selection.members[0].chunk.identifier,
                             original.chunk_versions[1][0])
            # A physical move also freezes each missing inherited field, so a
            # branch with only a supplied root never follows disk's new path.
            path.rename(self.artifact / 'new.md')
            self.apply(connection)
            retained = SourceResolver.from_store(connection, self.settings, kind='branch', location='retained-main')
            self.assertIsNotNone(retained.resolve('fixture:@artifact/guide.md#Guide').selection)
            self.assertEqual(retained.resolve('fixture:@artifact/new.md').fault, 'missing_file')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_branch_only_chunk_is_removed_from_disk_once_and_partial_old_binding_is_preserved

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_reconfigured_root_reaches_same_physical_file_and_updates_primary_without_reidentifying
    def test_reconfigured_root_reaches_same_physical_file_and_updates_primary_without_reidentifying(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nSame file.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            settings = self.configure(code=self.code, artifact=self.code)
            current = self.apply(connection, settings).files[0]
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions, original.chunk_versions)
            self.assertEqual(current.binding.primary.address, 'fixture:@artifact/docs/guide.md')
            followed = SourceResolver.from_store(connection, settings).resolve_retained(
                'fixture:@artifact/guide.md#Guide', original.chunk_versions[0][0])
            self.assertEqual(followed.selection.place.address, 'fixture:@artifact/docs/guide.md#Guide')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_reconfigured_root_reaches_same_physical_file_and_updates_primary_without_reidentifying

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_transaction_handoff_and_activity_failure_leave_complete_file_unchanged
    def test_transaction_handoff_and_activity_failure_leave_complete_file_unchanged(self):
        path = self.artifact / 'guide.md'
        path.write_bytes(b'# Guide\nBefore.\n')
        with self.connect() as connection:
            self.apply(connection)
            before = self.state(connection)
            path.write_bytes(b'# Renamed\nBefore.\n')
            def fail(conn, file):
                self.assertIs(conn, connection)
                self.assertEqual(file.identity.decisions[0].reason, 'renamed')
                self.assertEqual(file.identity.decisions[0].pin_decision, 'inherit_existing')
                located = conn.execute('SELECT v.source_bytes FROM public.mycel_chunk_versions v '
                    'JOIN public.mycel_locations l ON l.chunk_version=v.id WHERE l.file_location=%s',
                    (file.binding.location,)).fetchone()[0]
                self.assertEqual(bytes(located), b'# Renamed\nBefore.\n')
                raise RuntimeError('handoff failed')
            with MutationActivity(connection, build=1).session() as audit:
                with self.assertRaises(RuntimeError):
                    self.apply(connection, file_handoff=fail, activity=audit)
                self.assertEqual(self.state(connection), before)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                with patch.object(audit, '_details', side_effect=RuntimeError('audit failed')):
                    with self.assertRaises(RuntimeError):
                        self.apply(connection, activity=audit)
                self.assertEqual(self.state(connection), before)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                changed = self.apply(connection, activity=audit)
                self.assertEqual(changed.files[0].identity.decisions[0].pin_decision, 'inherit_existing')
                audit.finish('done')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_transaction_handoff_and_activity_failure_leave_complete_file_unchanged

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_retirement_refuses_incomplete_changed_or_unconfirmed_empty_capture
    def test_retirement_refuses_incomplete_changed_or_unconfirmed_empty_capture(self):
        path = self.artifact / 'guide.md'
        path.write_bytes(b'# Guide\nBefore.\n')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            before = self.state(connection)
            manifest = capture_repository(self.settings, 'fixture')
            forged_file = replace(manifest.disk.files[0], parsed=replace(manifest.disk.files[0].parsed, chunks=()))
            forged_disk = replace(manifest.disk, files=(forged_file,))
            forged = replace(manifest, locations=(forged_disk, *manifest.locations[1:]))
            self.assertEqual(forged.manifest_hash, manifest.manifest_hash)
            with self.assertRaises(MycelError):
                DiskCaptureStore(connection).apply(self.settings, forged)
            with self.assertRaises(MycelError):
                DiskCaptureStore(connection).apply(self.settings, replace(manifest, complete=False))
            path.write_bytes(b'# Guide\nChanged after capture.\n')
            with self.assertRaises(MycelError):
                DiskCaptureStore(connection).apply(self.settings, manifest)
            self.assertEqual(self.state(connection), before)
            path.unlink()
            with self.assertRaises(MycelError) as error:
                self.apply(connection)
            self.assertEqual(error.exception.code.value, 'refused')
            self.assertEqual(self.state(connection), before)
            retired = self.apply(connection, confirm_empty=True)
            self.assertEqual(retired.retired_locations, (original.binding.location,))
            self.assertEqual(retired.counts['chunks']['removed'], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_file_locations WHERE kind='disk'").fetchone()[0], 0)
            self.assertEqual(SourceResolver.from_store(connection, self.settings).resolve('fixture:@artifact/guide.md').fault,
                             'missing_file')
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_retirement_refuses_incomplete_changed_or_unconfirmed_empty_capture

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_checked_git_rename_preserves_identity_across_physical_replacement_and_retained_refs
    def test_checked_git_rename_preserves_identity_across_physical_replacement_and_retained_refs(self):
        path = self.artifact / 'guide.md'
        raw = b'# Guide\nComplete committed source.\n'
        path.write_bytes(raw)
        self.git('init', '--initial-branch=fixture-main')
        self.git('config', 'diff.renames', 'false')
        self.git('add', '--', 'docs/guide.md')
        self.git('commit', '--message', 'Before')
        before_commit = self.git('rev-parse', 'HEAD')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            inode = path.stat().st_ino
            destination = self.artifact / 'moved.md'
            shutil.copyfile(path, destination)
            path.unlink()
            self.assertNotEqual(inode, destination.stat().st_ino)
            self.git('add', '--all')
            self.git('commit', '--message', 'Recognized rename')
            after_commit = self.git('rev-parse', 'HEAD')
            from mycel._capture import FileAlias
            move = GitFileMove(original.binding.identifier, original.binding.version,
                before_commit, after_commit, FileAlias('artifact', 'guide.md'), FileAlias('artifact', 'moved.md'))
            current = self.apply(connection, recognized_moves=(move,)).files[0]
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions, original.chunk_versions)
            self.assertEqual(current.binding.version, original.binding.version)
            self.assertEqual(current.binding.location, original.binding.location)
            followed = SourceResolver.from_store(connection, self.settings).resolve_retained(
                'fixture:@artifact/guide.md#Guide', original.chunk_versions[0][0])
            self.assertEqual(followed.selection.place.address, 'fixture:@artifact/moved.md#Guide')
            metadata = connection.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s',
                (current.binding.location,)).fetchone()[0]
            self.assertEqual(metadata['moveEvidence'][0]['beforeCommit'], before_commit)
            self.assertEqual(metadata['moveEvidence'][0]['afterCommit'], after_commit)
            branch = SourceResolver.from_store(connection, self.settings, kind='branch', location='nonexistent')
            self.assertEqual(branch.resolve('fixture:@artifact/guide.md').fault, 'missing_file')
            # Reusing the old name makes it ordinary resolution, even though
            # the retained moved identity still carries immutable move evidence.
            path.write_bytes(b'# Other\nA distinct file.\n')
            self.apply(connection)
            reused = SourceResolver.from_store(connection, self.settings).resolve_retained(
                'fixture:@artifact/guide.md#Guide', original.chunk_versions[0][0])
            self.assertEqual(reused.fault, 'missing_name')
            self.assertIsNone(reused.selection)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_checked_git_rename_preserves_identity_across_physical_replacement_and_retained_refs

# TEST-TIER-BEGIN tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_stale_or_unrecognized_git_move_rolls_back_and_code_name_rename_has_exact_version
    def test_stale_or_unrecognized_git_move_rolls_back_and_code_name_rename_has_exact_version(self):
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nBody.\n')
        path = self.code / 'worker.py'
        path.write_bytes(b'def work():\n    return 1\n')
        with self.connect() as connection:
            first = self.apply(connection)
            old = self.disk(connection, 'fixture:@code/worker.py#work')
            path.write_bytes(b'def renew():\n    return 1\n')
            current = self.apply(connection)
            new = self.disk(connection, 'fixture:@code/worker.py#renew')
            self.assertEqual(old.members[0].chunk.identifier, new.members[0].chunk.identifier)
            self.assertNotEqual(old.members[0].chunk.version, new.members[0].chunk.version)
            decision = next(item.identity.decisions[0] for item in current.files if item.binding.primary.path == 'worker.py')
            self.assertEqual((decision.reason, decision.pin_decision, decision.reuse_vectors),
                             ('renamed', 'inherit_existing', False))
            before = self.state(connection)
            from mycel._capture import FileAlias
            guide = next(item for item in first.files if item.binding.primary.path == 'guide.md')
            move = GitFileMove(guide.binding.identifier, str(uuid4()), '0' * 40, '1' * 40,
                FileAlias('artifact', 'guide.md'), FileAlias('artifact', 'guide.md'))
            with self.assertRaises(MycelError):
                self.apply(connection, recognized_moves=(move,))
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_disk_reconciliation.py::DiskReconciliationStoreTests.test_stale_or_unrecognized_git_move_rolls_back_and_code_name_rename_has_exact_version
