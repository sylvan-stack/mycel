"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_guide_copies as _support
from test_guide_copies import (Path ,SYNC ,os ,tempfile)


class GuideCopyTests(_support.GuideCopyTests):


# TEST-TIER-BEGIN tests/test_guide_copies.py::GuideCopyTests.test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime
    def test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            docs, corpus = Path(directory) / "docs", Path(directory) / "tools"
            docs.mkdir()
            corpus.mkdir()
            (docs / "activity.md").write_text("# Current\n", encoding="utf-8")
            outside = Path(directory) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            before = outside.read_bytes(), outside.stat().st_mtime_ns
            copy = corpus / "mycel-2-activity.md"
            os.link(outside, copy)
            SYNC["write_copies"](docs, corpus, ("activity",))
            self.assertEqual(before, (outside.read_bytes(), outside.stat().st_mtime_ns))
            self.assertEqual(SYNC["check_copies"](docs, corpus, ("activity",)), [])
            self.assertNotEqual(copy.stat().st_ino, outside.stat().st_ino)
            self.assertEqual(set(corpus.iterdir()), {copy})
# TEST-TIER-END tests/test_guide_copies.py::GuideCopyTests.test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_guide_copies.py::GuideCopyTests.test_projection_keeps_prose_exact_and_rewrites_only_local_guide_links
# Reason: Narrower case removed from this family after retaining test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Projection keeps prose exact and rewrites only local guide links.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_guide_copies.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_projection_keeps_prose_exact_and_rewrites_only_local_guide_links(self):
#         original = ("# Guide\n\n[read](reading.md#exact) [cmd](command-line.md) "
#                     "[check](./checks.md) [other](./other.md) "
#                     "[remote](https://example.test/reading.md)\n"
#                     "`pending` remains a real reply state.\n")
#         expected = ("---\nrole: authored\n---\n# Guide\n\n"
#                     "[read](mycel-2-reading.md#exact) [cmd](mycel-2.md) "
#                     "[check](mycel-2-checks.md) [other](./other.md) "
#                     "[remote](https://example.test/reading.md)\n"
#                     "`pending` remains a real reply state.\n")
#         self.assertEqual(SYNC["render_corpus_guide"](original), expected)
#         self.assertEqual(SYNC["render_corpus_guide"](expected), expected)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_guide_copies.py::GuideCopyTests.test_check_reports_missing_and_changed_pairs_without_writing
# Reason: Narrower case removed from this family after retaining test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Check reports missing and changed pairs without writing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_guide_copies.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_check_reports_missing_and_changed_pairs_without_writing(self):
#         with tempfile.TemporaryDirectory() as directory:
#             docs, corpus = Path(directory) / "docs", Path(directory) / "tools"
#             docs.mkdir()
#             corpus.mkdir()
#             (docs / "activity.md").write_text("# Current\n", encoding="utf-8")
#             (docs / "capture.md").write_text("# Capture\n", encoding="utf-8")
#             changed = corpus / "mycel-2-activity.md"
#             changed.write_text("# Old\n", encoding="utf-8")
#             before = changed.read_bytes(), changed.stat().st_mtime_ns
#             faults = SYNC["check_copies"](docs, corpus, ("activity", "capture", "drifts"))
#             self.assertEqual(faults, ["activity: corpus copy differs",
#                                       "capture: corpus copy is missing",
#                                       "drifts: original is missing"])
#             self.assertEqual(before, (changed.read_bytes(), changed.stat().st_mtime_ns))
#             self.assertEqual(set(p.name for p in corpus.iterdir()), {changed.name})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_guide_copies.py::GuideCopyTests.test_explicit_cli_checks_every_selected_pair_and_refuses_drift
# Reason: Narrower case removed from this family after retaining test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Explicit cli checks every selected pair and refuses drift.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_guide_copies.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_explicit_cli_checks_every_selected_pair_and_refuses_drift(self):
#         with tempfile.TemporaryDirectory() as directory:
#             corpus = Path(directory)
#             args = ["--corpus", directory, "--docs", str(ROOT / "docs")]
#             with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
#                 self.assertEqual(SYNC["main"](["check", *args]), 1)
#                 self.assertEqual(SYNC["main"](["write", *args]), 0)
#                 self.assertEqual(SYNC["main"](["check", *args]), 0)
#                 (corpus / "mycel-2-capture.md").write_text("# Obsolete\n", encoding="utf-8")
#                 self.assertEqual(SYNC["main"](["check", *args]), 1)
#                 self.assertEqual(SYNC["main"](["check", *args, "--guide", "activity"]), 0)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_guide_copies.py::GuideCopyTests.test_write_validates_originals_before_replacing_and_refuses_symbolic_links
# Reason: Narrower case removed from this family after retaining test_copy_replacement_preserves_hard_linked_outside_bytes_and_mtime. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Write validates originals before replacing and refuses symbolic links.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_guide_copies.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_write_validates_originals_before_replacing_and_refuses_symbolic_links(self):
#         with tempfile.TemporaryDirectory() as directory:
#             docs, corpus = Path(directory) / "docs", Path(directory) / "tools"
#             docs.mkdir()
#             corpus.mkdir()
#             (docs / "activity.md").write_text("# Current\n", encoding="utf-8")
#             copy = corpus / "mycel-2-activity.md"
#             copy.write_text("# Old\n", encoding="utf-8")
#             with self.assertRaises(FileNotFoundError):
#                 SYNC["write_copies"](docs, corpus, ("activity", "capture"))
#             self.assertEqual(copy.read_text(), "# Old\n")
#             copy.unlink()
#             outside = Path(directory) / "outside.md"
#             outside.write_text("# Outside\n", encoding="utf-8")
#             copy.symlink_to(outside)
#             with self.assertRaisesRegex(ValueError, "symbolic link"):
#                 SYNC["write_copies"](docs, corpus, ("activity",))
#             self.assertEqual(outside.read_text(), "# Outside\n")
# LOW-TIER-SOURCE-END
# LOW-TIER-END
