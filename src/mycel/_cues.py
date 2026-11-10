"""Cue Card declarations and the compiled catalog (MYC-21).

``compile_catalog`` reads every ``mycel:cues`` declaration in the Markdown
files of the enabled repositories' artifact roots, builds the cards and writes
``~/.mycel/cues/catalog.json`` in the form of MYC-D88. A faulty declaration
is reported with its file and line and the other cards compile; the compile
fails, keeping the previous catalog, only when a root cannot be read
completely or the catalog cannot be written (MYC-D94).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import html
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any

import yaml

from ._capture import ArtifactDocument, artifact_documents
from ._cli import Invocation, Result
from ._errors import ErrorCode, MycelError
from ._markdown import _YAML_INPUT_ERRORS, CueComment, MarkdownOutline, OutlineHeading, outline_markdown
from ._scope import Repository, RepositoryLocations
from ._settings import SettingsSnapshot


CATALOG_VERSION = 1
KEYS = frozenset({"type", "match", "cue_target", "instructions", "literal", "heading-levels"})
_MARKER = b"mycel:cues"


# --- Files ---------------------------------------------------------------


@dataclass
class _File:
    repo: str
    document: ArtifactDocument
    _outline: MarkdownOutline | None = field(default=None, repr=False)
    _decoded: bool = False

    @property
    def path(self) -> str:
        return str(self.document.path)

    @property
    def outline(self) -> MarkdownOutline | None:
        """None for a file that is not UTF-8 text."""
        if not self._decoded:
            self._decoded = True
            try:
                self._outline = outline_markdown(self.document.source.decode("utf-8"))
            except UnicodeError:
                self._outline = None
        return self._outline


def _repositories(snapshot: SettingsSnapshot) -> tuple[tuple[Repository, frozenset[Path]], ...]:
    """Enabled repositories with an artifact root, each with the nested roots it leaves out.

    A file under two artifact roots belongs to the innermost one (MYC-D94), so
    the folder of every other configured root nested inside a root is left
    out of its walk, whether that inner repository is enabled or not. Two
    repositories configured with one folder read it once, for the first name.
    """
    roots: dict[Path, str] = {}
    for repository in RepositoryLocations(snapshot).repositories:
        if repository.documents is None:
            continue
        try:
            path = repository.documents.path.resolve()
        except (OSError, RuntimeError):
            continue
        roots.setdefault(path, repository.name)
    result = []
    for repository in RepositoryLocations(snapshot).repositories:
        if not repository.enabled or repository.documents is None:
            continue
        try:
            path = repository.documents.path.resolve()
        except (OSError, RuntimeError):
            raise MycelError(ErrorCode.IO, f"The artifact root of {repository.name!r} could not be resolved.") from None
        if roots.get(path) != repository.name:
            continue
        nested = frozenset(other for other in roots if other != path and other.is_relative_to(path))
        result.append((repository, nested))
    return tuple(result)


def _read_files(snapshot: SettingsSnapshot) -> dict[tuple[str, str], _File]:
    files: dict[tuple[str, str], _File] = {}
    for repository, nested in _repositories(snapshot):
        for document in artifact_documents(snapshot, repository, excluded=nested):
            files[(repository.name, document.relative)] = _File(repository.name, document)
    return files


# --- Sections and anchors -----------------------------------------------------


@dataclass(frozen=True)
class _Section:
    heading: OutlineHeading
    path: tuple[str, ...]
    end: int  # the last line before the next heading of the same level or higher
    anchor: str


def _blank(line: str) -> bool:
    return not line.strip(" \t")


_CODE_SPAN = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)", re.DOTALL)
_IMAGE_OR_LINK = re.compile(r"!?\[([^\[\]]*)\]")
_LINK_REFERENCE = re.compile(r"\[[^\]]*\]")
_LINK_ANGLE_DESTINATION = re.compile(r"<[^<>\n]*>")
_LINK_DESTINATION_MARK = re.compile(r"[() \t]")
_LINK_TRAILER = re.compile(r"""(?:[ \t]+(?:"[^"]*"|'[^']*'|\([^()]*\)))?[ \t]*\)""")
_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto):[^<>\s]*|[^<>\s@]+@[^<>\s@]+)>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|<!--.*?-->")
_ESCAPE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")
_EMPHASIS_UNDERSCORE = re.compile(r"(?<![^\W_])_+|_+(?![^\W_])")
_EMPHASIS_OTHER = re.compile(r"[*~]+")


def _inline_link_end(text: str, opening: int) -> int | None:
    """Find an inline link's end after escapes have been set aside."""
    start = opening + 1
    trailer = _LINK_TRAILER.match(text, start)
    if trailer is not None:
        return trailer.end()
    while text.startswith((" ", "\t"), start):
        start += 1
    if text.startswith("<", start):
        destination = _LINK_ANGLE_DESTINATION.match(text, start)
        trailer = _LINK_TRAILER.match(text, destination.end()) if destination is not None else None
        return trailer.end() if trailer is not None else None
    depth = 0
    for mark in _LINK_DESTINATION_MARK.finditer(text, start):
        if mark[0] == "(":
            depth += 1
            if depth > 32:  # cmark-gfm's limit for bare destinations
                return None
        elif mark[0] == ")" and depth:
            depth -= 1
        else:
            trailer = _LINK_TRAILER.match(text, mark.start()) if not depth else None
            return trailer.end() if trailer is not None else None
    return None


def _link_labels(text: str) -> str:
    parts: list[str] = []
    end = 0
    for label in _IMAGE_OR_LINK.finditer(text):
        if label.start() < end:
            continue
        parts.extend((text[end:label.start()], label[1]))
        end = label.end()
        if text.startswith("(", end):
            end = _inline_link_end(text, end) or end
        elif reference := _LINK_REFERENCE.match(text, end):
            end = reference.end()
    parts.append(text[end:])
    return "".join(parts)


def _rendered(title: str) -> str:
    """A heading's rendered text: links, emphasis, code spans and inline HTML reduced to text."""
    kept: list[str] = []

    def keep(text: str) -> str:
        kept.append(text)
        return f"\0{len(kept) - 1}\0"

    def code(content: str) -> str:
        # CommonMark strips one space from each side of a code span that has
        # both and is not only spaces.
        if len(content) > 1 and content[0] == content[-1] == " " and content.strip(" "):
            content = content[1:-1]
        return keep(content)

    text = _CODE_SPAN.sub(lambda match: code(match[2]), title)
    text = _ESCAPE.sub(lambda match: keep(match[1]), text)
    text = _AUTOLINK.sub(lambda match: keep(match[1]), text)
    previous = None
    while previous != text:
        previous, text = text, _link_labels(text)
    text = _TAG.sub("", text)
    text = _EMPHASIS_UNDERSCORE.sub("", text)
    text = _EMPHASIS_OTHER.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\0(\d+)\0", lambda match: kept[int(match[1])], text)


def _slug(title: str) -> str:
    """GitHub's anchor for a heading, before repeats are numbered."""
    text = _rendered(title).lower()
    text = "".join(character for character in text
                   if character in "-_ " or unicodedata.category(character)[0] in "LMN")
    return text.replace(" ", "-")


def _sections(outline: MarkdownOutline) -> tuple[_Section, ...]:
    result = []
    stack: list[OutlineHeading] = []
    seen: dict[str, int] = {}
    headings = outline.headings
    for position, heading in enumerate(headings):
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
        end = next((later.line - 1 for later in headings[position + 1:] if later.level <= heading.level),
                   len(outline.lines))
        base = _slug(heading.title)
        anchor = base
        while anchor in seen:
            seen[base] += 1
            anchor = f"{base}-{seen[base]}"
        seen[anchor] = 0
        result.append(_Section(heading, tuple(item.title for item in stack), end, anchor))
    return tuple(result)


def _last_line(outline: MarkdownOutline, first: int, last: int) -> int:
    while last > first and _blank(outline.lines[last - 1]):
        last -= 1
    return last


def _section_of(sections: tuple[_Section, ...], line: int) -> _Section | None:
    """The section of the last heading before ``line``."""
    return next((section for section in reversed(sections) if section.heading.line < line), None)


# --- Declarations ---------------------------------------------------------------


class _Loader(yaml.SafeLoader):
    """Safe YAML with UTF-8 text, textual dates and unique keys."""

    yaml_implicit_resolvers = {
        key: [(tag, expression) for tag, expression in values if tag != "tag:yaml.org,2002:timestamp"]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_scalar(self, node: yaml.Node) -> str:
        value = super().construct_scalar(node)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise _Fault("a scalar contains invalid Unicode text") from None
        return value

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if isinstance(key, str) and key in keys:
                raise _Fault(f"repeated key: {key}")
            if isinstance(key, str):
                keys.add(key)
        return super().construct_mapping(node, deep=deep)


class _Fault(Exception):
    def __init__(self, problem: str):
        super().__init__(problem)
        self.problem = problem


@dataclass(frozen=True)
class _Declaration:
    comment: CueComment
    keys: frozenset[str]
    literal: str | None  # "section_headings", "exclude" or None
    typed: bool  # `type: literal` written, or implied by `literal:`
    match: tuple[str, ...] | None
    cue_target: str | None
    instructions: str | None
    levels: tuple[int, ...] | None


def _terms(value: Any) -> tuple[str, ...]:
    values = [value] if isinstance(value, str) else value
    if (not isinstance(values, list) or not values
            or any(not isinstance(term, str) or not term.strip() for term in values)):
        raise _Fault("match must be a term or a list of terms that are not empty")
    return tuple(values)


def _declaration(comment: CueComment) -> _Declaration:
    """Read one declaration's body (MYC-D92); raise _Fault for a body that is no declaration."""
    if comment.body is None:
        raise _Fault("the comment has no -->")
    try:
        data = yaml.load(comment.body, Loader=_Loader)
    except _Fault:
        raise
    except _YAML_INPUT_ERRORS:
        raise _Fault("the body is not readable YAML") from None
    if not isinstance(data, dict):
        raise _Fault("the body is not a YAML mapping")
    unknown = sorted(str(key) for key in data if key not in KEYS)
    if unknown:
        raise _Fault("unknown key: " + ", ".join(unknown))
    kind = data.get("type")
    if "type" in data and kind != "literal":
        raise _Fault(f"unknown type: {kind}" if isinstance(kind, str) else "type must be literal")
    literal = data.get("literal")
    if "literal" in data and literal not in ("section_headings", "exclude"):
        raise _Fault("literal must be section_headings or exclude")
    match = _terms(data["match"]) if "match" in data else None
    target = data.get("cue_target")
    if "cue_target" in data and (not isinstance(target, str) or not target.strip()):
        raise _Fault("cue_target must be a target or none")
    instructions = data.get("instructions")
    if "instructions" in data and (not isinstance(instructions, str) or not instructions.strip()):
        raise _Fault("instructions must be text that is not empty")
    levels = data.get("heading-levels")
    if "heading-levels" in data:
        if (not isinstance(levels, list) or not levels
                or any(isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 6
                       for level in levels)):
            raise _Fault("heading-levels must be a list of heading levels from 1 to 6")
        levels = tuple(levels)
    return _Declaration(comment, frozenset(data), literal, "type" in data or "literal" in data,
                        match, target, instructions, levels)


# --- Cards ---------------------------------------------------------------------


@dataclass(frozen=True)
class _Target:
    file: _File
    section: _Section | None  # None for a whole file
    first_line: int
    last_line: int


@dataclass
class _Card:
    repo: str
    relative: str
    anchor: str | None  # of the target, or of the section holding an instructions-only declaration
    group: str
    title: str
    match: tuple[str, ...]
    target: _Target | None
    instructions: str | None
    declared: _File
    declared_at: CueComment
    id: str = ""


class _Compiler:
    def __init__(self, files: Mapping[tuple[str, str], _File]):
        self.files = files
        self.cards: list[_Card] = []
        self.faults: list[dict[str, Any]] = []

    def fault(self, file: _File, line: int, problem: str) -> None:
        self.faults.append({"file": file.path, "line": line, "problem": problem})

    # Targets

    def whole_file(self, file: _File) -> _Target:
        outline = file.outline
        return _Target(file, None, outline.body_start, len(outline.lines))

    def section_target(self, file: _File, section: _Section) -> _Target:
        last = _last_line(file.outline, section.heading.line, section.end)
        return _Target(file, section, section.heading.line, last)

    def named_target(self, written: str) -> _Target:
        """A cue_target in the Cue Target form, among the files read (MYC-D89, MYC-D90)."""
        repo, colon, rest = written.partition(":")
        if not colon or not repo or not rest:
            raise _Fault(f"cue_target is not in the form <repo>:<path> or <repo>:<path>#<heading path>: {written}")
        path, hash_mark, heading_path = rest.partition("#")
        file = self.files.get((repo, path))
        if file is None:
            raise _Fault(f"cue_target names no file the compile read: {repo}:{path}")
        if file.outline is None:
            raise _Fault(f"cue_target names a file that is not UTF-8 text: {repo}:{path}")
        if not hash_mark:
            return self.whole_file(file)
        wanted = tuple(heading_path.split(" > "))
        found = [section for section in _sections(file.outline) if section.path == wanted]
        if len(found) != 1:
            raise _Fault(f"cue_target names {'no section' if not found else 'more than one section'}: {written}")
        return self.section_target(file, found[0])

    # Files

    def read_file(self, file: _File) -> None:
        outline = file.outline
        if outline is None:
            if _MARKER in file.document.source:
                self.fault(file, 1, "the file is not UTF-8 text")
            return
        if not outline.comments:
            return
        sections = _sections(outline)
        declarations: list[_Declaration] = []
        for comment in outline.comments:
            try:
                declarations.append(_declaration(comment))
            except _Fault as error:
                self.fault(file, comment.first_line, error.problem)

        file_level = [item for item in declarations if item.literal == "section_headings"]
        form = None
        for position, item in enumerate(file_level):
            line = item.comment.first_line
            if position:
                self.fault(file, line, "a second section_headings declaration in the file")
            elif item.levels is None:
                self.fault(file, line, "section_headings without heading-levels")
            elif item.keys - {"type", "literal", "heading-levels"}:
                extra = sorted(item.keys - {"type", "literal", "heading-levels"})
                self.fault(file, line, "section_headings with another key: " + ", ".join(extra))
            else:
                form = item
        selected = () if form is None else tuple(section for section in sections
                                                 if section.heading.level in form.levels)

        def selected_section(line: int) -> _Section | None:
            return next((section for section in reversed(selected)
                         if section.heading.line < line <= section.end), None)

        excluded: set[int] = set()
        added: dict[int, list[str]] = {}
        local_matches: list[tuple[_Declaration, _Section]] = []
        for item in declarations:
            line = item.comment.first_line
            if item.literal == "section_headings":
                continue
            if item.levels is not None:
                self.fault(file, line, "heading-levels without literal: section_headings")
                continue
            holder = selected_section(line)
            if item.literal == "exclude":
                if item.keys != {"literal"}:
                    self.fault(file, line, "literal: exclude with another key: "
                               + ", ".join(sorted(item.keys - {"literal"})))
                elif holder is None:
                    self.fault(file, line, "literal: exclude outside a selected heading's section")
                else:
                    excluded.add(holder.heading.line)
                continue
            if holder is not None and item.match is not None and item.keys <= {"type", "match"}:
                local_matches.append((item, holder))
                continue
            if not item.typed:
                self.fault(file, line, "the declaration has neither type nor literal")
                continue
            self.ordinary(file, sections, item)
        for item, holder in local_matches:
            if holder.heading.line in excluded:
                self.fault(file, item.comment.first_line, "a match comment in a section whose card is excluded")
            else:
                added.setdefault(holder.heading.line, []).extend(item.match)

        if form is not None:
            for section in selected:
                if section.heading.line in excluded:
                    continue
                terms = [term for term in section.heading.title.split(" / ") if term.strip()]
                terms += added.get(section.heading.line, [])
                if not terms:
                    continue
                self.cards.append(_Card(file.repo, file.document.relative, section.anchor, "glossary",
                                        section.heading.title, tuple(terms), self.section_target(file, section),
                                        None, file, form.comment))

    def ordinary(self, file: _File, sections: tuple[_Section, ...], item: _Declaration) -> None:
        line = item.comment.first_line
        if item.match is None:
            self.fault(file, line, "a literal card without match")
            return
        holder = _section_of(sections, line)
        try:
            if item.cue_target is None:
                target = self.whole_file(file) if holder is None else self.section_target(file, holder)
            elif item.cue_target.strip() == "none":
                target = None
            else:
                target = self.named_target(item.cue_target)
        except _Fault as error:
            self.fault(file, line, error.problem)
            return
        if target is None and item.instructions is None:
            self.fault(file, line, "the card has neither target nor instructions")
            return
        if target is None:
            repo, relative = file.repo, file.document.relative
            anchor = None if holder is None else holder.anchor
            title = item.match[0]
        else:
            repo, relative = target.file.repo, target.file.document.relative
            anchor = None if target.section is None else target.section.anchor
            title = target.section.heading.title if target.section is not None else next(
                (heading.title for heading in target.file.outline.headings),
                target.file.document.path.name)
        self.cards.append(_Card(repo, relative, anchor, "other", title, item.match, target,
                                item.instructions, file, item.comment))


# --- The catalog ------------------------------------------------------------------


def pattern(terms: Iterable[str]) -> str:
    """One expression applying MYC-D85 to all the terms (MYC-21's rule)."""
    ordered = sorted(terms, key=len, reverse=True)  # stable: one length keeps written order
    alternatives = [r"\s+".join(re.escape(word) for word in term.split()) for term in ordered]
    return r"(?i)(?<!\w)(?:" + "|".join(alternatives) + r")(?:e?s)?(?!\w)"


def _target_text(target: _Target) -> str:
    """Remove declaration comments and one blank line after each comment-only line."""
    outline = target.file.outline
    removed: set[int] = set()
    trailing_text: dict[int, str] = {}
    for comment in outline.comments:
        if comment.body is None:
            continue  # an unclosed comment is no declaration and stays
        if comment.last_line < target.first_line or comment.first_line > target.last_line:
            continue
        removed.update(range(comment.first_line, comment.last_line))
        if not _blank(comment.trailing_text):
            trailing_text[comment.last_line] = comment.trailing_text
            continue
        removed.add(comment.last_line)
        after = comment.last_line + 1
        if after <= target.last_line and _blank(outline.lines[after - 1]):
            removed.add(after)
    lines = [trailing_text.get(number, outline.lines[number - 1])
             for number in range(target.first_line, target.last_line + 1)
             if number not in removed]
    while lines and _blank(lines[-1]):
        lines.pop()
    return "\n".join(lines)


def _record(card: _Card) -> dict[str, Any]:
    target = card.target
    text = None if target is None else _target_text(target)
    instructions = None if card.instructions is None else card.instructions.rstrip("\r\n")
    joined = "\n\n".join(piece for piece in (instructions, text) if piece is not None)
    sources = sorted({card.declared.path, *(() if target is None else (target.file.path,))})
    return {
        "id": card.id,
        "type": "literal",
        "group": card.group,
        "title": card.title,
        "match": list(card.match),
        "pattern": pattern(card.match),
        "cue_target": None if target is None else {
            "path": target.file.path,
            "heading": None if target.section is None else target.section.heading.title,
            "anchor": None if target.section is None else target.section.anchor,
            "first_line": target.first_line,
            "last_line": target.last_line,
        },
        "instructions": card.instructions,
        "text": joined,
        "sources": sources,
        "declared_at": {"path": card.declared.path, "first_line": card.declared_at.first_line,
                        "last_line": card.declared_at.last_line},
    }


def _assign_ids(cards: list[_Card]) -> None:
    by_id: dict[str, list[_Card]] = {}
    for card in cards:
        base = f"{card.repo}:{card.relative}" + ("" if card.anchor is None else f"#{card.anchor}")
        by_id.setdefault(base, []).append(card)
    for base, group in by_id.items():
        group.sort(key=lambda card: (card.declared.path, card.declared_at.first_line))
        for position, card in enumerate(group, start=1):
            card.id = base if position == 1 else f"{base}~{position}"


def build_catalog(files: Mapping[tuple[str, str], _File], compiled_at: datetime) -> dict[str, Any]:
    compiler = _Compiler(files)
    for key in sorted(files):
        compiler.read_file(files[key])
    _assign_ids(compiler.cards)
    cards = sorted((_record(card) for card in compiler.cards), key=lambda card: card["id"])
    by_path = {file.path: file for file in files.values()}
    used = sorted({path for card in cards for path in card["sources"]})
    sources = [{"path": path, "repo": by_path[path].repo, "size": by_path[path].document.size,
                "mtime_ns": by_path[path].document.mtime_ns,
                "sha256": sha256(by_path[path].document.source).hexdigest()} for path in used]
    faults = sorted(compiler.faults, key=lambda fault: (fault["file"], fault["line"], fault["problem"]))
    return {"version": CATALOG_VERSION,
            "compiled_at": compiled_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cards": cards, "sources": sources, "faults": faults}


def catalog_path(snapshot: SettingsSnapshot) -> Path:
    home = snapshot._home or Path.home()
    return home / ".mycel" / "cues" / "catalog.json"


def _read_catalog_cards(path: Path) -> list[dict[str, Any]]:
    """Read the cards in catalog order, with no cards when the catalog is unavailable."""
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return []
    if not isinstance(catalog, dict):
        return []
    version, cards = catalog.get("version"), catalog.get("cards")
    if type(version) is not int or version != CATALOG_VERSION or not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def _match_cards(cards: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """Report matches by first appearance, with catalog order for ties."""
    found: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        identifier, expression, terms = card.get("id"), card.get("pattern"), card.get("match")
        target = card.get("cue_target")
        if not isinstance(identifier, str) or not identifier or not isinstance(expression, str):
            continue
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            continue
        if "cue_target" not in card or (target is not None and not isinstance(target, dict)):
            continue
        try:
            match = re.search(expression, text)
        except (re.error, RecursionError, OverflowError, ValueError):
            continue
        if match is not None:
            found.append((match.start(), {"id": identifier, "match": terms, "cue_target": target}))
    found.sort(key=lambda item: item[0])
    return [card for _, card in found]


def write_catalog(path: Path, catalog: Mapping[str, Any]) -> None:
    """Write the whole catalog to a temporary file beside it, then move it into place."""
    encoded = (json.dumps(catalog, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".catalog-", suffix=".json", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise MycelError(ErrorCode.IO, "The Cue Card catalog could not be written; the previous one is kept.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    # Replacement has already published the new catalog. Sync its directory
    # entry for durability when possible.
    with suppress(OSError):
        folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)


@contextmanager
def _catalog_lock(path: Path):
    """Hold the catalog lock from the first source read through publication."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path.parent / "compile.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise MycelError(ErrorCode.IO, "The Cue Card compile lock could not be opened.") from None
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError:
            raise MycelError(ErrorCode.IO, "The Cue Card compile lock could not be acquired.") from None
        yield
    finally:
        os.close(descriptor)


def compile_catalog(snapshot: SettingsSnapshot) -> dict[str, Any]:
    """Compile every enabled repository's declarations and write the catalog (MYC-21.1 to 21.7)."""
    snapshot.require_valid(require_store=False)
    path = catalog_path(snapshot)
    with _catalog_lock(path):
        try:
            files = _read_files(snapshot)
        except OSError:
            raise MycelError(ErrorCode.IO, "An artifact root could not be read completely.") from None
        catalog = build_catalog(files, datetime.now(timezone.utc))
        write_catalog(path, catalog)
    return {"cards": len(catalog["cards"]), "sources": len(catalog["sources"]), "faults": catalog["faults"]}


def handle_cues(invocation: Invocation) -> Result:
    arguments = invocation.arguments
    if arguments != ("compile",) and (len(arguments) != 2 or arguments[0] != "match"):
        raise MycelError(ErrorCode.INVALID_INPUT, "Use mycel cues compile or mycel cues match <text>.")
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    if arguments == ("compile",):
        return Result(compile_catalog(invocation.settings))
    cards = _read_catalog_cards(catalog_path(invocation.settings))
    return Result({"cards": _match_cards(cards, arguments[1])})
