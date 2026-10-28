"""Portable command-audit regressions; no owner corpus or installed CLI needed."""

import runpy
import unittest
from pathlib import Path

AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                          "scripts/check_hub_commands.py"), run_name="hub_audit")
HELP = {"program": "mycel", "options": ["--help"], "commands": [
    {"name": "search", "available": True, "rawArguments": False,
     "options": ["--help", "--repo <name>", "--no-fresh"]},
    {"name": "grep", "available": True, "rawArguments": True, "options": []},
    {"name": "future", "available": False, "rawArguments": False, "options": []},
]}


class HubCommandTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_hub_commands.py::HubCommandTests.test_retired_commands_unavailable_handlers_and_command_specific_options_fail
#     def test_retired_commands_unavailable_handlers_and_command_specific_options_fail(self):
#         text = ("`mycel sync` `mycel search --path src query` "
#                 "`mycel future` `mycel --made-up` `--retired-option`")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual([faults for _, faults in rows], [
#             ("unknown command",), ("unknown option --path",),
#             ("command is unavailable",), ("unknown command",),
#             ("unknown option --retired-option",)])
# TEST-TIER-DISABLED-END tests/test_hub_commands.py::HubCommandTests.test_retired_commands_unavailable_handlers_and_command_specific_options_fail

# TEST-TIER-DISABLED-BEGIN tests/test_hub_commands.py::HubCommandTests.test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags
#     def test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags(self):
#         text = ("# Example\n`mycel search --repo <repo>\n[--no-fresh]`\n"
#                 "```sh\nmycel search --repo fixture \\\n  --no-fresh '--query-content'\n```\n")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual(len(rows), 2)
#         self.assertEqual([row.line for row, _ in rows], [2, 5])
#         for mention, faults in rows:
#             self.assertEqual(mention.options, ("--repo", "--no-fresh"))
#             self.assertEqual(faults, ())
# TEST-TIER-DISABLED-END tests/test_hub_commands.py::HubCommandTests.test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags

# TEST-TIER-DISABLED-BEGIN tests/test_hub_commands.py::HubCommandTests.test_grep_options_are_delegated_and_file_names_are_not_commands
#     def test_grep_options_are_delegated_and_file_names_are_not_commands(self):
#         text = ("`src/mycel/file.py` `mycel …` `mycel --help` "
#                 "`mycel grep -rn --regexp=needle src`")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual([mention.command for mention, _ in rows], ["--help", "grep"])
#         self.assertEqual([faults for _, faults in rows], [(), ()])
# TEST-TIER-DISABLED-END tests/test_hub_commands.py::HubCommandTests.test_grep_options_are_delegated_and_file_names_are_not_commands

# TEST-TIER-DISABLED-BEGIN tests/test_hub_commands.py::HubCommandTests.test_cli_executes_only_help_and_refuses_missing_files_or_invalid_help
#     def test_cli_executes_only_help_and_refuses_missing_files_or_invalid_help(self):
#         import json
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             for name in AUDIT["FILES"]:
#                 path = root / name
#                 path.parent.mkdir(parents=True, exist_ok=True)
#                 path.write_text("`mycel search --no-fresh '--not-an-option'`\n")
#             completed = CompletedProcess([], 0, json.dumps(HELP), "")
#             with patch("subprocess.run", return_value=completed) as process:
#                 with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
#                     self.assertEqual(AUDIT["main"](["--corpus", directory,
#                                                   "--program", "fixture-mycel"]), 0)
#                 process.assert_called_once_with(["fixture-mycel", "--help"],
#                     capture_output=True, text=True, timeout=30, check=True)
#             (root / "README.md").unlink()
#             with patch("subprocess.run", return_value=completed):
#                 with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
#                     self.assertEqual(AUDIT["main"](["--corpus", directory]), 1)
#             with patch("subprocess.run", return_value=CompletedProcess([], 0, "{}", "")):
#                 with redirect_stderr(io.StringIO()):
#                     self.assertEqual(AUDIT["main"](["--corpus", directory]), 1)
# TEST-TIER-DISABLED-END tests/test_hub_commands.py::HubCommandTests.test_cli_executes_only_help_and_refuses_missing_files_or_invalid_help

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_hub_commands.py:3
# from contextlib import redirect_stderr, redirect_stdout
# TEST-TIER-IMPORTS-END tests/test_hub_commands.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_hub_commands.py:4
# import io
# TEST-TIER-IMPORTS-END tests/test_hub_commands.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_hub_commands.py:7
# from subprocess import CompletedProcess
# TEST-TIER-IMPORTS-END tests/test_hub_commands.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_hub_commands.py:8
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_hub_commands.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_hub_commands.py:10
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_hub_commands.py:10
