"""Settings acceptance with private files and no store or model access."""

from dataclasses import FrozenInstanceError
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mycel._errors import MycelError
from mycel._settings import load_settings


STORE = 'postgresql://mycel@localhost:5432/mycel'


def toml_value(value):
    """Encode the scalar/list fixtures without a TOML-writing dependency."""
    if type(value) is float and value != value:
        return "nan"
    if value == float("inf"):
        return "inf"
    if value == float("-inf"):
        return "-inf"
    if type(value) is dict:
        return "{ " + ", ".join(f"{key} = {toml_value(item)}" for key, item in value.items()) + " }"
    if type(value) is list:
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=True)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.counter = 0

    def write_settings(self, content="", *, store=True):
        self.counter += 1
        path = self.home / f"settings-{self.counter}.toml"
        prefix = f"[store]\naddress = {toml_value(STORE)}\n\n" if store else ""
        path.write_text(prefix + content, encoding="utf-8")
        return path

    def load(self, content="", *, store=True):
        return load_settings(path=self.write_settings(content, store=store), home=self.home)

    def test_mutation_guard_preserves_original_home_and_ignores_format_only_changes(self):
        snapshot = self.load('[repos.fixture]\nenabled=true\nartifact_root="~/artifacts"\n')
        snapshot.require_current()
        snapshot.file.write_text(snapshot.file.read_text() + '\n# Formatting only.\n')
        snapshot.require_current()
        self.assertEqual(snapshot.values['repos']['fixture']['artifact_root'], str(self.home / 'artifacts'))

    def test_mutation_guard_refuses_changed_or_unavailable_effective_settings(self):
        for replacement in ('[repos.fixture]\nenabled=false\n', 'invalid = "private-sentinel"\n', None):
            with self.subTest(replacement=replacement):
                snapshot = self.load('[repos.fixture]\nenabled=true\n')
                if replacement is None:
                    snapshot.file.unlink()
                else:
                    snapshot.file.write_text(replacement)
                with self.assertRaises(MycelError) as error:
                    snapshot.require_current()
                self.assertEqual(error.exception.code, 'invalid_input')
                self.assertNotIn('private-sentinel', str(error.exception))

    def assert_fault(self, snapshot, key=None):
        report = snapshot.report()
        self.assertFalse(snapshot.valid)
        self.assertTrue(report["faults"])
        if key is not None:
            self.assertIn(key, [fault.get("key") for fault in report["faults"]])
        with self.assertRaises(MycelError) as raised:
            snapshot.require_valid()
        self.assertEqual(raised.exception.code, "settings")
        self.assertIn(str(snapshot.file), str(raised.exception))
        if key is not None:
            self.assertIn(key, str(raised.exception))
        return report, raised.exception

    def test_home_default_and_config_override_are_the_only_file_sources(self):
        default = self.home / ".mycel" / "config.toml"
        default.parent.mkdir()
        default.write_text(f'[store]\naddress = "{STORE}"\n[embedding]\nattempts = 7\n')
        override = self.write_settings("[embedding]\nattempts = 9\n")
        explicit = self.write_settings("[embedding]\nattempts = 11\n")
        with patch.dict(os.environ, {}, clear=True):
            snapshot = load_settings(home=self.home)
        self.assertEqual(snapshot.file, default)
        self.assertEqual(snapshot.values["embedding"]["attempts"], 7)
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(override)}, clear=True):
            snapshot = load_settings(home=self.home)
            chosen = load_settings(path=explicit, home=self.home)
        self.assertEqual(snapshot.file, override)
        self.assertEqual(snapshot.values["embedding"]["attempts"], 9)
        self.assertEqual(chosen.file, explicit)
        self.assertEqual(chosen.values["embedding"]["attempts"], 11)
        with patch.dict(os.environ, {"MYCEL_CONFIG": "~/" + override.name}, clear=True):
            expanded = load_settings(home=self.home)
        self.assertEqual(expanded.file, override)

    def test_legacy_environment_overrides_cannot_change_the_snapshot(self):
        path = self.write_settings('[repos.cellar]\ncode_root = "~/repos/cellar"\nenabled = false\n')
        overrides = {
            "MYCEL_PG_DSN": "postgresql://wrong@localhost/wrong",
            "MYCEL_PG_CONNECTION_FILE": "/wrong/private",
            "MYCEL_PG_CONNECTION_SHA256": "wrong",
            "MYCEL_PG_SCHEMA": "wrong",
            "MYCEL_EMBEDDER_URL": "http://wrong.invalid",
            "MYCEL_STORE_ADDRESS": "postgresql://wrong@localhost/wrong",
            "MYCEL_EMBEDDING_MODEL": "wrong",
            "MYCEL_REPO": "wrong",
            "MYCEL_SUMMARY_COMMAND": "/wrong/program",
            "VOYAGE_API_KEY": "fixture-credential",
            "JEV_API_KEY": "fixture-credential",
            "ARBOL_PG_DSN": "postgresql://wrong@localhost/wrong",
            "ARBOL_REPO": "wrong",
            "ARBOL_OVERLAY": "wrong",
        }
        with patch.dict(os.environ, {}, clear=True):
            expected = load_settings(path=path, home=self.home)
        with patch.dict(os.environ, overrides, clear=True):
            actual = load_settings(path=path, home=self.home)
        self.assertEqual(actual.values, expected.values)
        self.assertEqual(actual.report(), expected.report())
        self.assertEqual(set(actual.values["repos"]), {"cellar"})
        self.assertIs(actual.values["repos"]["cellar"]["enabled"], False)

    def test_each_load_reads_the_file_once_and_holds_an_immutable_snapshot(self):
        path = self.write_settings('[repos.cellar]\ncode_root = "~/repos/cellar"\nenabled = true\n')
        real_open = Path.open
        reads = []

        def observe_open(current, *args, **kwargs):
            if current == path:
                reads.append(args[0] if args else kwargs.get("mode", "r"))
            return real_open(current, *args, **kwargs)

        with patch.object(Path, "open", observe_open):
            first = load_settings(path=path, home=self.home)
            first.report()
            first.require_valid()
            first.values["repos"]["cellar"]["enabled"]
        self.assertEqual(len(reads), 1)
        self.assertNotIn("w", reads[0])
        path.write_text(f'[store]\naddress = "{STORE}"\n[repos.handbook]\nartifact_root = "~/Artifacts/handbook"\n')
        self.assertEqual(set(first.values["repos"]), {"cellar"})
        self.assertIs(first.values["repos"]["cellar"]["enabled"], True)
        first.require_valid()
        second = load_settings(path=path, home=self.home)
        self.assertEqual(set(second.values["repos"]), {"handbook"})
        self.assertIs(second.values["repos"]["handbook"]["enabled"], False)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            first.file = self.home / "another.toml"
        with self.assertRaises(TypeError):
            first.values["embedding"]["attempts"] = 99
        with self.assertRaises(TypeError):
            first.values["repos"]["cellar"]["enabled"] = False
        with self.assertRaises((AttributeError, TypeError)):
            first.values["scan"]["document_endings"].append(".txt")
        with self.assertRaises(TypeError):
            first.values["search"]["shared_documents"][0]["repo"] = "injected"
        with self.assertRaises((AttributeError, TypeError)):
            first.values["search"]["shared_documents"][0]["paths"].append("injected")
        report = first.report()
        report["unknownKeys"].append("injected")
        report["faults"].append({"message": "injected"})
        self.assertEqual(first.report()["unknownKeys"], [])
        self.assertEqual(first.report()["faults"], [])

    def test_absent_keys_have_the_specified_defaults(self):
        snapshot = self.load()
        snapshot.require_valid()
        values = snapshot.values
        self.assertEqual(values["store"]["address"], STORE)
        self.assertEqual(values["embedding"]["model"], "voyage-code-4")
        self.assertEqual(values["embedding"]["dimensions"], 1024)
        self.assertEqual(values["embedding"]["attempts"], 5)
        self.assertEqual(tuple(values["scan"]["document_endings"]), (".md",))
        self.assertEqual(tuple(values["scan"]["code_endings"]), (
            ".py", ".svelte", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
            ".sh", ".bash", ".plist", ".plist.in", ".swift",
        ))
        self.assertEqual(set(values["scan"]["skip_folders"]), {
            ".arbol", ".arco", ".bare", ".git", ".mypy_cache", ".next", ".pytest_cache", ".ruff_cache",
            ".svelte-kit", ".turbo", ".venv", "__pycache__", "build", "coverage", "dist", "node_modules",
            "releases", "site-packages", "storybook-static", "venv",
        })
        self.assertEqual(values["search"]["freshness_seconds"], 5)
        self.assertEqual([(entry["repo"], tuple(entry["paths"])) for entry in values["search"]["shared_documents"]],
                         [("mycel", (".",)), ("arbol", ("GLOSSARY.md",))])
        self.assertEqual(values["drifts"], {
            "debounce_seconds": 300, "model": "jev-1.13.0", "confidence_floor": 0.7,
            "candidates": 100, "at_once": 2, "seconds": 300, "jev_timeout_seconds": 10,
            "review_timeout_seconds": 120, "attempts": 2, "max_input_bytes": 24000,
            "review_max_input_bytes": 1048576, "origin_floor": 0.5, "conformance_floor": 0.5,
            "consistency_floor": 0.5, "ambiguity_floor": 0.5,
        })
        self.assertEqual(values["summaries"]["at_once"], 4)
        self.assertNotIn("command", values["summaries"])
        self.assertNotIn("instructions", values["summaries"])
        self.assertNotIn("key_command", values["embedding"])
        self.assertEqual(values["organizations"], {})
        self.assertEqual(values["repos"], {})
        repository = self.load('[repos.cellar]\ncode_root = "~/repos/cellar"\n').values["repos"]["cellar"]
        self.assertIs(repository["enabled"], False)
        self.assertEqual(tuple(repository["code_subdirs"]), ())
        self.assertEqual(tuple(repository["test_patterns"]), (
            r"(\.(spec|test)\.[jt]sx?$)|(/__tests__/)|((^|/)test_[^/]*\.py$)|(conftest\.py$)|(_test\.(py|go)$)",
        ))
        self.assertEqual(tuple(repository["generated_patterns"]), (
            r"(\.generated\.[jt]sx?$)|((^|/)gql/types\.ts$)",
        ))
        organization = self.load('[organizations.Orchard]\nroot = "~/repos/orchard"\n').values["organizations"]["Orchard"]
        self.assertEqual(organization["artifact_root"], str(self.home / "Artifacts/orchard"))

    def test_complete_schema_accepts_custom_values_and_literal_repository_names(self):
        snapshot = self.load('''[embedding]
model = "voyage-code-4"
dimensions = 256
key_command = ["/fixture/read-key", "--literal"]
attempts = 1
[scan]
document_endings = [".md", ".markdown"]
code_endings = [".py"]
skip_folders = [".git"]
[search]
shared_documents = [{ repo = "Handbook", paths = [".", "guides"] }]
freshness_seconds = 0.5
[drifts]
debounce_seconds = 0
model = "jev-2.0.1"
confidence_floor = 1
candidates = 1
at_once = 1
seconds = 0.5
jev_timeout_seconds = 0.5
review_timeout_seconds = 0.5
attempts = 1
max_input_bytes = 1
review_max_input_bytes = 1
review_command = ["/fixture/reviewer", "--config", "~/literal/config"]
review_provider = "example-provider"
review_model = "example-model-2026-10-01"
review_revision = "adapter:1.0+fixture"
[summaries]
command = ["summary-writer", "--literal"]
at_once = 1
instructions = "~/instructions"
[organizations.Orchard]
root = "~/repos/orchard"
artifact_root = "~/Artifacts/orchard"
[repos."Literal.Repository"]
enabled = true
code_root = "~/repos/literal"
artifact_root = "~/Artifacts/literal"
code_subdirs = ["src", "tests"]
test_patterns = ["*.test.py"]
generated_patterns = ["generated/*"]
evaluation = "evaluation/search.toml"
''')
        self.assertTrue(snapshot.valid, snapshot.report())
        snapshot.require_valid()
        self.assertEqual(set(snapshot.values["repos"]), {"Literal.Repository"})
        self.assertEqual(snapshot.values["embedding"]["dimensions"], 256)
        self.assertEqual(snapshot.values["search"]["shared_documents"][0]["repo"], "Handbook")
        self.assertEqual(snapshot.values["repos"]["Literal.Repository"]["evaluation"], "evaluation/search.toml")
        self.assertEqual(snapshot.report()["unknownKeys"], [])

    def test_every_known_key_rejects_wrong_types(self):
        cases = {
            "store": {"address": 1},
            "embedding": {"model": 1, "dimensions": "1024", "key_command": [1], "attempts": "5"},
            "scan": {"document_endings": [1], "code_endings": 1, "skip_folders": [1]},
            "search": {"shared_documents": "wrong", "freshness_seconds": "5"},
            "drifts": {
                "debounce_seconds": "300", "model": 1, "confidence_floor": "0.7", "candidates": "100",
                "at_once": "2", "seconds": "300", "jev_timeout_seconds": "10", "review_timeout_seconds": "120",
                "attempts": "2", "max_input_bytes": "24000", "review_max_input_bytes": "1048576",
                "review_command": "program", "review_provider": 1, "review_model": 1, "review_revision": 1,
            },
            "summaries": {"command": [1], "at_once": "4", "instructions": 1},
            "organizations.Orchard": {"root": 1, "artifact_root": 1},
            "repos.cellar": {
                "enabled": "false", "code_root": 1, "artifact_root": 1, "code_subdirs": [1],
                "test_patterns": [1], "generated_patterns": [1], "evaluation": 1,
            },
        }
        for table, entries in cases.items():
            for key, value in entries.items():
                with self.subTest(table=table, key=key):
                    snapshot = self.load(f"[{table}]\n{key} = {toml_value(value)}\n", store=table != "store")
                    self.assert_fault(snapshot, f"{table}.{key}")

    def test_tables_and_shared_document_members_have_exact_shapes(self):
        for table in ("store", "embedding", "scan", "search", "drifts", "summaries", "organizations", "repos"):
            with self.subTest(table=table):
                self.assert_fault(self.load(f'{table} = "fixture-secret"\n', store=False), table)
        for item in ("wrong", {"repo": 1, "paths": ["."]}, {"repo": "handbook", "paths": [1]},
                     {"repo": "handbook"}, {"paths": ["."]}):
            with self.subTest(item=item):
                snapshot = self.load(f"[search]\nshared_documents = {toml_value([item])}\n")
                self.assert_fault(snapshot)
        self.assert_fault(self.load('[organizations.Orchard]\nartifact_root = "~/Artifacts/orchard"\n'),
                          "organizations.Orchard.root")
        self.assert_fault(self.load('[repos]\ncellar = "fixture-secret"\n'), "repos.cellar")

    def test_integer_limits_exclude_booleans_and_fractional_numbers(self):
        keys = (
            ("embedding", "attempts"), ("drifts", "debounce_seconds"), ("drifts", "candidates"),
            ("drifts", "at_once"), ("drifts", "attempts"), ("drifts", "max_input_bytes"),
            ("drifts", "review_max_input_bytes"), ("summaries", "at_once"),
        )
        for table, key in keys:
            for value in (True, False, 1.5, -1):
                with self.subTest(table=table, key=key, value=value):
                    self.assert_fault(self.load(f"[{table}]\n{key} = {toml_value(value)}\n"), f"{table}.{key}")
            if key != "debounce_seconds":
                with self.subTest(table=table, key=key, value=0):
                    self.assert_fault(self.load(f"[{table}]\n{key} = 0\n"), f"{table}.{key}")
        self.assertTrue(self.load("[drifts]\ndebounce_seconds = 0\n").valid)

    def test_numeric_limits_and_confidence_are_finite_and_within_range(self):
        keys = (("search", "freshness_seconds"), ("drifts", "seconds"),
                ("drifts", "jev_timeout_seconds"), ("drifts", "review_timeout_seconds"))
        for table, key in keys:
            for value in (True, False, 0, -1, float("nan"), float("inf"), float("-inf")):
                with self.subTest(table=table, key=key, value=value):
                    self.assert_fault(self.load(f"[{table}]\n{key} = {toml_value(value)}\n"), f"{table}.{key}")
        for value in (True, False, -0.01, 1.01, float("nan"), float("inf"), float("-inf")):
            with self.subTest(confidence_floor=value):
                self.assert_fault(self.load(f"[drifts]\nconfidence_floor = {toml_value(value)}\n"),
                                  "drifts.confidence_floor")
        for value in (0, 0.7, 1):
            with self.subTest(accepted_floor=value):
                self.assertTrue(self.load(f"[drifts]\nconfidence_floor = {toml_value(value)}\n").valid)

    def test_supported_model_dimension_pairs_are_checked_locally(self):
        for dimensions in (256, 512, 1024, 2048):
            with self.subTest(dimensions=dimensions):
                self.load(f'[embedding]\nmodel = "voyage-code-4"\ndimensions = {dimensions}\n').require_valid()
        for model, dimensions in (("voyage-code-3", 1024), ("unknown-model", 1024), ("voyage-code-4", 768),
                                  ("voyage-code-4", True), ("voyage-code-4", 1024.0)):
            with self.subTest(model=model, dimensions=dimensions):
                snapshot = self.load(f"[embedding]\nmodel = {toml_value(model)}\ndimensions = {toml_value(dimensions)}\n")
                self.assert_fault(snapshot)
                self.assertTrue(any(fault.get("key") in {"embedding.model", "embedding.dimensions"}
                                    for fault in snapshot.report()["faults"]))

    def test_jev_model_must_be_an_exact_three_part_version(self):
        for model in ("jev", "jev-latest", "jev-1", "jev-1.13", "jev-1.13.0-preview", "other-1.13.0", ""):
            with self.subTest(model=model):
                self.assert_fault(self.load(f"[drifts]\nmodel = {toml_value(model)}\n"), "drifts.model")
        for model in ("jev-1.13.0", "jev-2.0.1"):
            with self.subTest(model=model):
                self.load(f"[drifts]\nmodel = {toml_value(model)}\n").require_valid()

    def test_unknown_tables_and_nested_keys_all_have_safe_qualified_diagnostics(self):
        secret = "fixture-secret-do-not-report"
        source = f'''unsupported = "{secret}"
[store]
address = "{STORE}"
password = "{secret}"
[embedding]
token = "{secret}"
[scan]
unknown_scan = "{secret}"
[search]
hidden = "{secret}"
shared_documents = [{{ repo = "handbook", paths = ["."], private = "{secret}" }}]
[drifts]
threshold = "{secret}"
[summaries]
secret = "{secret}"
[organizations.Orchard]
root = "~/repos/orchard"
url = "{secret}"
[repos.cellar]
code_root = "~/repos/cellar"
enabeld = "{secret}"
profile = "{secret}"
[providers.private]
api_key = "{secret}"
'''
        expected_lines = {
            "unsupported": 1, "store.password": 4, "embedding.token": 6, "scan.unknown_scan": 8,
            "search.hidden": 10, "search.shared_documents[0].private": 11, "drifts.threshold": 13,
            "summaries.secret": 15, "organizations.Orchard.url": 18, "repos.cellar.enabeld": 21,
            "repos.cellar.profile": 22, "providers.private.api_key": 24,
        }
        snapshot = self.load(source, store=False)
        report, error = self.assert_fault(snapshot)
        self.assertTrue(report["readable"])
        self.assertTrue(set(expected_lines).issubset(report["unknownKeys"]), report)
        for key, line in expected_lines.items():
            with self.subTest(key=key):
                faults = [fault for fault in report["faults"] if fault.get("key") == key]
                self.assertTrue(faults, report)
                self.assertEqual(faults[0].get("line"), line)
                self.assertRegex(faults[0]["message"].lower(), "unknown|unsupported")
                self.assertIn(key, str(error))
        enabled_fault = next(fault for fault in report["faults"] if fault.get("key") == "repos.cellar.enabeld")
        self.assertIn("enabled", enabled_fault["message"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn(secret, str(error))

    def test_inline_and_dotted_unknown_keys_are_not_hidden_by_table_syntax(self):
        sources = (
            ('repos.cellar = { code_root = "~/repos/cellar", profile = "fixture-secret" }\n', "repos.cellar.profile"),
            ('repos.cellar.code_root = "~/repos/cellar"\nrepos.cellar.enabeld = "fixture-secret"\n', "repos.cellar.enabeld"),
            ('[embedding.unknown]\nprivate = "fixture-secret"\n', "embedding.unknown.private"),
            ('[mystery]\n', "mystery"),
            ('providers = [[{ api_key = "fixture-secret" }]]\n', "providers[0][0].api_key"),
            ('[embedding]\nattempts = [{ private = "fixture-secret" }]\n', "embedding.attempts[0].private"),
            ('[[drifts]]\nthreshold = "fixture-secret"\n', "drifts[0].threshold"),
        )
        for source, key in sources:
            with self.subTest(key=key):
                # Dotted assignments must precede the first table to stay at
                # TOML's root rather than become members of [store].
                source = source + f'\n[store]\naddress = "{STORE}"\n'
                snapshot = self.load(source, store=False)
                report, error = self.assert_fault(snapshot)
                self.assertIn(key, report["unknownKeys"])
                self.assertNotIn("fixture-secret", str(error))
                self.assertNotIn("fixture-secret", json.dumps(report))

    def test_key_lines_ignore_comments_and_text_that_looks_like_toml(self):
        source = '''[store]
address = "postgresql://mycel@localhost:5432/mycel"
# [repos.cellar]
# enabeld = "fixture-secret"
[summaries]
command = ["program", """first line
[repos.cellar]
enabeld = "fixture-secret"
last line"""]
[repos.cellar]
code_root = "~/repos/cellar"
"enabeld" = "fixture-secret"
'''
        snapshot = self.load(source, store=False)
        report, error = self.assert_fault(snapshot, "repos.cellar.enabeld")
        self.assertEqual(report["unknownKeys"], ["repos.cellar.enabeld"])
        self.assertEqual(next(fault for fault in report["faults"] if fault.get("key") == "repos.cellar.enabeld")["line"], 12)
        self.assertNotIn("fixture-secret", json.dumps(report))
        self.assertNotIn("fixture-secret", str(error))
        report["faults"][0]["message"] = "injected"
        self.assertNotIn("injected", json.dumps(snapshot.report()))

    def test_missing_unreadable_and_invalid_toml_have_safe_file_diagnostics(self):
        missing = self.home / "missing.toml"
        snapshot = load_settings(path=missing, home=self.home)
        report, _ = self.assert_fault(snapshot)
        self.assertEqual(set(report), {"file", "exists", "readable", "unknownKeys", "faults"})
        self.assertFalse(report["exists"])
        self.assertFalse(report["readable"])
        path = self.write_settings()
        with patch.object(Path, "read_bytes", side_effect=PermissionError("fixture-secret-permission")):
            snapshot = load_settings(path=path, home=self.home)
        report, error = self.assert_fault(snapshot)
        self.assertTrue(report["exists"])
        self.assertFalse(report["readable"])
        self.assertNotIn("fixture-secret", json.dumps(report))
        self.assertNotIn("fixture-secret", str(error))
        invalid = self.write_settings('[embedding]\nmodel = "fixture-secret-unclosed\n', store=False)
        snapshot = load_settings(path=invalid, home=self.home)
        report, error = self.assert_fault(snapshot)
        self.assertFalse(report["readable"])
        self.assertTrue(any(type(fault.get("line")) is int for fault in report["faults"]))
        self.assertNotIn("fixture-secret", json.dumps(report))
        self.assertNotIn("fixture-secret", str(error))
        invalid.write_bytes(b'[store]\naddress = "\xfffixture-secret"\n')
        snapshot = load_settings(path=invalid, home=self.home)
        report, error = self.assert_fault(snapshot)
        self.assertFalse(report["readable"])
        self.assertNotIn("fixture-secret", json.dumps(report))
        self.assertNotIn("fixture-secret", str(error))

    def test_store_address_is_required_only_for_store_dependent_work(self):
        snapshot = self.load("", store=False)
        snapshot.require_valid(require_store=False)
        self.assert_fault(snapshot, "store.address")
        invalid = self.load('[store]\naddress = 3\n', store=False)
        with self.assertRaises(MycelError) as raised:
            invalid.require_valid(require_store=False)
        self.assertEqual(raised.exception.code, "settings")

    def test_store_addresses_cannot_carry_plaintext_passwords_or_malformed_locations(self):
        for address in (
            "postgresql://mycel:fixture-secret@localhost:5432/mycel",
            "postgresql://mycel:fixture%2Dsecret@localhost/mycel",
            "postgresql://mycel@localhost/mycel?password=fixture-secret",
            "postgresql://mycel@localhost/mycel?passfile=/fixture/secret",
            "host=localhost dbname=mycel password=fixture-secret", "", "relative/location",
        ):
            with self.subTest(address=address):
                snapshot = self.load(f"[store]\naddress = {toml_value(address)}\n", store=False)
                report, error = self.assert_fault(snapshot, "store.address")
                self.assertNotIn("fixture-secret", json.dumps(report))
                self.assertNotIn("fixture-secret", str(error))

    def test_folder_tildes_use_the_invocation_home_and_other_folders_are_absolute(self):
        snapshot = self.load('''[summaries]
instructions = "~/instructions"
[organizations.Orchard]
root = "~/repos/orchard"
artifact_root = "/fixture/artifacts"
[repos.cellar]
code_root = "~/repos/cellar"
artifact_root = "~/Artifacts/cellar"
''')
        snapshot.require_valid()
        self.assertEqual(snapshot.values["summaries"]["instructions"], str(self.home / "instructions"))
        self.assertEqual(snapshot.values["organizations"]["Orchard"]["root"], str(self.home / "repos/orchard"))
        self.assertEqual(snapshot.values["organizations"]["Orchard"]["artifact_root"], "/fixture/artifacts")
        self.assertEqual(snapshot.values["repos"]["cellar"]["code_root"], str(self.home / "repos/cellar"))
        self.assertEqual(snapshot.values["repos"]["cellar"]["artifact_root"], str(self.home / "Artifacts/cellar"))
        folders = (("summaries", "instructions"), ("organizations.Orchard", "root"),
                   ("organizations.Orchard", "artifact_root"), ("repos.cellar", "code_root"),
                   ("repos.cellar", "artifact_root"))
        for table, key in folders:
            for value in ("relative/folder", "", "~another/folder", "~/bad\x00folder"):
                with self.subTest(table=table, key=key, value=value):
                    self.assert_fault(self.load(f"[{table}]\n{key} = {toml_value(value)}\n"), f"{table}.{key}")

    def test_repository_relative_paths_cannot_escape_their_roots(self):
        for key in ("code_subdirs", "evaluation"):
            for value in ("../outside", "src/../../outside", "/absolute/outside", "~/outside", "bad\x00path"):
                with self.subTest(key=key, value=value):
                    fixture = [value] if key == "code_subdirs" else value
                    snapshot = self.load('[repos.cellar]\ncode_root = "~/repos/cellar"\n'
                                         'artifact_root = "~/Artifacts/cellar"\n'
                                         f'{key} = {toml_value(fixture)}\n')
                    self.assert_fault(snapshot, f"repos.cellar.{key}")
        self.load('[repos.cellar]\ncode_root = "~/repos/cellar"\ncode_subdirs = []\n').require_valid()

    def test_reviewer_command_provider_model_and_revision_are_all_or_none(self):
        entries = {
            "review_command": ["/fixture/reviewer", "--config", "/fixture/review.toml"],
            "review_provider": "example-provider", "review_model": "example-model-2026-10-01",
            "review_revision": "adapter-v1",
        }
        self.load().require_valid()
        for count in range(1, len(entries)):
            for keys in combinations(entries, count):
                with self.subTest(keys=keys):
                    source = "[drifts]\n" + "\n".join(f"{key} = {toml_value(entries[key])}" for key in keys)
                    snapshot = self.load(source)
                    self.assert_fault(snapshot)
                    diagnostic_keys = {fault.get("key") for fault in snapshot.report()["faults"]}
                    self.assertTrue(diagnostic_keys.intersection(f"drifts.{key}" for key in entries), snapshot.report())
        source = "[drifts]\n" + "\n".join(f"{key} = {toml_value(value)}" for key, value in entries.items())
        self.load(source).require_valid()

    def reviewer_source(self, **changes):
        entries = {
            "review_command": ["/fixture/reviewer"], "review_provider": "example-provider",
            "review_model": "example-model-2026-10-01", "review_revision": "adapter-v1",
        }
        entries.update(changes)
        return "[drifts]\n" + "\n".join(f"{key} = {toml_value(value)}" for key, value in entries.items())

    def test_reviewer_argv_is_nonempty_nul_free_and_has_an_absolute_executable(self):
        for command in ([], [""], ["reviewer"], ["./reviewer"], ["$HOME/reviewer"], ["~another/reviewer"],
                        ["/fixture/reviewer", ""], ["/fixture/reviewer", 1], ["/fixture/reviewer\x00"],
                        ["/fixture/reviewer", "bad\x00argument"]):
            with self.subTest(command=command):
                self.assert_fault(self.load(self.reviewer_source(review_command=command)), "drifts.review_command")
        for key in ("review_provider", "review_model"):
            for value in ("", " ", "bad\x00identity"):
                with self.subTest(key=key, value=value):
                    self.assert_fault(self.load(self.reviewer_source(**{key: value})), f"drifts.{key}")
        self.assert_fault(self.load(self.reviewer_source(review_model="latest")), "drifts.review_model")

    def test_only_the_reviewer_executable_leading_tilde_is_expanded(self):
        argv = ["~/bin/reviewer", "~/literal/config", "$HOME/private", "*.json", "$(literal)", "; literal"]
        snapshot = self.load(self.reviewer_source(review_command=argv))
        snapshot.require_valid()
        self.assertEqual(tuple(snapshot.values["drifts"]["review_command"]),
                         (str(self.home / "bin/reviewer"), *argv[1:]))

    def test_reviewer_revision_uses_exact_ascii_syntax_and_length(self):
        for revision in ("a", "Adapter.1_2:3+4-5", "a" * 128):
            with self.subTest(accepted_revision=revision):
                self.load(self.reviewer_source(review_revision=revision)).require_valid()
        for revision in ("", "a" * 129, ".version", "_version", ":version", "-version", "+version",
                         "contains space", "contains/slash", "é-version", "a\nversion", "a\x00version"):
            with self.subTest(revision=revision):
                self.assert_fault(self.load(self.reviewer_source(review_revision=revision)), "drifts.review_revision")

    def test_validation_never_writes_settings_or_acquires_credentials_or_launches_programs(self):
        valid = self.write_settings(self.reviewer_source(review_command=["~/bin/reviewer", "--probe"]))
        invalid = self.write_settings('[embedding]\nunknown = "fixture-secret"\n')
        before = {path: path.read_bytes() for path in (valid, invalid)}
        missing_home = self.home / "missing-home"
        with patch.object(Path, "write_text") as write_text, patch.object(Path, "write_bytes") as write_bytes, \
                patch.object(Path, "mkdir") as mkdir, patch.object(Path, "touch") as touch, \
                patch.object(subprocess, "Popen") as spawn, patch.object(subprocess, "run") as run, \
                patch("mycel._coverage.PostgresBackend._execute") as index:
            load_settings(path=valid, home=self.home).require_valid()
            self.assert_fault(load_settings(path=invalid, home=self.home))
            with patch.dict(os.environ, {}, clear=True):
                self.assert_fault(load_settings(home=missing_home))
            for operation in (write_text, write_bytes, mkdir, touch, spawn, run, index):
                operation.assert_not_called()
        self.assertEqual({path: path.read_bytes() for path in (valid, invalid)}, before)
        self.assertFalse((missing_home / ".mycel").exists())


if __name__ == "__main__":
    unittest.main()
