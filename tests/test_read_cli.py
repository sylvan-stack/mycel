"""Finite exact-read command syntax and Build capability description."""

import unittest


class ReadCliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_read_cli.py::ReadCliTests.test_cli_keeps_a_source_ref_or_identifier_context_and_skipped_check_explicit
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
# TEST-TIER-DISABLED-END tests/test_read_cli.py::ReadCliTests.test_cli_keeps_a_source_ref_or_identifier_context_and_skipped_check_explicit

# TEST-TIER-DISABLED-BEGIN tests/test_read_cli.py::ReadCliTests.test_info_names_the_running_build_commands_and_read_reply_without_a_capabilities_command
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
# TEST-TIER-DISABLED-END tests/test_read_cli.py::ReadCliTests.test_info_names_the_running_build_commands_and_read_reply_without_a_capabilities_command

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:3
# import io
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:4
# import json
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:5
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:6
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:8
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:10
# from mycel._cli import parse, run
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:11
# from mycel._commands import COMMANDS, help_reply
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_read_cli.py:12
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_read_cli.py:12
