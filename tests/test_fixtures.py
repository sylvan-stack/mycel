"""Acceptance for private feature-check helpers, separate from live providers."""

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel._cli import run
from mycel._coverage import CoverageError, proves, require_check_database
from mycel._safeguards import run_git
from mycel._settings import load_settings
from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn, repository_fixture


class ServiceFixtureTests(unittest.TestCase):
    @proves("MYC-13.7")
    def test_packaged_prompt_counts_enforce_limits_while_usage_counts_submitted_text(self):
        from mycel._embedding_plan import load_tokenizer
        tokenizer = load_tokenizer()
        service = EmbeddingStandIn(tokenizer.counts, input_cap=9, batch_cap=9)
        with self.assertRaises(EmbeddingFixtureFailure) as fault:
            service.embed(["hello world"], model="voyage-code-4", dimensions=256, input_type="query")
        self.assertEqual(fault.exception.kind, "content")
        self.assertEqual(service.attempts[0].tokens, (10,))
        self.assertEqual(service.attempts[0].submitted_tokens, (2,))
        service = EmbeddingStandIn(tokenizer.counts)
        response = service.embed(["hello world"], model="voyage-code-4", dimensions=256, input_type="query")
        self.assertEqual(response["usage"]["total_tokens"], 2)
        self.assertEqual((service.input_cap, service.batch_cap, service.inputs_cap),
                         (tokenizer.catalog.input_token_cap, tokenizer.catalog.batch_token_cap,
                          tokenizer.catalog.batch_input_cap))

    @proves("MYC-13.7")
    def test_deterministic_vectors_keep_word_similarity_and_exact_request_counts(self):
        calls = []

        def counter(text, kind):
            calls.append((text, kind))
            # A fixture of the counting contract. The feature tests pass the
            # packaged tokenizer here; this helper never chooses an estimate.
            return {"apple pear fruit": 4, "apple pear orchard": 4, "engine wheel road": 4}[text]

        service = EmbeddingStandIn(counter)
        texts = ["apple pear fruit", "apple pear orchard", "engine wheel road"]
        response = service.embed(texts, model="voyage-code-4", dimensions=1024, input_type="document")
        vectors = [row["embedding"] for row in response["data"]]
        dot = lambda a, b: sum(left * right for left, right in zip(a, b))
        self.assertGreater(dot(vectors[0], vectors[1]), dot(vectors[0], vectors[2]))
        self.assertEqual(vectors[0], service.vector(texts[0], 1024))
        self.assertEqual(response["usage"]["total_tokens"], 12)
        self.assertEqual(calls, [(text, "document") for text in texts])
        self.assertEqual(len(service.attempts), 1)
        self.assertEqual(service.attempts[0].inputs, tuple(texts))
        self.assertEqual(service.attempts[0].tokens, (4, 4, 4))
        self.assertTrue(all(len(vector) == 1024 for vector in vectors))
        self.assertEqual(service.vector("", 256), service.vector("", 256))

    @proves("MYC-13.7")
    def test_stand_in_enforces_input_batch_count_and_explicit_request_contract(self):
        counter = lambda text, kind: {"small": 2, "large": 5}[text]
        for inputs, caps in ((["large"], {"input_cap": 4}),
                             (["small", "small"], {"batch_cap": 3}),
                             (["small", "small"], {"inputs_cap": 1})):
            service = EmbeddingStandIn(counter, **caps)
            with self.assertRaises(EmbeddingFixtureFailure) as failure:
                service.embed(inputs, model="voyage-code-4", dimensions=256, input_type="query")
            self.assertEqual(failure.exception.kind, "content")
            self.assertEqual(len(service.attempts), 1)
            self.assertEqual(service.attempts[0].inputs, tuple(inputs))
        service = EmbeddingStandIn(counter)
        body = {"input": ["small"], "model": "voyage-code-4", "output_dimension": 256,
                "output_dtype": "float", "input_type": "query", "truncation": False}
        self.assertEqual(service.request(body)["usage"]["total_tokens"], 2)
        for mutation in ({"truncation": True}, {"input_type": "other"}, {"output_dtype": "int8"},
                         {"output_dimension": True}, {"endpoint": "https://example.invalid"}):
            with self.assertRaises(ValueError):
                service.request({**body, **mutation})
        with self.assertRaises(ValueError):
            service.request({key: value for key, value in body.items() if key != "truncation"})

    @proves("MYC-13.7")
    def test_each_service_failure_is_controllable_and_attempts_remain_counted(self):
        for kind in sorted(EmbeddingStandIn.FAILURES):
            with self.subTest(kind=kind):
                service = EmbeddingStandIn(lambda text, input_type: 1)
                service.fail_attempt(1, kind)
                with self.assertRaises(EmbeddingFixtureFailure) as fault:
                    service.embed(["fictional text"], model="voyage-code-4", dimensions=256,
                                  input_type="document")
                self.assertEqual(fault.exception.kind, kind)
                self.assertEqual(service.attempts[0].failure, kind)
                service.embed(["fictional text"], model="voyage-code-4", dimensions=256,
                              input_type="document")
                self.assertEqual(len(service.attempts), 2)
                self.assertIsNone(service.attempts[1].failure)
        service = EmbeddingStandIn(lambda text, input_type: 1)
        service.reject_input = lambda text: text == "bad content"
        with self.assertRaises(EmbeddingFixtureFailure):
            service.embed(["good", "bad content"], model="voyage-code-4", dimensions=256,
                          input_type="document")
        service.response_mutator = lambda response: {**response, "data": []}
        self.assertEqual(service.embed(["good"], model="voyage-code-4", dimensions=256,
                                      input_type="document")["data"], [])

    @proves("MYC-13.8")
    def test_installed_settings_and_cli_reject_provider_endpoint_substitution(self):
        from io import StringIO
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            for key in ("url", "endpoint", "base_url", "api_base", "provider_url"):
                path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture_owner"\n'
                                '[embedding]\n' + key + '="https://example.invalid"\n')
                snapshot = load_settings(path=path)
                self.assertIn("embedding." + key, snapshot.report()["unknownKeys"])
                self.assertFalse(snapshot.valid)
            path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture_owner"\n')
            with patch.dict("os.environ", {"MYCEL_CONFIG": str(path),
                                          "MYCEL_EMBEDDING_ENDPOINT": "https://example.invalid"}):
                self.assertNotIn("https://example.invalid", json.dumps(load_settings().report()))
                for option in ("--endpoint", "--base-url", "--provider-url"):
                    output = StringIO()
                    status = run(["embed", option, "https://example.invalid"], stdout=output,
                                 stderr=StringIO())
                    self.assertEqual(status, 1)
                    self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")


class RepositoryFixtureTests(unittest.TestCase):
    # The backend runs actual product init for this fixture. These checks remain
    # store-backed and cannot qualify against an in-memory substitute.

    @proves("MYC-13.6", kind="store")
    def test_real_git_locations_are_read_without_touching_the_generated_checkout(self):
        self.assertTrue(self.store_fixture.backend.real_store)
        with repository_fixture() as fixture:
            before = fixture.snapshot()
            refs = run_git(["for-each-ref", "--format=%(refname)", "refs/heads"], cwd=fixture.code)
            self.assertIn(b"refs/heads/fixture-base", refs.stdout)
            self.assertIn(b"refs/heads/fixture-second", refs.stdout)
            branch = run_git(["show", "fixture-second:README.md"], cwd=fixture.code)
            stash = run_git(["show", "refs/stash:docs/guide.md"], cwd=fixture.code)
            self.assertIn(b"Second branch text", branch.stdout)
            self.assertIn(b"Stashed guide text", stash.stdout)
            self.assertIn("Disk and base branch text", (fixture.code / "README.md").read_text())
            self.assertIn("A checkout document", (fixture.code / "docs/guide.md").read_text())
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual((fixture.overlapping_artifacts / "guide.md").resolve(),
                             (fixture.code / "docs/guide.md").resolve())
            self.assertNotEqual((fixture.artifacts / "README.md").resolve(),
                                (fixture.code / "README.md").resolve())
            self.assertNotEqual(sha256((fixture.artifacts / "README.md").read_bytes()).hexdigest(),
                                sha256((fixture.code / "README.md").read_bytes()).hexdigest())
            root = fixture.root
        self.assertFalse(root.exists())

    @proves("MYC-13.4", "MYC-13.5", kind="store")
    def test_private_store_fixture_has_safe_name_private_settings_and_real_database(self):
        fixture = self.store_fixture
        self.assertEqual(require_check_database(fixture.database), fixture.database)
        self.assertEqual(fixture.settings_file.stat().st_mode & 0o777, 0o600)
        self.assertIn(fixture.database, fixture.settings_file.read_text())
        self.assertEqual(fixture.backend.query(fixture.database, "SELECT current_database()"), fixture.database)
        for name in ("owner_database", "mycel_check_", "mycel_check_bad;DROP DATABASE owner", "mycel_check_Upper"):
            with self.assertRaises(CoverageError):
                fixture.backend.query(name, "SELECT 1")


if __name__ == "__main__":
    unittest.main()
