# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"


class CliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


        # Scope expansion is delegated to the settings feature; the CLI
        # retains the unresolved cwd request instead of selecting a default.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
