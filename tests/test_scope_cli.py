"""Scope and repository reports through the CLI's JSON boundary."""

from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel._cli import for_repositories, run
from mycel._errors import MycelError


class ScopeCliTests(unittest.TestCase):
    def invoke(self, config, arguments, *, handlers=None):
        output = StringIO()
        with patch.dict("os.environ", {"MYCEL_CONFIG": str(config)}):
            status = run(arguments, handlers=handlers, stdout=output, stderr=StringIO())
        return status, json.loads(output.getvalue())

    def test_repos_reads_current_settings_and_reports_faults_without_store_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            head = '[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
            config.write_text(head + '[repos.Enabled]\nenabled=true\nartifact_root="' + directory + '"\n'
                              '[repos.disabled]\n[repos.faulty]\nenabled=true\n')
            before = config.read_bytes()
            status, reply = self.invoke(config, ["repos"])
            self.assertEqual(status, 0)
            self.assertEqual(config.read_bytes(), before)
            by_name = {row["name"]: row for row in reply["repositories"]}
            self.assertTrue(by_name["Enabled"]["enabled"])
            self.assertEqual(by_name["Enabled"]["documents"]["from"], "repository")
            self.assertFalse(by_name["disabled"]["enabled"])
            self.assertIn("fault", by_name["faulty"])
            config.write_text(head + '[repos.Enabled]\nenabled=false\nartifact_root="' + directory + '"\n')
            status, reply = self.invoke(config, ["repos"])
            self.assertEqual(status, 0)
            self.assertEqual([row["name"] for row in reply["repositories"]], ["Enabled"])
            self.assertFalse(reply["repositories"][0]["enabled"])
            self.assertEqual([path.name for path in root.iterdir()], ["config.toml"])

    def test_selector_and_folder_faults_leave_unrelated_operations_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.valid]\nenabled=true\nartifact_root="' + directory + '"\n'
                              '[repos.bad]\nenabled=true\n')
            started = []
            def operation(repository):
                started.append(repository.name)
                return {"read": str(repository.documents.path)}
            handler = lambda invocation: for_repositories(invocation, operation)
            status, reply = self.invoke(config, ["ingest", "--repo", "missing", "--repo", "bad",
                                                "--repo", "valid", "--repo", "valid"],
                                        handlers={"ingest": handler})
            self.assertEqual(status, 1)
            self.assertEqual(started, ["valid"])
            entries = {entry["repository"]: entry for entry in reply["repositories"]}
            self.assertEqual(entries["missing"]["error"]["code"], "unknown_repository")
            self.assertEqual(entries["bad"]["error"]["code"], "settings")
            self.assertIn("result", entries["valid"])
            status, reply = self.invoke(config, ["ingest", "--repo", "bad"], handlers={"ingest": handler})
            self.assertEqual(status, 1)
            self.assertEqual(set(reply), {"repositories"})
            self.assertEqual(reply["repositories"][0]["error"]["code"], "settings")

    def test_shared_store_preflight_failure_is_one_error_before_any_repository_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.valid]\nenabled=true\nartifact_root="' + directory + '"\n')
            touched = []
            for code in ("store_unavailable", "store_format"):
                def preflight():
                    raise MycelError(code, "A fictional store cannot start this invocation.")
                handler = lambda invocation: for_repositories(invocation, lambda repository: touched.append(repository.name),
                                                               prepare=preflight)
                status, reply = self.invoke(config, ["ingest", "--repo", "valid"], handlers={"ingest": handler})
                self.assertEqual(status, 1)
                self.assertEqual(set(reply), {"error"})
                self.assertEqual(reply["error"]["code"], code)
                self.assertEqual(touched, [])

    def test_started_operation_errors_keep_per_repository_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.valid]\nenabled=true\nartifact_root="' + directory + '"\n')
            def operation(repository):
                raise MycelError("busy", "A fictional repository lock is held.")
            handler = lambda invocation: for_repositories(invocation, operation)
            status, reply = self.invoke(config, ["ingest", "--repo", "valid"], handlers={"ingest": handler})
            self.assertEqual(status, 1)
            self.assertEqual(reply["repositories"][0]["error"]["code"], "busy")

    def test_repos_unimplemented_removal_and_extra_arguments_have_closed_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n')
            for args, code in ((["repos", "remove"], "invalid_input"), (["repos", "extra"], "invalid_input")):
                status, reply = self.invoke(config, args)
                self.assertEqual(status, 1)
                self.assertEqual(reply["error"]["code"], code)
            _, help = self.invoke(config, ["repos", "--help"])
            self.assertTrue(help["commands"][0]["available"])


if __name__ == "__main__":
    unittest.main()
