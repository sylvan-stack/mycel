
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_hub_commands.py::HubCommandTests.test_retired_commands_unavailable_handlers_and_command_specific_options_fail
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Retired commands unavailable handlers and command specific options fail.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_hub_commands.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_retired_commands_unavailable_handlers_and_command_specific_options_fail(self):
#         text = ("`mycel sync` `mycel search --path src query` "
#                 "`mycel future` `mycel --made-up` `--retired-option`")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual([faults for _, faults in rows], [
#             ("unknown command",), ("unknown option --path",),
#             ("command is unavailable",), ("unknown command",),
#             ("unknown option --retired-option",)])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_hub_commands.py::HubCommandTests.test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Multiline inline and shell examples keep options and skip quoted query flags.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_hub_commands.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_multiline_inline_and_shell_examples_keep_options_and_skip_quoted_query_flags(self):
#         text = ("# Example\n`mycel search --repo <repo>\n[--no-fresh]`\n"
#                 "```sh\nmycel search --repo fixture \\\n  --no-fresh '--query-content'\n```\n")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual(len(rows), 2)
#         self.assertEqual([row.line for row, _ in rows], [2, 5])
#         for mention, faults in rows:
#             self.assertEqual(mention.options, ("--repo", "--no-fresh"))
#             self.assertEqual(faults, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_hub_commands.py::HubCommandTests.test_grep_options_are_delegated_and_file_names_are_not_commands
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Grep options are delegated and file names are not commands.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_hub_commands.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_grep_options_are_delegated_and_file_names_are_not_commands(self):
#         text = ("`src/mycel/file.py` `mycel …` `mycel --help` "
#                 "`mycel grep -rn --regexp=needle src`")
#         rows = AUDIT["audit"](text, HELP)
#         self.assertEqual([mention.command for mention, _ in rows], ["--help", "grep"])
#         self.assertEqual([faults for _, faults in rows], [(), ()])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_hub_commands.py::HubCommandTests.test_cli_executes_only_help_and_refuses_missing_files_or_invalid_help
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Cli executes only help and refuses missing files or invalid help.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_hub_commands.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END
