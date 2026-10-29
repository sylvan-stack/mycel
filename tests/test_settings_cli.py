# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Settings refusal and diagnostics at the actual command boundary."""
import io
import json
import tempfile
from unittest.mock import patch

from mycel._cli import Result, StreamedResult, run
from mycel._settings import load_settings


import os
import subprocess
import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
VALID = '[store]\naddress = "postgresql://check@localhost:5432/fixture"\n'


class SettingsCliTests(unittest.TestCase):
    def invoke(self, root, args, *, content=None, extra=None, input=b""):
        config = root / "config.toml"
        if content is not None:
            config.write_text(content)
        environment = {"HOME": str(root), "PATH": os.defpath,
                       "PYTHONPATH": str(SOURCE), "PYTHONDONTWRITEBYTECODE": "1",
                       "MYCEL_CONFIG": str(config)}
        environment.update(extra or {})
        unit_boundary = ("from mycel._coverage import no_network\n"
                         "from mycel._cli import main\n"
                         "with no_network():\n raise SystemExit(main())\n")
        return subprocess.run([sys.executable, "-c", unit_boundary, *args],
                              env=environment, cwd=root, input=input,
                              capture_output=True, timeout=5)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
