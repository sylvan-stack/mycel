
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_settings.py::SettingsTests.test_absent_keys_have_the_specified_defaults
# Reason: Even after the first-pass trim, this still enumerates direct defaults, absent keys and a constructed default path; no distinct behavior needs execution to establish.
# Source: mycel@97335499256bd7aa68a7647e303155bfc3261f40:tests/test_settings.py
# Retained evidence at review: Snapshot isolation, schema diagnostics, scope resolution and settings CLI integration remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_absent_keys_have_the_specified_defaults(self):
#         snapshot = self.load()
#         snapshot.require_valid()
#         values = snapshot.values
#         self.assertEqual(values["store"]["address"], STORE)
#         self.assertEqual(values["embedding"]["model"], "voyage-code-4")
#         self.assertEqual(values["embedding"]["dimensions"], 1024)
#         self.assertEqual(values["embedding"]["attempts"], 5)
#         self.assertEqual(tuple(values["scan"]["document_endings"]), (".md",))
#         self.assertEqual(tuple(values["scan"]["code_endings"]), (
#             ".py", ".svelte", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
#             ".sh", ".bash", ".plist", ".plist.in", ".swift",
#         ))
#         self.assertEqual(set(values["scan"]["skip_folders"]), {
#             ".arbol", ".arco", ".bare", ".git", ".mypy_cache", ".next", ".pytest_cache", ".ruff_cache",
#             ".svelte-kit", ".turbo", ".venv", "__pycache__", "build", "coverage", "dist", "node_modules",
#             "releases", "site-packages", "storybook-static", "venv",
#         })
#         self.assertEqual(values["search"]["freshness_seconds"], 5)
#         self.assertEqual([(entry["repo"], tuple(entry["paths"])) for entry in values["search"]["shared_documents"]],
#                          [("mycel", (".",)), ("arbol", ("GLOSSARY.md",))])
#         self.assertEqual(values["drifts"], {
#             "debounce_seconds": 300, "model": "jev-1.13.0", "confidence_floor": 0.7,
#             "candidates": 100, "at_once": 2, "seconds": 300, "jev_timeout_seconds": 10,
#             "review_timeout_seconds": 120, "attempts": 2, "max_input_bytes": 24000,
#             "review_max_input_bytes": 1048576, "origin_floor": 0.7, "conformance_floor": 0.7,
#             "consistency_floor": 0.7, "ambiguity_floor": 0.8,
#         })
#         self.assertEqual(values["summaries"]["at_once"], 4)
#         self.assertNotIn("command", values["summaries"])
#         self.assertNotIn("instructions", values["summaries"])
#         self.assertNotIn("key_command", values["embedding"])
#         self.assertEqual(values["organizations"], {})
#         self.assertEqual(values["repos"], {})
#         repository = self.load('[repos.cellar]\ncode_root = "~/repos/cellar"\n').values["repos"]["cellar"]
#         self.assertIs(repository["enabled"], False)
#         self.assertEqual(tuple(repository["code_subdirs"]), ())
#         self.assertEqual(tuple(repository["test_patterns"]), (
#             r"(\.(spec|test)\.[jt]sx?$)|(/__tests__/)|((^|/)test_[^/]*\.py$)|(conftest\.py$)|(_test\.(py|go)$)",
#         ))
#         self.assertEqual(tuple(repository["generated_patterns"]), (
#             r"(\.generated\.[jt]sx?$)|((^|/)gql/types\.ts$)",
#         ))
#         organization = self.load('[organizations.Orchard]\nroot = "~/repos/orchard"\n').values["organizations"]["Orchard"]
#         self.assertEqual(organization["artifact_root"], str(self.home / "Artifacts/orchard"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_settings.py::SettingsTests.test_complete_schema_accepts_custom_values_and_literal_repository_names
# Reason: A large positive configuration round trip mostly copies schema fields into the fixture and checks them back; substantive parsing/validation boundaries are covered separately.
# Source: mycel@97335499256bd7aa68a7647e303155bfc3261f40:tests/test_settings.py
# Retained evidence at review: Wrong-type, finite-number, quoted/dotted-key diagnostic, path-escape and snapshot-isolation cases remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_schema_accepts_custom_values_and_literal_repository_names(self):
#         snapshot = self.load('''[embedding]
# model = "voyage-code-4"
# dimensions = 256
# key_command = ["/fixture/read-key", "--literal"]
# attempts = 1
# [scan]
# document_endings = [".md", ".markdown"]
# code_endings = [".py"]
# skip_folders = [".git"]
# [search]
# shared_documents = [{ repo = "Handbook", paths = [".", "guides"] }]
# freshness_seconds = 0.5
# [drifts]
# debounce_seconds = 0
# model = "jev-2.0.1"
# confidence_floor = 1
# candidates = 1
# at_once = 1
# seconds = 0.5
# jev_timeout_seconds = 0.5
# review_timeout_seconds = 0.5
# attempts = 1
# max_input_bytes = 1
# review_max_input_bytes = 1
# review_command = ["/fixture/reviewer", "--config", "~/literal/config"]
# review_provider = "example-provider"
# review_model = "example-model-2026-10-01"
# review_revision = "adapter:1.0+fixture"
# [summaries]
# command = ["summary-writer", "--literal"]
# at_once = 1
# instructions = "~/instructions"
# [organizations.Orchard]
# root = "~/repos/orchard"
# artifact_root = "~/Artifacts/orchard"
# [repos."Literal.Repository"]
# enabled = true
# code_root = "~/repos/literal"
# artifact_root = "~/Artifacts/literal"
# code_subdirs = ["src", "tests"]
# test_patterns = ["*.test.py"]
# generated_patterns = ["generated/*"]
# evaluation = "evaluation/search.toml"
# ''')
#         self.assertTrue(snapshot.valid, snapshot.report())
#         snapshot.require_valid()
#         self.assertEqual(set(snapshot.values["repos"]), {"Literal.Repository"})
#         self.assertEqual(snapshot.values["embedding"]["dimensions"], 256)
#         self.assertEqual(snapshot.values["search"]["shared_documents"][0]["repo"], "Handbook")
#         self.assertEqual(snapshot.values["repos"]["Literal.Repository"]["evaluation"], "evaluation/search.toml")
#         self.assertEqual(snapshot.report()["unknownKeys"], [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_settings.py::SettingsTests.test_every_known_key_rejects_wrong_types
# Reason: Enumerates the obvious type declared for almost every schema field; this is a second schema inventory rather than a distinct interaction or subtle case.
# Source: mycel@97335499256bd7aa68a7647e303155bfc3261f40:tests/test_settings.py
# Retained evidence at review: Boolean/integer, nonfinite numeric, malformed nested tables, reviewer argv and secret-safe diagnostics remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_every_known_key_rejects_wrong_types(self):
#         cases = {
#             "store": {"address": 1},
#             "embedding": {"model": 1, "dimensions": "1024", "key_command": [1], "attempts": "5"},
#             "scan": {"document_endings": [1], "code_endings": 1, "skip_folders": [1]},
#             "search": {"shared_documents": "wrong", "freshness_seconds": "5"},
#             "drifts": {
#                 "debounce_seconds": "300", "model": 1, "confidence_floor": "0.7", "candidates": "100",
#                 "at_once": "2", "seconds": "300", "jev_timeout_seconds": "10", "review_timeout_seconds": "120",
#                 "attempts": "2", "max_input_bytes": "24000", "review_max_input_bytes": "1048576",
#                 "review_command": "program", "review_provider": 1, "review_model": 1, "review_revision": 1,
#             },
#             "summaries": {"command": [1], "at_once": "4", "instructions": 1},
#             "organizations.Orchard": {"root": 1, "artifact_root": 1},
#             "repos.cellar": {
#                 "enabled": "false", "code_root": 1, "artifact_root": 1, "code_subdirs": [1],
#                 "test_patterns": [1], "generated_patterns": [1], "evaluation": 1,
#             },
#         }
#         for table, entries in cases.items():
#             for key, value in entries.items():
#                 with self.subTest(table=table, key=key):
#                     snapshot = self.load(f"[{table}]\n{key} = {toml_value(value)}\n", store=table != "store")
#                     self.assert_fault(snapshot, f"{table}.{key}")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_settings.py::SettingsTests.test_jev_model_must_be_an_exact_three_part_version
# Reason: Restates the exact-version regular expression with routine accepted/rejected spellings.
# Source: mycel@97335499256bd7aa68a7647e303155bfc3261f40:tests/test_settings.py
# Retained evidence at review: Provider operation/profile compatibility and settings diagnostics remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_jev_model_must_be_an_exact_three_part_version(self):
#         for model in ("jev", "jev-latest", "jev-1", "jev-1.13", "jev-1.13.0-preview", "other-1.13.0", ""):
#             with self.subTest(model=model):
#                 self.assert_fault(self.load(f"[drifts]\nmodel = {toml_value(model)}\n"), "drifts.model")
#         for model in ("jev-1.13.0", "jev-2.0.1"):
#             with self.subTest(model=model):
#                 self.load(f"[drifts]\nmodel = {toml_value(model)}\n").require_valid()
# LOW-TIER-SOURCE-END
# LOW-TIER-END
