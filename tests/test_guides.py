import unittest


class GuideTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_guides.py::GuideTests.test_command_and_reply_guide_matches_program
#     def test_command_and_reply_guide_matches_program(self):
#         guide = (Path(__file__).resolve().parents[1] / "docs" / "command-line.md").read_text()
#         start = "<!-- command-contract:start -->\n```json\n"
#         end = "\n```\n<!-- command-contract:end -->"
#         self.assertEqual(guide.count(start), 1)
#         self.assertEqual(guide.count(end), 1)
#         contract = json.loads(guide.split(start)[1].split(end)[0])
#         self.assertEqual(contract, {"help": help_reply(), "errors": [c.value for c in ErrorCode],
#                                     "exitStatuses": {"done": 0, "failed": 1, "stopped": 2}})
# TEST-TIER-DISABLED-END tests/test_guides.py::GuideTests.test_command_and_reply_guide_matches_program

# TEST-TIER-DISABLED-BEGIN tests/test_guides.py::GuideTests.test_settings_guide_contract_and_fictional_examples_match_validation
#     def test_settings_guide_contract_and_fictional_examples_match_validation(self):
#         root = Path(__file__).resolve().parents[1]
#         guide = (root / "docs/settings.md").read_text()
#         start = "<!-- settings-contract:start -->\n```json\n"
#         end = "\n```\n<!-- settings-contract:end -->"
#         self.assertEqual(guide.count(start), 1)
#         self.assertEqual(guide.count(end), 1)
#         contract = json.loads(guide.split(start)[1].split(end)[0])
#         catalog = json.loads((root / "src/mycel/data/embedding-models.json").read_text())
#         self.assertEqual(contract["embeddingModels"], {name: row["dimensions"] for name, row in catalog["models"].items()})
#         self.assertEqual(contract["environment"], ["MYCEL_CONFIG", "MYCEL_GREP_PLAIN"])
#         examples = [part.split("\n```", 1)[0] for part in guide.split("```toml\n")[1:]]
#         self.assertEqual(len(examples), 2)
#         with tempfile.TemporaryDirectory() as directory:
#             path = Path(directory) / "config.toml"
#             for example in examples:
#                 path.write_text(example)
#                 snapshot = load_settings(path=path, home=Path(directory))
#                 snapshot.require_valid(require_store=False)
#                 self.assertEqual(set(snapshot.report()), set(contract["reportFields"]))
#             self.assertEqual(snapshot.values["drifts"]["review_command"][2], "~/literal-config.toml")
#             path.write_text('[drifts]\nthreshold = "private-sentinel"\n')
#             report = load_settings(path=path).report()
#             self.assertTrue(any(set(fault) == set(contract["faultFields"]) for fault in report["faults"]))
#             self.assertNotIn("private-sentinel", json.dumps(report))
# TEST-TIER-DISABLED-END tests/test_guides.py::GuideTests.test_settings_guide_contract_and_fictional_examples_match_validation

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:1
# import json
# TEST-TIER-IMPORTS-END tests/test_guides.py:1
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:2
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_guides.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:3
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_guides.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:6
# from mycel._commands import help_reply
# TEST-TIER-IMPORTS-END tests/test_guides.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:7
# from mycel._errors import ErrorCode
# TEST-TIER-IMPORTS-END tests/test_guides.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_guides.py:8
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_guides.py:8
