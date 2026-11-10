"""Qualify the Cue Card and Hub commands against private filesystem fixtures."""

import io
import json
import os
import stat
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
        paragraph = self.write(
            "artifacts/paragraph.md",
            "## Alpha\n"
            "<!-- mycel:cues {type: literal, match: First} -->\n"
            "Some prose\n"
            "2. ```\n"
            "   <!-- mycel:cues {type: literal, match: Second} -->\n",
        )
        heading = "A``[B](/path)`C"
        backticks = self.write(
            "artifacts/backticks.md",
            f"## {heading}\n<!-- mycel:cues {{type: literal, match: Backticks}} -->\n",
        )
        whole = self.write(
            "artifacts/whole-file.md",
            "<!-- mycel:cues {type: literal, match: Intro} -->\n\nBody.\n \t\n",
        )

        reply = self.command("cues", "compile")
        catalog = json.loads(self.catalog.read_bytes())
        self.assertEqual(catalog["version"], 1)
        self.assertEqual(reply["faults"], catalog["faults"])
        self.assertEqual(
            [(fault["file"], fault["line"]) for fault in catalog["faults"]],
            [(str(declarations), line) for line in (9, 15, 20, 26)],
        )
        self.assertEqual(reply["cards"], len(catalog["cards"]))
        self.assertEqual(reply["sources"], 6)
        boundary_paths = {str(paragraph), str(backticks), str(whole)}
        named, local, glossary = [
            card for card in catalog["cards"] if card["declared_at"]["path"] not in boundary_paths
        ]
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
        for document, written, anchor, end, text, declarations in (
            (
                paragraph, "Alpha", "alpha", 5, "## Alpha\nSome prose\n2. ```",
                (("outer:paragraph.md#alpha", "First", 2),
                 ("outer:paragraph.md#alpha~2", "Second", 5)),
            ),
            (
                backticks, heading, "abc", 2, f"## {heading}",
                (("outer:backticks.md#abc", "Backticks", 2),),
            ),
            (
                whole, None, None, 4, "Body.\n \t",
                (("outer:whole-file.md", "Intro", 1),),
            ),
        ):
            with self.subTest(document=document.name):
                path = str(document)
                actual = [
                    (card["id"], card["match"], card["title"], card["cue_target"],
                     card["declared_at"], card["text"])
                    for card in catalog["cards"] if card["declared_at"]["path"] == path
                ]
                self.assertEqual(
                    actual,
                    [
                        (card_id, [term], written or document.name,
                         {"path": path, "heading": written, "anchor": anchor,
                          "first_line": 1, "last_line": end},
                         {"path": path, "first_line": line, "last_line": line}, text)
                        for card_id, term, line in declarations
                    ],
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

    def test_heading_cards_preserve_prose_aliases_and_unique_anchors(self):
        defined = self.write(
            "artifacts/headings.md",
            """# Parent
<!-- mycel:cues {literal: section_headings, heading-levels: [1, 3]} -->

## Branch
### Alpha
<!-- mycel:cues {type: literal, match: Exact} -->Closing prose.

Next paragraph.

### Alpha-1
Numbered heading.

### Alpha
Repeated heading.

### [Example](https://example.com/a(b))
Linked heading.

### [Reference][Guide Label]
Defined reference.

[guide  label]: https://example.com/guide

## Remaining
<!-- mycel:cues {match: [Parent alias]} -->

Still in Parent.
""",
        )
        undefined = self.write(
            "artifacts/undefined.md",
            """<!-- mycel:cues {literal: section_headings, heading-levels: [3]} -->

### [Reference][Guide Label]
Undefined reference.
""",
        )
        boundaries = (
            (
                "list-paragraph.md",
                "alphabeta",
                "## [Alpha][Beta]\n\nSome prose\n2. [Beta]: /beta",
            ),
            (
                "uri-autolink.md",
                "alphasshexamplecomqbeta",
                "## [Alpha<ssh://example.com/?q=][Beta]>\n\n[Beta]: /beta",
            ),
        )
        boundary_documents = [
            (
                self.write(
                    f"artifacts/{name}",
                    "<!-- mycel:cues {literal: section_headings, heading-levels: [2]} -->\n\n"
                    f"{text}\n",
                ),
                anchor,
                text,
            )
            for name, anchor, text in boundaries
        ]
        reply = self.command("cues", "compile")
        cards = json.loads(self.catalog.read_bytes())["cards"]
        glossary = [card for card in cards if card["group"] == "glossary"]

        with self.subTest("closing-line prose"):
            exact = next(
                card for card in glossary if card["cue_target"]["anchor"] == "alpha"
            )
            self.assertEqual(
                exact["text"], "### Alpha\nClosing prose.\n\nNext paragraph."
            )
        with self.subTest("containing selected parent"):
            parent = next(
                card for card in glossary if card["cue_target"]["anchor"] == "parent"
            )
            self.assertEqual(parent["match"], ["Parent", "Parent alias"])
            self.assertEqual(reply["faults"], [])
        with self.subTest("numbered anchor collision"):
            targets = sorted(
                (
                    card["cue_target"]
                    for card in glossary
                    if card["title"].startswith("Alpha")
                ),
                key=lambda target: target["first_line"],
            )
            self.assertEqual(
                [target["anchor"] for target in targets],
                ["alpha", "alpha-1", "alpha-2"],
            )
        with self.subTest("rendered link anchor"):
            heading = "[Example](https://example.com/a(b))"
            linked = next(card for card in glossary if card["title"] == heading)
            self.assertEqual(linked["cue_target"]["anchor"], "example")
            self.assertEqual(linked["cue_target"]["heading"], heading)
            self.assertEqual(linked["text"], f"### {heading}\nLinked heading.")

        for document, anchor, text in (
            (
                defined,
                "reference",
                "### [Reference][Guide Label]\nDefined reference.\n\n"
                "[guide  label]: https://example.com/guide",
            ),
            (
                undefined,
                "referenceguide-label",
                "### [Reference][Guide Label]\nUndefined reference.",
            ),
            *boundary_documents,
        ):
            with self.subTest(document=document.name):
                heading = text.split("\n", 1)[0].partition(" ")[2]
                card = next(
                    card
                    for card in glossary
                    if card["title"] == heading
                    and card["cue_target"]["path"] == str(document)
                )
                self.assertEqual(
                    (
                        card["cue_target"]["anchor"],
                        card["id"],
                        card["cue_target"]["heading"],
                        card["text"],
                    ),
                    (
                        anchor,
                        f"outer:{document.name}#{anchor}",
                        heading,
                        text,
                    ),
                )

    def test_invalid_escaped_scalars_report_faults_without_losing_valid_cards(self):
        source = self.write(
            "artifacts/scalars.md",
            r"""# Rules
<!-- mycel:cues {type: literal, match: "\uD800"} -->
<!-- mycel:cues {"\uD800": first, "\uD800": second, type: literal, match: Broken} -->
<!-- mycel:cues {type: literal, match: Valid} -->

Valid content.
""",
        )
        reply = self.command("cues", "compile")
        catalog = json.loads(self.catalog.read_bytes())
        self.assertEqual(reply["faults"], catalog["faults"])
        self.assertEqual(
            [(fault["file"], fault["line"]) for fault in reply["faults"]],
            [(str(source), 2), (str(source), 3)],
        )
        self.assertTrue(all("Unicode" in fault["problem"] for fault in reply["faults"]))
        self.assertEqual([card["match"] for card in catalog["cards"]], [["Valid"]])

    def test_directory_sync_failure_reports_the_published_catalog(self):
        source = self.write(
            "artifacts/card.md",
            "<!-- mycel:cues {type: literal, match: Original} -->\n\nSaved.\n",
        )
        self.command("cues", "compile")
        previous = self.catalog.read_bytes()
        source.write_text(source.read_text().replace("Original", "Changed"))
        sync = os.fsync
        observed = []

        def fail_directory_sync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                observed.append(self.catalog.read_bytes())
                raise OSError("directory sync failed")
            sync(descriptor)

        with patch("mycel._cues.os.fsync", side_effect=fail_directory_sync):
            reply = self.command("cues", "compile")
        published = self.catalog.read_bytes()
        self.assertEqual(observed, [published])
        self.assertNotEqual(published, previous)
        self.assertEqual(reply["cards"], 1)
        self.assertEqual(json.loads(published)["cards"][0]["match"], ["Changed"])

    def test_malformed_tagged_values_leave_valid_cards_in_the_catalog(self):
        source = self.write(
            "artifacts/tagged.md",
            """## Rules
<!-- mycel:cues {type: literal, match: !!timestamp invalid} -->
<!-- mycel:cues {type: literal, match: !!int ''} -->
<!-- mycel:cues {type: literal, match: !!bool maybe} -->
<!-- mycel:cues {type: literal, match: Valid} -->

Valid content.
""",
        )
        reply = self.command("cues", "compile")
        catalog = json.loads(self.catalog.read_bytes())
        self.assertEqual(reply["faults"], catalog["faults"])
        self.assertEqual(
            [(fault["file"], fault["line"]) for fault in reply["faults"]],
            [(str(source), 2), (str(source), 3), (str(source), 4)],
        )
        self.assertEqual([card["match"] for card in catalog["cards"]], [["Valid"]])

    def test_html_container_declares_a_card_and_preserves_literal_examples(self):
        declaration = "<!-- mycel:cues {type: literal, match: Inside} -->"
        text = f"""## Section
<div>
<!-- Ordinary comment
<!-- mycel:cues {{type: literal, match: Nested}} -->
<script type="text/plain">

<!-- mycel:cues {{type: literal, match: Script}} -->
</script
>
{declaration}
Visible prose.
</div>

```markdown
<!-- mycel:cues {{type: literal, match: Fenced}} -->
```
"""
        self.write("artifacts/html.md", text)

        reply = self.command("cues", "compile")
        self.assertEqual(reply["faults"], [])
        self.assertEqual(reply["cards"], 1)
        (card,) = json.loads(self.catalog.read_bytes())["cards"]
        self.assertEqual(card["match"], ["Inside"])
        self.assertEqual(card["cue_target"]["heading"], "Section")
        self.assertEqual(
            card["text"], text.replace(f"{declaration}\n", "", 1).rstrip("\n")
        )

    def test_literal_nul_in_heading_preserves_catalog_publication(self):
        heading = "Rules \x000\x00"
        self.write(
            "artifacts/nul.md",
            f"## {heading}\n"
            "<!-- mycel:cues {type: literal, match: Rules} -->\n"
            "Rules content.\n",
        )
        self.write(
            "artifacts/other.md",
            "## Other\n<!-- mycel:cues {type: literal, match: Other} -->\n",
        )

        reply = self.command("cues", "compile")
        self.assertEqual(reply["faults"], [])
        self.assertEqual(reply["cards"], 2)
        cards = {
            tuple(card["match"]): card
            for card in json.loads(self.catalog.read_bytes())["cards"]
        }
        self.assertEqual(set(cards), {("Rules",), ("Other",)})
        rules = cards[("Rules",)]
        self.assertEqual(rules["cue_target"]["anchor"], "rules-0")
        self.assertEqual(rules["cue_target"]["heading"], heading)
        self.assertEqual(rules["text"], f"## {heading}\nRules content.")

    def test_malformed_front_matter_keeps_scanning_cue_files(self):
        malformed = self.write(
            "artifacts/metadata.md",
            """---
created: !!timestamp invalid
---

## Local
<!-- mycel:cues {type: literal, match: Local} -->

Local content.
""",
        )
        separate = self.write(
            "artifacts/separate.md",
            """## Separate
<!-- mycel:cues {type: literal, match: Separate} -->

Separate content.
""",
        )
        reply = self.command("cues", "compile")
        cards = json.loads(self.catalog.read_bytes())["cards"]
        self.assertEqual(reply["cards"], 2)
        self.assertEqual(reply["faults"], [])
        self.assertEqual(
            {tuple(card["match"]): card["cue_target"]["path"] for card in cards},
            {("Local",): str(malformed), ("Separate",): str(separate)},
        )

    def test_html_tokens_preserve_cue_lookalikes_in_the_published_target(self):
        declaration = "<!-- mycel:cues {type: literal, match: Real} -->"
        text = f"""## Rules
<div title="
<!-- mycel:cues {{type: literal, match: Attribute before blank}} -->

<!-- mycel:cues {{type: literal, match: Attribute after blank}} -->
">
</div>
<section><!-- Comment starting on the tag line
<!-- mycel:cues {{type: literal, match: Nested}} -->
</section>
<div><script>
<!-- mycel:cues {{type: literal, match: Script}} -->
</script></div>
{declaration}
Visible prose.

```markdown
<!-- mycel:cues {{type: literal, match: Fenced}} -->
```
"""
        self.write("artifacts/html-tokens.md", text)

        reply = self.command("cues", "compile")
        self.assertEqual(reply["faults"], [])
        self.assertEqual(reply["cards"], 1)
        (card,) = json.loads(self.catalog.read_bytes())["cards"]
        self.assertEqual(card["match"], ["Real"])
        self.assertEqual(card["cue_target"]["heading"], "Rules")
        self.assertEqual(
            card["text"], text.replace(f"{declaration}\n", "", 1).rstrip("\n")
        )
