# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Executable boundary proofs; all programs and repositories are local fixtures."""

import sys
import unittest

from mycel._safeguards import (
    run_child,
)


class ModelPolicyTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class ChildBoundaryTests(unittest.TestCase):
    def child(self, code, request=b"", **kwargs):
        return run_child([sys.executable, "-c", code], request, timeout_seconds=kwargs.pop("timeout_seconds", 5), **kwargs)


class GitBoundaryTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
