"""Lossless internal Markdown section splitting and comparison hashes.

Stored chunk text is never normalized. Comparisons normalize a separate title
or body projection; file and snapshot hashes always cover exact UTF-8 bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import re
from types import MappingProxyType
import unicodedata
from typing import Any

import yaml


COMPARISON_REVISION = "sha256-nfkc-unicode-whitespace-v1"
UNICODE_VERSION = unicodedata.unidata_version
_ATX = re.compile(r"^ {0,3}(#{1,6})([ \t].*|$)")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_DELIMITER = re.compile(r"^(?:---|\.\.\.)[ \t]*$")
_NON_PARAGRAPH = re.compile(r"^ {0,3}(?:>|(?:[-+*]|[0-9]{1,9}[.)])[ \t]+|<(?:[A-Za-z!/]|\?))")
_THEMATIC = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$")
_CONTAINER = re.compile(r"^ {0,3}(?:>[ ]?|(?:[-+*]|[0-9]{1,9}[.)])[ ]+)")
_QUOTE = re.compile(r"^ {0,3}>[ ]?")
_RAW_HTML_OPEN = re.compile(r"^ {0,3}<(?:pre|script|style|textarea)(?=[ \t>]|$)", re.IGNORECASE)
_RAW_HTML_CLOSE = re.compile(r"</(?:pre|script|style|textarea)>", re.IGNORECASE)
_HTML_BLOCK_TAGS = ("address article aside base basefont blockquote body caption center col colgroup dd "
                    "details dialog dir div dl dt fieldset figcaption figure footer form frame frameset "
                    "h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu menuitem nav "
                    "noframes ol optgroup option p param search section summary table tbody td tfoot "
                    "th thead title tr track ul")
_BLOCK_HTML_OPEN = re.compile(r"^ {0,3}</?(?:" + "|".join(_HTML_BLOCK_TAGS.split())
                              + r")(?=[ \t/>]|$)", re.IGNORECASE)
_TABLE_ROW = re.compile(r"^ {0,3}\|.*\|[ \t]*$")
_DELIMITER_ROW = re.compile(r"^ {0,3}\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$")
_ENTITY_CELL = re.compile(r"^(?P<id>[A-Z][A-Z0-9]*-(?:D[1-9][0-9]*|[0-9]+\.[1-9][0-9]*))"
                          r"(?:[ \t]+<!--[ \t]*(?P<uuid>[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
                          r"-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})[ \t]*-->)?$")
_CHAT_URI = re.compile(r"\[(?:[A-Za-z0-9_-]+:)?cht:[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
                       r"-[0-9A-Fa-f]{12}:[A-Za-z0-9+/=_-]*\]")
_DECIDED = re.compile(r"^Decided (?P<when>[0-9]{1,2} [A-Za-z]+ [0-9]{4})(?: by (?P<who>[^:;.]+?))?(?=[:;.]|$)")
_COMPLETE_HTML_TAG = re.compile(
    r"^ {0,3}(?:</[A-Za-z][A-Za-z0-9-]*+[ \t]*+>|"
    r"<[A-Za-z][A-Za-z0-9-]*+(?:[ \t]++[A-Za-z_:][A-Za-z0-9_.:-]*+"
    r"(?:[ \t]*+=[ \t]*+(?:[^ \t\r\n\"'=<>`]++|'[^']*+'|\"[^\"]*+\"))?)*+[ \t]*+/?>)[ \t]*+$")


class MarkdownDecodeError(ValueError):
    """The source cannot be represented as exact UTF-8 Markdown text."""


@dataclass(frozen=True)
class SourceSpan:
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class MarkdownDiagnostic:
    code: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class MarkdownChunk:
    name: str
    title: str | None
    heading_path: tuple[str, ...]
    heading_level: int | None
    text: str = field(repr=False)
    body: str = field(repr=False)
    span: SourceSpan
    heading_end_line: int | None
    content_hash: str
    title_hash: str
    snapshot_hash: str
    comparison_revision: str = COMPARISON_REVISION
    unicode_version: str = UNICODE_VERSION


@dataclass(frozen=True)
class EntityRow:
    """One requirement or decision row of a table, an entity keyed by its UUID (MYC-17).

    ``text`` is the exact physical row with its line ending; ``title`` and the
    metadata are read from the cells under the table's header. ``section`` is
    the name of the chunk that holds the row, ``position`` the row's place
    among the body rows of its table, counted from 1.
    """

    kind: str                      # "req" or "dec"
    uuid: str
    id: str                        # the human id, the display name
    title: str
    text: str = field(repr=False)
    line: int
    position: int
    section: str
    byte_start: int
    byte_end: int
    columns: tuple[str, ...]
    cells: tuple[str, ...]
    status: str | None
    decided_by: str | None
    decided_at: str | None
    verified_by: str | None
    from_v1: str | None
    discussion: tuple[str, ...]
    content_hash: str
    snapshot_hash: str

    def metadata(self) -> dict[str, Any]:
        """The JSON-ready entity fields of a stored chunk version."""
        result: dict[str, Any] = {"kind": self.kind, "uuid": self.uuid, "id": self.id, "title": self.title}
        if self.status is not None:
            result["status"] = self.status
        for key, value in (("decidedBy", self.decided_by), ("decidedAt", self.decided_at),
                           ("verifiedBy", self.verified_by), ("fromV1", self.from_v1)):
            if value is not None:
                result[key] = value
        if self.kind == "dec":
            result["discussion"] = list(self.discussion)
        return result


@dataclass(frozen=True)
class MarkdownDocument:
    source: bytes = field(repr=False)
    text: str = field(repr=False)
    file_hash: str
    frontmatter: Mapping[str, Any] = field(repr=False)
    frontmatter_present: bool
    frontmatter_valid: bool
    frontmatter_span: SourceSpan | None
    frontmatter_text: str | None = field(repr=False)
    chunks: tuple[MarkdownChunk, ...]
    diagnostics: tuple[MarkdownDiagnostic, ...] = ()
    entities: tuple[EntityRow, ...] = ()


@dataclass(frozen=True)
class _Line:
    text: str
    content: str
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class _Heading:
    title: str
    level: int
    start: int
    end: int


class _FrontmatterError(yaml.YAMLError):
    def __init__(self, message: str, mark: Any = None):
        self.problem = message
        self.problem_mark = mark
        super().__init__(message)


class _SettingsLoader(yaml.SafeLoader):
    """Safe YAML, with explicit duplicate and non-text-key faults."""

    # Timestamp-like unknown settings remain text rather than becoming
    # datetime instances that cannot travel through a later JSON reply.
    yaml_implicit_resolvers = {
        key: [(tag, expression) for tag, expression in values
              if tag != "tag:yaml.org,2002:timestamp"]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise _FrontmatterError("Frontmatter must be a settings mapping.", node.start_mark)
        explicit = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise _FrontmatterError("Frontmatter settings keys must be text.", key_node.start_mark)
            if key in explicit:
                raise _FrontmatterError("Frontmatter contains a repeated settings key.", key_node.start_mark)
            explicit.add(key)
        # YAML merges precede explicit fields, so an explicit value may
        # intentionally override its anchor without becoming a repeated key.
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise _FrontmatterError("Frontmatter settings keys must be text.", key_node.start_mark)
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _immutable(value: Any, *, seen: set[int] | None = None,
               memo: dict[int, Any] | None = None) -> Any:
    """Freeze safe YAML while preserving shared aliases and refusing cycles."""
    if not isinstance(value, (dict, list, tuple, set)):
        return value
    seen, memo = (set() if seen is None else seen), ({} if memo is None else memo)
    identity = id(value)
    if identity in seen:
        raise _FrontmatterError("Frontmatter contains a recursive YAML alias.")
    if identity in memo:
        return memo[identity]
    seen.add(identity)
    if isinstance(value, dict):
        result = MappingProxyType({key: _immutable(member, seen=seen, memo=memo)
                                   for key, member in value.items()})
    elif isinstance(value, set):
        result = frozenset(_immutable(member, seen=seen, memo=memo) for member in value)
    else:
        result = tuple(_immutable(member, seen=seen, memo=memo) for member in value)
    seen.remove(identity)
    memo[identity] = result
    return result


def normalize_comparison(text: str) -> str:
    """The complete MYC-1 title/body comparison projection."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def comparison_hash(text: str) -> str:
    return sha256(normalize_comparison(text).encode("utf-8")).hexdigest()


def snapshot_hash(source: bytes) -> str:
    return sha256(source).hexdigest()


def _lines(text: str) -> tuple[_Line, ...]:
    lines, byte_offset = [], 0
    # Only CR/LF are Markdown line endings. str.splitlines would split
    # Unicode whitespace inside text and change source line/heading semantics.
    for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text):
        raw = match.group()
        if not raw:
            continue
        encoded_size = len(raw.encode("utf-8"))
        lines.append(_Line(raw, raw.rstrip("\r\n"), byte_offset, byte_offset + encoded_size))
        byte_offset += encoded_size
    return tuple(lines)


def _frontmatter(lines: tuple[_Line, ...]) -> tuple[Mapping[str, Any], bool, bool, int,
                                                 SourceSpan | None, str | None,
                                                 tuple[MarkdownDiagnostic, ...]]:
    empty = MappingProxyType({})
    if not lines or not re.fullmatch(r"---[ \t]*", lines[0].content.removeprefix("\ufeff")):
        return empty, False, True, 0, None, None, ()
    ending = next((index for index in range(1, len(lines))
                   if _DELIMITER.fullmatch(lines[index].content)), None)
    if ending is None:
        return empty, True, False, 0, None, None, (
            MarkdownDiagnostic("frontmatter_unclosed", "The leading frontmatter block has no closing delimiter.", 1),)
    raw = "".join(line.text for line in lines[:ending + 1])
    span = SourceSpan(1, ending + 1, 0, lines[ending].byte_end)
    content = "".join(line.text for line in lines[1:ending])
    try:
        settings = yaml.load(content, Loader=_SettingsLoader)
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise _FrontmatterError("Frontmatter must be a settings mapping.")
        settings = _immutable(settings)
    except (yaml.YAMLError, RecursionError, ValueError, TypeError) as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 2 if mark is not None else 1
        message = (error.problem if isinstance(error, _FrontmatterError)
                   else "The leading frontmatter block is not readable safe YAML.")
        return empty, True, False, 0, span, raw, (
            MarkdownDiagnostic("frontmatter_invalid", message, line),)
    return settings, True, True, ending + 1, span, raw, ()


def _container_prefix(content: str) -> tuple[str, tuple[tuple[str, int], ...]]:
    """Read explicit quote/list chains for block state, without altering source."""
    view = content.expandtabs(4)
    containers = []
    while marker := _CONTAINER.match(view):
        prefix = marker.group()
        containers.append(("quote" if ">" in prefix else "list", len(prefix)))
        view = view[marker.end():]
    return view, tuple(containers)


def _in_container(content: str, containers: tuple[tuple[str, int], ...]) -> str | None:
    view = content.expandtabs(4)
    for kind, width in containers:
        if kind == "quote":
            marker = _QUOTE.match(view)
            if marker is None:
                return None
            view = view[marker.end():]
        elif not view.strip(" "):
            view = ""
        elif len(view) - len(view.lstrip(" ")) < width:
            return None
        else:
            view = view[width:]
    return view


def _html_block(content: str, *, can_start_type_seven: bool) -> str | None:
    """CommonMark 4.6 block kinds; None means ordinary Markdown content."""
    if _RAW_HTML_OPEN.match(content):
        return "raw"
    beginning = content.lstrip(" ") if len(content) - len(content.lstrip(" ")) <= 3 else content
    if beginning.startswith("<!--"):
        return "comment"
    if beginning.startswith("<?"):
        return "processing"
    if beginning.startswith("<![CDATA["):
        return "cdata"
    if re.match(r"<![A-Za-z]", beginning):
        return "declaration"
    if _BLOCK_HTML_OPEN.match(content):
        return "blank"
    if can_start_type_seven and _COMPLETE_HTML_TAG.fullmatch(content):
        return "blank"
    return None


def _html_ends(kind: str, content: str) -> bool:
    if kind == "raw":
        return _RAW_HTML_CLOSE.search(content) is not None
    if kind == "blank":
        return not content.strip(" \t")
    return {"comment": "-->", "processing": "?>", "declaration": ">", "cdata": "]]>"}[kind] in content


class _ReferenceCursor:
    """A bounded-lookahead character cursor over original physical lines."""

    def __init__(self, lines: tuple[_Line, ...], line: int, column: int = 0):
        self.lines, self.line, self.column = lines, line, column

    def peek(self) -> str | None:
        if self.line >= len(self.lines):
            return None
        content = self.lines[self.line].content
        if self.column < len(content):
            return content[self.column]
        return "\n" if self.lines[self.line].text.endswith(("\r", "\n")) else None

    def advance(self) -> None:
        if self.peek() == "\n":
            self.line, self.column = self.line + 1, 0
        else:
            self.column += 1

    def horizontal(self) -> None:
        while self.peek() in {" ", "\t"}:
            self.advance()


_ESCAPABLE = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _reference_title(cursor: _ReferenceCursor) -> int | None:
    opening = cursor.peek()
    if opening not in {"\"", "'", "("}:
        return None
    closing = ")" if opening == "(" else opening
    cursor.advance()
    while (character := cursor.peek()) is not None:
        if character == closing:
            cursor.advance()
            cursor.horizontal()
            return cursor.line + 1 if cursor.peek() in {None, "\n"} else None
        if character == "(" and opening == "(":
            return None
        if character == "\n":
            cursor.advance()
            if cursor.line < len(cursor.lines) and not cursor.lines[cursor.line].content.strip(" \t"):
                return None
        elif character == "\\":
            cursor.advance()
            if cursor.peek() in _ESCAPABLE:
                cursor.advance()
        else:
            cursor.advance()
    return None


def _link_reference_end(lines: tuple[_Line, ...], beginning: int) -> int | None:
    """Consume a valid top-level CommonMark definition before section headings.

    Definitions stay in their exact preamble/body text. They are not heading
    paragraphs, including when a destination or optional title uses later
    physical lines. Failed title lookahead on a later line keeps a valid URL
    definition on its own line, rather than consuming ordinary document text.
    """
    marker = re.match(r"^ {0,3}\[", lines[beginning].content)
    if marker is None:
        return None
    cursor = _ReferenceCursor(lines, beginning, marker.end())
    label = []
    while (character := cursor.peek()) is not None and character != "]":
        if character == "[" or len(label) >= 999:
            return None
        label.append(character)
        cursor.advance()
        if character == "\\" and cursor.peek() in _ESCAPABLE:
            label.append(cursor.peek())
            cursor.advance()
        elif character == "\n" and (cursor.line >= len(lines) or not lines[cursor.line].content.strip(" \t")):
            return None
    if cursor.peek() != "]" or len(label) > 999 or not "".join(label).strip():
        return None
    cursor.advance()
    if cursor.peek() != ":":
        return None
    cursor.advance()
    cursor.horizontal()
    if cursor.peek() == "\n":
        cursor.advance()
        cursor.horizontal()
    if cursor.peek() == "<":
        cursor.advance()
        while (character := cursor.peek()) not in {None, "\n", ">"}:
            if character == "<":
                return None
            cursor.advance()
            if character == "\\" and cursor.peek() in _ESCAPABLE:
                cursor.advance()
        if cursor.peek() != ">":
            return None
        cursor.advance()
    else:
        length, parentheses = 0, 0
        while (character := cursor.peek()) not in {None, "\n", " ", "\t"}:
            if character == "<" or ord(character) < 32 or ord(character) == 127:
                return None
            if character == "(":
                parentheses += 1
            elif character == ")":
                parentheses -= 1
                if parentheses < 0:
                    return None
            cursor.advance()
            length += 1
            if character == "\\" and cursor.peek() in _ESCAPABLE:
                cursor.advance()
        if not length or parentheses:
            return None
    had_space = cursor.peek() in {" ", "\t"}
    cursor.horizontal()
    if cursor.peek() in {None, "\n"}:
        url_end = cursor.line + 1
        if cursor.peek() == "\n":
            cursor.advance()
            cursor.horizontal()
            title_end = _reference_title(cursor)
            return url_end if title_end is None else title_end
        return url_end
    return _reference_title(cursor) if had_space else None


def _headings(lines: tuple[_Line, ...], start: int) -> tuple[_Heading, ...]:
    result: list[_Heading] = []
    fence_character, fence_length = None, 0
    fence_containers: tuple[tuple[str, int], ...] = ()
    container_context: tuple[tuple[str, int], ...] = ()
    html_kind: str | None = None
    html_containers: tuple[tuple[str, int], ...] = ()
    reference_end = start
    paragraph_start: int | None = None
    for index in range(start, len(lines)):
        if index < reference_end:
            continue
        content = lines[index].content
        if index == 0:
            content = content.removeprefix("\ufeff")
        if fence_character is not None:
            view = _in_container(content, fence_containers)
            if view is None:
                # A fence contained in a list/quote ends with that container.
                fence_character, fence_length = None, 0
                container_context = ()
            elif re.fullmatch(r" {0,3}" + re.escape(fence_character) + "{" + str(fence_length) + r",}[ \t]*", view):
                fence_character, fence_length = None, 0
                continue
            else:
                continue
        if html_kind is not None:
            view = _in_container(content, html_containers)
            if view is None:
                html_kind = None
                container_context = ()
            else:
                if _html_ends(html_kind, view):
                    html_kind = None
                continue
        inherited = _in_container(content, container_context)
        if inherited is None:
            container_context = ()
            inherited = content
        view, explicit_containers = _container_prefix(inherited)
        containers = container_context + explicit_containers
        if explicit_containers:
            container_context = containers
        opener = _FENCE.fullmatch(view)
        if opener is not None:
            marker, info = opener.groups()
            if marker[0] != "`" or "`" not in info:
                fence_character, fence_length = marker[0], len(marker)
                fence_containers = containers
                paragraph_start = None
                continue
        block = _html_block(view, can_start_type_seven=paragraph_start is None)
        if block is not None:
            if not _html_ends(block, view):
                html_kind, html_containers = block, containers
            paragraph_start = None
            continue
        if paragraph_start is None:
            definition_end = _link_reference_end(lines, index)
            if definition_end is not None:
                reference_end = definition_end
                continue
        heading = _ATX.fullmatch(content)
        if heading is not None:
            marks, title = heading.groups()
            title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip(" \t")
            result.append(_Heading(title, len(marks), index, index + 1))
            paragraph_start = None
            continue
        underline = _SETEXT.fullmatch(content)
        if underline is not None and paragraph_start is not None:
            title = " ".join(lines[position].content.strip(" \t")
                             for position in range(paragraph_start, index))
            result.append(_Heading(title, 1 if underline.group(1)[0] == "=" else 2,
                                   paragraph_start, index + 1))
            paragraph_start = None
            continue
        if (not content.strip(" \t") or (content.startswith(("    ", "\t")) and paragraph_start is None)
                or _NON_PARAGRAPH.match(content) or _THEMATIC.fullmatch(content)):
            paragraph_start = None
        elif paragraph_start is None:
            paragraph_start = index
    return tuple(result)


def _names(bases: tuple[str, ...]) -> tuple[str, ...]:
    # Reserve literal names throughout the file before allocating a suffix.
    # A later heading literally called "Setup (2)" keeps that name even when
    # an earlier duplicate "Setup" needs its own number.
    reserved, used, next_number, result = set(bases), set(), {}, []
    for base in bases:
        if base not in used:
            name = base
        else:
            number = next_number.get(base, 2)
            name = f"{base} ({number})"
            while name in used or name in reserved:
                number += 1
                name = f"{base} ({number})"
            next_number[base] = number + 1
        used.add(name)
        result.append(name)
    return tuple(result)


def _cells(content: str) -> tuple[str, ...]:
    """Split a pipe-table row into its cells; a backslash keeps a literal pipe."""
    inner = content.strip(" \t")
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    cells, current, escaped = [], [], False
    for character in inner:
        if escaped:
            current.append(character if character == "|" else "\\" + character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip(" \t"))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip(" \t"))
    return tuple(cells)


def _column(columns: tuple[str, ...], cells: tuple[str, ...], *names: str) -> str | None:
    lowered = [column.strip().lower() for column in columns]
    for name in names:
        if name in lowered:
            index = lowered.index(name)
            return cells[index] if index < len(cells) else None
    return None


def _entity_row(content: str, line: int, position: int, section: str, columns: tuple[str, ...],
                text: str, original: bytes, byte_start: int, byte_end: int,
                document_status: str | None) -> EntityRow | tuple[str, int, str] | None:
    cells = _cells(content)
    if not cells:
        return None
    match = _ENTITY_CELL.fullmatch(cells[0])
    if match is None:
        return None
    identifier, uuid = match.group("id"), match.group("uuid")
    if uuid is None:
        return ("entity_missing_uuid", line, f"The row {identifier} has no UUID comment in its first cell.")
    kind = "dec" if "-D" in identifier else "req"
    second = cells[1] if len(cells) > 1 else ""
    if kind == "req":
        title = second
        verified = _column(columns, cells, "verified by")
        from_v1 = _column(columns, cells, "from v1", "origin")
        # A requirement can describe withdrawn objects while still active.
        # Withdrawal is an explicit row marker, not an arbitrary word in it.
        withdrawn = re.match(r"^withdrawn(?:$|:|\s+[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\b)",
                             second.strip(), re.IGNORECASE)
        status = "withdrawn" if withdrawn else document_status
        decided_by = decided_at = None
        discussion: tuple[str, ...] = ()
    else:
        title = _column(columns, cells, "question") or second
        outcome = _column(columns, cells, "outcome") or ""
        decided = _DECIDED.match(outcome.strip())
        status = "decided" if decided is not None else "open"
        decided_at = decided.group("when") if decided is not None else None
        decided_by = (decided.group("who") or "").strip() or None if decided is not None else None
        verified = from_v1 = None
        discussion = tuple(_CHAT_URI.findall(_column(columns, cells, "discussion") or ""))
    return EntityRow(kind, uuid.lower(), identifier, title, text, line, position, section, byte_start, byte_end,
                     columns, cells,
                     status, decided_by, decided_at, verified, from_v1, discussion,
                     comparison_hash(text), snapshot_hash(original[byte_start:byte_end]))


def _entities(lines: tuple[_Line, ...], original: bytes, chunks: tuple[MarkdownChunk, ...],
              frontmatter: Mapping[str, Any]) -> tuple[tuple[EntityRow, ...], tuple[MarkdownDiagnostic, ...]]:
    """Recognise requirement and decision rows of pipe tables outside fences.

    A table is a header row followed by a delimiter row; its body rows follow
    until a line that is not a row. Rows inside a code fence are text.
    """
    status = frontmatter.get("status") if isinstance(frontmatter, Mapping) else None
    status = status if isinstance(status, str) else None
    section_of = {}
    for chunk in chunks:
        for number in range(chunk.span.line_start, chunk.span.line_end + 1):
            section_of[number] = chunk.name
    rows: list[EntityRow] = []
    faults: list[MarkdownDiagnostic] = []
    fence: str | None = None
    columns: tuple[str, ...] | None = None
    position = 0
    index = 0
    while index < len(lines):
        content = lines[index].content
        if index == 0:
            content = content.removeprefix("\ufeff")
        stripped = content.lstrip(" ")
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            columns = None
            index += 1
            continue
        opener = _FENCE.fullmatch(content)
        if opener is not None:
            fence = opener.group(1)[0] * len(opener.group(1))
            columns = None
            index += 1
            continue
        if _TABLE_ROW.fullmatch(content):
            if columns is None:
                if index + 1 < len(lines) and _DELIMITER_ROW.fullmatch(lines[index + 1].content):
                    columns = _cells(content)
                    position = 0
                    index += 2
                    continue
                index += 1
                continue
            position += 1
            line = lines[index]
            result = _entity_row(content, index + 1, position, section_of.get(index + 1, "<preamble>"), columns,
                                 line.text, original, line.byte_start, line.byte_end, status)
            if isinstance(result, EntityRow):
                rows.append(result)
            elif result is not None:
                faults.append(MarkdownDiagnostic(result[0], result[2], result[1]))
        else:
            columns = None
        index += 1
    seen: dict[str, list[EntityRow]] = {}
    for row in rows:
        seen.setdefault(row.uuid, []).append(row)
    kept = []
    for row in rows:
        if len(seen[row.uuid]) > 1:
            faults.append(MarkdownDiagnostic("entity_repeated_uuid",
                                             f"The row {row.id} repeats the UUID {row.uuid} of another row.", row.line))
        else:
            kept.append(row)
    return tuple(kept), tuple(sorted(faults, key=lambda item: (item.line or 0, item.code)))


def split_markdown(source: bytes | str) -> MarkdownDocument:
    """Split exact UTF-8 source into independent logical heading sections.

    Line spans are inclusive, byte spans half-open. Valid leading frontmatter
    has its own retained span and settings. Invalid frontmatter is diagnostic
    and remains in complete chunk coverage so that no bytes disappear.
    """
    if not isinstance(source, (bytes, str)):
        raise TypeError("Markdown source must be bytes or text.")
    try:
        original = source.encode("utf-8") if isinstance(source, str) else source
        text = original.decode("utf-8")
    except UnicodeError:
        raise MarkdownDecodeError("Markdown source is not exact UTF-8 text.") from None
    lines = _lines(text)
    settings, present, valid, start, frontmatter_span, frontmatter_text, diagnostics = _frontmatter(lines)
    headings = _headings(lines, start)
    sections: list[tuple[_Heading | None, int, int, tuple[str, ...]]] = []
    stack: list[_Heading] = []
    if start < len(lines) and (not headings or start < headings[0].start):
        sections.append((None, start, headings[0].start if headings else len(lines), ()))
    for position, heading in enumerate(headings):
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
        path = tuple(parent.title for parent in stack)
        end = headings[position + 1].start if position + 1 < len(headings) else len(lines)
        sections.append((heading, heading.start, end, path))
    names = _names(tuple((" > ".join(path) or "<untitled>") if heading is not None else "<preamble>"
                         for heading, _, _, path in sections))
    chunks = []
    for name, (heading, beginning, ending, path) in zip(names, sections, strict=True):
        exact = "".join(line.text for line in lines[beginning:ending])
        body_start = heading.end if heading is not None else beginning
        body = "".join(line.text for line in lines[body_start:ending])
        span = SourceSpan(beginning + 1, ending, lines[beginning].byte_start, lines[ending - 1].byte_end)
        title = heading.title if heading is not None else None
        chunks.append(MarkdownChunk(name, title, path, heading.level if heading is not None else None,
                                    exact, body, span, heading.end if heading is not None else None,
                                    comparison_hash(body), comparison_hash(title or ""),
                                    snapshot_hash(original[span.byte_start:span.byte_end])))
    entities, faults = _entities(lines, original, tuple(chunks), settings)
    return MarkdownDocument(original, text, snapshot_hash(original), settings, present, valid,
                            frontmatter_span, frontmatter_text, tuple(chunks), diagnostics + faults, entities)
