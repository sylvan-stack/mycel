"""Report-only overview argument and scope boundaries."""

from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel._cli import parse, run
from mycel._errors import MycelError
from mycel._overview import handle_overview, overview_repository
from mycel._settings import load_settings


class OverviewCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config.toml"
        self.config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
            '[organizations.team]\nroot=' + json.dumps(str(self.root / "team")) + '\n'
            '[repos.example]\nenabled=true\ncode_root=' +
            json.dumps(str(self.root / "team" / "example")) + '\n'
            '[repos.disabled]\nenabled=false\ncode_root=' +
            json.dumps(str(self.root / "disabled")) + '\n')
        self.settings = load_settings(path=self.config, home=self.root)
        self.settings.require_valid()

    def test_directory_options_are_normalized_and_escape_is_rejected_before_store_access(self):
        for value, expected in ((".", "."), ("src/./net", "src/net"),
                ("src/cache/../net", "src/net"), ("src/net/", "src/net")):
            self.assertEqual(parse(["overview", "--repo", "example", "--dir", value]).arguments,
                             ("--dir", expected))
        with patch("mycel._cli.invocation_store") as store:
            for args in (["overview", "extra"], ["overview", "--all"],
                    ["overview", "--repo", "example", "--repo", "example"],
                    *(["overview", "--dir", value] for value in
                      ("/tmp", "..", "src/../../outside", "", "src\x00net"))):
                with self.subTest(arguments=args), self.assertRaises(MycelError) as error:
                    parse(args)
                self.assertEqual(error.exception.code.value, "invalid_input")
            store.assert_not_called()

    def test_stored_report_returns_empty_without_folders_freshness_embedding_or_writes(self):
        connection = object()
        observations = []
        @contextmanager
        def store(invocation):
            observations.append(("store", invocation.command))
            yield connection, None
        @contextmanager
        def snapshot(supplied):
            self.assertIs(supplied, connection)
            observations.append(("snapshot",))
            yield
        self.assertFalse((self.root / "team").exists())
        before = self.config.read_bytes()
        with patch("mycel._cli.invocation_store", side_effect=store), \
                patch("mycel._overview.snapshot_transaction", side_effect=snapshot), \
                patch("mycel._overview.OverviewStore") as catalog, \
                patch("mycel._ingest.ingest") as ingest, \
                patch("mycel._embed.embed") as embed, \
                patch.dict("os.environ", {"MYCEL_CONFIG": str(self.config)}):
            catalog.return_value.sections.return_value = []
            output, diagnostic = StringIO(), StringIO()
            status = run(["overview", "--repo", "example", "--dir", "missing"],
                         stdout=output, stderr=diagnostic)
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), {"repository": "example", "sections": []})
            self.assertEqual(diagnostic.getvalue(), "")
            catalog.assert_called_once_with(connection, location="disk")
            catalog.return_value.sections.assert_called_once_with("example", "missing")
            ingest.assert_not_called()
            embed.assert_not_called()
        self.assertEqual(observations, [("store", "overview"), ("snapshot",)])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.config])

    def test_repository_scope_is_single_enabled_and_explicit_reports_need_no_folder(self):
        self.assertEqual(overview_repository(self.settings, ("example",)), "example")
        self.assertEqual(overview_repository(self.settings, cwd=self.root / "team" / "example"), "example")
        for names, cwd in ((("team",), None), ((), self.root / "team"),
                (("example", "example"), None), (("disabled",), None), (("unknown",), None)):
            with self.subTest(names=names, cwd=cwd), self.assertRaises(MycelError):
                overview_repository(self.settings, names, cwd=cwd)
        with patch("mycel._cli.invocation_store") as store:
            invalid = replace(parse(["overview", "--repo", "example"]),
                              arguments=("--dir", "../escape"), settings=self.settings)
            with self.assertRaises(MycelError) as error:
                handle_overview(invalid)
            self.assertEqual(error.exception.code.value, "invalid_input")
            store.assert_not_called()
