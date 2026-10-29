"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_settings_cli as _support
# from test_settings_cli import (
#     Path,
#     SOURCE,
#     SettingsCliTests,
#     VALID,
#     os,
#     subprocess,
#     sys,
#     unittest,
# )


# class SettingsCliTests(_support.SettingsCliTests):
# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_info_reports_missing_and_invalid_settings_without_writes_or_values
#     def test_info_reports_missing_and_invalid_settings_without_writes_or_values(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             result = self.invoke(root, ["info"])
#             self.assertEqual(result.returncode, 0)
#             report = json.loads(result.stdout)["settings"]
#             self.assertFalse(report["exists"])
#             self.assertFalse(report["readable"])
#             self.assertEqual(list(root.iterdir()), [])
#             content = VALID + '[providers]\napi_key = "private-sentinel"\n'
#             result = self.invoke(root, ["info"], content=content)
#             self.assertEqual(result.returncode, 0)
#             report = json.loads(result.stdout)["settings"]
#             self.assertIn("providers.api_key", report["unknownKeys"])
#             self.assertNotIn(b"private-sentinel", result.stdout + result.stderr)
#             self.assertEqual((root / "config.toml").read_text(), content)
#             self.assertEqual([p.name for p in root.iterdir()], ["config.toml"])
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_info_reports_missing_and_invalid_settings_without_writes_or_values

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_invalid_settings_prevent_every_feature_handler_before_access
#     def test_invalid_settings_prevent_every_feature_handler_before_access(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / "config.toml"
#             content = VALID + '[embedding]\ndimensions = true\n[repos.sample]\nenabeld = "private-sentinel"\n'
#             config.write_text(content)
#             snapshot = load_settings(path=config)
#             touched = []
#             def access(invocation):
#                 touched.append(invocation.command)
#                 raise AssertionError("invalid settings reached service/index access")
#             commands = ("search", "ingest", "embed", "status", "repos", "stale", "refs", "derive",
#                         "confirm", "drifts", "relate", "verifications", "classify", "summaries",
#                         "overview", "read", "activity", "evaluate", "init")
#             with patch("mycel._cli.load_settings", return_value=snapshot) as load:
#                 for name in commands:
#                     out, err = io.StringIO(), io.StringIO()
#                     arguments = [name, "sample:@artifact/guide.md#Guide"] if name in {"confirm", "read"} else [name]
#                     self.assertEqual(run(arguments, handlers={name: access}, stdout=out, stderr=err), 1)
#                     reply = json.loads(out.getvalue())
#                     self.assertEqual(reply["error"]["code"], "settings")
#                     self.assertIn(str(config), reply["error"]["message"])
#                     self.assertIn("repos.sample.enabeld", reply["error"]["message"])
#                     self.assertNotIn("private-sentinel", out.getvalue() + err.getvalue())
#                 self.assertEqual(load.call_count, len(commands))
#             self.assertEqual(touched, [])
#             self.assertEqual(config.read_text(), content)
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_invalid_settings_prevent_every_feature_handler_before_access

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_each_handler_receives_one_immutable_snapshot_and_no_env_settings_override
#     def test_each_handler_receives_one_immutable_snapshot_and_no_env_settings_override(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / "config.toml"
#             initial = VALID + '[drifts]\ncandidates = 7\n'
#             config.write_text(initial)
#             read_bytes = Path.read_bytes
#             reads = []
#             def count_read(path):
#                 if path == config:
#                     reads.append(path)
#                 return read_bytes(path)
#             def handler(invocation):
#                 self.assertEqual(invocation.settings.values["drifts"]["candidates"], 7)
#                 self.assertEqual(invocation.settings.values["embedding"]["model"], "voyage-code-4")
#                 with self.assertRaises(TypeError):
#                     invocation.settings.values["drifts"]["candidates"] = 999
#                 # A caller edit during an operation cannot change its snapshot.
#                 config.write_text(VALID + '[drifts]\ncandidates = 8\n')
#                 self.assertEqual(invocation.settings.values["drifts"]["candidates"], 7)
#                 return Result({"snapshot": True})
#             with patch.dict(os.environ, {"MYCEL_CONFIG": str(config), "MYCEL_MODEL": "private-sentinel",
#                                          "MYCEL_PG_DSN": "private-sentinel", "MYCEL_REPO": "private-sentinel"}), \
#                     patch.object(Path, "read_bytes", count_read):
#                 out = io.StringIO()
#                 self.assertEqual(run(["search", "question"], handlers={"search": handler}, stdout=out), 0)
#             self.assertEqual(reads, [config])
#             self.assertEqual(json.loads(out.getvalue()), {"snapshot": True})
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_each_handler_receives_one_immutable_snapshot_and_no_env_settings_override

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_grep_handler_receives_invalid_snapshot_and_plain_flag_without_refusal
#     def test_grep_handler_receives_invalid_snapshot_and_plain_flag_without_refusal(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             invalid = load_settings(path=root / "missing.toml")
#             calls = []
#             def grep(invocation):
#                 self.assertIs(invocation.settings, invalid)
#                 self.assertTrue(invocation.grep_plain)
#                 calls.append(invocation.arguments)
#                 return StreamedResult(1)
#             with patch("mycel._cli.load_settings", return_value=invalid):
#                 out = io.StringIO()
#                 self.assertEqual(run(["grep", "--", "literal"], handlers={"grep": grep}, stdout=out), 1)
#                 self.assertEqual(out.getvalue(), "")
#             config = root / "valid.toml"
#             config.write_text(VALID)
#             valid = load_settings(path=config)
#             with patch("mycel._cli.load_settings", return_value=valid), \
#                     patch.dict(os.environ, {"MYCEL_GREP_PLAIN": "1"}):
#                 self.assertEqual(run(["grep", "literal"], handlers={"grep": lambda i:
#                                      StreamedResult(0 if i.grep_plain else 9)}, stdout=io.StringIO()), 0)
#             self.assertEqual(calls, [("--", "literal")])
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_grep_handler_receives_invalid_snapshot_and_plain_flag_without_refusal

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_real_grep_preserves_bytes_stdin_arguments_and_status_for_invalid_settings
#     def test_real_grep_preserves_bytes_stdin_arguments_and_status_for_invalid_settings(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             for args in (["-n", "needle"], ["-q", "absent"], ["--invalid-option"]):
#                 input = b"needle\nother\nneedle\xff\n"
#                 native = subprocess.run(["grep", *args], input=input, capture_output=True,
#                                         env={"PATH": os.defpath, "LC_ALL": "C"}, cwd=root)
#                 wrapped = self.invoke(root, ["grep", *args], input=input, extra={"LC_ALL": "C"})
#                 self.assertEqual(wrapped.returncode, native.returncode)
#                 self.assertEqual(wrapped.stdout, native.stdout)
#                 # argv[0] differs on some systems, but no Mycel JSON enters it.
#                 self.assertNotIn(b'"error"', wrapped.stderr)
#             self.assertFalse((root / "config.toml").exists())
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_real_grep_preserves_bytes_stdin_arguments_and_status_for_invalid_settings

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_plain_grep_uses_path_and_forwards_no_parent_credentials
#     def test_plain_grep_uses_path_and_forwards_no_parent_credentials(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             executable = root / "grep"
#             executable.write_text("#!" + sys.executable + "\nimport json,os,sys\n"
#                                   "print(json.dumps({'argv':sys.argv[1:],'stdin':sys.stdin.read(),"
#                                   "'leaked':[k for k in ['MYCEL_CONFIG','MYCEL_GREP_PLAIN','PGPASSWORD','VOYAGE_API_KEY','JEV_API_KEY'] if k in os.environ]}))\n"
#                                   "sys.exit(7)\n")
#             executable.chmod(0o700)
#             args = ["--", "$(not-executed)", "~literal"]
#             result = self.invoke(root, ["grep", *args], input=b"input\n",
#                                  extra={"PATH": str(root), "MYCEL_GREP_PLAIN": "1",
#                                         "PGPASSWORD": "private-sentinel", "VOYAGE_API_KEY": "private-sentinel",
#                                         "JEV_API_KEY": "private-sentinel"})
#             self.assertEqual(result.returncode, 7)
#             self.assertEqual(json.loads(result.stdout), {"argv": args, "stdin": "input\n", "leaked": []})
#             self.assertNotIn(b"private-sentinel", result.stdout + result.stderr)
#             self.assertFalse((root / "config.toml").exists())
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_plain_grep_uses_path_and_forwards_no_parent_credentials

# TEST-TIER-DISABLED-BEGIN tests/test_settings_cli.py::SettingsCliTests.test_settings_do_not_probe_reviewer_command_even_for_info
#     def test_settings_do_not_probe_reviewer_command_even_for_info(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             probe = root / "reviewer"
#             marker = root / "executed"
#             probe.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n")
#             probe.chmod(0o700)
#             content = VALID + '[drifts]\nreview_command = [' + json.dumps(str(probe)) + ']\nreview_provider = "example"\nreview_model = "example-model-2026-10-01"\nreview_revision = "v1"\n'
#             result = self.invoke(root, ["info"], content=content)
#             self.assertEqual(result.returncode, 0)
#             self.assertEqual(json.loads(result.stdout)["settings"]["faults"], [])
#             self.assertFalse(marker.exists())
# TEST-TIER-DISABLED-END tests/test_settings_cli.py::SettingsCliTests.test_settings_do_not_probe_reviewer_command_even_for_info


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:3
# import io
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:4
# import json
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:9
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:11
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:13
# from mycel._cli import Result, StreamedResult, run
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:13

# TEST-TIER-IMPORTS-BEGIN tests/test_settings_cli.py:14
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_settings_cli.py:14

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
