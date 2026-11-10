"""Qualify the Cue Card and Hub commands against private filesystem fixtures."""

import io
import json
import os
import tomllib
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mycel import _hub
from mycel._cli import run


class CueCardTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.artifacts = self.home / "artifacts"
        self.catalog = self.home / ".mycel/cues/catalog.json"
        self.settings = self.write(
            "config.toml",
            "\n".join(
                (
                    "[store]",
                    'address = "postgresql://fixture@localhost/mycel_check_config_only"',
                    "[repos.outer]",
                    "enabled = true",
                    f"artifact_root = {json.dumps(str(self.artifacts))}",
                    f"code_root = {json.dumps(str(self.home / 'code'))}",
                    "[repos.inner]",
                    "enabled = true",
                    f"artifact_root = {json.dumps(str(self.artifacts / 'inner'))}",
                    "[repos.disabled]",
                    f"artifact_root = {json.dumps(str(self.artifacts / 'disabled'))}",
                    "enabled = false",
                    "[repos.absent]",
                    "enabled = true",
                    f"artifact_root = {json.dumps(str(self.home / 'absent'))}",
                    "",
                )
            ),
        )

    def write(self, relative, text):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
        return path

    def command(self, *args, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(Path, "home", return_value=self.home),
            patch.dict(os.environ, {"MYCEL_CONFIG": str(self.settings)}),
        ):
            status = run(args, stdout=stdout, stderr=stderr)
        reply = json.loads(stdout.getvalue())
        self.assertEqual(status, int(error is not None), (reply, stderr.getvalue()))
        if error is not None:
            self.assertEqual(reply["error"]["code"], error)
        return reply

    def test_compile_keeps_exact_cross_root_targets_and_reports_faults(self):
        target = self.write(
            "artifacts/inner/guide.md", "# Guide\n\n## Book `Code`\n\nExact text.\n"
        )
        declarations = self.write(
            "artifacts/cards.md",
            """# Cards
<!-- mycel:cues
type: literal
match: Book work
cue_target: 'inner:guide.md#Guide > Book `Code`'
instructions: Read first.
-->

<!-- mycel:cues
type: literal
match: Broken
cue_target: 'outer:inner/guide.md'
-->

<!-- mycel:cues
type: semantic
match: Unknown
-->

<!-- mycel:cues
type: literal
match: Neither
cue_target: none
-->

<!-- mycel:cues
type: literal
match: Unknown field
color: blue
-->

## Local
<!-- mycel:cues
type: literal
match: Local cue
-->

```markdown
<!-- mycel:cues
type: literal
match: Example only
-->
```
""",
        )
        self.write(
            "artifacts/glossary.md",
            """# Glossary
<!-- mycel:cues
literal: section_headings
heading-levels: [2]
-->

## Fold / Projection
<!-- mycel:cues
match: [View]
-->

Shared text.

## Excluded
<!-- mycel:cues
literal: exclude
-->

Excluded text.
""",
        )
        ignored_card = "<!-- mycel:cues\ntype: literal\nmatch: Ignored\n-->\n"
        self.write("artifacts/.gitignore", "ignored.md\n")
        self.write("artifacts/ignored.md", ignored_card)
        self.write("artifacts/disabled/disabled.md", ignored_card)
        self.write("code/code.md", ignored_card)

        reply = self.command("cues", "compile")
        catalog = json.loads(self.catalog.read_bytes())
        self.assertEqual(catalog["version"], 1)
        self.assertEqual(reply["faults"], catalog["faults"])
        self.assertEqual(
            [(fault["file"], fault["line"]) for fault in catalog["faults"]],
            [(str(declarations), line) for line in (9, 15, 20, 26)],
        )
        self.assertEqual((reply["cards"], reply["sources"]), (3, 3))
        named, local, glossary = catalog["cards"]
        self.assertEqual(named["id"], "inner:guide.md#book-code")
        self.assertEqual(
            named["cue_target"],
            {
                "path": str(target),
                "heading": "Book `Code`",
                "anchor": "book-code",
                "first_line": 3,
                "last_line": 5,
            },
        )
        self.assertEqual(named["text"], "Read first.\n\n## Book `Code`\n\nExact text.")
        self.assertEqual(set(named["sources"]), {str(declarations), str(target)})
        self.assertEqual(
            local["text"],
            "## Local\n```markdown\n"
            + ignored_card.replace("Ignored", "Example only")
            + "```",
        )
        self.assertEqual(
            (glossary["group"], glossary["match"], glossary["text"]),
            (
                "glossary",
                ["Fold", "Projection", "View"],
                "## Fold / Projection\nShared text.",
            ),
        )
        source = next(row for row in catalog["sources"] if row["path"] == str(target))
        info = target.stat()
        self.assertEqual(
            source,
            {
                "path": str(target),
                "repo": "inner",
                "size": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "sha256": sha256(target.read_bytes()).hexdigest(),
            },
        )

    def test_fatal_compile_leaves_previous_catalog_bytes(self):
        source = self.write(
            "artifacts/card.md",
            "<!-- mycel:cues\ntype: literal\nmatch: Original\n-->\n\nSaved.\n",
        )
        self.command("cues", "compile")
        saved = self.catalog.read_bytes()

        moved = self.home / "moved-artifacts"
        self.artifacts.rename(moved)
        self.artifacts.write_text("A file cannot be scanned as an artifact root.\n")
        self.command("cues", "compile", error="io")
        self.assertEqual(self.catalog.read_bytes(), saved)
        self.artifacts.unlink()
        moved.rename(self.artifacts)

        source.write_text(source.read_text().replace("Original", "Changed"))
        with patch(
            "mycel._cues.os.replace", side_effect=OSError("publication refused")
        ) as replace:
            self.command("cues", "compile", error="io")
        replace.assert_called_once()
        self.assertEqual(replace.call_args.args[1], self.catalog)
        self.assertEqual(self.catalog.read_bytes(), saved)
        self.assertEqual(list(self.catalog.parent.glob(".catalog-*")), [])

    def test_match_uses_published_patterns_over_the_whole_message(self):
        self.write(
            "artifacts/match.md",
            """## First
<!-- mycel:cues
type: literal
match: Whole phrase
-->

## Second
<!-- mycel:cues
type: literal
match: Box
-->

## Third
<!-- mycel:cues
type: literal
match: Leaf
cue_target: none
instructions: Check leaves.
-->
""",
        )
        self.command("cues", "compile")
        saved = self.catalog.read_bytes()
        reply = self.command(
            "cues", "match", "xboxes; BOXES.\n```text\nWHOLE\n  PHRASES\n```\nleafs."
        )
        self.assertEqual(
            [card["id"] for card in reply["cards"]],
            ["outer:match.md#second", "outer:match.md#first", "outer:match.md#third"],
        )
        self.assertIsNone(reply["cards"][-1]["cue_target"])
        self.assertEqual(
            self.command("cues", "match", "xboxes leafs_extra whole phrasebook")[
                "cards"
            ],
            [],
        )
        self.assertEqual(self.catalog.read_bytes(), saved)

    def test_interrupted_hub_switch_resumes_and_preserves_first_backups(self):
        source = self.write(
            "Artifacts/mycel/README.md",
            "---\nrole: authored\n---\n\n# Fixture Hub\n\nRead this.\n",
        )
        active = self.write(".mycel/hub/active.md", "")
        agents = self.write(".agents/AGENTS.md", "")
        self.write(".claude/CLAUDE.md", "@~/.mycel/hub/active.md\n")
        codex = self.write(
            ".codex/config.toml",
            'model = "fixture" # preserve\n\n[profiles.example]\ndeveloper_instructions = "nested"\n',
        )
        original = codex.read_bytes()
        codex.chmod(0o640)
        self.assertEqual(
            self.command("hub", "status"),
            {"state": "off", "last_sync": None, "pending": False},
        )
        original_replace = _hub._replace

        def interrupt_after_active(scratch, destination):
            if destination == agents:
                raise OSError("second copy refused")
            original_replace(scratch, destination)

        with patch.object(_hub, "_replace", side_effect=interrupt_after_active):
            self.command("hub", "on", error="io")
        self.assertEqual(active.read_bytes(), source.read_bytes())
        self.assertEqual((agents.read_bytes(), codex.read_bytes()), (b"", original))
        self.assertEqual(
            self.command("hub", "status"),
            {"state": "on", "last_sync": None, "pending": True},
        )

        state = self.command("hub", "on")
        self.assertEqual((state["state"], state["pending"]), ("on", False))
        value = tomllib.loads(codex.read_text()).pop("developer_instructions")
        self.assertEqual(agents.read_text(), value)
        self.assertTrue(value.endswith("# Fixture Hub\n\nRead this.\n"))
        self.assertEqual(codex.read_bytes().split(b"\n", 1)[1], original)
        self.assertEqual(codex.stat().st_mode & 0o777, 0o640)

        self.assertEqual(self.command("hub", "off")["state"], "off")
        self.assertEqual(
            (active.read_bytes(), agents.read_bytes(), codex.read_bytes()),
            (b"", b"", original),
        )
        backups = active.parent / "backups"
        self.assertEqual(
            {path.name: path.read_bytes() for path in backups.iterdir()},
            {
                "active.md": b"",
                "agents-AGENTS.md": b"",
                "codex-config.toml": original,
            },
        )
