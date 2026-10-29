# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Portable command-audit regressions; no owner corpus or installed CLI needed."""
from contextlib import redirect_stderr, redirect_stdout
import io
from subprocess import CompletedProcess
import tempfile
from unittest.mock import patch


import runpy
import unittest
from pathlib import Path

AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                          "scripts/check_hub_commands.py"), run_name="hub_audit")
HELP = {"program": "mycel", "options": ["--help"], "commands": [
    {"name": "search", "available": True, "rawArguments": False,
     "options": ["--help", "--repo <name>", "--no-fresh"]},
    {"name": "grep", "available": True, "rawArguments": True, "options": []},
    {"name": "future", "available": False, "rawArguments": False, "options": []},
]}


class HubCommandTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
