# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import tempfile


import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = runpy.run_path(str(ROOT / "scripts/sync_guides.py"))


class GuideCopyTests(unittest.TestCase):

    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_guide_copies.py::GuideCopyTests.test_every_repository_guide_has_a_portable_corpus_copy
# Reason: Duplicates the full write/check path in the CLI case and freezes the incidental count of 21 guides.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_guide_copies.py
# Retained evidence at review: test_explicit_cli_checks_every_selected_pair_and_refuses_drift plus independent link-projection and safe-write cases remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_every_repository_guide_has_a_portable_corpus_copy(self):
#         self.assertEqual(len(SYNC["GUIDES"]), 21)
#         self.assertEqual(len(set(SYNC["GUIDES"])), 21)
#         with tempfile.TemporaryDirectory() as directory:
#             corpus = Path(directory)
#             SYNC["write_copies"](ROOT / "docs", corpus)
#             self.assertEqual(SYNC["check_copies"](ROOT / "docs", corpus), [])
#             self.assertEqual(len(list(corpus.glob("*.md"))), 21)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
