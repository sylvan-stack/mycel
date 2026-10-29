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
