# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Real PostgreSQL proof of the foundation gate, not product-schema acceptance."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from unittest.mock import patch

from mycel._coverage import CoverageError, PostgresBackend, disposable_store, run_checks


import tomllib
import unittest
from urllib.parse import urlsplit


def initialize_probe(backend, settings_file):
    """Explicit test bootstrap until feature checks supply Mycel's initializer."""
    settings = tomllib.loads(settings_file.read_text())
    if set(settings) != {"store"} or set(settings["store"]) != {"address"}:
        raise AssertionError("fixture copied settings unrelated to the test store")
    database = urlsplit(settings["store"]["address"]).path.removeprefix("/")
    backend.query(database, "CREATE TABLE foundation_probe (value text NOT NULL)")


class StoreGateTests(unittest.TestCase):
    check_kind = "store"

    initialize_store = staticmethod(initialize_probe)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
