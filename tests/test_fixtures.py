# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Acceptance for private feature-check helpers, separate from live providers."""

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
