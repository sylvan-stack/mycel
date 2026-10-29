# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public scoped embed acceptance uses the gate's disposable PostgreSQL only."""
from dataclasses import replace

from mycel._activity import MutationActivity
from mycel._cli import parse, run
from mycel._embedding_store import (EmbeddingCounts, EmbeddingStore, PreparedRepository,
                                   RetainedVersion, VersionEmbedding)
from mycel._errors import MycelError
from mycel._locks import atomic_transaction, operation_guard
from mycel._settings import load_settings
try:
    from .test_declared_refs import seed_document
    from .test_refs import store_state
except ImportError:
    from test_declared_refs import seed_document
    from test_refs import store_state

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn

from mycel._cli import run
from mycel._credentials import Secret
from mycel._embedding_plan import load_tokenizer
from mycel._embedding_store import EmbeddingStore
from mycel._voyage import HTTPResult, ProviderFailure, VoyageClient

try:
    pass
    pass
except ImportError:
    pass


def invoke(config, args):
    output, diagnostics = StringIO(), StringIO()
    with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}):
        status = run(args, stdout=output, stderr=diagnostics)
    return status, json.loads(output.getvalue()), diagnostics.getvalue()


class EmbedCliTests(unittest.TestCase):
    @contextmanager
    def dry_run_boundary(self):
        """Only scope/reply behavior is mocked; no PostgreSQL claim is made."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.a]\nenabled=true\n[repos.b]\nenabled=true\n')
            before = config.read_bytes()
            writer = SimpleNamespace(model="voyage-code-4", dimensions=1024, tokenizer=load_tokenizer(), prepare=Mock())
            @contextmanager
            def connected(invocation, *, operation):
                self.assertEqual((invocation.command, operation), ("embed", "read"))
                yield object(), SimpleNamespace(index_generation="public-fixture-generation")
            with patch("mycel._cli.invocation_store", connected), \
                    patch("mycel._embed.EmbeddingStore", return_value=writer), \
                    patch("mycel._embed.VoyageClient") as provider, \
                    patch("mycel._credentials.Credentials.require_embedding_key") as key, \
                    patch("mycel._activity.MutationActivity.session") as activity:
                yield config, writer
                provider.assert_not_called()
                key.assert_not_called()
                activity.assert_not_called()
            self.assertEqual(before, config.read_bytes())


class EmbedStoreTests(unittest.TestCase):
    check_kind = "store"

    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def configured(self, root, *, repositories=("a", "b"), disabled=("disabled",), organization=False):
        config = root / "config.toml"
        config.write_text('[store]\naddress=' + json.dumps(self.store_fixture.backend.address(self.store_fixture.database)) +
            '\n[embedding]\nattempts=1\n' + ''.join(
                '[repos.' + name + ']\nenabled=' + str(name in repositories).lower() +
                '\ncode_root=' + json.dumps(str(root / "org" / name)) + '\n'
                for name in (*repositories, *disabled)) +
            ('[organizations.group]\nroot=' + json.dumps(str(root / "org")) + '\nartifact_root=' +
             json.dumps(str(root / "docs")) + '\n' if organization else ''))
        for name in (*repositories, *disabled):
            (root / "org" / name / ".git").mkdir(parents=True)
        return config

    @contextmanager
    def product(self, connection, *, tokenizer=None, service=None, transport=None, build=None):
        tokenizer = tokenizer or self.tokenizer
        service = service or EmbeddingStandIn(tokenizer.counts, input_cap=tokenizer.catalog.input_token_cap,
                    batch_cap=tokenizer.catalog.batch_token_cap, inputs_cap=tokenizer.catalog.batch_input_cap)
        def fixture_transport(body, secret, **kwargs):
            try:
                response = service.request(json.loads(body))
            except EmbeddingFixtureFailure as failure:
                raise ProviderFailure(failure.kind) from None
            return HTTPResult(200, json.dumps(response).encode(), {})
        def client(credentials, policy, **kwargs):
            return VoyageClient(credentials, policy, **kwargs, _transport=transport or fixture_transport,
                                _waiter=lambda *args: None)
        @contextmanager
        def connected(credentials):
            self.assertEqual(credentials.store_target().address,
                             self.store_fixture.backend.address(self.store_fixture.database))
            yield connection
        with patch("mycel._database.store_connection", connected), \
                patch("mycel._embed.EmbeddingStore", side_effect=lambda *args, **kwargs: EmbeddingStore(
                    *args, **kwargs, tokenizer=tokenizer)), \
                patch("mycel._embed.VoyageClient", side_effect=client), \
                patch("mycel._credentials.Credentials.require_embedding_key", return_value=Secret("public-fixture-key")), \
                patch("mycel._build_identity.current_build", return_value=build):
            yield service


# Archived complete imports; restore needed names in their original scope, not at this file tail.
