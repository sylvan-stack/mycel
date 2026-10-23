#!/usr/bin/env python3
"""Name each requirement's passing checks in its specification, and set the specification statuses.

fill   reads the Origin report of the tests (`mycel origins --repo mycel --path tests
       --no-fresh`) and complete passing check reports, then writes the Named checks
       section of every accepted or implemented chapter, its front matter status and
       its status in the specifications index.
check  confirms against complete check reports that every named check exists and
       passed, and that each status agrees with the Named checks sections.

The requirement rows themselves are never changed: a changed row is a new version of
the requirement, which would put every test resting on it stale.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from mycel._markdown import _cells, split_markdown


KINDS = ("unit", "store", "eval", "live")
ON_DEMAND = ("eval", "live")
SHOWN = 3
HEADING = "## Named checks"
NO_REPORT = "no on-demand report yet"
NO_CHECK = "no passing check"
STATUSES = ("accepted", "implemented")
CHAPTER = re.compile(r"^[0-9]{2}-[a-z0-9-]+\.md$")
TEST_CHUNK = re.compile(r"^[^:@\s]+:@code/tests/(?P<path>[^#]+)\.py#(?P<symbol>[^#]+)$")
REQUIREMENT_URI = re.compile(r"^\[[^:\]]+:req:(?P<uuid>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}):[^\]]*\]$")
FRONT_STATUS = re.compile(r"\A(---\n(?:(?!---\n).*\n)*?status: )([a-z]+)(\n)")
INDEX_ROW = re.compile(r"^\| \[(?P<spec>[A-Z]+-[0-9]+)\]\((?P<file>[^)]+)\) \| (?P<title>[^|]+) \| (?P<status>[^|]+) \|$")
NAMED = re.compile(r"`([A-Za-z0-9_.]+)`")
MORE = re.compile(r" and [1-9][0-9]* more$")
INTRODUCTION = (
    "Written by `scripts/name_checks.py` from the `proven` Origin Links of the tests and "
    "a complete check report in which they passed. Each requirement keeps its kind in its "
    "Verified by cell and names here up to three of its passing checks: those of its own "
    "kind first, then those that rest on the fewest requirements. `mycel origins --repo "
    "mycel --path tests` lists every link. Do not edit this section by hand: run the "
    "script again.")


class NamingError(Exception):
    pass


@dataclass(frozen=True)
class Requirement:
    id: str
    uuid: str
    kind: str


@dataclass(frozen=True)
class Chapter:
    path: Path
    text: str
    spec: str
    status: str
    requirements: tuple[Requirement, ...]


def passed_checks(paths) -> dict[str, str]:
    """Each passing check of the complete reports, with its kind."""
    passed = {}
    for path in paths:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("schema_version") != 2 or report.get("passed") is not True:
            raise NamingError(f"{path}: not a passing schema 2 check report")
        for check in report["checks"]:
            if check["status"] == "passed":
                if check["kind"] not in KINDS:
                    raise NamingError(f"{path}: {check['name']} has unknown kind {check['kind']!r}")
                passed[check["name"]] = check["kind"]
    return passed


def proven_links(path) -> dict[str, set[str]]:
    """Requirement UUID -> the checks that the Origin report says prove it."""
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    links: dict[str, set[str]] = {}
    for chunk in report["chunks"]:
        for link in chunk["links"]:
            if link["method"] != "proven":
                continue
            test, origin = TEST_CHUNK.fullmatch(link["chunk"]), REQUIREMENT_URI.fullmatch(link["origin"])
            if test is None or origin is None:
                raise NamingError(f"{path}: {link['chunk']} -> {link['origin']} is not a test proving a requirement")
            name = test["path"].replace("/", ".") + "." + test["symbol"]
            links.setdefault(origin["uuid"], set()).add(name)
    return links


def read_chapters(specifications: Path) -> tuple[Chapter, ...]:
    """Every accepted or implemented chapter with its active requirements."""
    chapters = []
    for path in sorted(specifications.iterdir()):
        if not CHAPTER.fullmatch(path.name):
            continue
        text = path.read_text(encoding="utf-8")
        document = split_markdown(text)
        status = document.frontmatter.get("status")
        if status not in STATUSES:
            continue
        faults = [item for item in document.diagnostics if item.code.startswith("entity_")]
        if faults:
            raise NamingError(f"{path.name}: {faults[0].message}")
        requirements = []
        for row in document.entities:
            if row.kind != "req" or row.status == "withdrawn" or row.verified_by is None:
                continue
            if row.verified_by not in KINDS:
                raise NamingError(f"{path.name}: {row.id} has Verified by {row.verified_by!r}, not one kind")
            requirements.append(Requirement(row.id, row.uuid, row.verified_by))
        chapters.append(Chapter(path, text, document.frontmatter.get("spec"), status, tuple(requirements)))
    return tuple(chapters)


def name_checks(requirement: Requirement, names, passed: dict[str, str], weight: dict[str, int]) -> tuple[str, bool]:
    """The Checks cell of one requirement, and whether a passing check of its kind proves it."""
    order = sorted((name for name in names if name in passed),
                   key=lambda name: (passed[name] != requirement.kind, weight[name], name))
    if not order:
        return (NO_REPORT if requirement.kind in ON_DEMAND else NO_CHECK), False
    cell = ", ".join(f"`{name}`" for name in order[:SHOWN])
    if len(order) > SHOWN:
        cell += f" and {len(order) - SHOWN} more"
    return cell, passed[order[0]] == requirement.kind


def render_section(rows) -> str:
    lines = [HEADING, "", INTRODUCTION, "", "| Requirement | Kind | Checks |", "|---|---|---|"]
    lines += [f"| `{requirement.id}` | {requirement.kind} | {cell} |" for requirement, cell in rows]
    return "\n".join(lines) + "\n"


def split_section(chapter: Chapter) -> tuple[str, str | None]:
    """The chapter before its Named checks section, and that section, which must come last."""
    lines = chapter.text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip("\n") == HEADING]
    if not starts:
        return chapter.text, None
    if len(starts) > 1 or any(line.startswith("## ") or line.startswith("# ")
                              for line in lines[starts[0] + 1:]):
        raise NamingError(f"{chapter.path.name}: the Named checks section must be the last one, once")
    return "".join(lines[:starts[0]]), "".join(lines[starts[0]:])


def set_status(text: str, status: str, name: str) -> str:
    result, count = FRONT_STATUS.subn(lambda match: match[1] + status + match[3], text, count=1)
    if count != 1:
        raise NamingError(f"{name}: no status in the front matter")
    return result


def index_status(held: list[str]) -> str:
    if not held:
        return "implemented"
    names = held[0] if len(held) == 1 else ", ".join(held[:-1]) + " and " + held[-1]
    return f"accepted, held back by {names}"


def set_index(text: str, statuses: dict[str, str]) -> str:
    lines, seen = text.splitlines(keepends=True), set()
    for index, line in enumerate(lines):
        match = INDEX_ROW.fullmatch(line.rstrip("\n"))
        if match is not None and match["file"] in statuses:
            lines[index] = f"| [{match['spec']}]({match['file']}) | {match['title']} | {statuses[match['file']]} |\n"
            seen.add(match["file"])
    missing = sorted(set(statuses) - seen)
    if missing:
        raise NamingError(f"README.md: no index row for {', '.join(missing)}")
    return "".join(lines)


def replace_files(contents: dict[Path, str]) -> None:
    for path in contents:
        if path.is_symlink():
            raise NamingError(f"{path.name}: a symbolic link")
    for path, content in contents.items():
        if path.read_text(encoding="utf-8") == content:
            continue
        mode = path.stat().st_mode & 0o777
        descriptor, staged = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content.encode("utf-8"))
                os.fchmod(handle.fileno(), mode)
            os.replace(staged, path)
        finally:
            Path(staged).unlink(missing_ok=True)


def fill(specifications: Path, origins: Path, reports) -> dict[str, list[str]]:
    """Write the sections and statuses; return each chapter's held-back requirements."""
    passed, links = passed_checks(reports), proven_links(origins)
    weight: dict[str, int] = {}
    for names in links.values():
        for name in names:
            weight[name] = weight.get(name, 0) + 1
    chapters = read_chapters(specifications)
    contents, statuses, held_back = {}, {}, {}
    for chapter in chapters:
        rows, held = [], []
        for requirement in chapter.requirements:
            cell, proven = name_checks(requirement, links.get(requirement.uuid, ()), passed, weight)
            rows.append((requirement, cell))
            if not proven:
                held.append(requirement.id)
        before, _ = split_section(chapter)
        text = before.rstrip("\n") + "\n\n" + render_section(rows)
        contents[chapter.path] = set_status(text, "accepted" if held else "implemented", chapter.path.name)
        statuses[chapter.path.name] = index_status(held)
        held_back[chapter.spec] = held
    index = specifications / "README.md"
    contents[index] = set_index(index.read_text(encoding="utf-8"), statuses)
    replace_files(contents)
    return held_back


def check(specifications: Path, reports) -> tuple[list[str], dict[str, list[str]], int]:
    """Return every fault, each chapter's held-back requirements and the number of named checks."""
    passed = passed_checks(reports)
    faults, held_back, named, statuses = [], {}, 0, {}
    for chapter in read_chapters(specifications):
        _, section = split_section(chapter)
        if section is None:
            faults.append(f"{chapter.path.name}: no Named checks section")
            continue
        rows = [_cells(line) for line in section.splitlines() if line.startswith("| `")]
        expected = [(f"`{requirement.id}`", requirement.kind) for requirement in chapter.requirements]
        if [row[:2] for row in rows] != expected or any(len(row) != 3 for row in rows):
            faults.append(f"{chapter.path.name}: the Named checks rows differ from its active requirements")
            continue
        if render_section([(requirement, row[2]) for requirement, row in zip(chapter.requirements, rows)]) != section:
            faults.append(f"{chapter.path.name}: the Named checks section was edited by hand")
            continue
        held = []
        for requirement, (_, _, cell) in zip(chapter.requirements, rows):
            if cell in (NO_CHECK, NO_REPORT):
                if cell == NO_REPORT and requirement.kind not in ON_DEMAND:
                    faults.append(f"{requirement.id}: only an eval or live requirement waits for an on-demand report")
                held.append(requirement.id)
                continue
            names = NAMED.findall(cell)
            if (not names or len(names) > SHOWN or (MORE.search(cell) is not None and len(names) != SHOWN)
                    or MORE.sub("", cell) != ", ".join(f"`{name}`" for name in names)):
                faults.append(f"{requirement.id}: unreadable Checks cell {cell!r}")
                held.append(requirement.id)
                continue
            named += len(names)
            failed = [name for name in names if name not in passed]
            faults += [f"{requirement.id}: {name} did not pass in the reports" for name in failed]
            if failed or passed[names[0]] != requirement.kind:
                held.append(requirement.id)
                if not failed:
                    faults.append(f"{requirement.id}: its first named check is not a {requirement.kind} check")
        status = "accepted" if held else "implemented"
        if chapter.status != status:
            faults.append(f"{chapter.path.name}: status {chapter.status}, its Named checks say {status}")
        statuses[chapter.path.name] = index_status(held)
        held_back[chapter.spec] = held
    index = (specifications / "README.md").read_text(encoding="utf-8")
    try:
        if set_index(index, statuses) != index:
            faults.append("README.md: an index status differs from its chapter")
    except NamingError as error:
        faults.append(str(error))
    return faults, held_back, named


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operation", choices=("fill", "check"))
    parser.add_argument("--specifications", type=Path, required=True, help="the explicit specifications folder")
    parser.add_argument("--report", type=Path, action="append", required=True,
                        help="a complete passing check report; repeat to add an on-demand report")
    parser.add_argument("--origins", type=Path, help="the Origin report of the tests (fill only)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.operation == "fill":
            if arguments.origins is None:
                raise NamingError("fill requires --origins")
            fill(arguments.specifications, arguments.origins, arguments.report)
        faults, held_back, named = check(arguments.specifications, arguments.report)
    except (OSError, KeyError, TypeError, ValueError, NamingError) as error:
        print(f"Named checks: {error}", file=sys.stderr)
        return 1
    for fault in faults:
        print(fault, file=sys.stderr)
    implemented = sorted(spec for spec, held in held_back.items() if not held)
    print(f"{named} named checks; {len(implemented)} of {len(held_back)} specifications implemented")
    for spec, held in held_back.items():
        if held:
            print(f"{spec} held back by {', '.join(held)}")
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
