"""Check the file-pieces interface against disposable Git inputs."""

import io
import json
import os
from hashlib import sha256
from unittest.mock import patch

import test_capture as support

from mycel._capture import capture_repository
from mycel._cli import run
from mycel._code import code_identity_key


class FilePiecesTests(support.TemporaryGitCaptureTests):
    def pieces(self, settings, address, *, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(settings.file)}):
            status = run(["pieces", address], stdout=stdout, stderr=stderr)
        reply = json.loads(stdout.getvalue())
        self.assertEqual(status, int(error is not None), (reply, stderr.getvalue()))
        if error is not None:
            self.assertEqual(reply["error"]["code"], error)
        return reply

    def test_working_and_head_match_ingest_across_rename_and_body_edit(self):
        path = "worker.py"
        address = f"fixture:@code/{path}"
        original = b"def before():\r\n    return 'initial'\r\n"
        renamed = b"def after():\r\n    return 'initial'\r\n"
        edited = renamed.replace(b"'initial'", b"'edited'")
        self.write(self.code, path, original)
        self.write(
            self.code,
            "guide.md",
            "# Fixture guide\n\nA document has no declaration key.\n",
        )
        self.commit()
        head = self.git("rev-parse", "HEAD")
        self.write(self.code, path, renamed.replace(b"'initial'", b"'staged'"))
        self.git("add", "--", path)
        self.write(self.code, path, renamed)
        settings = self.settings(artifact=False)
        before = self.state()

        reply = self.pieces(settings, address)
        self.assertEqual((reply["path"], reply["headCommit"]), (address, head))
        manifest = capture_repository(settings, "fixture")
        self.assertTrue(manifest.complete, manifest.diagnostics)
        committed = next(
            location for location in manifest.locations if location.commit == head
        )
        for side, location, source in (
            ("working", manifest.disk, renamed),
            ("committed", committed, original),
        ):
            captured = next(
                file for file in location.files if file.primary.path == path
            )
            self.assertEqual(captured.source, source)
            self.assertEqual(
                reply[side],
                {
                    "present": True,
                    "pieces": [
                        {
                            "name": chunk.symbol,
                            "lineStart": chunk.line_start,
                            "lineEnd": chunk.line_end,
                            "sha256": sha256(
                                source[chunk.byte_start : chunk.byte_end]
                            ).hexdigest(),
                            "renameKey": code_identity_key(chunk),
                        }
                        for chunk in captured.parsed
                    ],
                },
            )
        (working,) = reply["working"]["pieces"]
        (saved,) = reply["committed"]["pieces"]
        self.assertEqual((working["name"], saved["name"]), ("after", "before"))
        self.assertIsNotNone(working["renameKey"])
        self.assertEqual(working["renameKey"], saved["renameKey"])
        self.assertNotEqual(working["sha256"], saved["sha256"])
        guide = self.pieces(settings, "fixture:@code/guide.md")
        self.assertTrue(guide["working"]["pieces"])
        self.assertTrue(
            all(piece["renameKey"] is None for piece in guide["working"]["pieces"])
        )
        self.assertEqual(self.state(), before)

        self.write(self.code, path, edited)
        before = self.state()
        after = self.pieces(settings, address)
        self.assertEqual(after["committed"], reply["committed"])
        (changed,) = after["working"]["pieces"]
        self.assertNotEqual(changed["renameKey"], working["renameKey"])
        self.assertEqual(self.state(), before)

    def test_absent_and_unsafe_versions_are_distinct_without_mutation(self):
        absent = {"present": False, "pieces": []}
        address = "fixture:@code/worker.py"
        file = self.write(self.code, "worker.py", "def committed():\n    return 1\n")
        settings = self.settings(artifact=False)
        before = self.state()
        unborn = self.pieces(settings, address)
        self.assertIsNone(unborn["headCommit"])
        self.assertEqual(unborn["committed"], absent)
        self.assertTrue(unborn["working"]["present"])
        self.assertEqual(self.state(), before)

        self.commit()
        head = self.git("rev-parse", "HEAD")
        file.unlink()
        outside = self.write(self.home, "outside.py", "def secret():\n    return 3\n")
        link = self.code / "link.py"
        link.symlink_to(outside)
        self.write(self.code, "broken.py", b"\xff")
        before = self.state()
        deleted = self.pieces(settings, address)
        self.assertEqual(deleted["headCommit"], head)
        self.assertEqual(deleted["working"], absent)
        self.assertEqual(deleted["committed"], unborn["working"])
        for name in ("missing.py", "link.py", "broken.py"):
            self.pieces(settings, f"fixture:@code/{name}", error="io")
        self.pieces(settings, "fixture:@artifact/worker.py", error="invalid_input")
        self.pieces(settings, "fixture:@code/.git/config", error="invalid_input")
        self.assertEqual(self.state(), before)
        self.assertEqual(link.readlink(), outside)
        self.assertEqual(outside.read_text(), "def secret():\n    return 3\n")
