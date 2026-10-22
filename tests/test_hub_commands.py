"""Portable command-audit regressions; no owner corpus or installed CLI needed."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import runpy
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from mycel._coverage import proves


AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                          "scripts/check_hub_commands.py"), run_name="hub_audit")
HELP = {"program": "mycel", "options": ["--help"], "commands": [
    {"name": "search", "available": True, "rawArguments": False,
     "options": ["--help", "--repo <name>", "--no-fresh"]},
    {"name": "grep", "available": True, "rawArguments": True, "options": []},
    {"name": "future", "available": False, "rawArguments": False, "options": []},
]}


class HubCommandTests(unittest.TestCase):
    @proves("MYC-0.12")
    def test_retired_commands_unavailable_handlers_and_command_specific_options_fail(self):
        text = ("`mycel sync` `mycel search --path src query` "
                "`mycel future` `mycel --made-up` `--retired-option`")
        rows = AUDIT["audit"](text, HELP)
        self.assertEqual([faults for _, faults in rows], [
            ("unknown command",), ("unknown option --path",),
            ("command is unavailable",), ("unknown command",),
            ("unknown option --retired-option",)])

    @proves("MYC-0.12")
    def test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags(self):
        text = ("# Example\n`mycel search --repo <repo>\n[--no-fresh]`\n"
                "```sh\nmycel search --repo fixture \\\n  --no-fresh '--query-content'\n```\n")
        rows = AUDIT["audit"](text, HELP)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row.line for row, _ in rows], [2, 5])
        for mention, faults in rows:
            self.assertEqual(mention.options, ("--repo", "--no-fresh"))
            self.assertEqual(faults, ())

    @proves("MYC-0.12")
    def test_grep_options_are_delegated_and_file_names_are_not_commands(self):
        text = ("`src/mycel/file.py` `mycel …` `mycel --help` "
                "`mycel grep -rn --regexp=needle src`")
        rows = AUDIT["audit"](text, HELP)
        self.assertEqual([mention.command for mention, _ in rows], ["--help", "grep"])
        self.assertEqual([faults for _, faults in rows], [(), ()])

    @proves("MYC-0.12")
    def test_cli_executes_only_help_and_refuses_missing_files_or_invalid_help(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in AUDIT["FILES"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("`mycel search --no-fresh '--not-an-option'`\n")
            completed = CompletedProcess([], 0, json.dumps(HELP), "")
            with patch("subprocess.run", return_value=completed) as process:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(AUDIT["main"](["--corpus", directory,
                                                  "--program", "fixture-mycel"]), 0)
                process.assert_called_once_with(["fixture-mycel", "--help"],
                    capture_output=True, text=True, timeout=30, check=True)
            (root / "README.md").unlink()
            with patch("subprocess.run", return_value=completed):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(AUDIT["main"](["--corpus", directory]), 1)
            with patch("subprocess.run", return_value=CompletedProcess([], 0, "{}", "")):
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(AUDIT["main"](["--corpus", directory]), 1)
