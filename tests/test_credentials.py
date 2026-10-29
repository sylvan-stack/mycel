# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Private credential proofs with public values and local child stand-ins."""
import io
import os
import subprocess
import threading
import time
from unittest.mock import patch

from mycel._cli import run
from mycel._credentials import (
    CREDENTIAL_STDERR_LIMIT, CREDENTIAL_STDOUT_LIMIT, SECURITY,
    CredentialUnavailable, Credentials, Secret, StoreTarget,
    configured_store_address,
)
from mycel._errors import MycelError
from mycel._safeguards import (
    ChildProcessFailure, CompletedChild, InvocationPolicy,
    run_git, run_model_child,
)


import json
import sys
import tempfile
import unittest
from pathlib import Path

from mycel._safeguards import (
    CompletedChild,
)
from mycel._settings import load_settings

ADDRESS = "postgresql://fixture@localhost:5432/fixture?sslmode=prefer"
SENTINEL = "public-credential-sentinel"


def completed(stdout=b"public-key\n", *, returncode=0, stderr=b""):
    return CompletedChild(returncode, stdout, stderr, 0.0)


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.toml"

    def settings(self, extra="", *, address=ADDRESS):
        self.config.write_text("[store]\naddress = " + json.dumps(address) + "\n" + extra)
        return load_settings(path=self.config, home=self.root)

    def script(self, body):
        path = self.root / "credential-command"
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o700)
        return path


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.toml"
        self.config.write_text("[store]\naddress = 'postgresql://fixture@localhost/fixture'\n")


# Archived complete imports; restore needed names in their original scope, not at this file tail.
