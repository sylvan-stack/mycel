"""Check that a recoverable plan fault leaves later diagnostics visible."""

from contextlib import contextmanager, nullcontext
import io
import json
import os
from unittest.mock import Mock, patch

import test_capture as support

from mycel._cli import run
from mycel._credentials import Credentials


class PlanCheckTests(support.TemporaryGitCaptureTests):
    def test_reports_ordered_faults_and_preserves_inputs(self):
        self.write(self.code, "src/present.py", b"# existing\r\n")
        outside = self.write(self.home, "outside.py", b"# outside\r\n")
        link = self.code / "src/escape.py"
        link.symlink_to(outside)
        beat = self.write(self.home, "SAMPLE-1.md", """# SAMPLE-1 · Verify a plan

## Plan

- [x] 1. Use existing and planned source.
      Files: `fixture:src/present.py`, `fixture:src/planned.py`. Serves SAMPLE-1.1.
- [?] 2. Report faults even on a malformed step.
      Files: `fixture:missing/new.py`. Serves SAMPLE-1.2.
- [ ] 3. Check the symlink and both decision IDs.
      Files: `fixture:src/escape.py`. Serves SAMPLE-D1 and SAMPLE-D2.
""")
        settings = self.settings(artifact=False).file
        before = self.state()
        fixture_files = (beat, outside, settings)
        fixture_bytes = [path.read_bytes() for path in fixture_files]

        in_snapshot = False

        @contextmanager
        def read_only_snapshot(_connection):
            nonlocal in_snapshot
            in_snapshot = True
            try:
                yield
            finally:
                in_snapshot = False

        def read(sql, parameters):
            self.assertTrue(in_snapshot)
            self.assertTrue(sql.lstrip().startswith("SELECT "))
            self.assertEqual(parameters, (["SAMPLE-1.1", "SAMPLE-1.2", "SAMPLE-D1", "SAMPLE-D2"],))
            return Mock(fetchall=Mock(return_value=[("SAMPLE-1.1",), ("SAMPLE-D1",)]))

        connection = Mock(spec_set=["execute"])
        connection.execute.side_effect = read
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"MYCEL_CONFIG": str(settings)}),
            patch("mycel._plan_check.invocation_store", return_value=nullcontext((connection, None))),
            patch("mycel._plan_check.read_snapshot", side_effect=read_only_snapshot) as snapshot,
            patch.object(Credentials, "embedding_key", side_effect=AssertionError("unexpected model call")) as embedding,
            patch.object(Credentials, "jev_key", side_effect=AssertionError("unexpected model call")) as jev,
        ):
            status = run(["plan", "check", str(beat)], stdout=stdout, stderr=stderr)

        self.assertEqual((status, stderr.getvalue()), (0, ""), stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue()), {
            "beat": "SAMPLE-1",
            "steps": [
                {"number": "1", "done": True},
                {"number": "2", "done": False},
                {"number": "3", "done": False},
            ],
            "problems": [
                {"step": "2", "kind": "form", "detail": "Use a checkbox list item for each step."},
                {"step": "2", "kind": "file", "detail": "fixture:missing/new.py: Neither the path nor its containing folder exists."},
                {"step": "2", "kind": "origin", "detail": "SAMPLE-1.2 does not resolve to an indexed requirement or decision."},
                {"step": "3", "kind": "file", "detail": "fixture:src/escape.py: The path resolves outside its configured code checkout."},
                {"step": "3", "kind": "origin", "detail": "SAMPLE-D2 does not resolve to an indexed requirement or decision."},
            ],
        })
        snapshot.assert_called_once_with(connection)
        self.assertEqual(connection.execute.call_count, 1)
        embedding.assert_not_called()
        jev.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual([path.read_bytes() for path in fixture_files], fixture_bytes)
        self.assertEqual(link.readlink(), outside)
        self.assertFalse((self.code / "src/planned.py").exists())
        self.assertFalse((self.code / "missing").exists())
