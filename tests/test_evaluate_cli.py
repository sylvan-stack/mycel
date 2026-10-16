"""Public validation/dispatch acceptance before unavailable feature adapters."""

from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from mycel._cli import parse, run
from mycel._coverage import proves
from mycel._evaluate import evaluate


class EvaluateCliTests(unittest.TestCase):
    def configured(self, root, names=("a",)):
        config = root / "config.toml"
        config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n' +
            ''.join('[repos.' + name + ']\nenabled=true\nartifact_root=' + json.dumps(str(root / name)) +
                '\nevaluation="evaluation.toml"\n' for name in names))
        for name in names:
            (root / name).mkdir()
        return config

    def invoke(self, config, arguments, *, handler=None):
        output, diagnostic = StringIO(), StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}):
            status = run(arguments, handlers=None if handler is None else {"evaluate": handler},
                         stdout=output, stderr=diagnostic)
        return status, json.loads(output.getvalue()), diagnostic.getvalue()

    @proves("MYC-0.6", "MYC-0.7", "MYC-13.10")
    def test_kind_and_live_validation_and_help_precede_configuration_and_services(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("mycel._database.store_connection") as store, \
                patch("mycel._credentials.Credentials.embedding_key") as key, \
                patch("mycel._voyage._https_request") as provider:
            config = Path(directory) / "absent.toml"
            for tail in (("--kind", "unknown"), ("--kind",), ("--live",),
                         ("--kind", "retrieval", "--live"), ("extra",), ("--all",),
                         ("--repo", "a", "--repo", "b")):
                status, reply, diagnostic = self.invoke(config, ("evaluate", *tail))
                self.assertEqual((status, reply["error"]["code"], diagnostic), (1, "invalid_input", ""))
            status, reply, diagnostic = self.invoke(config, ("evaluate", "--help"))
            self.assertEqual((status, diagnostic), (0, ""))
            self.assertIn("--kind retrieval|drift", reply["commands"][0]["options"])
            self.assertEqual(parse(("evaluate",)).arguments, ("--kind", "retrieval"))
            self.assertEqual(parse(("evaluate", "--kind", "drift", "--live")).arguments,
                             ("--kind", "drift", "--live"))
            store.assert_not_called()
            key.assert_not_called()
            provider.assert_not_called()

    @proves("MYC-13.10", "MYC-0.6")
    def test_organization_and_disabled_scope_refuse_before_file_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.configured(root)
            checkout = root / "organization/a"
            (checkout / ".git").mkdir(parents=True)
            config.write_text(config.read_text() + '[organizations.group]\nroot=' +
                json.dumps(str(root / "organization")) + '\nartifact_root=' + json.dumps(str(root / "documents")) + '\n')
            with patch("mycel._evaluation.load_evaluation_file") as loading:
                status, reply, _ = self.invoke(config, ("evaluate", "--repo", "group"))
                self.assertEqual((status, reply["error"]["code"]), (1, "invalid_input"))
                with patch("mycel._scope.Path.cwd", return_value=root / "organization"):
                    status, reply, _ = self.invoke(config, ("evaluate",))
                self.assertEqual((status, reply["error"]["code"]), (1, "invalid_input"))
                config.write_text(config.read_text().replace("enabled=true", "enabled=false"))
                status, reply, _ = self.invoke(config, ("evaluate", "--repo", "a"))
                self.assertEqual((status, reply["error"]["code"]), (1, "refused"))
                loading.assert_not_called()

    @proves("MYC-13.10", "MYC-0.10")
    def test_empty_selected_sections_are_null_reports_without_any_service_or_write(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("mycel._database.store_connection") as store, \
                patch("mycel._credentials.Credentials.embedding_key") as key, \
                patch("mycel._voyage._https_request") as provider, \
                patch("mycel._activity.MutationActivity.session") as activity, \
                patch("mycel._build_identity.current_build", return_value=None):
            root = Path(directory)
            config = self.configured(root)
            evaluation = root / "a/evaluation.toml"
            evaluation.write_text("schema_version = 1\n")
            before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            for tail in ((), ("--kind", "drift"), ("--kind", "drift", "--live")):
                status, reply, diagnostic = self.invoke(config, ("evaluate", "--repo", "a", *tail))
                self.assertEqual((status, diagnostic), (0, ""))
                report = reply
                self.assertEqual(report["results"], [])
                self.assertEqual(report["build"], "development")
                if report["kind"] == "retrieval":
                    self.assertEqual(report["recall"], {"at3": None, "at10": None})
                    self.assertIsNone(report["indexFingerprint"])
                else:
                    self.assertIsNone(report["errorRate"])
                    self.assertIsNone(report["pipeline"])
                    self.assertFalse(report["qualified"])
            self.assertEqual(before, {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()})
            for mock in (store, key, provider, activity):
                mock.assert_not_called()

    @proves("MYC-13.10", "MYC-0.7")
    def test_unselected_section_faults_and_unreadable_files_precede_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.configured(root)
            evaluation = root / "a/evaluation.toml"
            pipeline = Mock()
            handler = lambda invocation: evaluate(invocation, drift=pipeline)
            for content in ('[[query]]\ntext=" "\nexpect=["a:doc.md#Heading"]\n',
                            '[[drift]]\nid="case"\nbefore="old"\ncurrent="new"\ndependant="text"\nexpect="needs_review"\nextra=1\n'):
                evaluation.write_text(content)
                status, reply, diagnostic = self.invoke(config, ("evaluate", "--repo", "a", "--kind", "drift"), handler=handler)
                self.assertEqual((status, reply["error"]["code"], diagnostic), (1, "invalid_input", ""))
                self.assertIn(str(evaluation), reply["error"]["message"])
            evaluation.unlink()
            status, reply, _ = self.invoke(config, ("evaluate", "--repo", "a"), handler=handler)
            self.assertEqual((status, reply["error"]["code"]), (1, "io"))
            pipeline.assert_not_called()

    @proves("MYC-13.10", "MYC-0.10")
    def test_nonempty_unavailable_pipelines_refuse_without_paid_or_store_work(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("mycel._database.store_connection") as store, \
                patch("mycel._credentials.Credentials.embedding_key") as key, \
                patch("mycel._voyage._https_request") as provider:
            root = Path(directory)
            config = self.configured(root)
            (root / "a/evaluation.toml").write_text('[[query]]\ntext="real question"\nexpect=["a:doc.md#Heading"]\n'
                '[[drift]]\nid="case"\nbefore="old"\ncurrent="new"\ndependant="text"\nexpect="needs_review"\n')
            before = {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}
            status, reply, diagnostic = self.invoke(config, ("evaluate", "--repo", "a", "--kind", "drift"))
            self.assertEqual((status, diagnostic), (0, ''))
            self.assertEqual((reply['kind'], reply['live'], reply['qualified'], reply['cases']),
                             ('drift', False, False, 1))
            self.assertEqual(reply['pipeline']['mode'], 'deterministic-stand-ins')
            self.assertEqual(reply['pipeline']['reviewer']['provider'], 'mycel-deterministic-stand-in')
            self.assertEqual(reply['results'][0]['actual'], 'needs_review')
            self.assertEqual((reply['usage'], reply['cost']), (None, None))
            status, reply, _ = self.invoke(config, ("evaluate", "--repo", "a", "--kind", "drift", "--live"))
            self.assertEqual(status, 0)
            self.assertEqual((reply['kind'], reply['live'], reply['qualified'], reply['cases']),
                             ('drift', True, False, 1))
            self.assertEqual(reply['batches'], [])
            self.assertEqual(reply['results'][0]['actual'], 'unresolved')
            self.assertEqual(reply['results'][0]['attempts'], 0)
            self.assertFalse(reply['results'][0]['processed'])
            self.assertTrue(any('reviewer' in reason for reason in reply['qualificationFailures']))
            self.assertEqual({str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}, before)
            for mock in (store, key, provider):
                mock.assert_not_called()
