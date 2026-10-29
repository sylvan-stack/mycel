"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_git_correspondence as _support
from test_git_correspondence import (
    CompletedChild,
    FileAlias,
    GitCorrespondenceTests,
    MycelError,
    Path,
    correspondence,
    os,
    patch,
    replace,
    run_git,
    subprocess,
    tempfile,
    unittest,
)


class GitCorrespondenceTests(_support.GitCorrespondenceTests):
# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_complete_rename_bytes_are_checked_and_the_checkout_is_unchanged
    def test_complete_rename_bytes_are_checked_and_the_checkout_is_unchanged(self):
        before, after = self.rename()
        head, status = self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')
        plan = correspondence.build_correspondences((before, after))
        peers = plan.peers({after.place.logical}, after.source)
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0][0], before)
        self.assertEqual(peers[0][1][0].similarity, 100)
        self.assertEqual(plan, correspondence.build_correspondences((after, before)))
        self.assertEqual((self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')), (head, status))
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_complete_rename_bytes_are_checked_and_the_checkout_is_unchanged

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_equal_copies_and_uncommitted_text_do_not_supply_identity
    def test_equal_copies_and_uncommitted_text_do_not_supply_identity(self):
        raw = b'# Guide\nExact text.\n'
        (self.base / 'original.md').write_bytes(raw)
        first = self.commit()
        (self.base / 'copied.md').write_bytes(raw)
        second = self.commit()
        before, after = self.snapshot(first, 'original.md', raw), self.snapshot(second, 'copied.md', raw)
        self.assertEqual(correspondence.build_correspondences((before, after)).renames, ())
        before, after = self.rename()
        plan = correspondence.build_correspondences((before, after))
        self.assertEqual(plan.peers({after.place.logical}, b'# Guide\nUncommitted different text.\n'), ())
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_equal_copies_and_uncommitted_text_do_not_supply_identity

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_changed_endpoint_bytes_and_retargeted_checkout_scope_are_refused
    def test_changed_endpoint_bytes_and_retargeted_checkout_scope_are_refused(self):
        before, after = self.rename()
        with self.assertRaises(MycelError):
            correspondence.build_correspondences((replace(before, source=b'wrong complete bytes'), after))
        with self.assertRaises(MycelError):
            correspondence.build_correspondences((before, replace(after,
                place=replace(after.place, identity=(after.place.identity[0], after.place.identity[1] + 1)))))
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_changed_endpoint_bytes_and_retargeted_checkout_scope_are_refused

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_malformed_or_truncated_rename_inventory_is_refused
    def test_malformed_or_truncated_rename_inventory_is_refused(self):
        before, after = self.rename()
        for raw in (b'R100\0old name.md\0', b'R100\0old name.md\0new name.md',
                    b'R101\0old name.md\0new name.md\0', b'R100\0old\xff.md\0new name.md\0'):
            def broken(arguments, **kwargs):
                return CompletedChild(0, raw, b'', 0) if arguments[0] == 'diff' else run_git(arguments, **kwargs)
            with patch.object(correspondence, 'run_git', side_effect=broken):
                with self.assertRaises(MycelError):
                    correspondence.build_correspondences((before, after))
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_malformed_or_truncated_rename_inventory_is_refused

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_large_regular_blobs_are_verified_with_their_complete_finite_bound
    def test_large_regular_blobs_are_verified_with_their_complete_finite_bound(self):
        before, after = self.rename(raw=b'# Guide\n' + b'complete line\n' * 100000)
        with patch.object(correspondence, 'run_git', wraps=run_git) as reader:
            plan = correspondence.build_correspondences((before, after))
        self.assertEqual(len(plan.renames), 1)
        blobs = [call for call in reader.call_args_list if call.args[0][:2] == ('cat-file', '-p')]
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0].kwargs['stdout_limit'], len(before.source))
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_large_regular_blobs_are_verified_with_their_complete_finite_bound

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_edited_rename_uses_the_padded_git_score_and_both_exact_blobs
    def test_edited_rename_uses_the_padded_git_score_and_both_exact_blobs(self):
        original = b'# Guide\n' + b'Original complete paragraph.\n' * 20
        (self.base / 'old.md').write_bytes(original)
        first = self.commit()
        changed = original + b'An added exact paragraph.\n'
        (self.base / 'new.md').write_bytes(changed)
        (self.base / 'old.md').unlink()
        second = self.commit()
        before, after = self.snapshot(first, 'old.md', original), self.snapshot(second, 'new.md', changed)
        plan = correspondence.build_correspondences((before, after))
        self.assertEqual(len(plan.renames), 1)
        self.assertLess(plan.renames[0].similarity, 100)
        self.assertEqual(plan.peers({after.place.logical}, changed)[0][0], before)
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_edited_rename_uses_the_padded_git_score_and_both_exact_blobs

# TEST-TIER-BEGIN tests/test_git_correspondence.py::GitCorrespondenceTests.test_equal_text_on_unrelated_local_histories_does_not_make_a_rename
    def test_equal_text_on_unrelated_local_histories_does_not_make_a_rename(self):
        raw = b'# Guide\nUnrelated exact text.\n'
        (self.base / 'old.md').write_bytes(raw)
        first = self.commit()
        self.git('checkout', '--orphan', 'unrelated')
        self.git('rm', '--cached', 'old.md')
        (self.base / 'old.md').unlink()
        (self.base / 'new.md').write_bytes(raw)
        second = self.commit()
        before, after = self.snapshot(first, 'old.md', raw), self.snapshot(second, 'new.md', raw)
        self.assertIn('R100', self.git('diff', '-M', '--name-status', first, second))
        self.assertEqual(correspondence.build_correspondences((before, after)).renames, ())
# TEST-TIER-END tests/test_git_correspondence.py::GitCorrespondenceTests.test_equal_text_on_unrelated_local_histories_does_not_make_a_rename
