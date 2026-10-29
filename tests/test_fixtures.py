# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Acceptance for private feature-check helpers, separate from live providers."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import json
import shutil
import tempfile

from mycel._cli import run
from mycel._coverage import CoverageError, require_check_database
from mycel._settings import load_settings
from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn


import importlib.util
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


class ServiceFixtureTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RunnerFixtureTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def source_runner():
        source = Path(__file__).resolve().parents[1] / "scripts" / "run_checks.py"
        name = "_mycel_runner_fixture"
        specification = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(specification)
        with patch.dict(os.environ), patch.object(sys, "path", list(sys.path)):
            sys.modules[name] = module
            try:
                specification.loader.exec_module(module)
                yield module
            finally:
                sys.modules.pop(name, None)


class RepositoryFixtureTests(unittest.TestCase):
    # The backend runs actual product init for this fixture. These checks remain
    # store-backed and cannot qualify against an in-memory substitute.

    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
