# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Jev contract proofs using public stand-ins; no provider or real credential."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_classification_payload import fixture, reviewed

from mycel._classification_payload import LABELS
from mycel._credentials import Credentials
from mycel._jev import HTTPResult, JevClient
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._settings import load_settings

KEY = "public-jev-credential-sentinel"


def response(*, label="still_supported", top=0.8, confidence=0.7, model="jev-1.13.0"):
    probabilities = {member: 0.1 for member in LABELS}
    probabilities[label] = top
    return {"model": model, "answers": {"dependency": {"type": "choice", "choice": label,
            "probabilities": probabilities, "confidence": confidence}},
            "usage": {"input_tokens": 100, "output_tokens": 8}}


def http(value=None, *, status=200, body=None, headers=None):
    return HTTPResult(status, body if body is not None else json.dumps(value or response()).encode(), headers or {})


class JevTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        path = self.root / "config.toml"
        path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n')
        self.settings = load_settings(path=path, home=self.root)
        self.key_reads, self.requests, self.guards = [], [], []
        self.decision = reviewed(fixture()[2])
        # Every network test explicitly installs a fake HTTPSConnection.
        self.network = patch("http.client.HTTPSConnection",
                             side_effect=AssertionError("Jev proofs cannot reach a provider"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def credentials(self, policy, *, present=True, runner=None):
        def read(argv, **kwargs):
            self.key_reads.append((argv, kwargs))
            return CompletedChild(0 if present else 1, (KEY + "\n").encode(), KEY.encode(), 0.0)
        return Credentials(self.settings, policy, home=self.root, _runner=runner or read)

    def transport(self, body, key, **kwargs):
        self.assertEqual(key.reveal(), KEY)
        self.requests.append((body, kwargs))
        return http()

    def client(self, *, limits=None, policy=None, present=True, transport=None, runner=None):
        policy = policy or InvocationPolicy("classify")
        return JevClient(self.credentials(policy, present=present, runner=runner), policy,
                         limits=limits, _transport=transport or self.transport)

    def guard(self):
        self.guards.append(len(self.key_reads))

    def classify(self, client=None, decision=None, **kwargs):
        return (client or self.client()).classify(decision or self.decision,
            deadline=kwargs.pop("deadline", time.monotonic() + 2),
            before_call=kwargs.pop("before_call", self.guard), **kwargs)



# Archived complete imports; restore needed names in their original scope, not at this file tail.
