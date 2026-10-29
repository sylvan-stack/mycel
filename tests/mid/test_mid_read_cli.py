
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_read_cli.py::ReadCliTests.test_cli_keeps_a_source_ref_or_identifier_context_and_skipped_check_explicit
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Cli keeps a source ref or identifier context and skipped check explicit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_read_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cli_keeps_a_source_ref_or_identifier_context_and_skipped_check_explicit(self):
#         place = "fixture:@artifact/docs/guide.md#Limits%20%3E%20Backoff"
#         invocation = parse(["read", place, "--context", "5", "--no-fresh"])
#         self.assertEqual(invocation.command, "read")
#         self.assertEqual(invocation.arguments, (place, "--context", "5", "--no-fresh"))
#         by_id = parse(["read", "--id", "01JB2M0000000000000000000A", "--no-fresh"])
#         self.assertEqual(by_id.arguments, ("--id", "01JB2M0000000000000000000A", "--no-fresh"))
#         selected = parse(["read", "--repo", "fixture", "note.md#Note", "--context", "0"])
#         self.assertEqual(selected.repositories, ("fixture",))
#         self.assertEqual(selected.arguments, ("note.md#Note", "--context", "0"))
#         for args in (["read"], ["read", place, "--id", "also-id"], ["read", "--id", ""],
#                      ["read", place, "--context", "51"], ["read", place, "--context", "-1"],
#                      ["read", place, "--context", "1.5"],
#                      ["read", place, "--repo", "fixture", "--repo", "other"]):
#             with self.subTest(args=args), self.assertRaises(MycelError) as error:
#                 parse(args)
#             self.assertEqual(error.exception.code, "invalid_input")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_read_cli.py::ReadCliTests.test_info_names_the_running_build_commands_and_read_reply_without_a_capabilities_command
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Info names the running build commands and read reply without a capabilities command.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_read_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_info_names_the_running_build_commands_and_read_reply_without_a_capabilities_command(self):
#         with tempfile.TemporaryDirectory(prefix="mycel_read_info_") as directory:
#             missing = Path(directory) / "absent.toml"
#             output, errors = io.StringIO(), io.StringIO()
#             with patch.dict("os.environ", {"MYCEL_CONFIG": str(missing)}):
#                 self.assertEqual(run(["info"], stdout=output, stderr=errors), 0)
#             reply = json.loads(output.getvalue())
#         self.assertEqual(reply["readReply"], 1)
#         self.assertEqual(reply["commands"], [command.name for command in COMMANDS])
#         self.assertIn("read", reply["commands"])
#         self.assertNotIn("capabilities", reply["commands"])
#         self.assertEqual(errors.getvalue(), "")
#         help_commands = {item["name"]: item for item in help_reply()["commands"]}
#         self.assertTrue(help_commands["read"]["available"])
#         self.assertNotIn("capabilities", help_commands)
#         with self.assertRaises(MycelError) as error:
#             parse(["capabilities"])
#         self.assertEqual(error.exception.code, "invalid_input")
# LOW-TIER-SOURCE-END
# LOW-TIER-END
