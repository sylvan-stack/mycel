#!/usr/bin/env python3
"""Render or check the 19 Mycel 2 guide copies in an explicit corpus folder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile


GUIDES = (
    "activity", "capture", "classification", "drifts", "embedding", "evidence",
    "generated", "identity", "origins", "overview", "parsing", "pin-observation", "reading",
    "reconciliation", "relations", "retrieval", "source-refs", "store", "summaries",
)
FRONTMATTER = "---\nrole: authored\n---\n"
LINK_NAMES = dict.fromkeys(GUIDES + (
    "builds", "checks", "evaluation", "jev", "replacement", "reviewer", "settings",
))
LINK_NAMES = {f"{name}.md": f"mycel-2-{name}.md" for name in LINK_NAMES}
LINK_NAMES["command-line.md"] = "mycel-2.md"
LOCAL_GUIDE_LINK = re.compile(r"(\]\()(?:\./)?([a-z][a-z0-9-]*\.md)(?=[#)])")


def render_corpus_guide(original: str) -> str:
    """Keep authored text exact except for the documented local-link projection."""
    body = original.removeprefix(FRONTMATTER)
    body = LOCAL_GUIDE_LINK.sub(
        lambda match: (match[1] + LINK_NAMES[match[2]]
                       if match[2] in LINK_NAMES else match[0]), body)
    return FRONTMATTER + body


def check_copies(docs: Path, corpus: Path, names=GUIDES) -> list[str]:
    """Return every missing or unequal pair; never create or change a file."""
    faults = []
    for name in names:
        original = docs / f"{name}.md"
        copy = corpus / f"mycel-2-{name}.md"
        if not original.is_file():
            faults.append(f"{name}: original is missing")
        elif not copy.is_file():
            faults.append(f"{name}: corpus copy is missing")
        elif copy.read_bytes() != render_corpus_guide(
                original.read_text(encoding="utf-8")).encode("utf-8"):
            faults.append(f"{name}: corpus copy differs")
    return faults


def write_copies(docs: Path, corpus: Path, names=GUIDES) -> None:
    """Render selected, known guide names, with all originals validated first."""
    names = tuple(names)
    if any(name not in GUIDES for name in names):
        raise ValueError("unknown guide")
    copies = [(corpus / f"mycel-2-{name}.md", render_corpus_guide(
        (docs / f"{name}.md").read_text(encoding="utf-8"))) for name in names]
    if not corpus.is_dir():
        raise ValueError("corpus must be an existing folder")
    for copy, content in copies:
        if copy.is_symlink():
            raise ValueError(f"{copy.name}: corpus copy is a symbolic link")
    for copy, content in copies:
        mode = copy.stat().st_mode & 0o777 if copy.exists() else 0o644
        descriptor, name = tempfile.mkstemp(dir=corpus, prefix=f".{copy.name}.")
        try:
            with os.fdopen(descriptor, "wb") as staged:
                staged.write(content.encode("utf-8"))
                os.fchmod(staged.fileno(), mode)
            os.replace(name, copy)
        finally:
            Path(name).unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "write"))
    parser.add_argument("--corpus", type=Path, required=True,
                        help="explicit destination tools folder")
    parser.add_argument("--docs", type=Path,
                        default=Path(__file__).resolve().parents[1] / "docs")
    parser.add_argument("--guide", action="append", choices=GUIDES)
    arguments = parser.parse_args(argv)
    names = tuple(dict.fromkeys(arguments.guide or GUIDES))
    try:
        if arguments.operation == "write":
            write_copies(arguments.docs, arguments.corpus, names)
        faults = check_copies(arguments.docs, arguments.corpus, names)
    except (OSError, ValueError) as error:
        print(f"Guide copies: {error}", file=sys.stderr)
        return 1
    if faults:
        for fault in faults:
            print(fault, file=sys.stderr)
        return 1
    print(f"{len(names)} guide copies match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
