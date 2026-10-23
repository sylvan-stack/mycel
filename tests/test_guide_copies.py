from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import runpy
import tempfile
import unittest

from mycel._coverage import proves


ROOT = Path(__file__).resolve().parents[1]
SYNC = runpy.run_path(str(ROOT / "scripts/sync_guides.py"))


class GuideCopyTests(unittest.TestCase):
    @proves("MYC-0.12")
    def test_every_repository_guide_has_a_portable_corpus_copy(self):
        self.assertEqual(len(SYNC["GUIDES"]), 21)
        self.assertEqual(len(set(SYNC["GUIDES"])), 21)
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory)
            SYNC["write_copies"](ROOT / "docs", corpus)
            self.assertEqual(SYNC["check_copies"](ROOT / "docs", corpus), [])
            self.assertEqual(len(list(corpus.glob("*.md"))), 21)

    @proves("MYC-0.12")
    def test_projection_keeps_prose_exact_and_rewrites_only_local_guide_links(self):
        original = ("# Guide\n\n[read](reading.md#exact) [cmd](command-line.md) "
                    "[check](./checks.md) [other](./other.md) "
                    "[remote](https://example.test/reading.md)\n"
                    "`pending` remains a real reply state.\n")
        expected = ("---\nrole: authored\n---\n# Guide\n\n"
                    "[read](mycel-2-reading.md#exact) [cmd](mycel-2.md) "
                    "[check](mycel-2-checks.md) [other](./other.md) "
                    "[remote](https://example.test/reading.md)\n"
                    "`pending` remains a real reply state.\n")
        self.assertEqual(SYNC["render_corpus_guide"](original), expected)
        self.assertEqual(SYNC["render_corpus_guide"](expected), expected)

    @proves("MYC-0.12")
    def test_check_reports_missing_and_changed_pairs_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            docs, corpus = Path(directory) / "docs", Path(directory) / "tools"
            docs.mkdir()
            corpus.mkdir()
            (docs / "activity.md").write_text("# Current\n", encoding="utf-8")
            (docs / "capture.md").write_text("# Capture\n", encoding="utf-8")
            changed = corpus / "mycel-2-activity.md"
            changed.write_text("# Old\n", encoding="utf-8")
            before = changed.read_bytes(), changed.stat().st_mtime_ns
            faults = SYNC["check_copies"](docs, corpus, ("activity", "capture", "drifts"))
            self.assertEqual(faults, ["activity: corpus copy differs",
                                      "capture: corpus copy is missing",
                                      "drifts: original is missing"])
            self.assertEqual(before, (changed.read_bytes(), changed.stat().st_mtime_ns))
            self.assertEqual(set(p.name for p in corpus.iterdir()), {changed.name})

    @proves("MYC-0.12")
    def test_explicit_cli_checks_every_selected_pair_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory)
            args = ["--corpus", directory, "--docs", str(ROOT / "docs")]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(SYNC["main"](["check", *args]), 1)
                self.assertEqual(errors.getvalue().count("corpus copy is missing"), 21)
                self.assertEqual(SYNC["main"](["write", *args]), 0)
                self.assertEqual(SYNC["main"](["check", *args]), 0)
                (corpus / "mycel-2-capture.md").write_text("# Obsolete\n", encoding="utf-8")
                self.assertEqual(SYNC["main"](["check", *args]), 1)
                self.assertEqual(SYNC["main"](["check", *args, "--guide", "activity"]), 0)

    @proves("MYC-0.12")
    def test_write_validates_originals_before_replacing_and_refuses_symbolic_links(self):
        with tempfile.TemporaryDirectory() as directory:
            docs, corpus = Path(directory) / "docs", Path(directory) / "tools"
            docs.mkdir()
            corpus.mkdir()
            (docs / "activity.md").write_text("# Current\n", encoding="utf-8")
            copy = corpus / "mycel-2-activity.md"
            copy.write_text("# Old\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                SYNC["write_copies"](docs, corpus, ("activity", "capture"))
            self.assertEqual(copy.read_text(), "# Old\n")
            copy.unlink()
            outside = Path(directory) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            copy.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                SYNC["write_copies"](docs, corpus, ("activity",))
            self.assertEqual(outside.read_text(), "# Outside\n")

    @proves("MYC-0.12")
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
