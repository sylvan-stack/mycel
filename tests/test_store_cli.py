"""Command integration with stand-ins; these do not qualify SQL acceptance."""

from contextlib import contextmanager
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel._cli import run
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._settings import load_settings
from mycel._store import InitResult, StoreInspection, STORE_FORMAT


class StoreCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "config.toml"
        self.address = "postgresql://fixture@localhost/private_fixture?sslmode=disable"
        self.path.write_text('[store]\naddress=' + json.dumps(self.address) + '\n[embedding]\ndimensions=256\n')
        self.snapshot = load_settings(path=self.path)

    def invoke(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with patch("mycel._cli.load_settings", return_value=self.snapshot):
            status = run(arguments, stdout=out, stderr=err)
        return status, json.loads(out.getvalue()), err.getvalue()

    @proves("MYC-6.2", "MYC-6.4", "MYC-5.11")
    def test_init_uses_one_snapshot_and_private_connection_without_child_forwarding(self):
        connection = object()
        @contextmanager
        def connect(credentials):
            self.assertEqual(credentials.store_target().address, self.address)
            yield connection
        before = StoreInspection("empty")
        after = StoreInspection("current", STORE_FORMAT, 256, "b45a9826-caca-4481-a4b0-8d60c55d9894")
        with patch("mycel._database.store_connection", connect), \
                patch("mycel._store.initialize_store", return_value=InitResult(before, after, True)) as initialize, \
                patch("mycel._build_identity.current_build", return_value=None), \
                patch("subprocess.Popen") as child:
            status, result, error = self.invoke(["init"])
        self.assertEqual(status, 0)
        self.assertEqual(result["store"], self.address)
        self.assertEqual(result["indexGeneration"], after.index_generation)
        self.assertEqual(result["dimensions"], {"before": None, "after": 256})
        initialize.assert_called_once_with(connection, dimensions=256)
        child.assert_not_called()
        self.assertEqual(error, "")

    @proves("MYC-6.2", "MYC-5.11")
    def test_info_keeps_unavailable_and_newer_store_diagnostics_successful(self):
        with patch("mycel._database.store_connection", side_effect=MycelError("store_unavailable", "Store unavailable.")):
            status, result, error = self.invoke(["info"])
        self.assertEqual(status, 0)
        self.assertEqual(result["store"]["state"], "unavailable")
        self.assertEqual(result["store"]["location"], self.address)
        @contextmanager
        def connect(credentials):
            yield object()
        with patch("mycel._database.store_connection", connect), \
                patch("mycel._store.inspect_store", return_value=StoreInspection("newer", STORE_FORMAT + 1, 256, "generation")), \
                patch("mycel._store.initialize_store") as initialize:
            status, result, error = self.invoke(["info"])
        self.assertEqual(status, 0)
        self.assertEqual(result["store"]["format"], STORE_FORMAT + 1)
        initialize.assert_not_called()

    @proves("MYC-5.11", "MYC-6.4")
    def test_invalid_init_arguments_and_settings_stop_before_connection(self):
        with patch("mycel._database.store_connection") as connect:
            status, result, error = self.invoke(["init", "unexpected"])
            self.assertEqual((status, result["error"]["code"]), (1, "invalid_input"))
            self.path.write_text('[store]\naddress="postgresql://fixture:private-sentinel@localhost/fixture"\n')
            self.snapshot = load_settings(path=self.path)
            status, result, error = self.invoke(["init"])
            self.assertEqual((status, result["error"]["code"]), (1, "settings"))
            status, result, error = self.invoke(["info"])
            self.assertEqual(status, 0)
            self.assertNotIn("private-sentinel", json.dumps(result) + error)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
