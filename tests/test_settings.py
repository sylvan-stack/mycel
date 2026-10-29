# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Settings acceptance with private files and no store or model access."""

import json
import tempfile
import unittest
from pathlib import Path

from mycel._errors import MycelError
from mycel._settings import load_settings

STORE = 'postgresql://mycel@localhost:5432/mycel'


def toml_value(value):
    """Encode the scalar/list fixtures without a TOML-writing dependency."""
    if type(value) is float and value != value:
        return "nan"
    if value == float("inf"):
        return "inf"
    if value == float("-inf"):
        return "-inf"
    if type(value) is dict:
        return "{ " + ", ".join(f"{key} = {toml_value(item)}" for key, item in value.items()) + " }"
    if type(value) is list:
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=True)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.counter = 0

    def write_settings(self, content="", *, store=True):
        self.counter += 1
        path = self.home / f"settings-{self.counter}.toml"
        prefix = f"[store]\naddress = {toml_value(STORE)}\n\n" if store else ""
        path.write_text(prefix + content, encoding="utf-8")
        return path

    def load(self, content="", *, store=True):
        return load_settings(path=self.write_settings(content, store=store), home=self.home)


    def assert_fault(self, snapshot, key=None):
        report = snapshot.report()
        self.assertFalse(snapshot.valid)
        self.assertTrue(report["faults"])
        if key is not None:
            self.assertIn(key, [fault.get("key") for fault in report["faults"]])
        with self.assertRaises(MycelError) as raised:
            snapshot.require_valid()
        self.assertEqual(raised.exception.code, "settings")
        self.assertIn(str(snapshot.file), str(raised.exception))
        if key is not None:
            self.assertIn(key, str(raised.exception))
        return report, raised.exception


    def reviewer_source(self, **changes):
        entries = {
            "review_command": ["/fixture/reviewer"], "review_provider": "example-provider",
            "review_model": "example-model-2026-10-01", "review_revision": "adapter-v1",
        }
        entries.update(changes)
        return "[drifts]\n" + "\n".join(f"{key} = {toml_value(value)}" for key, value in entries.items())



# Archived complete imports; restore needed names in their original scope, not at this file tail.
