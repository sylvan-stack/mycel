"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_capture as _support
from test_capture import (CompletedChild ,capture ,replace ,run_git ,sha256)


class TemporaryGitCaptureTests(_support.TemporaryGitCaptureTests):


# TEST-TIER-BEGIN tests/test_capture.py::TemporaryGitCaptureTests.test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals
    def test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals(self):
        self.write(self.code,'file.md','# Main\n')
        self.commit()
        settings=self.settings(artifact=False)
        first,_=self.read_git(settings)
        def failure(args,**options):
            if args[0]=='cat-file':
                return CompletedChild(1,b'',b'private provider target',0)
            return run_git(args,**options)
        failed=capture.capture_repository(settings,'fixture',_git=failure)
        self.assertFalse(failed.complete)
        self.assertEqual(failed.delta(first).removed,())
        self.assertEqual(failed.disk.files[0].source,b'# Main\n')
        self.assertNotIn('private',failed.canonical_bytes().decode())
        calls=0
        def inventory_race(args,**options):
            nonlocal calls
            result=run_git(args,**options)
            if args[0]=='for-each-ref':
                calls+=1
                if calls==2:
                    return replace(result,stdout=b'')
            return result
        raced=capture.capture_repository(settings,'fixture',_git=inventory_race)
        self.assertFalse(raced.complete)
        self.assertTrue(any(item.code=='changed_during_capture' for item in raced.diagnostics))
# TEST-TIER-END tests/test_capture.py::TemporaryGitCaptureTests.test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals


# TEST-TIER-BEGIN tests/test_capture.py::TemporaryGitCaptureTests.test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file
    def test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file(self):
        self.write(self.code,'.gitignore','docs/blocked/\n')
        self.write(self.code,'docs/visible.md','# Visible\n')
        self.write(self.code,'docs/blocked/no.md','# Blocked\n')
        self.commit()
        worktree=self.home/'worktree'
        self.git('worktree','add','-b','other',str(worktree))
        self.code=worktree/'docs'
        before={str(path.relative_to(worktree)):sha256(path.read_bytes()).hexdigest()
                for path in worktree.rglob('*') if path.is_file()}
        result,_=self.read_git(self.settings(artifact=False))
        self.assertTrue(result.complete,result.diagnostics)
        self.assertEqual([location.id.identity for location in result.locations],['disk','refs/heads/main','refs/heads/other'])
        self.assertTrue(all([file.primary.path for file in location.files]==['visible.md'] for location in result.locations))
        self.assertEqual(before,{str(path.relative_to(worktree)):sha256(path.read_bytes()).hexdigest()
                                for path in worktree.rglob('*') if path.is_file()})
# TEST-TIER-END tests/test_capture.py::TemporaryGitCaptureTests.test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file


# TEST-TIER-BEGIN tests/test_capture.py::TemporaryGitCaptureTests.test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity
    def test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity(self):
        self.write(self.code,'file.md','# Original commit\n')
        self.commit('original')
        original=self.git('rev-parse','HEAD')
        self.write(self.code,'file.md','# Replacement commit\n')
        self.commit('replacement')
        replacement=self.git('rev-parse','HEAD')
        self.git('update-ref','refs/heads/main',original)
        self.git('replace',original,replacement)
        before=self.state()
        result,_=self.read_git(self.settings(artifact=False))
        branch=next(location for location in result.locations if location.id.kind=='branch')
        self.assertEqual(branch.commit,original)
        self.assertEqual(branch.files[0].source,b'# Original commit\n')
        self.assertEqual(result.disk.files[0].source,b'# Replacement commit\n')
        self.assertEqual(self.state(),before)
# TEST-TIER-END tests/test_capture.py::TemporaryGitCaptureTests.test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity


# TEST-TIER-BEGIN tests/test_capture.py::TemporaryGitCaptureTests.test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git
    def test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git(self):
        self.git('config','core.ignorecase','false')
        rules='[[:digit:]].md\n[[:alpha:]].md\n[[:lower:]]lower.md\n[[:punct:]]punct.md\n?.one.md\n??.two.md\n[Éé].bracket.md\n'
        self.write(self.code,'.gitignore',rules)
        selected=('0.md','9.md','a.md','Z.md','zlower.md','BLOWER.md','!punct.md',
                  'a.one.md','雪.one.md','é.one.md','aa.two.md','é.two.md','雪.two.md',
                  'É.bracket.md','visible.md')
        for path in selected:
            self.write(self.code,path,'# Exact bytes\n')
        self.git('add','--force','.')
        self.commit()
        native=set(self.git('-c','core.quotepath=false','check-ignore','--no-index',*selected).splitlines())
        self.assertEqual(native,{'0.md','9.md','a.md','Z.md','zlower.md','!punct.md',
                                 'a.one.md','aa.two.md','é.two.md'})
        result,_=self.read_git(self.settings(artifact=False))
        self.assertTrue(result.complete,result.diagnostics)
        self.assertTrue(all({file.primary.path for file in location.files}==set(selected)-native
                            for location in result.locations))
# TEST-TIER-END tests/test_capture.py::TemporaryGitCaptureTests.test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_both_roots_share_configured_endings_skips_and_markdown_ignores_code_subdirs
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Both roots share configured endings skips and markdown ignores code subdirs.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_both_roots_share_configured_endings_skips_and_markdown_ignores_code_subdirs(self):
#         for root in (self.code, self.artifact):
#             for path in ('README.md', 'docs/design.md', 'nested/build/private.md', 'nested/node_modules/private.md'):
#                 self.write(root, path, '# Document\n')
#         self.write(self.code, 'src/code.py', 'def run():\n    pass\n')
#         self.write(self.code, 'tests/excluded.py', 'pass\n')
#         self.write(self.code, 'src/module.plist.in', '<plist/>\n')
#         self.write(self.code, 'src/UPPER.PY', 'pass\n')
#         self.write(self.artifact, 'wrong.py', 'pass\n')
#         manifest = self.read(self.settings(subfolders=('src',)))
#         self.assertTrue(manifest.complete)
#         self.assertEqual(self.paths(manifest), {
#             ('code', 'README.md', 'documents'), ('code', 'docs/design.md', 'documents'),
#             ('artifact', 'README.md', 'documents'), ('artifact', 'docs/design.md', 'documents'),
#             ('code', 'src/code.py', 'code'), ('code', 'src/module.plist.in', 'code')})
#         self.assertEqual(manifest.disk.files[-1].parsed[0].language, 'plist')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_custom_scan_policy_uses_literal_endings_and_the_same_exclusions
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Custom scan policy uses literal endings and the same exclusions.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_custom_scan_policy_uses_literal_endings_and_the_same_exclusions(self):
#         for root in (self.code, self.artifact):
#             self.write(root, 'read.txt', '# Text\n')
#             self.write(root, 'old.md', '# Not configured\n')
#             self.write(root, 'hidden/read.txt', '# Excluded\n')
#         self.write(self.code, 'file.xyz', 'whole file\n')
#         manifest = self.read(self.settings(scan={'document_endings':['.txt'], 'code_endings':['.xyz'],
#                                                'skip_folders':['hidden']}))
#         self.assertEqual(self.paths(manifest), {('code','read.txt','documents'),
#                                               ('artifact','read.txt','documents'),('code','file.xyz','code')})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_skip_folders_never_excludes_an_identically_named_regular_file
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Skip folders never excludes an identically named regular file.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_skip_folders_never_excludes_an_identically_named_regular_file(self):
#         self.write(self.code,'excluded.md','# Regular document\n')
#         self.write(self.code,'nested/excluded.md','# Nested regular document\n')
#         self.write(self.code,'other/excluded.md/child.md','# Excluded directory\n')
#         result=self.read(self.settings(artifact=False,scan={'skip_folders':['excluded.md']}))
#         self.assertEqual(self.paths(result),{('code','excluded.md','documents'),
#                                             ('code','nested/excluded.md','documents')})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_hierarchical_gitignore_anchoring_negation_escapes_and_excluded_parents
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Hierarchical gitignore anchoring negation escapes and excluded parents.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_hierarchical_gitignore_anchoring_negation_escapes_and_excluded_parents(self):
#         self.write(self.code, '.gitignore', '/top.md\n*.tmp.md\nblocked/\n!blocked/keep.md\nallowed/*\n!allowed/keep.md\n\\#literal.md\nspace\\ .md\n')
#         self.write(self.code, 'nested/.gitignore', '!keep.tmp.md\nlocal.md\n')
#         for path in ('top.md','nested/top.md','discard.tmp.md','nested/keep.tmp.md','nested/local.md',
#                      'blocked/keep.md','allowed/no.md','allowed/keep.md','#literal.md','space .md'):
#             self.write(self.code, path, '# Exact\n')
#         manifest = self.read(self.settings(artifact=False))
#         self.assertTrue(manifest.complete)
#         self.assertEqual(self.paths(manifest), {('code','nested/top.md','documents'),
#                                               ('code','nested/keep.tmp.md','documents'),
#                                               ('code','allowed/keep.md','documents')})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_unicode_line_separator_is_literal_in_an_ignore_pattern
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unicode line separator is literal in an ignore pattern.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unicode_line_separator_is_literal_in_an_ignore_pattern(self):
#         self.write(self.code,'.gitignore','odd\u2028name.md\n')
#         self.write(self.code,'odd\u2028name.md','# Ignored literal filename\n')
#         self.write(self.code,'name.md','# Retained distinct filename\n')
#         result=self.read(self.settings(artifact=False))
#         self.assertEqual(self.paths(result),{('code','name.md','documents')})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_overlap_uses_specific_root_and_retains_previous_primary_when_still_reachable
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Overlap uses specific root and retains previous primary when still reachable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_overlap_uses_specific_root_and_retains_previous_primary_when_still_reachable(self):
#         self.artifact = self.code / 'docs'
#         self.artifact.mkdir()
#         self.write(self.artifact,'README.md','# Shared\n')
#         settings=self.settings()
#         manifest=self.read(settings)
#         self.assertEqual(len(manifest.disk.files),1)
#         file=manifest.disk.files[0]
#         self.assertEqual(file.primary,capture.FileAlias('artifact','README.md'))
#         self.assertEqual(file.aliases,(capture.FileAlias('artifact','README.md'),capture.FileAlias('code','docs/README.md')))
#         old_file=replace(file,primary=capture.FileAlias('code','docs/README.md'))
#         previous=replace(manifest,locations=(replace(manifest.disk,files=(old_file,)),))
#         current=self.read(settings,previous=previous)
#         self.assertEqual(current.disk.files[0].primary,old_file.primary)
#         self.assertTrue(current.disk.files[0].reused_parse)
#         self.assertEqual(len(current.delta(previous).unchanged),1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_equal_roots_choose_artifact_but_distinct_same_paths_and_bytes_never_merge
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Equal roots choose artifact but distinct same paths and bytes never merge.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_equal_roots_choose_artifact_but_distinct_same_paths_and_bytes_never_merge(self):
#         self.write(self.code,'README.md','# Same\n')
#         self.write(self.artifact,'README.md','# Same\n')
#         distinct=self.read()
#         self.assertEqual(len(distinct.disk.files),2)
#         self.assertEqual({file.primary.root for file in distinct.disk.files},{'code','artifact'})
#         self.artifact=self.code
#         equal=self.read()
#         self.assertEqual(len(equal.disk.files),1)
#         self.assertEqual(equal.disk.files[0].primary.root,'artifact')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_directory_links_file_links_loops_and_fifos_are_never_followed
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Directory links file links loops and fifos are never followed.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_directory_links_file_links_loops_and_fifos_are_never_followed(self):
#         self.write(self.code,'real.md','# Real\n')
#         outside=self.write(self.home,'outside.md','# Outside\n')
#         (self.code/'outside.md').symlink_to(outside)
#         (self.code/'alias.md').symlink_to(self.code/'real.md')
#         (self.code/'loop').symlink_to(self.code,target_is_directory=True)
#         (self.code/'escape').symlink_to(self.home,target_is_directory=True)
#         os.mkfifo(self.code/'fifo.md')
#         result=self.read(self.settings(artifact=False))
#         self.assertTrue(result.complete)
#         self.assertEqual(self.paths(result),{('code','real.md','documents')})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_configured_root_link_resolves_once_and_retains_portable_binding
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Configured root link resolves once and retains portable binding.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_configured_root_link_resolves_once_and_retains_portable_binding(self):
#         actual=self.home/'actual'
#         actual.mkdir()
#         self.write(actual,'雪 #%.md','# Exact\r\n')
#         self.code=self.home/'root-link'
#         self.code.symlink_to(actual,target_is_directory=True)
#         result=self.read(self.settings(artifact=False))
#         file=result.disk.files[0]
#         self.assertEqual(file.primary.address('fixture'),'fixture:@code/%E9%9B%AA%20%23%25.md')
#         self.assertEqual(file.source,b'# Exact\r\n')
#         self.assertNotIn(str(actual),result.canonical_bytes().decode())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_complete_bytes_exact_hashes_immutable_manifest_and_local_decode_failure
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Complete bytes exact hashes immutable manifest and local decode failure.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_bytes_exact_hashes_immutable_manifest_and_local_decode_failure(self):
#         large=b'# Complete\r\n'+('雪 and spaces\r\n'.encode()*90000)
#         self.write(self.code,'large.md',large)
#         invalid=b'# Broken\n\xff\x00'
#         self.write(self.code,'invalid.md',invalid)
#         result=self.read(self.settings(artifact=False))
#         self.assertTrue(result.complete)
#         self.assertFalse(result.deletion_safe)
#         files={file.primary.path:file for file in result.disk.files}
#         self.assertEqual(files['large.md'].source,large)
#         self.assertEqual(files['large.md'].file_hash,sha256(large).hexdigest())
#         self.assertEqual(files['invalid.md'].source,invalid)
#         self.assertEqual(files['invalid.md'].failure,'invalid_utf8')
#         self.assertIsNone(files['invalid.md'].parsed)
#         self.assertTrue(any(item.alias.path=='invalid.md' for item in result.diagnostics))
#         with self.assertRaises(FrozenInstanceError):
#             result.complete=False
#         self.assertEqual(result.manifest_hash,sha256(result.canonical_bytes()).hexdigest())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_every_disk_file_is_reread_and_only_exact_unchanged_text_reuses_parsing
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Every disk file is reread and only exact unchanged text reuses parsing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_every_disk_file_is_reread_and_only_exact_unchanged_text_reuses_parsing(self):
#         path=self.write(self.code,'file.py','def f():\n    return 1\n')
#         settings=self.settings(artifact=False)
#         first=self.read(settings)
#         with patch('mycel._capture.chunk_code',wraps=capture.chunk_code) as parser:
#             unchanged=self.read(settings,previous=first)
#             parser.assert_not_called()
#         self.assertTrue(unchanged.disk.files[0].reused_parse)
#         # Same byte length, including after a preliminary observation.
#         self.assertEqual(sha256(path.read_bytes()).hexdigest(),first.disk.files[0].file_hash)
#         path.write_text('def f():\n    return 2\n')
#         changed=self.read(settings,previous=first)
#         self.assertEqual(len(changed.delta(first).changed),1)
#         self.assertFalse(changed.disk.files[0].reused_parse)
#         self.assertIn('return 2',changed.disk.files[0].parsed[0].text)
#         self.assertEqual(first.disk.files[0].source,b'def f():\n    return 1\n')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_changed_policy_or_parser_revision_requires_fresh_parsing_even_with_identical_bytes
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Changed policy or parser revision requires fresh parsing even with identical bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_policy_or_parser_revision_requires_fresh_parsing_even_with_identical_bytes(self):
#         self.write(self.code,'file.py','def f():\n    pass\n')
#         settings=self.settings(artifact=False)
#         first=self.read(settings)
#         with patch('mycel._capture._parser_revision',return_value='deliberately-new-parser-revision'), \
#                 patch('mycel._capture.chunk_code',wraps=capture.chunk_code) as parser:
#             revised=self.read(settings,previous=first)
#             parser.assert_called_once()
#         self.assertNotEqual(revised.policy_hash,first.policy_hash)
#         self.assertFalse(revised.disk.files[0].reused_parse)
#         self.assertEqual(len(revised.delta(first).changed),1)
#         policy=self.settings(artifact=False,scan={'skip_folders':['custom-exclusion']})
#         changed=self.read(policy,previous=first)
#         self.assertFalse(changed.disk.files[0].reused_parse)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_deleted_recreated_empty_and_incomplete_manifests_never_authorize_unsafe_removal
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Deleted recreated empty and incomplete manifests never authorize unsafe removal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deleted_recreated_empty_and_incomplete_manifests_never_authorize_unsafe_removal(self):
#         path=self.write(self.code,'README.md','# First\n')
#         settings=self.settings(artifact=False)
#         first=self.read(settings)
#         path.unlink()
#         empty=self.read(settings,previous=first)
#         self.assertEqual(len(empty.delta(first).removed),1)
#         with self.assertRaises(MycelError) as error:
#             empty.require_safe_reconciliation(first)
#         self.assertEqual(error.exception.code,'refused')
#         empty.require_safe_reconciliation(first,confirm_empty=True)
#         path.write_text('# Recreated\n')
#         recreated=self.read(settings,previous=empty)
#         self.assertEqual(len(recreated.delta(empty).new),1)
#         path.unlink()
#         self.code.rmdir()
#         incomplete=self.read(settings,previous=first)
#         self.assertFalse(incomplete.complete)
#         self.assertFalse(incomplete.delta(first).deletion_safe)
#         self.assertEqual(incomplete.delta(first).removed,())
#         with self.assertRaises(MycelError):
#             incomplete.require_safe_reconciliation(first,confirm_empty=True)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_observed_disk_race_invalid_path_and_broken_git_context_prevent_deletion
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Observed disk race invalid path and broken git context prevent deletion.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_observed_disk_race_invalid_path_and_broken_git_context_prevent_deletion(self):
#         path=self.write(self.code,'README.md','# First\n')
#         settings=self.settings(artifact=False)
#         original=capture._Capture.verify_disk
#         def race(current):
#             path.write_text('# Changed\n')
#             original(current)
#         with patch.object(capture._Capture,'verify_disk',race):
#             raced=self.read(settings)
#         self.assertFalse(raced.complete)
#         self.assertTrue(any(item.code=='changed_during_capture' for item in raced.diagnostics))
#         self.write(self.code,'bad\\path.md','# Cannot address\n')
#         invalid=self.read(settings)
#         self.assertFalse(invalid.complete)
#         (self.code/'.git').write_text('gitdir: /private/nonexistent\n')
#         broken=self.read(settings)
#         self.assertFalse(broken.complete)
#         self.assertNotIn('private',broken.canonical_bytes().decode())
#         self.assertTrue(any(file.primary.path=='README.md' for file in broken.disk.files))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::CaptureTests.test_disabled_or_non_settings_folders_refuse_before_git_and_cancellation_propagates
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disabled or non settings folders refuse before git and cancellation propagates.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disabled_or_non_settings_folders_refuse_before_git_and_cancellation_propagates(self):
#         settings=self.settings(enabled=False)
#         with patch('mycel._capture.run_git') as git:
#             with self.assertRaises(MycelError):
#                 capture.capture_repository(settings,'fixture',_git=git)
#             git.assert_not_called()
#         settings=self.settings()
#         repository=RepositoryLocations(settings).named('fixture')[0]
#         with self.assertRaises(MycelError):
#             self.read(settings,previous=capture.CaptureManifest('other','',(),True))
#         with self.assertRaises(MycelError):
#             capture.capture_repository(settings,replace(repository,code=Folder(self.home,'repository')),_git=no_checkout)
#         with self.assertRaises(KeyboardInterrupt):
#             self.read(settings,cancelled=lambda:True)
#         current=self.read(settings)
#         with self.assertRaises(MycelError):
#             current.require_safe_reconciliation(replace(current,repository='other'),confirm_empty=True)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_disk_local_branches_and_commit_named_untracked_stashes_are_read_without_mutation
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disk local branches and commit named untracked stashes are read without mutation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disk_local_branches_and_commit_named_untracked_stashes_are_read_without_mutation(self):
#         self.write(self.code,'README.md','# Main\n')
#         self.write(self.code,'src/code.py','def original():\n    pass\n')
#         self.commit()
#         self.git('branch','feature')
#         # Construct a distinct local tip and a remote-only ref in this private
#         # fixture. Production capture performs none of these mutations.
#         self.git('checkout','feature')
#         self.write(self.code,'README.md','# Feature\n')
#         self.write(self.code,'remote-only.md','# Local feature\n')
#         self.commit('feature')
#         feature=self.git('rev-parse','HEAD')
#         self.git('checkout','main')
#         self.git('update-ref','refs/remotes/origin/private',feature)
#         self.write(self.code,'README.md','# Stashed\r\n')
#         self.write(self.code,'untracked 雪.md','# Untracked stash\n')
#         self.git('stash','push','--include-untracked','-m','public stash')
#         stash=self.git('rev-parse','refs/stash')
#         self.write(self.code,'README.md','# Dirty disk\n')
#         self.write(self.code,'untracked-disk.md','# Untracked disk\n')
#         before=self.state()
#         result,calls=self.read_git(self.settings(artifact=False))
#         self.assertTrue(result.complete,result.diagnostics)
#         self.assertEqual(self.state(),before)
#         self.assertEqual([(location.id.kind,location.id.identity) for location in result.locations],
#                          [('disk','disk'),('branch','refs/heads/feature'),('branch','refs/heads/main'),('stash',stash)])
#         versions={location.id.identity:{file.primary.path:file.source for file in location.files} for location in result.locations}
#         self.assertEqual(versions['disk']['README.md'],b'# Dirty disk\n')
#         self.assertEqual(versions['refs/heads/main']['README.md'],b'# Main\n')
#         self.assertEqual(versions['refs/heads/feature']['README.md'],b'# Feature\n')
#         self.assertEqual(versions[stash]['README.md'],b'# Stashed\r\n')
#         self.assertEqual(versions[stash]['untracked 雪.md'],b'# Untracked stash\n')
#         self.assertNotIn('untracked 雪.md',versions['disk'])
#         self.assertNotIn('remote-only.md',versions['refs/heads/main'])
#         self.assertTrue(all(args[0] in {'rev-parse','for-each-ref','stash','ls-tree','cat-file','config'} for args in calls))
#         self.assertTrue(all(args==('config','--bool','--get','core.ignorecase')
#                             for args in calls if args[0]=='config'))
#         self.assertTrue(all(args[:2]==('stash','list') for args in calls if args[0]=='stash'))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_each_immutable_location_uses_its_own_hierarchical_ignore_bytes
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Each immutable location uses its own hierarchical ignore bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_each_immutable_location_uses_its_own_hierarchical_ignore_bytes(self):
#         self.write(self.code,'.gitignore','private.md\n')
#         self.write(self.code,'private.md','# Main private\n')
#         self.write(self.code,'visible.md','# Main visible\n')
#         self.git('add','--force','private.md')
#         self.commit()
#         self.git('branch','feature')
#         self.git('checkout','feature')
#         self.write(self.code,'.gitignore','visible.md\n')
#         self.commit('different ignore')
#         self.git('checkout','main')
#         self.write(self.code,'.gitignore','nothing-matches\n')
#         result,_=self.read_git(self.settings(artifact=False))
#         paths={location.id.identity:{file.primary.path for file in location.files} for location in result.locations}
#         self.assertEqual(paths['disk'],{'visible.md','private.md'})
#         self.assertEqual(paths['refs/heads/main'],{'visible.md'})
#         self.assertEqual(paths['refs/heads/feature'],{'private.md'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_nested_configured_roots_keep_checkout_paths_and_git_overlap_aliases
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Nested configured roots keep checkout paths and git overlap aliases.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_nested_configured_roots_keep_checkout_paths_and_git_overlap_aliases(self):
#         self.write(self.code,'.gitignore','hidden/\n')
#         self.write(self.code,'docs/a.md','# Artifact\n')
#         self.write(self.code,'docs/hidden/no.md','# Hidden\n')
#         self.write(self.code,'src/yes.py','pass\n')
#         self.write(self.code,'other/no.py','pass\n')
#         self.commit()
#         self.artifact=self.code/'docs'
#         result,_=self.read_git(self.settings(subfolders=('src',)))
#         for location in result.locations:
#             self.assertEqual({file.primary.path for file in location.files},{'a.md','src/yes.py'})
#             document=next(file for file in location.files if file.corpus=='documents')
#             self.assertEqual(document.primary,capture.FileAlias('artifact','a.md'))
#             self.assertEqual(document.aliases,(capture.FileAlias('artifact','a.md'),capture.FileAlias('code','docs/a.md')))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_known_commit_reuse_removed_recreated_branch_and_stash_commit_identity
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Known commit reuse removed recreated branch and stash commit identity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_known_commit_reuse_removed_recreated_branch_and_stash_commit_identity(self):
#         self.write(self.code,'file.md','# Main\n')
#         self.commit()
#         self.git('branch','same')
#         self.write(self.code,'file.md','# Stash one\n')
#         self.git('stash','push','-m','one')
#         oldest=self.git('rev-parse','refs/stash')
#         settings=self.settings(artifact=False)
#         first,_=self.read_git(settings)
#         reused,calls=self.read_git(settings,previous=first)
#         self.assertTrue(all(location.reused for location in reused.locations if location.id.kind!='disk'))
#         self.assertFalse(any(args[0] in {'ls-tree','cat-file'} for args in calls))
#         self.assertEqual(first.manifest_hash,reused.manifest_hash)
#         self.git('branch','-D','same')
#         self.write(self.code,'file.md','# Stash two\n')
#         self.git('stash','push','-m','two')
#         changed,_=self.read_git(settings,previous=reused)
#         self.assertIn(capture.LocationId('branch','code','refs/heads/same'),changed.delta(reused).removed_locations)
#         self.assertIn(capture.LocationId('stash','code',oldest),{location.id for location in changed.locations})
#         self.git('branch','same')
#         recreated,_=self.read_git(settings,previous=changed)
#         self.assertIn(capture.LocationId('branch','code','refs/heads/same'),recreated.delta(changed).added_locations)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_two_independent_checkouts_do_not_merge_equal_names_or_bytes_and_order_stashes_last
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Two independent checkouts do not merge equal names or bytes and order stashes last.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_two_independent_checkouts_do_not_merge_equal_names_or_bytes_and_order_stashes_last(self):
#         self.git('init','--initial-branch=main',cwd=self.artifact)
#         for root in (self.code,self.artifact):
#             self.write(root,'README.md','# Same bytes\n')
#             self.git('add','--all',cwd=root)
#             self.git('commit','-m','same public text',cwd=root)
#             self.write(root,'README.md','# Stashed bytes\n')
#             self.git('stash','push','-m','public stash',cwd=root)
#         result,_=self.read_git()
#         self.assertTrue(result.complete,result.diagnostics)
#         self.assertEqual([location.id.kind for location in result.locations],['disk','branch','branch','stash','stash'])
#         self.assertEqual(len(result.disk.files),2)
#         self.assertEqual({location.id.checkout for location in result.locations if location.id.kind=='branch'},
#                          {'code','artifact'})
#         self.assertTrue(all(len(location.files)==1 for location in result.locations if location.id.kind!='disk'))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_git_symlink_blobs_are_excluded_and_large_regular_blobs_are_not_truncated
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Git symlink blobs are excluded and large regular blobs are not truncated.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_git_symlink_blobs_are_excluded_and_large_regular_blobs_are_not_truncated(self):
#         large=b'# Full bytes\n'+b'x'*1200000+b'\n'
#         self.write(self.code,'large.md',large)
#         (self.code/'linked.md').symlink_to('large.md')
#         self.write(self.code,'excluded.md','# A regular filename\n')
#         self.commit()
#         result,calls=self.read_git(self.settings(artifact=False,scan={'skip_folders':['excluded.md']}))
#         self.assertTrue(result.complete,result.diagnostics)
#         for location in result.locations:
#             self.assertEqual({file.primary.path for file in location.files},{'large.md','excluded.md'})
#             self.assertEqual(next(file.source for file in location.files if file.primary.path=='large.md'),large)
#         self.assertTrue(any(args[0]=='cat-file' for args in calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_oversized_metadata_and_short_blob_leave_visible_incomplete_manifests
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Oversized metadata and short blob leave visible incomplete manifests.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_oversized_metadata_and_short_blob_leave_visible_incomplete_manifests(self):
#         self.write(self.code,'file.md','# Complete\n')
#         self.commit()
#         settings=self.settings(artifact=False)
#         first,_=self.read_git(settings)
#         def oversized(args,**options):
#             if args[0]=='for-each-ref':
#                 self.assertEqual(options['stdout_limit'],capture.GIT_METADATA_LIMIT)
#                 self.assertEqual(options['timeout_seconds'],capture.GIT_READ_SECONDS)
#                 return CompletedChild(0,b'x'*(capture.GIT_METADATA_LIMIT+1),b'',0)
#             return run_git(args,**options)
#         result=capture.capture_repository(settings,'fixture',_git=oversized)
#         self.assertFalse(result.complete)
#         self.assertEqual(result.delta(first).removed_locations,())
#         self.assertTrue(any(item.code=='git_output_limit' for item in result.diagnostics))
#         def short(args,**options):
#             response=run_git(args,**options)
#             if args[0]=='cat-file':
#                 return replace(response,stdout=response.stdout[:-1])
#             return response
#         result=capture.capture_repository(settings,'fixture',_git=short)
#         self.assertFalse(result.complete)
#         self.assertEqual(result.delta(first).removed,())
#         self.assertTrue(any(item.code=='git_blob' for item in result.diagnostics))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_sha256_git_object_ids_are_retained_and_captured_as_complete_bytes
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Sha256 git object ids are retained and captured as complete bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_sha256_git_object_ids_are_retained_and_captured_as_complete_bytes(self):
#         self.code=self.home/'sha256'
#         self.code.mkdir()
#         self.git('init','--object-format=sha256','--initial-branch=main')
#         self.write(self.code,'雪.md','# Exact SHA-256 repository\r\n')
#         self.commit()
#         oid=self.git('rev-parse','HEAD')
#         self.assertEqual(len(oid),64)
#         result,_=self.read_git(self.settings(artifact=False))
#         self.assertTrue(result.complete,result.diagnostics)
#         branch=next(location for location in result.locations if location.id.kind=='branch')
#         self.assertEqual(branch.commit,oid)
#         self.assertEqual(branch.files[0].source,b'# Exact SHA-256 repository\r\n')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_new_ancestor_ignore_file_and_changed_overlap_metadata_prevent_deletion
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: New ancestor ignore file and changed overlap metadata prevent deletion.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_new_ancestor_ignore_file_and_changed_overlap_metadata_prevent_deletion(self):
#         self.write(self.code,'docs/file.md','# Exact\n')
#         self.commit()
#         self.code=self.code/'docs'
#         settings=self.settings(artifact=False)
#         verify=capture._Capture.verify_disk
#         def changed_ancestor(current):
#             self.write(self.code.parent,'.gitignore','docs/\n')
#             verify(current)
#         with patch.object(capture._Capture,'verify_disk',changed_ancestor):
#             result,_=self.read_git(settings)
#         self.assertFalse(result.complete)
#         self.assertTrue(any(item.code=='changed_during_capture' for item in result.diagnostics))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_ignored_ignore_files_still_supply_rules_in_every_location
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Ignored ignore files still supply rules in every location.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ignored_ignore_files_still_supply_rules_in_every_location(self):
#         self.write(self.code,'.gitignore','.gitignore\n')
#         self.write(self.code,'nested/.gitignore','hidden.md\n')
#         self.write(self.code,'nested/hidden.md','# Must be excluded\n')
#         self.write(self.code,'nested/visible.md','# Must be read\n')
#         self.git('add','--force','.gitignore','nested/.gitignore','nested/hidden.md')
#         self.commit()
#         self.assertEqual(self.git('check-ignore','--no-index','nested/hidden.md'),'nested/hidden.md')
#         result,_=self.read_git(self.settings(artifact=False))
#         self.assertTrue(result.complete,result.diagnostics)
#         self.assertTrue(all([file.primary.path for file in location.files]==['nested/visible.md']
#                             for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_unselected_unaddressable_names_do_not_obstruct_selected_disk_or_git_files
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unselected unaddressable names do not obstruct selected disk or git files.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unselected_unaddressable_names_do_not_obstruct_selected_disk_or_git_files(self):
#         self.write(self.code,'unselected\\bytes.bin',b'not a selected source')
#         self.write(self.code,'visible.md','# Selected\n')
#         self.commit()
#         result,_=self.read_git(self.settings(artifact=False))
#         self.assertTrue(result.complete,result.diagnostics)
#         self.assertTrue(all([file.primary.path for file in location.files]==['visible.md']
#                             for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_unselected_non_utf8_git_tree_name_does_not_obstruct_selected_bytes
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unselected non utf8 git tree name does not obstruct selected bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unselected_non_utf8_git_tree_name_does_not_obstruct_selected_bytes(self):
#         self.write(self.code,'visible.md','# Visible disk source\n')
#         self.commit()
#         visible=self.git('hash-object','-w','--stdin',request=b'# Visible saved source\n')
#         unselected=self.git('hash-object','-w','--stdin',request=b'not selected bytes')
#         tree=self.git('mktree','-z',request=(b'100644 blob '+unselected.encode()+b'\tunselected-\xff.bin\0'+
#                                            b'100644 blob '+visible.encode()+b'\tvisible.md\0'))
#         commit=self.git('commit-tree',tree,'-m','public opaque-name tree')
#         self.git('update-ref','refs/heads/main',commit)
#         result,_=self.read_git(self.settings(artifact=False))
#         self.assertTrue(result.complete,result.diagnostics)
#         branch=next(location for location in result.locations if location.id.kind=='branch')
#         self.assertEqual(branch.files[0].source,b'# Visible saved source\n')
#         self.assertTrue(all([file.primary.path for file in location.files]==['visible.md']
#                             for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_ascii_ignorecase_matches_native_git_and_invalidates_cached_locations
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Ascii ignorecase matches native git and invalidates cached locations.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ascii_ignorecase_matches_native_git_and_invalidates_cached_locations(self):
#         self.git('config','core.ignorecase','false')
#         self.write(self.code,'.gitignore','HIDDEN.md\n[A-Z]ase.md\nÄ.md\n')
#         for path in ('hidden.md','case.md','ä.md','visible.md'):
#             self.write(self.code,path,'# Selected bytes\n')
#         self.commit()
#         settings=self.settings(artifact=False)
#         before,_=self.read_git(settings)
#         self.assertTrue(before.complete,before.diagnostics)
#         self.assertEqual({file.primary.path for file in before.disk.files},
#                          {'hidden.md','case.md','ä.md','visible.md'})
#         self.git('config','core.ignorecase','true')
#         self.assertEqual(self.git('check-ignore','--no-index','hidden.md','case.md'),'hidden.md\ncase.md')
#         after,_=self.read_git(settings,previous=before)
#         self.assertTrue(after.complete,after.diagnostics)
#         self.assertNotEqual(before.policy_hash,after.policy_hash)
#         self.assertTrue(all({file.primary.path for file in location.files}=={'ä.md','visible.md'}
#                             for location in after.locations))
#         self.assertTrue(all(not location.reused for location in after.locations))
#         self.git('config','--unset','core.ignorecase')
#         absent,_=self.read_git(settings,previous=after)
#         self.assertEqual(absent.policy_hash,before.policy_hash)
#         self.assertTrue(all({file.primary.path for file in location.files}==
#                             {'hidden.md','case.md','ä.md','visible.md'} for location in absent.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_ignorecase_fault_or_changed_final_policy_refuses_complete_reconciliation
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Ignorecase fault or changed final policy refuses complete reconciliation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ignorecase_fault_or_changed_final_policy_refuses_complete_reconciliation(self):
#         self.git('config','core.ignorecase','false')
#         self.write(self.code,'visible.md','# Selected\n')
#         self.commit()
#         settings=self.settings(artifact=False)
#         first,_=self.read_git(settings)
#         for value in (CompletedChild(128,b'',b'secret diagnostic',0), CompletedChild(0,b'invalid\n',b'',0)):
#             def failed(args,**options):
#                 return value if args[0]=='config' else run_git(args,**options)
#             result=capture.capture_repository(settings,'fixture',previous=first,_git=failed)
#             self.assertFalse(result.complete)
#             self.assertEqual(result.delta(first).removed,())
#             self.assertTrue(any(item.code=='git_policy' for item in result.diagnostics))
#             self.assertNotIn('secret',result.canonical_bytes().decode())
#         calls=0
#         def changed(args,**options):
#             nonlocal calls
#             result=run_git(args,**options)
#             if args[0]=='config':
#                 calls+=1
#                 if calls==2:
#                     return replace(result,stdout=b'true\n')
#             return result
#         raced=capture.capture_repository(settings,'fixture',previous=first,_git=changed)
#         self.assertFalse(raced.complete)
#         self.assertEqual(raced.delta(first).removed,())
#         self.assertTrue(any(item.code=='changed_during_capture' for item in raced.diagnostics))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_bracket_escapes_inverted_ranges_and_directory_globstar_match_native_git
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Bracket escapes inverted ranges and directory globstar match native git.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_bracket_escapes_inverted_ranges_and_directory_globstar_match_native_git(self):
#         selected=('a.md','b.md','c.md','z.md','-.md','].md','foo/bar.md','foo/x/bar.md')
#         for path in selected:
#             self.write(self.code,path,'# Complete document\n')
#         self.commit()
#         settings=self.settings(artifact=False)
#         cases={r'[\]].md':{'].md'}, r'[a\-c].md':{'a.md','-.md','c.md'},
#                '[z-a].md':{'z.md'}, r'foo\/bar.md':{'foo/bar.md'},
#                'foo/**/':{'foo/x/bar.md'}}
#         for ignorecase in ('false','true'):
#             self.git('config','core.ignorecase',ignorecase)
#             for pattern,expected in cases.items():
#                 with self.subTest(pattern=pattern,ignorecase=ignorecase):
#                     self.write(self.code,'.gitignore',pattern+'\r\n')
#                     self.git('add','--force','.gitignore')
#                     self.commit(pattern)
#                     native=set(self.git('check-ignore','--no-index','--',*selected).splitlines())
#                     self.assertEqual(native,expected)
#                     result,_=self.read_git(settings)
#                     self.assertTrue(result.complete,result.diagnostics)
#                     self.assertTrue(all({file.primary.path for file in location.files}==set(selected)-native
#                                         for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_literal_trailing_controls_and_space_escaping_match_native_git_bytes
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Literal trailing controls and space escaping match native git bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_literal_trailing_controls_and_space_escaping_match_native_git_bytes(self):
#         selected=('plain.md','tab.md\t','vtab.md\v','form.md\f','nbsp.md\u00a0','space.md ')
#         for path in selected:
#             self.write(self.code,path,'# Exact selected bytes\n')
#         self.write(self.code,'.gitignore',b'plain.md\r\n'+b'tab.md\t  \n'+b'vtab.md\v\n'+
#                    b'form.md\f\n'+'nbsp.md\u00a0\n'.encode()+b'space.md\\  \n')
#         self.git('add','--force','.')
#         self.commit()
#         settings=self.settings(artifact=False,scan={'document_endings':['.md','.md\t','.md\v','.md\f','.md\u00a0','.md ']})
#         # NUL-delimited output keeps literal whitespace and quotes separate
#         # from display formatting. All six native exclusions must agree.
#         native=self.git('check-ignore','--no-index','--stdin','-z',
#                         request=b'\0'.join(path.encode() for path in selected)+b'\0').split('\0')
#         self.assertEqual(set(native)-{''},set(selected))
#         result,_=self.read_git(settings)
#         self.assertTrue(result.complete,result.diagnostics)
#         self.assertTrue(all(not location.files for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_capture.py::TemporaryGitCaptureTests.test_casefold_preserves_native_bracket_literal_and_escaped_uppercase_rules
# Reason: Narrower case removed from this family after retaining test_bounded_git_failure_and_changed_final_inventory_preserve_disk_and_disable_removals, test_root_inside_checkout_honors_parent_ignore_rules_and_worktree_git_file, test_replacement_refs_cannot_substitute_bytes_under_an_unchanged_commit_identity, test_posix_bracket_classes_and_utf8_byte_wildcards_match_native_git. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Casefold preserves native bracket literal and escaped uppercase rules.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_casefold_preserves_native_bracket_literal_and_escaped_uppercase_rules(self):
#         self.git('config','core.ignorecase','true')
#         selected={'a.md','b.md','z.md','_.md','fallback.md'}
#         for path in selected:
#             self.write(self.code,path,'# Exact source\n')
#         self.commit()
#         settings=self.settings(artifact=False)
#         cases={'[A].md':set(),r'\A.md':set(),'[a].md':{'a.md'},
#                '[A-Z].md':{'a.md','b.md','z.md'}, '[a-Z].md':{'a.md'},
#                '[Z-a].md':{'a.md','z.md','_.md'}}
#         for pattern,expected in cases.items():
#             with self.subTest(pattern=pattern):
#                 self.write(self.code,'.gitignore',pattern+'\nfallback.md\n')
#                 self.git('add','--force','.gitignore')
#                 self.commit(pattern)
#                 native=set(self.git('check-ignore','--no-index',*sorted(selected)).splitlines())
#                 self.assertEqual(native,expected|{'fallback.md'})
#                 result,_=self.read_git(settings)
#                 self.assertTrue(result.complete,result.diagnostics)
#                 self.assertTrue(all({file.primary.path for file in location.files}==selected-native
#                                     for location in result.locations))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
