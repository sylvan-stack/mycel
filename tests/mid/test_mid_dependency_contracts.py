"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_dependency_contracts as _support
from test_dependency_contracts import (EvidenceStore)


class DependencyContractStoreTests(_support.DependencyContractStoreTests):


# TEST-TIER-BEGIN tests/test_dependency_contracts.py::DependencyContractStoreTests.test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline
    def test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'---\nsources: ["fixture:@artifact/source.md#Source"]\n---\n# Guide\nMain dependant.\n')
        self.base.commit()
        self.base.git('checkout', '-b', 'feature')
        guide.write_bytes(guide.read_bytes().replace(b'Main dependant.', b'Feature dependant.'))
        self.fixture.source.write_bytes(b'# Source\nFeature governing source.\n')
        self.base.commit()
        self.base.git('checkout', 'fixture-main')
        guide.write_bytes(guide.read_bytes().replace(b'Main dependant.', b'Stashed dependant.'))
        self.fixture.source.write_bytes(b'# Source\nStashed governing source.\n')
        self.base.git('stash', 'push', '--message', 'Dependency baseline fixture')

        def rows(connection):
            return connection.execute("""SELECT l.kind,l.location,d.dependant_version,d.id,d.baseline_owner,
                r.manifest_hash,d.state FROM public.mycel_dependencies d
                JOIN public.mycel_file_locations l ON l.id::text=d.state->'declarationLocation'->>'file'
                JOIN public.mycel_locations c ON c.file_location=l.id AND c.chunk_version=d.dependant_version
                JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
                WHERE d.repository='fixture' AND l.metadata->>'path'='guide.md'
                ORDER BY l.kind,l.location,d.dependant_version""").fetchall()

        with self.base.connect() as connection:
            self.fixture.publish(connection)
            first = rows(connection)
            self.assertEqual({row[0] for row in first}, {'disk', 'branch', 'stash'})
            disk = next(row for row in first if row[0] == 'disk')
            retained = [row for row in first if row[0] != 'disk']
            stash = next(row for row in first if row[0] == 'stash')
            stash_baseline = EvidenceStore(connection).read_baseline('fixture', stash[5]).manifest.payload
            self.assertEqual(stash_baseline['location']['kind'], 'stash')
            self.assertNotEqual(stash[2], disk[2])
            self.assertIn(b'# Source\nStashed governing source.\n',
                [item.source for item in EvidenceStore(connection).read_baseline('fixture', stash[5]).snapshots])
            self.base.git('checkout', 'feature')
            self.fixture.publish(connection)
            later = next(row for row in rows(connection) if row[0] == 'disk')
            self.assertNotEqual(later[2], disk[2])
            self.assertNotEqual(later[5], disk[5])
            self.assertEqual([row for row in rows(connection) if row[0] != 'disk'], retained)
            self.base.git('checkout', 'fixture-main')
            restored = self.fixture.publish(connection)
            self.assertEqual(next(row for row in rows(connection) if row[0] == 'disk'), disk)
            self.assertEqual(restored.counts['pinsCaptured'], 0)
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            missing = next(row for row in rows(connection) if row[0] == 'disk')
            self.assertEqual(missing[:6], disk[:6])
            self.assertEqual((missing[6]['sourceExistence'], missing[6]['reasons']), ('away', ['source_removed']))
            self.assertEqual([row for row in rows(connection) if row[0] != 'disk'], retained)
# TEST-TIER-END tests/test_dependency_contracts.py::DependencyContractStoreTests.test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_family_membership_and_complete_file_changes_keep_pin_until_declaration_removal
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Family membership and complete file changes keep pin until declaration removal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_family_membership_and_complete_file_changes_keep_pin_until_declaration_removal(self):
#         code = self.base.code / 'policy.py'
#         original = b'class Policy:\n    def apply(self):\n        return 1\n'
#         code.write_bytes(original)
#         self.base.commit()
#         self.fixture.answer.write_bytes(b'---\nsources: ["fixture:@code/policy.py#Policy", '
#             b'"fixture:@artifact/source.md"]\n---\n# Answer\nUnchanged dependant.\n')
#         with self.base.connect() as connection:
#             before = self.fixture.prepare(connection)
#             self.assertEqual(len(before), 2)
#             family = next(row for row in before if row[4].endswith('#Policy'))
#             whole = next(row for row in before if row[4].endswith('/source.md'))
#             family_manifest, file_manifest = self.baseline(connection, family), self.baseline(connection, whole)
#             self.assertEqual(len(family_manifest['members']), 2)
#             self.assertEqual(file_manifest['pinnedHash'], sha256(self.fixture.source_bytes).hexdigest())
#             self.assertEqual(len(self.fixture.edges(connection)), 3)
#             code.write_bytes(original + b'    def added(self):\n        return 2\n')
#             self.fixture.source.write_bytes(b'---\nrole: authored\n---\n' + self.fixture.source_bytes)
#             observed = self.fixture.publish(connection)
#             current = self.fixture.dependencies(connection)
#             self.assertEqual(self.fixture.pins(current), self.fixture.pins(before))
#             self.assertEqual(len(self.fixture.edges(connection)), 4)
#             self.assertTrue(all(row[5]['reasons'] == ['source_changed'] for row in current))
#             self.assertEqual(observed.counts['dependencyRepositories']['downstream']['pinsCaptured'], 0)
#             code.write_bytes(b'class Policy:\n    def added(self):\n        return 2\n')
#             self.fixture.publish(connection)
#             current_family = next(row for row in self.fixture.dependencies(connection) if row[4].endswith('#Policy'))
#             self.assertEqual(current_family[5]['reasons'], ['source_removed', 'source_changed'])
#             self.assertEqual(self.baseline(connection, current_family), family_manifest)
#             self.fixture.answer.write_bytes(b'# Answer\nUnchanged dependant.\n')
#             removed = self.fixture.publish(connection, 'downstream')
#             self.assertEqual(removed.counts['dependenciesReleased'], 2)
#             self.assertEqual(self.fixture.dependencies(connection), [])
#             self.assertEqual(self.fixture.edges(connection), [])
#             self.assertEqual(self.fixture.role(connection), 'unclassified')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners '
#                 'WHERE id=ANY(%s)', ([family[6], whole[6]],)).fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_each_publication_recomputes_file_role_and_document_code_defaults
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Each publication recomputes file role and document code defaults.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_each_publication_recomputes_file_role_and_document_code_defaults(self):
#         self.fixture.answer.write_bytes(b'# Answer\nUnchanged dependant.\n')
#         (self.base.code / 'plain.py').write_bytes(b'def plain():\n    return 1\n')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             self.assertEqual(self.fixture.role(connection), 'unclassified')
#             self.assertEqual(connection.execute("""SELECT DISTINCT l.metadata->>'role'
#                 FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
#                 JOIN public.mycel_chunks c ON c.id=v.chunk_id
#                 WHERE c.repository='fixture' AND l.kind='disk' AND c.kind<>'document'""").fetchall(), [('authored',)])
#             old_version = connection.execute("""SELECT c.chunk_version FROM public.mycel_locations c
#                 JOIN public.mycel_file_locations l ON l.id=c.file_location
#                 JOIN public.mycel_file_versions v ON v.id=l.file_version
#                 JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository='downstream'""").fetchone()[0]
#             for role in ('authored', 'derived', 'authored'):
#                 self.fixture.answer.write_bytes(('---\nrole: ' + role + '\n---\n# Answer\nUnchanged dependant.\n').encode())
#                 self.fixture.publish(connection, 'downstream')
#                 self.assertEqual(self.fixture.role(connection), role)
#                 self.assertEqual(connection.execute("""SELECT c.chunk_version FROM public.mycel_locations c
#                     JOIN public.mycel_file_locations l ON l.id=c.file_location
#                     JOIN public.mycel_file_versions v ON v.id=l.file_version
#                     JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository='downstream'""").fetchone()[0], old_version)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_source_sibling_frontmatter_observations_keep_pin_and_authorized_confirmation_answers_change
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Source sibling frontmatter observations keep pin and authorized confirmation answers change.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_source_sibling_frontmatter_observations_keep_pin_and_authorized_confirmation_answers_change(self):
#         self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() + b'\n## Other\nOriginal sibling.\n')
#         with self.base.connect() as connection:
#             before = self.fixture.prepare(connection)
#             answer = next(row for row in before if row[6] is not None)
#             baseline = self.baseline(connection, answer)
#             self.fixture.source.write_bytes(b'# Source\nCurrent changed source.\n')
#             self.fixture.publish(connection)
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Original sibling.', b'Edited sibling.')
#                 .replace(b'role: authored', b'role: derived'))
#             observed = self.fixture.publish(connection, 'downstream')
#             current = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
#             self.assertEqual(self.fixture.pins([current]), self.fixture.pins([answer]))
#             self.assertEqual(current[5]['reasons'], ['source_changed'])
#             self.assertEqual(observed.counts['pinsCaptured'], 0)
#             confirmed = self.confirm(connection)
#             self.assertEqual(confirmed.captured, 1)
#             renewed = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
#             self.assertEqual(renewed[1], answer[1])
#             self.assertNotEqual(renewed[7], answer[7])
#             self.assertNotEqual(self.baseline(connection, renewed)['pinnedHash'], baseline['pinnedHash'])
#             self.assertEqual(renewed[5]['reasons'], [])
#             self.assertEqual(confirmed.plan.decisions[0].reasons, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_substantive_dependant_edit_pins_current_source_and_answers_direct_change_in_same_commit
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Substantive dependant edit pins current source and answers direct change in same commit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_substantive_dependant_edit_pins_current_source_and_answers_direct_change_in_same_commit(self):
#         with self.base.connect() as connection:
#             before = self.fixture.prepare(connection)
#             old_hash = self.baseline(connection, before[0])['pinnedHash']
#             self.fixture.source.write_bytes(b'# Source\nCurrent changed source.\n')
#             self.fixture.publish(connection)
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Revised dependant.'))
#             edited = self.fixture.publish(connection, 'downstream')
#             current = self.fixture.dependencies(connection)
#             self.assertEqual(edited.counts['pinsCaptured'], 1)
#             self.assertNotEqual(self.baseline(connection, current[0])['pinnedHash'], old_hash)
#             self.assertEqual(current[0][5]['reasons'], [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_guarded_confirmation_withdraws_deleted_baseline_but_retains_declared_fault
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Guarded confirmation withdraws deleted baseline but retains declared fault.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_guarded_confirmation_withdraws_deleted_baseline_but_retains_declared_fault(self):
#         with self.base.connect() as connection:
#             before = self.fixture.prepare(connection)
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             retained = self.fixture.dependencies(connection)
#             self.assertEqual(self.fixture.pins(retained), self.fixture.pins(before))
#             self.assertEqual(retained[0][5]['reasons'], ['source_removed'])
#             confirmed = self.confirm(connection)
#             current = self.fixture.dependencies(connection)
#             self.assertEqual(confirmed.released, 1)
#             self.assertIsNone(current[0][6])
#             self.assertEqual(current[0][5]['resolution']['fault'], 'missing_file')
#             self.assertEqual(current[0][5]['reasons'], [])
#             self.assertFalse(current[0][5]['everResolved'])
#             self.assertEqual(self.fixture.role(connection), 'authored')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
#                 (before[0][6],)).fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dependency_contracts.py::DependencyContractStoreTests.test_unresolved_declared_selection_refuses_confirmation_before_any_repin_or_withdrawal
# Reason: Narrower case removed from this family after retaining test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unresolved declared selection refuses confirmation before any repin or withdrawal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dependency_contracts.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unresolved_declared_selection_refuses_confirmation_before_any_repin_or_withdrawal(self):
#         with self.base.connect() as connection:
#             original = self.fixture.prepare(connection)
#             self.fixture.source.write_bytes(b'# Source\nChanged before confirmation.\n')
#             self.fixture.publish(connection)
#             self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(
#                 b'source.md#Source"]', b'source.md#Source", "fixture:@artifact/missing.md#Absent"]'))
#             self.fixture.publish(connection, 'downstream')
#             before = self.fixture.state(connection)
#             with self.assertRaises(ReconciliationError) as error:
#                 self.confirm(connection)
#             self.assertEqual(error.exception.status, 'invalid_input')
#             self.assertEqual(self.fixture.state(connection), before)
#             pinned = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
#             self.assertEqual(self.fixture.pins([pinned]), self.fixture.pins(original))
#             self.fixture.source.unlink()
#             self.base.commit()
#             self.fixture.publish(connection)
#             before = self.fixture.state(connection)
#             with self.assertRaises(ReconciliationError):
#                 self.confirm(connection)
#             self.assertEqual(self.fixture.state(connection), before)
#             self.assertIsNotNone(next(row for row in self.fixture.dependencies(connection) if row[6] is not None)[6])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
