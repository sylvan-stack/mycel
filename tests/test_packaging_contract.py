# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Complete staged metadata and terminal registry immutability proofs."""
import io
from pathlib import Path
import tarfile
import tempfile
from unittest.mock import patch

from mycel_build._core import (BuildError, atomic_json, digest,
                               json_bytes, read_json, seal_program, validate_manifest)
from mycel_build._registry import allocate, read_record, update_staging
from mycel_build._staging import check_input_manifest, create_stage
try:
    from .test_build import SOURCE, _frozen_fixture, _wheel_fixture
except ImportError:
    from test_build import SOURCE, _frozen_fixture, _wheel_fixture

import unittest

try:
    pass
except ImportError:
    pass


class PackagingContractTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
