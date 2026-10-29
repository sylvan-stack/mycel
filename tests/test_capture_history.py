# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured-store proofs for unchanged parsing and fresh acquisition guards."""
from dataclasses import replace
from hashlib import sha256
import os
from unittest.mock import patch

from psycopg.types.json import Jsonb
from mycel import _capture
from mycel._disk_reconciliation import DiskCaptureStore
from mycel._errors import MycelError
from mycel._located_reconciliation import LocatedCaptureStore

import unittest

import test_located_reconciliation as _fixture_module


class CaptureHistoryStoreTests(unittest.TestCase):
    # Reuse genuine fixture setup without inheriting/discovering its proofs.
    check_kind = "store"

    setUp = _fixture_module.LocatedReconciliationStoreTests.setUp
    configure = _fixture_module.LocatedReconciliationStoreTests.configure
    connect = _fixture_module.LocatedReconciliationStoreTests.connect
    git = _fixture_module.LocatedReconciliationStoreTests.git
    commit = _fixture_module.LocatedReconciliationStoreTests.commit
    initialize = _fixture_module.LocatedReconciliationStoreTests.initialize
    state = _fixture_module.LocatedReconciliationStoreTests.state

    def populate(self, *, git=True):
        (self.artifact / 'guide.md').write_bytes(
            b'---\nrole: authored\nextra: !!set {beta: null, alpha: null}\n'
            b'binary: !!binary YWJj\nnumber: .nan\n'
            b'unknown_nul: "malformed\\0ref"\nunknown_surrogate: "\\uD800"\n'
            b'"unknown\\0key": "\\uDFFF"\n---\n# Guide\nOriginal body.\n')
        self.source = self.code / 'module.py'
        self.source.write_bytes(b'def value():\n    return 1\n')
        if git:
            self.git('init', '--initial-branch=fixture-main')
            self.commit()
            self.git('branch', 'feature')
            self.source.write_bytes(b'def value():\n    return 2\n')
            self.git('stash', 'push', '--message', 'Saved')


# Archived complete imports; restore needed names in their original scope, not at this file tail.
