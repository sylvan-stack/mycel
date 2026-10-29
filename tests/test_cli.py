# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
import io
import json
import os
import signal
import subprocess
import sys
import tempfile

from mycel._cli import Invocation, Result, StreamedResult, parse, run
from mycel._errors import ErrorCode, MycelError

import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"


class CliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


        # Scope expansion is delegated to the settings feature; the CLI
        # retains the unresolved cwd request instead of selecting a default.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
