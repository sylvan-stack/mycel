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
