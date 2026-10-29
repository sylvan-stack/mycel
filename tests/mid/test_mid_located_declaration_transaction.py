"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_located_declaration_transaction as _support
from test_located_declaration_transaction import (MycelError)


class LocatedDeclarationTransactionStoreTests(_support.LocatedDeclarationTransactionStoreTests):


# TEST-TIER-BEGIN tests/test_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_git_ref_change_after_last_pin_refuses_complete_publication
    def test_git_ref_change_after_last_pin_refuses_complete_publication(self):
        self.prepare()
        with self.fixture.connect() as connection:
            before = self.fixture.state(connection)
            def change():
                self.fixture.git('branch', 'added-during-publication')
            with self.assertRaises(MycelError) as error:
                self.publish(connection,
                    batch_handoff=lambda conn, result: self.producer(conn, result, after=change))
            self.assertEqual(error.exception.code.value, 'invalid_input')
            self.assertEqual(self.fixture.state(connection), before)
# TEST-TIER-END tests/test_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_git_ref_change_after_last_pin_refuses_complete_publication

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_settings_change_after_capture_refuses_publication_without_dependency_handoff
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Settings change after capture refuses publication without dependency handoff.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_settings_change_after_capture_refuses_publication_without_dependency_handoff(self):
#         self.fixture.initialize()
#         captured = capture_repository(self.fixture.settings, 'fixture')
#         self.fixture.config.write_text(self.fixture.config.read_text().replace('enabled=true', 'enabled=false'))
#         with self.fixture.connect() as connection:
#             before = self.fixture.state(connection)
#             with self.guards(connection):
#                 with self.assertRaises(MycelError) as error:
#                     LocatedCaptureStore(connection).apply(self.fixture.settings, captured)
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(self.fixture.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_settings_change_after_last_handoff_or_reply_counts_rolls_back_complete_publication
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Settings change after last handoff or reply counts rolls back complete publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_settings_change_after_last_handoff_or_reply_counts_rolls_back_complete_publication(self):
#         self.prepare()
#         original = self.fixture.config.read_text()
#         with self.fixture.connect() as connection:
#             before = self.fixture.state(connection)
#             for stage in ('handoff', 'reply_counts'):
#                 with self.subTest(stage=stage):
#                     def change_settings():
#                         self.fixture.config.write_text(original.replace('enabled=true', 'enabled=false'))
#
#                     def handoff(conn, result):
#                         self.producer(conn, result)
#                         if stage == 'handoff':
#                             change_settings()
#
#                     def reply_counts(repository, counts):
#                         change_settings()
#                         return counts
#
#                     try:
#                         with MutationActivity(connection, build=1).session() as activity:
#                             with self.assertRaises(MycelError) as error:
#                                 self.publish(connection, batch_handoff=handoff, activity=activity,
#                                     reply_counts=reply_counts if stage == 'reply_counts' else None)
#                             self.assertEqual(error.exception.code, 'invalid_input')
#                             self.assertEqual(self.fixture.state(connection), before)
#                             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
#                             activity.finish('failed', error={'code': 'invalid_input', 'message': 'Settings changed.'})
#                     finally:
#                         self.fixture.config.write_text(original)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_complete_capture_declarations_edges_pins_and_activity_commit_together
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Complete capture declarations edges pins and activity commit together.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_capture_declarations_edges_pins_and_activity_commit_together(self):
#         self.prepare()
#         with self.fixture.connect() as connection, self.fixture.connect() as reader:
#             def handoff(conn, result):
#                 self.producer(conn, result)
#                 self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 0)
#                 self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0], 0)
#                 self.assertEqual(len(self.rows(conn)), 2)
#             with MutationActivity(connection, build=1).session() as activity:
#                 result = self.publish(connection, batch_handoff=handoff, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): result.counts})
#             self.assertEqual(len(self.rows(reader)), 2)
#             self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 2)
#             self.assertEqual(reader.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 1)
#             entry = reader.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
#             self.assertEqual(activity_state(reader, entry)['counts'], result.counts)
#             self.assertEqual(result.counts['pinsCaptured'], 2)
#             manifests = [EvidenceStore(connection).read_baseline('fixture', row[3]).manifest.payload
#                          for row in self.rows(connection)]
#             self.assertEqual({item['location']['kind'] for item in manifests}, {'disk', 'branch'})
#             self.assertEqual(len({item['dependantVersion'] for item in manifests}), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_frontmatter_locations_sharing_exact_version_keep_different_source_pins
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Frontmatter locations sharing exact version keep different source pins.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_frontmatter_locations_sharing_exact_version_keep_different_source_pins(self):
#         self.prepare()
#         path = self.fixture.artifact / 'guide.md'
#         path.write_bytes(path.read_bytes().replace(b'#Source', b'#Other'))
#         with self.fixture.connect() as connection:
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             rows = self.rows(connection)
#             self.assertEqual(len(rows), 2)
#             self.assertEqual(len({row[1] for row in rows}), 1)
#             manifests = [EvidenceStore(connection).read_baseline('fixture', row[3]).manifest.payload for row in rows]
#             self.assertEqual({item['source']['name'] for item in manifests}, {'Source', 'Other'})
#             self.assertEqual(len({row[2] for row in rows}), 2)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_evidence_and_audit_failures_roll_back_the_complete_prospective_publication
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Evidence and audit failures roll back the complete prospective publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_evidence_and_audit_failures_roll_back_the_complete_prospective_publication(self):
#         self.prepare()
#         with self.fixture.connect() as connection:
#             before = self.fixture.state(connection)
#             def fail():
#                 raise RuntimeError('fixture producer failed after pinning')
#             with self.assertRaises(RuntimeError):
#                 self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result, after=fail))
#             self.assertEqual(self.fixture.state(connection), before)
#             with MutationActivity(connection, build=1).session() as activity:
#                 with patch.object(activity, '_details', side_effect=RuntimeError('fixture audit failed')):
#                     with self.assertRaises(RuntimeError):
#                         self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result), activity=activity)
#                 self.assertEqual(self.fixture.state(connection), before)
#                 activity.finish('failed', error={'code': 'internal', 'message': 'fixture failure'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_changed_real_disk_source_before_pin_refuses_and_rolls_back_all_rows
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Changed real disk source before pin refuses and rolls back all rows.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_real_disk_source_before_pin_refuses_and_rolls_back_all_rows(self):
#         self.prepare()
#         with self.fixture.connect() as connection:
#             before = self.fixture.state(connection)
#             def change():
#                 (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nChanged after capture.\n')
#             with self.assertRaises(EvidenceError) as error:
#                 self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result, before_pin=change))
#             self.assertEqual(error.exception.status, 'changed_since_ingest')
#             self.assertEqual(self.fixture.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_source_change_after_last_pin_refuses_complete_publication_and_activity
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Source change after last pin refuses complete publication and activity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_change_after_last_pin_refuses_complete_publication_and_activity(self):
#         self.prepare()
#         with self.fixture.connect() as connection:
#             before = self.fixture.state(connection)
#             def change():
#                 (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nChanged after all pins.\n')
#             with MutationActivity(connection, build=1).session() as activity:
#                 with self.assertRaises(MycelError) as error:
#                     self.publish(connection, activity=activity,
#                         batch_handoff=lambda conn, result: self.producer(conn, result, after=change))
#                 self.assertEqual(error.exception.code.value, 'invalid_input')
#                 self.assertEqual(self.fixture.state(connection), before)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
#                 activity.finish('failed', error={'code': 'internal', 'message': 'fixture changed capture'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_source_only_change_keeps_baseline_and_unchanged_capture_can_retry_refs
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Source only change keeps baseline and unchanged capture can retry refs.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_only_change_keeps_baseline_and_unchanged_capture_can_retry_refs(self):
#         self.prepare()
#         with self.fixture.connect() as connection:
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             original = self.rows(connection)
#             (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nNew source text.\n# Other\nOther body.\n')
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             self.assertEqual(self.rows(connection), original)
#             with self.guards(connection), atomic_transaction(connection):
#                 repeated = DeclaredRefStore(connection).recheck_in_transaction(self.fixture.settings, repository='fixture')
#                 self.assertEqual((repeated.checked, repeated.changed), (2, 0))
#             self.assertFalse(self.publish(connection).changed)
#             self.assertEqual(self.rows(connection), original)
#             self.assertTrue(all(item.baseline_status == 'retained' for item in repeated.refs))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_unresolved_and_malformed_refs_remain_visible_and_initial_resolution_retries
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unresolved and malformed refs remain visible and initial resolution retries.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unresolved_and_malformed_refs_remain_visible_and_initial_resolution_retries(self):
#         self.prepare()
#         (self.fixture.artifact / 'waiting.md').write_bytes(b'---\nsources: ["fixture:@artifact/later.md#Later", "bad"]\n---\n# Waiting\nBody.\n')
#         with self.fixture.connect() as connection:
#             initial = self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             self.assertEqual(initial.counts['refFaults'], 2)
#             faults = DeclaredRefStore(connection).list(repository='fixture', faults_only=True)
#             self.assertEqual({item.fault for item in faults}, {'missing_file', 'not_a_ref'})
#             missing = next(item for item in faults if item.fault == 'missing_file')
#             original = self.rows(connection)
#             (self.fixture.artifact / 'later.md').write_bytes(b'# Later\nNow present.\n')
#             applied = self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             self.assertEqual(applied.counts['pinsCaptured'], 1)
#             self.assertEqual(applied.counts['refFaults'], 1)
#             current = self.rows(connection)
#             self.assertTrue(set(original).issubset(current))
#             self.assertIn(missing.identifier, {str(row[0]) for row in current})
#             self.assertEqual(DeclaredRefStore(connection).list(repository='fixture', faults_only=True)[0].declaration, 'bad')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_pinned_alias_or_version_replacement_refuses_without_identity_policy
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Pinned alias or version replacement refuses without identity policy.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_pinned_alias_or_version_replacement_refuses_without_identity_policy(self):
#         self.prepare()
#         with self.fixture.connect() as connection:
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             before = self.fixture.state(connection)
#             path = self.fixture.artifact / 'guide.md'
#             original = path.read_bytes()
#             for changed in (original.replace(b'Plain body.', b'Substantive edit.'),
#                             original.replace(b'fixture:@artifact/source.md', b'fixture:source.md')):
#                 path.write_bytes(changed)
#                 with self.assertRaises(MycelError) as error:
#                     self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#                 self.assertEqual(error.exception.code.value, 'refused')
#                 self.assertEqual(self.fixture.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_frontmatter_line_shift_refreshes_ref_occurrence_without_changing_pins
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Frontmatter line shift refreshes ref occurrence without changing pins.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_frontmatter_line_shift_refreshes_ref_occurrence_without_changing_pins(self):
#         self.prepare()
#         path = self.fixture.artifact / 'guide.md'
#         original = b'---\nrole: authored\n---\n# Guide\n<!-- sources:\nfixture:@artifact/source.md#Source\n-->\nPlain body.\n'
#         path.write_bytes(original)
#         self.fixture.commit()
#         with self.fixture.connect() as connection:
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             rows = self.rows(connection)
#             refs = DeclaredRefStore(connection).list(repository='fixture')
#             before = {ref.identifier: ref.line for ref in refs}
#             path.write_bytes(original.replace(b'role: authored\n', b'role: authored\nignored: value\n'))
#             self.publish(connection, batch_handoff=lambda conn, result: self.producer(conn, result))
#             self.assertEqual(self.rows(connection), rows)
#             shifted = DeclaredRefStore(connection).list(repository='fixture')
#             locations = connection.execute('SELECT id,kind FROM public.mycel_file_locations').fetchall()
#             kinds = {str(identifier): kind for identifier, kind in locations}
#             for ref in shifted:
#                 self.assertEqual(ref.line, before[ref.identifier] + (1 if kinds[ref.location] == 'disk' else 0))
#                 self.assertEqual(ref.baseline_status, 'retained')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_located_declaration_transaction.py::LocatedDeclarationTransactionStoreTests.test_idle_unguarded_foreign_and_expired_transaction_adapters_refuse_before_writes
# Reason: Narrower case removed from this family after retaining test_git_ref_change_after_last_pin_refuses_complete_publication. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Idle unguarded foreign and expired transaction adapters refuse before writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_located_declaration_transaction.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_idle_unguarded_foreign_and_expired_transaction_adapters_refuse_before_writes(self):
#         self.prepare()
#         with self.fixture.connect() as connection, self.fixture.connect() as foreign:
#             result = self.publish(connection)
#             located = result.files[0]
#             file = SourceResolver.from_store(connection, self.fixture.settings).resolve(
#                 'fixture:@artifact/guide.md').selection.file
#             declarations = read_document_declarations(split_markdown(file.source), file=file.primary.address)
#             operations = (lambda: SourceResolver.from_transaction(connection, self.fixture.settings),
#                 lambda: DeclaredRefStore(connection).retain_in_transaction(self.fixture.settings, located.binding.location, declarations),
#                 lambda: DeclaredRefStore(connection).recheck_in_transaction(self.fixture.settings, repository='fixture'))
#             before = self.fixture.state(connection)
#             for operation in operations:
#                 with self.assertRaises(MycelError):
#                     operation()
#                 with atomic_transaction(connection), self.assertRaises(MycelError):
#                     operation()
#             with self.guards(connection), atomic_transaction(foreign), self.assertRaises(MycelError):
#                 SourceResolver.from_transaction(foreign, self.fixture.settings)
#             with self.assertRaises(RuntimeError), self.guards(connection), atomic_transaction(connection):
#                 refs = DeclaredRefStore(connection)
#                 refs.retain_in_transaction(self.fixture.settings, located.binding.location, declarations)
#                 ref = refs.recheck_in_transaction(self.fixture.settings, repository='fixture').refs[0]
#                 expected = self.input(connection, located, ref)
#                 with checked_transaction_input_guard(connection, expected,
#                         lambda: self.input(connection, located, ref, fresh=True)) as token:
#                     pass
#                 with self.assertRaises(EvidenceError):
#                     EvidenceStore(connection).pin_in_transaction(token, dependency_id=ref.identifier, kind='declared',
#                         declaration=ref.declaration, captured_at='2026-10-09T09:30:00Z', authorization='initial_resolution')
#                 raise RuntimeError('fixture rolls back retained refs after expired token refusal')
#             self.assertEqual(self.fixture.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
