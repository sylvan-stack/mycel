# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = runpy.run_path(str(ROOT / "scripts/sync_guides.py"))


class GuideCopyTests(unittest.TestCase):

    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
