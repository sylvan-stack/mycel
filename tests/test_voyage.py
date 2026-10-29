# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Voyage acceptance using fictional credentials, service and HTTPS sockets."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn

from mycel._credentials import Credentials
from mycel._embedding_plan import load_tokenizer, plan_batches, plan_chunk
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._settings import load_settings
from mycel._voyage import (
    CommitReceipt,
    HTTPResult,
    ProviderFailure,
    VoyageClient,
)

KEY = "public-fixture-credential-sentinel"


class VoyageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        path = self.root / "config.toml"
        path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n')
        self.settings = load_settings(path=path)
        self.key_reads = []
        self.requests = []
        self.waits = []
        self.writes = []
        self.failures = []
        self.service = EmbeddingStandIn(self.tokenizer.counts)

    def credentials(self, policy, *, present=True):
        def read(argv, **kwargs):
            self.key_reads.append(argv)
            return CompletedChild(0 if present else 1, (KEY + "\n").encode(), KEY.encode(), 0.0)
        return Credentials(self.settings, policy, home=self.root, _runner=read)

    def transport(self, body, key, *, deadline, cancelled):
        self.assertEqual(key.reveal(), KEY)
        request = json.loads(body)
        self.assertNotIn(KEY, body.decode())
        self.requests.append((body, deadline))
        try:
            result = self.service.request(request)
            return HTTPResult(200, json.dumps(result).encode())
        except EmbeddingFixtureFailure as error:
            status = {"rate_limit": 429, "server": 503, "authentication": 401,
                      "authorization": 403, "missing_model": 404, "content": 413}.get(error.kind)
            if status:
                return HTTPResult(status, json.dumps({"detail": KEY}).encode())
            raise ProviderFailure(error.kind)

    def client(self, *, policy=None, present=True, attempts=5, transport=None, cancelled=None, waiter=None):
        policy = policy or InvocationPolicy("embed")
        return VoyageClient(self.credentials(policy, present=present), policy, tokenizer=self.tokenizer,
                            attempts=attempts, _transport=transport or self.transport,
                            cancelled=cancelled, _waiter=waiter or (lambda seconds, check: self.waits.append(seconds)))

    def batches(self, texts=("one", "two", "three"), *, batch_inputs=64):
        local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=batch_inputs))
        plans = [plan_chunk("repo", f"chunk-{index}", "version", text, place_line="doc.md › Heading",
                            kind="document", dimensions=256, tokenizer=local) for index, text in enumerate(texts)]
        return plan_batches(plans, tokenizer=local)

    def commit(self, writes):
        self.writes.append(writes)
        return CommitReceipt(tuple(write.part for write in writes))

    def record(self, failures):
        self.failures.extend(failures)
        return CommitReceipt(tuple(failure.part for failure in failures))

    def embed(self, client, batches=None, commit=None):
        return client.embed_repository("repo", self.batches() if batches is None else batches,
                                       commit=commit or self.commit, record_failures=self.record)



# Archived complete imports; restore needed names in their original scope, not at this file tail.
