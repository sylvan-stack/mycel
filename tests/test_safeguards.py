# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Executable boundary proofs; all programs and repositories are local fixtures."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from unittest.mock import patch

from mycel._errors import MycelError
from mycel._safeguards import (
    ChildProcessFailure, InvocationPolicy, SYSTEM_PATH, model_call_allowed,
    require_model_call, resolve_command, run_child, run_git, run_model_child,
    validate_read_only_git_args,
)


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
