# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Real PID/stream checks and finite native-probe orchestration regressions.

Host-interpreter fixtures prove process mechanics, not the pinned distribution.
The real native packaged probe remains mandatory when a Build is qualified.
"""
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

from mycel_build import _packaged_release as packaged
from mycel_build._automatic import _sanitize_report
from mycel_build._core import BuildError, digest, json_bytes, read_json, seal_program
from mycel_build._process import run_group
from mycel_build._staging import create_stage
try:
    from .test_build import _frozen_fixture, _wheel_fixture
    from .test_offline_build import contract_fixture, report
    from .test_launcher_selection import LauncherFixture, tree_state
except ImportError:
    from test_build import _frozen_fixture, _wheel_fixture
    from test_offline_build import contract_fixture, report
    from test_launcher_selection import LauncherFixture, tree_state

import unittest

try:
    pass
    pass
    pass
except ImportError:
    pass


class PackagedReleaseTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
