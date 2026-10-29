"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_replacement as _support
from test_replacement import (Fixture ,Path ,tempfile)


class ReplacementTests(_support.ReplacementTests):


# TEST-TIER-BEGIN tests/test_replacement.py::ReplacementTests.test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog
    def test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory).resolve()); fixture.compile()
            for step in fixture.plan['steps']:
                if not step['required']: continue
                fixture.observe(step['id'], 'completed', fixture.action(step['id']))
            report = fixture.validate()
            self.assertTrue(report['complete']); self.assertFalse(report['partial'])
            self.assertFalse(fixture.old.exists()); self.assertFalse(fixture.link.is_symlink())
            self.assertEqual(fixture.corpus.read_bytes(), b'Keep exact source evidence.\n')
            self.assertEqual(fixture.unrelated.read_bytes(), b'Keep unrelated bytes.\n')
            self.assertEqual(fixture.shell.read_text(), 'export KEEP=one\n# retained tail\n')
            self.assertEqual(report['commandAvailability'], 'mycel2_verified')
            self.assertFalse(report['ownerReplacementPerformedByValidator']); self.assertEqual(report['databaseConnections'], 0)
# TEST-TIER-END tests/test_replacement.py::ReplacementTests.test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_plan_is_read_only_exactly_inventoried_restrictive_and_contains_no_state_import
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Plan is read only exactly inventoried restrictive and contains no state import.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_plan_is_read_only_exactly_inventoried_restrictive_and_contains_no_state_import(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); before = {p: p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()}
#             result = replacement_plan(fixture.inventory_path, now=AT); plan = result['plan']
#             self.assertEqual([x['path'] for x in plan['files']], [str(fixture.old), str(fixture.link)])
#             self.assertEqual(len(plan['aliases']), 1)
#             self.assertEqual(plan['aliases'][0]['names'], ['mycel', 'better-grep'])
#             self.assertEqual(plan['version1StateToCopy'], [])
#             self.assertFalse(plan['executionAuthorized']); self.assertFalse(plan['shellFilesEdited'])
#             self.assertIn('DROP TABLE "legacy"."kn_nodes" RESTRICT;', plan['operatorSql'])
#             self.assertNotIn('kn_unrelated', plan['operatorSql']); self.assertNotIn('CASCADE', plan['operatorSql'])
#             self.assertIn('ACCESS EXCLUSIVE MODE NOWAIT', plan['operatorSql'])
#             self.assertIn('END;\n$mycel_replacement$;', plan['operatorSql'])
#             self.assertTrue(all(x['status'] == 'pending' for x in result['report']['steps']))
#             self.assertEqual(before, {p: p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_patterns_aliases_database_drop_unqualified_names_and_unknown_authority_are_refused
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Patterns aliases database drop unqualified names and unknown authority are refused.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_patterns_aliases_database_drop_unqualified_names_and_unknown_authority_are_refused(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); original = deepcopy(fixture.inventory)
#             changes = [lambda v: v['files'][0].update(path=str(fixture.old.parent / '*')),
#                 lambda v: v['files'][0].update(path=str(fixture.old.parent) + '/../old/mycel'),
#                 lambda v: v.update(newDatabase=v['oldDatabase']['identity']),
#                 lambda v: v['tables'][0].update(name='kn_*'),
#                 lambda v: v['tables'][0].update(schema=''),
#                 lambda v: v['tables'][0].update(cascade=True),
#                 lambda v: v['files'][0].update(owned=True)]
#             for change in changes:
#                 with self.subTest(change=changes.index(change)):
#                     fixture.inventory = deepcopy(original); change(fixture.inventory); fixture.save()
#                     with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#             fixture.inventory = deepcopy(original); fixture.inventory['files'][0]['path'] = str(fixture.old.parent)
#             fixture.inventory['files'][0].update(kind='directory', sha256=None, ownership=None)
#             fixture.inventory['previousCommand'] = str(fixture.link)
#             fixture.save(); plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertTrue(plan['blocked']); self.assertIsNone(plan['operatorSql'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_uncertain_and_corpus_ownership_is_preserved_and_changed_or_stale_evidence_refuses
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Uncertain and corpus ownership is preserved and changed or stale evidence refuses.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_uncertain_and_corpus_ownership_is_preserved_and_changed_or_stale_evidence_refuses(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); fixture.inventory['files'][0]['ownership'] = None
#             fixture.save(); plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertTrue(plan['blocked']); self.assertNotIn(str(fixture.old), [x['path'] for x in plan['files']])
#             fixture.inventory['files'][0].update(role='uncertain', uncertainty='Fixture ownership remains unresolved.')
#             fixture.save(); plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertIn('Fixture ownership remains unresolved.', [x['reason'] for x in plan['blocked']])
#             fixture.inventory['files'][0].update(role='source_corpus', uncertainty=None); fixture.save()
#             plan = replacement_plan(fixture.inventory_path, now=AT)['plan']; self.assertNotIn(str(fixture.old), [x['path'] for x in plan['files']])
#             fixture.old.write_bytes(b'changed')
#             with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); Path(fixture.basis['path']).write_text('changed independent evidence')
#             with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT + timedelta(days=2))
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             evidence = json.loads(Path(fixture.inventory['files'][0]['ownership']['path']).read_text())
#             evidence['observedAt'] = (AT - timedelta(days=2)).isoformat()
#             fixture.inventory['files'][0]['ownership'] = write(Path(fixture.inventory['files'][0]['ownership']['path']), evidence)
#             fixture.save()
#             with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             fixture.inventory['files'].append({'id': 'protected-root', 'path': str(fixture.old.parent),
#                 'role': 'source_corpus', 'kind': 'directory', 'sha256': None, 'ownership': None, 'uncertainty': None})
#             fixture.save(); plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertEqual(plan['files'], [])
#             self.assertIn(str(fixture.old.parent), plan['preservedTrees'])
#             self.assertTrue(any('corpora' in row['reason'] for row in plan['blocked']))
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             ownership_path = Path(fixture.inventory['files'][0]['ownership']['path'])
#             evidence = json.loads(ownership_path.read_text())
#             evidence['basis'][0]['artifact'] = binding(fixture.shell)
#             fixture.inventory['files'][0]['ownership'] = write(ownership_path, evidence)
#             fixture.save()
#             before = {p: p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()}
#             with self.assertRaisesRegex(BuildError, 'Ownership evidence must survive cleanup'):
#                 replacement_plan(fixture.inventory_path, now=AT)
#             self.assertEqual(before, {p: p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_uninventoried_dependents_block_without_cascade_and_changed_catalog_identity_refuses
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Uninventoried dependents block without cascade and changed catalog identity refuses.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_uninventoried_dependents_block_without_cascade_and_changed_catalog_identity_refuses(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             view = {'schema': 'outside', 'name': 'keep_view', 'kind': 'view', 'oid': 103, 'definitionSha256': sha(b'view')}
#             fixture.catalog['objects'].append(view); fixture.catalog['dependencies'].append({
#                 'owner': {'schema': 'legacy', 'name': 'kn_nodes'}, 'dependent': {'schema': 'outside', 'name': 'keep_view'}, 'automatic': False})
#             fixture.inventory['oldDatabase']['catalog'] = write(Path(fixture.catalog_binding['path']), fixture.catalog)
#             fixture.save(); plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertTrue(plan['blocked']); self.assertIsNone(plan['operatorSql'])
#             fixture.catalog['objects'][0]['oid'] = 999
#             fixture.inventory['oldDatabase']['catalog'] = write(Path(fixture.catalog_binding['path']), fixture.catalog); fixture.save()
#             with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_each_failure_or_interruption_keeps_actual_prefix_and_late_effects_without_old_store_fallback
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Each failure or interruption keeps actual prefix and late effects without old store fallback.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_each_failure_or_interruption_keeps_actual_prefix_and_late_effects_without_old_store_fallback(self):
#         for late in (False, True):
#             with tempfile.TemporaryDirectory() as directory:
#                 fixture = Fixture(Path(directory).resolve()); fixture.compile()
#                 ids = [x['id'] for x in fixture.plan['steps'] if x['required']]
#             for position in range(len(ids)):
#                 with self.subTest(position=position, late=late), tempfile.TemporaryDirectory() as directory:
#                     fixture = Fixture(Path(directory).resolve()); fixture.compile(); actual = []
#                     stop = [x['id'] for x in fixture.plan['steps'] if x['required']][position]
#                     for step in fixture.plan['steps']:
#                         if not step['required']: continue
#                         if step['id'] == stop:
#                             facts = fixture.action(stop) if late else {'interrupted': True, 'observedBeforeMutation': True}
#                             if not late and stop.startswith('remove_file:'):
#                                 target = next(x for x in fixture.plan['files'] if stop == 'remove_file:' + x['id'])
#                                 facts.update(path=target['path'], beforeSha256=target['sha256'], after='present')
#                             fixture.observe(stop, 'failed', facts); break
#                         fixture.observe(step['id'], 'completed', fixture.action(step['id'])); actual.append(step['id'])
#                     report = fixture.validate()
#                     self.assertFalse(report['complete']); self.assertEqual(report['completedPrefix'], actual)
#                     cutover = 'command_cutover' in actual or (late and stop == 'command_cutover')
#                     self.assertEqual(report['commandAvailability'], 'mycel2_verified' if cutover else 'previous_command_present')
#                     if late and stop.startswith('remove_file:'):
#                         self.assertTrue(any('removedFile' in x for x in report['observedEffects']))
#                     self.assertTrue(fixture.corpus.exists()); self.assertTrue(fixture.unrelated.exists())
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); fixture.compile()
#             fixture.action('qualification_and_launcher')
#             fixture.observe('command_cutover', 'failed', fixture.action('command_cutover'))
#             report = fixture.validate()
#             self.assertEqual(report['completedPrefix'], [])
#             self.assertTrue(all(row['status'] != 'completed' for row in report['steps']))
#             self.assertEqual(report['steps'][0]['status'], 'pending')
#             self.assertFalse(report['complete']); self.assertTrue(report['partial'])
#             self.assertEqual(report['observedEffects'], [{'commandCutoverObserved': str(fixture.new)}])
#             self.assertEqual(report['commandAvailability'], 'mycel2_verified')
#             self.assertTrue(fixture.old.exists()); self.assertTrue(fixture.corpus.exists())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_report_rejects_unverified_flags_changed_approved_plan_sequence_jumps_and_copied_state
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Report rejects unverified flags changed approved plan sequence jumps and copied state.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_report_rejects_unverified_flags_changed_approved_plan_sequence_jumps_and_copied_state(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); fixture.compile()
#             fixture.report['steps'][0]['status'] = 'completed'
#             with self.assertRaises(BuildError): fixture.validate()
#             fixture.compile(); fixture.observe('new_private_store', 'completed', fixture.action('new_private_store'))
#             with self.assertRaises(BuildError): fixture.validate()
#             fixture.compile(); fixture.observe('inventory_review', 'completed', fixture.action('inventory_review'))
#             fixture.plan_path.write_text(fixture.plan_path.read_text().replace('RESTRICT', 'CASCADE'))
#             with self.assertRaises(BuildError): fixture.validate()
#             fixture.compile(); fixture.observe('inventory_review', 'completed', {'copiedVersion1State': ['vectors'],
#                 **fixture.action('inventory_review')})
#             with self.assertRaises(BuildError): fixture.validate()
#             fixture.compile(); fixture.observe('inventory_review', 'completed', fixture.action('inventory_review'))
#             verification = fixture.report['steps'][0]['verification']
#             Path(verification['path']).write_text('{}')
#             with self.assertRaises(BuildError): fixture.validate()
#             for malformed in (123, None, 'not a step'):
#                 with self.subTest(malformed=malformed):
#                     fixture.compile(); fixture.report['steps'] = [malformed]
#                     with self.assertRaises(BuildError) as refused:
#                         fixture.validate()
#                     self.assertEqual(refused.exception.code, 'invalid_input')
#             for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
#                 with self.subTest(nonfinite=token):
#                     fixture.compile()
#                     facts = {**fixture.action('inventory_review'), 'extraObservedNumber': 'nonfiniteFixtureToken'}
#                     fixture.observe('inventory_review', 'completed', facts)
#                     verification_path = Path(fixture.report['steps'][0]['verification']['path'])
#                     verification_path.write_bytes(verification_path.read_bytes().replace(
#                         b'"nonfiniteFixtureToken"', token.encode('ascii')))
#                     fixture.report['steps'][0]['verification'] = binding(verification_path)
#                     with self.assertRaises(BuildError) as refused:
#                         fixture.validate()
#                     self.assertEqual(refused.exception.code, 'invalid_input')
#
#
#         # Real file swaps after a completed read must not replace the bytes
#         # actually hashed, decoded, or used to derive shell-file instructions.
#         from mycel_build import _replacement as replacement
#         original_read = replacement._regular_bytes
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             path = fixture.root / 'evidence/snapshot.json'
#             approved = write(path, {'observation': 'approved original bytes'})
#             swapped = False
#             def swap_evidence(selected):
#                 nonlocal swapped
#                 data = original_read(selected)
#                 if Path(selected) == path and not swapped:
#                     swapped = True
#                     write(path, {'observation': 'different unapproved bytes'})
#                 return data
#             with patch.object(replacement, '_regular_bytes', side_effect=swap_evidence):
#                 self.assertEqual(replacement._bound(approved), {'observation': 'approved original bytes'})
#             self.assertTrue(swapped)
#             self.assertNotEqual(binding(path), approved)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); fixture.compile()
#             changed = deepcopy(fixture.plan); changed['newDatabase'] = 'fixture-server/changed-private'
#             body = {key: value for key, value in changed.items() if key != 'sha256'}
#             changed['sha256'] = sha((json.dumps(body, sort_keys=True, separators=(',', ':'),
#                 ensure_ascii=True, allow_nan=False) + '\n').encode())
#             changed_report = deepcopy(fixture.report); changed_report['planSha256'] = changed['sha256']
#             swapped = False
#             def swap_plan(selected):
#                 nonlocal swapped
#                 data = original_read(selected)
#                 if Path(selected) == fixture.plan_path and not swapped:
#                     swapped = True
#                     write(fixture.plan_path, changed)
#                     write(fixture.root / 'report.json', changed_report)
#                 return data
#             with patch.object(replacement, '_regular_bytes', side_effect=swap_plan):
#                 with self.assertRaises(BuildError): fixture.validate()
#             self.assertTrue(swapped)
#             self.assertNotEqual(sha(fixture.plan_path.read_bytes()), fixture.plan_sha)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); approved = binding(fixture.inventory_path)
#             changed = deepcopy(fixture.inventory); changed['newDatabase'] = 'fixture-server/changed-private'
#             swapped = False
#             def swap_inventory(selected):
#                 nonlocal swapped
#                 data = original_read(selected)
#                 if Path(selected) == fixture.inventory_path and not swapped:
#                     swapped = True
#                     write(fixture.inventory_path, changed)
#                 return data
#             with patch.object(replacement, '_regular_bytes', side_effect=swap_inventory):
#                 plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertTrue(swapped)
#             self.assertEqual(plan['inventory'], approved)
#             self.assertEqual(plan['newDatabase'], fixture.inventory['newDatabase'])
#             self.assertNotEqual(binding(fixture.inventory_path), approved)
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve()); before = fixture.shell.read_bytes()
#             definitions = {row['definition'].encode() for row in fixture.inventory['aliases']}
#             expected_remaining = b''.join(line for line in before.splitlines(keepends=True)
#                 if line.rstrip(b'\r\n') not in definitions)
#             swapped = False
#             def swap_shell(selected):
#                 nonlocal swapped
#                 data = original_read(selected)
#                 if Path(selected) == fixture.shell and not swapped:
#                     swapped = True
#                     fixture.shell.write_bytes(before + b'# separately changed tail\n')
#                 return data
#             with patch.object(replacement, '_regular_bytes', side_effect=swap_shell):
#                 plan = replacement_plan(fixture.inventory_path, now=AT)['plan']
#             self.assertTrue(swapped)
#             self.assertEqual(plan['aliases'][0]['sourceSha256'], sha(before))
#             self.assertEqual(plan['aliases'][0]['remainingSha256'], sha(expected_remaining))
#             self.assertEqual(fixture.shell.read_bytes(), before + b'# separately changed tail\n')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_already_absent_old_runtime_is_observed_without_inventing_cleanup_or_availability
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Already absent old runtime is observed without inventing cleanup or availability.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_already_absent_old_runtime_is_observed_without_inventing_cleanup_or_availability(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             fixture.link.unlink(); fixture.old.unlink()
#             fixture.inventory['aliases'] = []
#             for row in fixture.inventory['files'][:2]:
#                 row.update(kind='absent', sha256=None, ownership=None)
#             fixture.compile()
#             self.assertFalse(fixture.plan['blocked'])
#             self.assertEqual(fixture.plan['files'], [])
#             self.assertFalse(any(row['id'].startswith('remove_file:') for row in fixture.plan['steps']))
#             self.assertEqual(fixture.validate()['commandAvailability'], 'unverified')
#             for step in fixture.plan['steps']:
#                 if step['required']:
#                     fixture.observe(step['id'], 'completed', fixture.action(step['id']))
#             self.assertTrue(fixture.validate()['complete'])
#             # Final verification refuses a newly present file or dangling link.
#             for kind in ('file', 'symlink'):
#                 with self.subTest(kind=kind):
#                     if kind == 'file': fixture.old.write_bytes(b'new unrelated owner')
#                     else: fixture.old.symlink_to('missing-target')
#                     with self.assertRaises(BuildError): fixture.validate()
#                     fixture.old.unlink()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_absent_inventory_refuses_present_objects_ambiguous_claims_and_unobservable_paths
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Absent inventory refuses present objects ambiguous claims and unobservable paths.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_absent_inventory_refuses_present_objects_ambiguous_claims_and_unobservable_paths(self):
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             fixture.inventory['aliases'] = []
#             original = deepcopy(fixture.inventory['files'][0])
#             row = fixture.inventory['files'][0]
#             row.update(kind='absent', sha256=None, ownership=None)
#             for kind in ('file', 'directory', 'symlink'):
#                 with self.subTest(presentKind=kind):
#                     fixture.save()
#                     with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#                     if fixture.old.is_dir(): fixture.old.rmdir()
#                     else: fixture.old.unlink()
#                     if kind == 'file': fixture.old.mkdir()
#                     elif kind == 'directory': fixture.old.symlink_to('missing-target')
#             # The last loop leaves a genuinely absent target.
#             valid = deepcopy(row)
#             for change in ({'sha256': sha(b'')}, {'ownership': original['ownership']},
#                            {'role': 'source_corpus'}, {'uncertainty': 'Not observed'}):
#                 with self.subTest(change=change):
#                     row.clear(); row.update(valid); row.update(change); fixture.save()
#                     with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
#             row.clear(); row.update(valid); fixture.save()
#             from mycel_build import _replacement as replacement
#             original_stat = Path.lstat
#             def denied(selected, *args, **kwargs):
#                 if selected == fixture.old: raise PermissionError('Cannot observe this path')
#                 return original_stat(selected, *args, **kwargs)
#             with patch.object(Path, 'lstat', denied):
#                 with self.assertRaises(BuildError): replacement_plan(fixture.inventory_path, now=AT)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_replacement.py::ReplacementTests.test_mycel_owned_help_and_replacement_guide_require_no_other_product_or_runtime_cleanup_command
# Reason: Narrower case removed from this family after retaining test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Mycel owned help and replacement guide require no other product or runtime cleanup command.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_replacement.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_mycel_owned_help_and_replacement_guide_require_no_other_product_or_runtime_cleanup_command(self):
#         root = Path(_support.__file__).resolve().parents[1]
#         guide = (root / 'docs/replacement.md').read_text()
#         self.assertIn('python -m mycel_build replacement-plan', guide)
#         self.assertIn('RESTRICT', guide); self.assertIn('mycel init', guide)
#         self.assertIn('No Arbol script', guide)
#         output = io.StringIO()
#         with patch('mycel_build.__main__.registry_path', side_effect=AssertionError('registry read')), redirect_stdout(output):
#             self.assertEqual(main(['--help']), 0)
#         help_reply = json.loads(output.getvalue())
#         self.assertIn('replacement-plan', help_reply['commands']); self.assertIn('replacement-validate', help_reply['commands'])
#         self.assertNotIn('replacement-execute', help_reply['commands'])
#         with tempfile.TemporaryDirectory() as directory:
#             fixture = Fixture(Path(directory).resolve())
#             output = io.StringIO()
#             with patch('mycel_build._replacement.datetime') as clock, \
#                     patch('mycel_build.__main__.registry_path', side_effect=AssertionError('registry')), redirect_stdout(output):
#                 clock.now.return_value = AT
#                 clock.fromisoformat.side_effect = datetime.fromisoformat
#                 self.assertEqual(main(['replacement-plan', '--inventory', str(fixture.inventory_path)]), 0)
#             actual = json.loads(output.getvalue())
#             plan_path = fixture.root / 'cli-plan.json'; write(plan_path, actual['plan'])
#             report_path = fixture.root / 'cli-report.json'; write(report_path, actual['report'])
#             output = io.StringIO()
#             with patch('mycel_build._replacement.datetime') as clock, \
#                     patch('mycel_build.__main__.registry_path', side_effect=AssertionError('registry')), redirect_stdout(output):
#                 clock.now.return_value = AT
#                 clock.fromisoformat.side_effect = datetime.fromisoformat
#                 self.assertEqual(main(['replacement-validate', '--plan', str(plan_path), '--plan-sha256',
#                     sha(plan_path.read_bytes()), '--report', str(report_path)]), 0)
#             validated = json.loads(output.getvalue())
#             self.assertFalse(validated['complete'])
#             self.assertEqual(validated['databaseConnections'], 0)
#             write(report_path, {'schemaVersion': 1, 'planSha256': actual['plan']['sha256'], 'steps': [123]})
#             output = io.StringIO()
#             with patch('mycel_build._replacement.datetime') as clock, \
#                     patch('mycel_build.__main__.registry_path', side_effect=AssertionError('registry')), redirect_stdout(output):
#                 clock.now.return_value = AT
#                 clock.fromisoformat.side_effect = datetime.fromisoformat
#                 self.assertEqual(main(['replacement-validate', '--plan', str(plan_path), '--plan-sha256',
#                     sha(plan_path.read_bytes()), '--report', str(report_path)]), 1)
#             self.assertEqual(json.loads(output.getvalue())['error']['code'], 'invalid_input')
# LOW-TIER-SOURCE-END
# LOW-TIER-END
