"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_derive as _support
from test_derive import (
    DeriveCliTests,
    DeriveStore,
    DeriveStoreTests,
    EvidenceStore,
    ExitStack,
    Invocation,
    Jsonb,
    LocatedCaptureStore,
    LocatedDependencyProducer,
    MutationActivity,
    MycelError,
    activity_state,
    atomic_transaction,
    capture_repository,
    checked_store,
    fixtures,
    io,
    json,
    load_settings,
    operation_guard,
    parse,
    patch,
    run,
    sha256,
    unittest,
)


class DeriveCliTests(_support.DeriveCliTests):
# TEST-TIER-BEGIN tests/test_derive.py::DeriveCliTests.test_exact_two_ref_syntax_remove_option_and_closed_failures
    def test_exact_two_ref_syntax_remove_option_and_closed_failures(self):
        dependant, source = 'fixture:@artifact/guide.md#Guide', 'fixture:@artifact/source.md#Source'
        self.assertEqual(parse(['derive', dependant, '--remove', source]),
                         Invocation('derive', arguments=('--remove', dependant, source)))
        self.assertEqual(parse(['derive', dependant, source]), Invocation('derive', arguments=(dependant, source)))
        for arguments in (['derive', '--repo', 'fixture'], ['derive', '--rem'], ['derive', '--all'],
                          ['derive', 'x', 'y', 'z'], ['derive', 'invalid', source]):
            output = io.StringIO()
            # Direct dispatch overrides only the store-bearing handler. Public
            # grammar still refuses unknown options before settings are loaded.
            if arguments[:2] in (['derive', '--repo'], ['derive', '--rem'], ['derive', '--all']):
                self.assertEqual(run(arguments, stdout=output, stderr=io.StringIO()), 1)
                self.assertEqual(json.loads(output.getvalue())['error']['code'], 'invalid_input')
            else:
                from mycel._derive import derive
                with self.assertRaises(MycelError) as error:
                    derive(Invocation('derive', arguments=tuple(arguments[1:])))
                self.assertEqual(error.exception.code, 'invalid_input')
# TEST-TIER-END tests/test_derive.py::DeriveCliTests.test_exact_two_ref_syntax_remove_option_and_closed_failures



class DeriveStoreTests(_support.DeriveStoreTests):
# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_public_assertion_exact_baseline_alias_noop_and_committed_activity
    def test_public_assertion_exact_baseline_alias_noop_and_committed_activity(self):
        with self.base.connect() as connection:
            self.publish(connection)
            before_files = self.base.state(connection)['mycel_file_versions']
            reply = self.derive(connection)
            self.assertTrue(reply['changed'])
            self.assertEqual((reply['dependant']['address'], reply['source']['address'], reply['action'], reply['members']),
                             (self.dependant, self.ref, 'assert', 1))
            baseline = EvidenceStore(connection).read_baseline('fixture', reply['baselineManifest'])
            self.assertEqual(baseline.manifest.payload['kind'], 'asserted')
            self.assertIn(self.source_bytes, [snapshot.source for snapshot in baseline.snapshots])
            self.assertEqual(self.base.state(connection)['mycel_file_versions'], before_files)
            self.assertEqual(self.role(connection), 'derived')
            entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
            recorded = activity_state(connection, entry)
            self.assertEqual((recorded['kind'], recorded['outcome'], recorded['counts']), ('derive', 'done', reply))
            self.assertEqual((recorded['files'], recorded['decisions']), ([], []))
            before = self.state(connection)
            again = self.derive(connection, 'fixture:source.md#Source')
            self.assertFalse(again['changed'])
            self.assertEqual(again['baselineManifest'], reply['baselineManifest'])
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_public_assertion_exact_baseline_alias_noop_and_committed_activity

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_identical_assertion_leaves_unrelated_unreferenced_evidence_and_activity_untouched
    def test_identical_assertion_leaves_unrelated_unreferenced_evidence_and_activity_untouched(self):
        with self.base.connect() as connection:
            self.publish(connection)
            self.derive(connection)
            raw = b'Unrelated abandoned evidence.'
            with self.guards(connection), atomic_transaction(connection):
                connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s)',
                    ('fixture', sha256(raw).hexdigest(), raw, Jsonb({})))
            before = self.state(connection)
            self.assertFalse(self.derive(connection)['changed'])
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_identical_assertion_leaves_unrelated_unreferenced_evidence_and_activity_untouched

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_removing_last_assertion_does_not_give_ambiguous_retained_declaration_authority
    def test_removing_last_assertion_does_not_give_ambiguous_retained_declaration_authority(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(guide.read_bytes().replace(b'role: authored',
            b'role: authored\nsources: ["fixture:source.md#Source"]'))
        with self.base.connect() as connection:
            self.publish(connection)
            other = 'fixture:@artifact/other.md#Other%20source'
            self.derive(connection, other)
            (self.base.code / 'source.md').write_bytes(b'# Source\nNew colliding file.\n')
            self.publish(connection)
            declared = [row for row in self.dependencies(connection) if row[2] == 'declared']
            self.assertTrue(any(row[5]['resolution']['fault'] == 'ambiguous_path' for row in declared))
            self.derive(connection, other, remove=True)
            self.assertEqual([row for row in self.dependencies(connection) if row[2] == 'declared'], declared)
            self.assertEqual(self.role(connection), 'authored')
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_removing_last_assertion_does_not_give_ambiguous_retained_declaration_authority

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_remove_preserves_declared_and_unrelated_asserted_rows_pins_faults_and_role
    def test_remove_preserves_declared_and_unrelated_asserted_rows_pins_faults_and_role(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(guide.read_bytes().replace(b'role: authored', b'role: authored\nsources: ["' + self.ref.encode() + b'"]'))
        with self.base.connect() as connection:
            self.publish(connection)
            self.derive(connection)
            self.derive(connection, 'fixture:@artifact/other.md#Other%20source')
            selected = next(row for row in self.dependencies(connection) if row[2] == 'asserted' and row[4] == self.ref)
            remaining = [row for row in self.dependencies(connection) if row[0] != selected[0]]
            snapshots = [row for row in connection.execute('SELECT repository,hash,bytes FROM public.mycel_snapshots').fetchall()]
            reply = self.derive(connection, remove=True)
            self.assertTrue(reply['changed'])
            self.assertEqual(self.dependencies(connection), remaining)
            self.assertEqual(self.role(connection), 'derived')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
                (selected[6],)).fetchone(), (0,))
            self.assertTrue(all(row in snapshots for row in connection.execute(
                'SELECT repository,hash,bytes FROM public.mycel_snapshots').fetchall()))
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_remove_preserves_declared_and_unrelated_asserted_rows_pins_faults_and_role

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_absent_unqualified_assertion_removal_is_a_guarded_quiet_noop
    def test_absent_unqualified_assertion_removal_is_a_guarded_quiet_noop(self):
        with self.base.connect() as connection:
            self.publish(connection)
            self.derive(connection)
            before = self.state(connection)
            absent = self.derive(connection, 'fixture:absent.md#Unknown', remove=True)
            self.assertEqual((absent['changed'], absent['members'], absent['source']), (False, 0, None))
            self.assertEqual(absent['sourceRef'], 'fixture:absent.md#Unknown')
            self.assertEqual(self.state(connection), before)
            absent_file = self.derive(connection, 'fixture:@artifact/absent.md', remove=True)
            self.assertFalse(absent_file['changed'])
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_absent_unqualified_assertion_removal_is_a_guarded_quiet_noop

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_file_family_and_member_selections_keep_separate_baselines_and_alias_removal
    def test_file_family_and_member_selections_keep_separate_baselines_and_alias_removal(self):
        with self.base.connect() as connection:
            self.publish(connection)
            file = self.derive(connection, 'fixture:@code/policy.py')
            family = self.derive(connection, 'fixture:@code/policy.py#Policy')
            method = self.derive(connection, 'fixture:@code/policy.py#Policy.apply')
            self.assertGreater(file['members'], 1)
            self.assertEqual(family['members'], 2)
            self.assertEqual(method['members'], 1)
            before = self.dependencies(connection)
            self.assertFalse(self.derive(connection, 'fixture:policy.py#Policy')['changed'])
            self.assertEqual(self.dependencies(connection), before)
            removed = self.derive(connection, 'fixture:policy.py#Policy', remove=True)
            self.assertTrue(removed['changed'])
            self.assertEqual({row[7] for row in self.dependencies(connection)},
                             {file['baselineManifest'], method['baselineManifest']})
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_file_family_and_member_selections_keep_separate_baselines_and_alias_removal

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_self_expanded_file_family_and_multistep_cycles_refuse_atomically
    def test_self_expanded_file_family_and_multistep_cycles_refuse_atomically(self):
        with self.base.connect() as connection:
            self.publish(connection)
            for source in (self.dependant, 'fixture:@artifact/guide.md'):
                before = self.state(connection)
                with self.assertRaises(MycelError) as error:
                    self.derive(connection, source)
                self.assertIn('dependency_cycle', error.exception.message)
                self.assertEqual(self.state(connection), before)
            with self.assertRaises(MycelError):
                DeriveStore(connection).apply(self.base.settings, 'fixture:@code/policy.py#Policy',
                    'fixture:@code/policy.py#Policy', build=0xDA, settings_home=self.base.base)
            self.assertEqual(self.state(connection), before)
            DeriveStore(connection).apply(self.base.settings, self.ref, self.dependant,
                build=0xDA, settings_home=self.base.base)
            before = self.state(connection)
            with self.assertRaises(MycelError) as error:
                self.derive(connection)
            self.assertIn('dependency_cycle', error.exception.message)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_self_expanded_file_family_and_multistep_cycles_refuse_atomically

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_retained_away_and_deleted_assertions_remove_exact_owner_without_empty_baseline
    def test_retained_away_and_deleted_assertions_remove_exact_owner_without_empty_baseline(self):
        with self.base.connect() as connection:
            self.publish(connection)
            asserted = self.derive(connection)
            baseline = EvidenceStore(connection).read_baseline('fixture', asserted['baselineManifest'])
            self.source.unlink()
            self.publish(connection)
            rows = self.dependencies(connection)
            self.assertEqual(rows[0][5]['sourceExistence'], 'away')
            self.assertEqual(EvidenceStore(connection).read_baseline('fixture', asserted['baselineManifest']).manifest,
                             baseline.manifest)
            self.base.commit()
            self.publish(connection)
            rows = self.dependencies(connection)
            self.assertEqual(rows[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(rows[0][5]['sourceAbsence']['previousFileHash'], baseline.manifest.payload['members'][0]['evidence']['fileHash'])
            removed = self.derive(connection, 'fixture:source.md#Source', remove=True)
            self.assertTrue(removed['changed'])
            self.assertEqual(self.dependencies(connection), [])
            self.assertEqual(self.role(connection), 'authored')
            self.assertFalse(self.derive(connection, 'fixture:source.md#Source', remove=True)['changed'])
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_retained_away_and_deleted_assertions_remove_exact_owner_without_empty_baseline

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_changed_dependant_source_and_unindexed_recreation_refuse_assert_and_remove
    def test_changed_dependant_source_and_unindexed_recreation_refuse_assert_and_remove(self):
        with self.base.connect() as connection:
            self.publish(connection)
            self.derive(connection)
            before = self.state(connection)
            for remove in (False, True):
                self.source.write_bytes(b'# Source\nUnindexed changed source.\n')
                with self.assertRaises(MycelError) as error:
                    self.derive(connection, remove=remove)
                self.assertIn('changed_since_ingest', error.exception.message)
                self.assertEqual(self.state(connection), before)
                self.source.write_bytes(self.source_bytes)
            guide = self.base.artifact / 'guide.md'
            original = guide.read_bytes()
            guide.write_bytes(original.replace(b'Other body.', b'Unindexed sibling edit.'))
            with self.assertRaises(MycelError) as error:
                self.derive(connection, remove=True)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            guide.write_bytes(original)
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            missing = self.state(connection)
            self.source.write_bytes(self.source_bytes)
            with self.assertRaises(MycelError) as error:
                self.derive(connection, remove=True)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), missing)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_changed_dependant_source_and_unindexed_recreation_refuse_assert_and_remove

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_ambiguous_paths_and_headings_disabled_unknown_index_and_file_dependants_refuse
    def test_ambiguous_paths_and_headings_disabled_unknown_index_and_file_dependants_refuse(self):
        (self.base.code / 'source.md').write_bytes(b'# Source\nDifferent physical file.\n')
        (self.base.artifact / 'ambiguous.md').write_bytes(b'# One\n\n## Repeat\nA.\n\n# Two\n\n## Repeat\nB.\n')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.disabled]\nenabled=false\n'
                                   + 'artifact_root=' + json.dumps(str(self.base.artifact)) + '\n')
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        with self.base.connect() as connection:
            self.publish(connection)
            before = self.state(connection)
            for source in ('fixture:source.md#Source', 'fixture:@artifact/ambiguous.md#Repeat',
                           'unknown:@artifact/source.md#Source', 'disabled:@artifact/source.md#Source',
                           'fixture:@index/summaries#Summary'):
                for remove in (False, True):
                    with self.assertRaises(MycelError):
                        self.derive(connection, source, remove=remove)
                    self.assertEqual(self.state(connection), before)
            with self.assertRaises(MycelError):
                DeriveStore(connection).apply(self.base.settings, 'fixture:@artifact/guide.md', self.ref)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_ambiguous_paths_and_headings_disabled_unknown_index_and_file_dependants_refuse

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_cross_repository_assertion_owns_exact_source_evidence_in_dependant_repository
    def test_cross_repository_assertion_owns_exact_source_evidence_in_dependant_repository(self):
        foreign = self.base.base / 'foreign'
        foreign.mkdir()
        source = foreign / 'foreign.md'
        raw = b'# Foreign\nSource in a different repository.\n'
        source.write_bytes(raw)
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.foreign]\nenabled=true\n'
                                   + 'artifact_root=' + json.dumps(str(foreign)) + '\n')
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        with self.base.connect() as connection:
            self.publish(connection)
            self.publish(connection, 'foreign')
            asserted = self.derive(connection, 'foreign:@artifact/foreign.md#Foreign')
            baseline = EvidenceStore(connection).read_baseline('fixture', asserted['baselineManifest'])
            self.assertEqual(baseline.manifest.payload['ownerRepository'], 'fixture')
            self.assertEqual(baseline.manifest.payload['source']['repository'], 'foreign')
            self.assertIn(raw, [item.source for item in baseline.snapshots])
            before = self.state(connection)
            source.write_bytes(b'# Foreign\nUnindexed foreign change.\n')
            with self.assertRaises(MycelError) as error:
                self.derive(connection, 'foreign:@artifact/foreign.md#Foreign', remove=True)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_cross_repository_assertion_owns_exact_source_evidence_in_dependant_repository

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_audit_failure_and_late_capture_change_roll_back_feature_and_activity
    def test_audit_failure_and_late_capture_change_roll_back_feature_and_activity(self):
        with self.base.connect() as connection:
            self.publish(connection)
            before = self.state(connection)
            with patch.object(MutationActivity, 'record_in_transaction', side_effect=MycelError('internal', 'Audit failed.')):
                with self.assertRaises(MycelError):
                    self.derive(connection)
            self.assertEqual(self.state(connection), before)
            record = MutationActivity.record_in_transaction
            def late_change(activity, repository, kind, result):
                record(activity, repository, kind, result)
                self.source.write_bytes(b'# Source\nChanged during audit.\n')
            with patch.object(MutationActivity, 'record_in_transaction', late_change):
                with self.assertRaises(MycelError) as error:
                    self.derive(connection)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            self.source.write_bytes(self.source_bytes)
            original_settings = self.base.config.read_text()
            def late_settings(activity, repository, kind, result):
                record(activity, repository, kind, result)
                self.base.config.write_text(original_settings.replace('enabled=true', 'enabled=false'))
            with patch.object(MutationActivity, 'record_in_transaction', late_settings):
                with self.assertRaises(MycelError) as error:
                    self.derive(connection)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            self.base.config.write_text(original_settings)
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_audit_failure_and_late_capture_change_roll_back_feature_and_activity

# TEST-TIER-BEGIN tests/test_derive.py::DeriveStoreTests.test_real_cli_dispatch_uses_current_store_and_single_reply_for_assert_remove_and_noop
    def test_real_cli_dispatch_uses_current_store_and_single_reply_for_assert_remove_and_noop(self):
        with self.base.connect() as connection:
            self.publish(connection)
        with patch('mycel._cli.load_settings', return_value=self.base.settings), \
                patch('mycel._build_identity.current_build', return_value=0xDA):
            replies = []
            for arguments in (['derive', self.dependant, self.ref],
                              ['derive', '--remove', self.dependant, self.ref],
                              ['derive', self.dependant, self.ref, '--remove']):
                output, errors = io.StringIO(), io.StringIO()
                self.assertEqual(run(arguments, stdout=output, stderr=errors), 0, errors.getvalue() + output.getvalue())
                self.assertEqual(output.getvalue().count('\n'), 1)
                replies.append(json.loads(output.getvalue()))
            self.assertEqual([(reply['action'], reply['changed']) for reply in replies],
                             [('assert', True), ('remove', True), ('remove', False)])
# TEST-TIER-END tests/test_derive.py::DeriveStoreTests.test_real_cli_dispatch_uses_current_store_and_single_reply_for_assert_remove_and_noop
