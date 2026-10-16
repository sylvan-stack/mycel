"""Verification option validation at the public command boundary."""

from io import StringIO
import json
import unittest
from unittest.mock import patch

from mycel._cli import Invocation, parse, run
from mycel._coverage import proves


class VerificationCliTests(unittest.TestCase):
    @proves("MYC-0.6")
    def test_exact_endpoint_and_voucher_options_survive_argument_parsing(self):
        endpoint = "cellar:@artifact/docs/net.md#Retry policy"
        self.assertEqual(parse(("confirm", endpoint)), Invocation("confirm", arguments=(endpoint,)))
        self.assertEqual(parse(("confirm", "--how", "check", endpoint, "--by", "Ana María")).arguments,
                         ("--by", "Ana María", "--how", "check", endpoint))
        self.assertEqual(parse(("verifications", "--repo", "Cellar", "--history")),
                         Invocation("verifications", ("Cellar",), arguments=("--history",)))
        self.assertEqual(parse(("verifications",)).arguments, ())

    @proves("MYC-0.6", "MYC-0.7")
    def test_invalid_verification_options_refuse_before_settings_or_store_access(self):
        cases = (("confirm",), ("confirm", "one", "two"),
                 ("confirm", "one", "--by", " "), ("confirm", "one", "--by"),
                 ("confirm", "one", "--how", "maybe"), ("confirm", "one", "--history"),
                 ("confirm", "one", "--repo", "cellar"), ("verifications", "extra"),
                 ("verifications", "--repo", "a", "--repo", "b"),
                 ("verifications", "--all"), ("verifications", "--how", "read"))
        with patch("mycel._cli.load_settings") as settings:
            for arguments in cases:
                output, diagnostic = StringIO(), StringIO()
                self.assertEqual(run(arguments, stdout=output, stderr=diagnostic), 1)
                self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
                self.assertEqual(diagnostic.getvalue(), "")
            settings.assert_not_called()

    @proves("MYC-0.6")
    def test_verification_help_is_available_without_configuration(self):
        with patch("mycel._cli.load_settings") as settings:
            for command, options in (("confirm", ("--by <name>", "--how read|check")),
                                     ("verifications", ("--repo <name>", "--history"))):
                output = StringIO()
                self.assertEqual(run((command, "--help"), stdout=output), 0)
                entry = json.loads(output.getvalue())["commands"][0]
                self.assertTrue(entry["available"])
                for option in options:
                    self.assertIn(option, entry["options"])
            settings.assert_not_called()
