
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_verification_cli.py::VerificationCliTests.test_exact_endpoint_and_voucher_options_survive_argument_parsing
# Reason: Copies the parser invocation record for valid flags without exercising confirmation or history.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_verification_cli.py
# Retained evidence at review: tests/test_verification_commands.py exercises real confirm dispatch and history with explicit/default vouchers.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_endpoint_and_voucher_options_survive_argument_parsing(self):
#         endpoint = "cellar:@artifact/docs/net.md#Retry policy"
#         self.assertEqual(parse(("confirm", endpoint)), Invocation("confirm", arguments=(endpoint,)))
#         self.assertEqual(parse(("confirm", "--how", "check", endpoint, "--by", "Ana María")).arguments,
#                          ("--by", "Ana María", "--how", "check", endpoint))
#         self.assertEqual(parse(("verifications", "--repo", "Cellar", "--history")),
#                          Invocation("verifications", ("Cellar",), arguments=("--history",)))
#         self.assertEqual(parse(("verifications",)).arguments, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_verification_cli.py::VerificationCliTests.test_verification_help_is_available_without_configuration
# Reason: Checks copied help option strings for two commands; the generic clean-environment help case already establishes configuration-free help.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_verification_cli.py
# Retained evidence at review: CliTests.test_clean_environment_finite_help_and_refusal; invalid verification options remain.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_verification_help_is_available_without_configuration(self):
#         with patch("mycel._cli.load_settings") as settings:
#             for command, options in (("confirm", ("--by <name>", "--how read|check")),
#                                      ("verifications", ("--repo <name>", "--history"))):
#                 output = StringIO()
#                 self.assertEqual(run((command, "--help"), stdout=output), 0)
#                 entry = json.loads(output.getvalue())["commands"][0]
#                 self.assertTrue(entry["available"])
#                 for option in options:
#                     self.assertIn(option, entry["options"])
#             settings.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END
