"""Pure document declarations and portable source-address syntax.

Parsing does not look up repositories or select indexed identities. A parsed
legacy address deliberately has no root; only the shared store resolver may
establish whether its literal path names one physical file.
"""

from __future__ import annotations

import base64
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Any, Literal
import unicodedata
from urllib.parse import quote, unquote_to_bytes

from mycel._markdown import (MarkdownDocument, _ATX, _FENCE, _SETEXT, _THEMATIC,
                             _container_prefix, _html_block, _html_ends,
                             _in_container, _lines, _link_reference_end)


Root = Literal["code", "artifact", "index"]
_ROOTS = frozenset({"code", "artifact", "index"})
_QUALIFIED = re.compile(r"^@(code|artifact|index)/")
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ENCODED_SEPARATOR = re.compile(r"%2[fF]")
_DECLARATION_HEADER = re.compile(r"<!--[ \t\r\n]*(sources|related):[ \t]*", re.IGNORECASE)
_BACKTICKS = re.compile(r"`+")
_ESCAPABLE = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_HTML_TAG = re.compile(
    r"(?:</[A-Za-z][A-Za-z0-9-]*+[ \t\r\n]*+>|"
    r"<[A-Za-z][A-Za-z0-9-]*+(?:[ \t\r\n]++[A-Za-z_:][A-Za-z0-9_.:-]*+"
    r"(?:[ \t\r\n]*+=[ \t\r\n]*+(?:[^ \t\r\n\"'=<>`]++|'[^']*+'|\"[^\"]*+\"))?)*+[ \t\r\n]*+/?>)")
_AUTOLINK = re.compile(
    r"<(?:[A-Za-z][A-Za-z0-9.+-]{1,31}:[^<>\x00-\x20]*|"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>")


_ENTITY_URI = re.compile(r"\[(?:(?P<repository>[^:\[\]\s]+):)?(?P<kind>[a-z0-9]{1,3}):(?P<uuid>[0-9A-Fa-f]{8}-"
                         r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}):(?P<title>[A-Za-z0-9+/=_-]*)\]\Z")
ENTITY_KIND_TAGS = MappingProxyType({"req": "req", "dec": "dec", "cht": "cht"})


@dataclass(frozen=True)
class EntityUri:
    """The glossary's Entity URI: [<repo>:<tag>:<uuid>:<title-base64>] or without the repo.

    Identity is the UUID alone; the kind tag is a check and the title a display
    snapshot. ``repository`` is None for the three-part form and for ``any``.
    """

    kind: str
    uuid: str
    title_base64: str = ""
    repository: str | None = None

    @property
    def title(self) -> str:
        if not self.title_base64:
            return ""
        try:
            padded = self.title_base64 + "=" * (-len(self.title_base64) % 4)
            return base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=False).decode("utf-8")
        except (ValueError, UnicodeError):
            return ""

    @property
    def text(self) -> str:
        parts = [self.kind, self.uuid, self.title_base64]
        if self.repository is not None:
            parts.insert(0, self.repository)
        return "[" + ":".join(parts) + "]"


def parse_entity_uri(value: str) -> EntityUri | None:
    """Parse an Entity URI; None when the text is not one. Never raises."""
    if not isinstance(value, str):
        return None
    match = _ENTITY_URI.fullmatch(value.strip())
    if match is None:
        return None
    repository = match.group("repository")
    if repository == "any":
        repository = None
    return EntityUri(match.group("kind").lower(), match.group("uuid").lower(), match.group("title"), repository)


def format_entity_uri(kind: str, uuid: str, title: str, repository: str | None = None) -> str:
    """Write an Entity URI with the title Base64-encoded as the glossary says."""
    if kind not in ENTITY_KIND_TAGS or not isinstance(uuid, str) or not isinstance(title, str):
        raise ValueError("An Entity URI needs a known kind tag, a UUID and a title.")
    encoded = base64.b64encode(title.encode("utf-8")).decode("ascii")
    return EntityUri(kind, uuid.lower(), encoded, repository).text


class SourceAddressError(ValueError):
    """Visible syntax failure; eligibility and lookup faults are separate."""

    fault = "not_a_ref"


@dataclass(frozen=True)
class SourceAddress:
    repository: str
    root: Root | None
    path: str
    name: str | None = None

    @property
    def address(self) -> str:
        return format_source_address(self)


def _component(value: str, description: str) -> None:
    if not isinstance(value, str) or not value:
        raise SourceAddressError(f"The {description} must be nonempty text.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise SourceAddressError(f"The {description} is not exact UTF-8 text.") from None
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise SourceAddressError(f"The {description} contains a control character.")


def _path(value: str) -> None:
    _component(value, "path")
    if "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise SourceAddressError("The path must use nonempty relative slash-separated components.")


def _validate(address: SourceAddress) -> None:
    _component(address.repository, "repository")
    _path(address.path)
    if address.root is not None and (not isinstance(address.root, str) or address.root not in _ROOTS):
        raise SourceAddressError("The qualified root is not supported.")
    if address.root == "index" and address.path not in {"summaries", "overview"}:
        raise SourceAddressError("The index namespace is not supported.")
    if address.name is not None:
        _component(address.name, "name")
    if address.root is None:
        if ":" in address.repository or "#" in address.repository or "#" in address.path:
            raise SourceAddressError("A legacy component contains a literal address delimiter.")
        if _QUALIFIED.match(address.path):
            raise SourceAddressError("The path begins with a reserved qualified prefix.")


def _decode(value: str, description: str) -> str:
    if _BAD_ESCAPE.search(value):
        raise SourceAddressError(f"The {description} contains a malformed percent escape.")
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError:
        raise SourceAddressError(f"The {description} is not exact UTF-8 text.") from None


def parse_source_address(ref: str) -> SourceAddress:
    """Parse one ref without guessing its root, meaning or eligibility.

    Only the three literal reserved prefixes select qualified syntax. Legacy
    percent signs remain literal, including sequences resembling bad escapes.
    """
    _component(ref, "reference")
    repository, separator, rest = ref.partition(":")
    if not separator:
        raise SourceAddressError("The reference has no repository separator.")
    path, name_separator, name = rest.partition("#")
    marker = _QUALIFIED.match(path)
    if marker is None:
        address = SourceAddress(repository, None, path, name if name_separator else None)
    else:
        root = marker.group(1)
        encoded_path = path[marker.end():]
        if (":" in encoded_path or ":" in name or "#" in name or "#" in repository):
            raise SourceAddressError("Qualified component delimiters must be percent escaped.")
        if _ENCODED_SEPARATOR.search(encoded_path):
            raise SourceAddressError("A path component contains an encoded slash.")
        address = SourceAddress(_decode(repository, "repository"), root,
                                _decode(encoded_path, "path"),
                                _decode(name, "name") if name_separator else None)
    _validate(address)
    return address


def format_source_address(address: SourceAddress) -> str:
    """Format qualified components canonically; retain literal legacy refs."""
    if not isinstance(address, SourceAddress):
        raise TypeError("A SourceAddress is required.")
    _validate(address)
    if address.root is None:
        return f"{address.repository}:{address.path}" + (f"#{address.name}" if address.name is not None else "")
    repository = quote(address.repository, safe="-._~", encoding="utf-8", errors="strict")
    path = quote(address.path, safe="/-._~", encoding="utf-8", errors="strict")
    name = "" if address.name is None else "#" + quote(address.name, safe="-._~", encoding="utf-8", errors="strict")
    return f"{repository}:@{address.root}/{path}{name}"


@dataclass(frozen=True)
class DeclarationDiagnostic:
    file: str
    code: str
    message: str
    key: str | None = None
    line: int | None = None
    value: Any = field(default=None, repr=False)


@dataclass(frozen=True)
class DeclaredSource:
    ref: str
    declared: str
    raw_line: str
    origin: Literal["frontmatter", "comment"]
    chunk: str | None
    line: int | None
    address: SourceAddress | None
    fault: Literal["not_a_ref"] | None = None


@dataclass(frozen=True)
class ChunkSources:
    chunk: str
    sources: tuple[DeclaredSource, ...]


@dataclass(frozen=True)
class ChunkRelations:
    chunk: str
    relations: tuple[DeclaredSource, ...]


@dataclass(frozen=True)
class DocumentDeclarations:
    file: str
    metadata: Mapping[str, Any]
    frontmatter_sources: tuple[DeclaredSource, ...]
    chunk_sources: tuple[ChunkSources, ...]
    diagnostics: tuple[DeclarationDiagnostic, ...]
    chunk_relations: tuple[ChunkRelations, ...] = ()

    @property
    def role(self) -> Literal["authored", "derived"] | None:
        return self.metadata.get("role")

    @property
    def heartwood(self) -> bool:
        return self.metadata.get("heartwood", False)

    @property
    def generated(self) -> bool:
        return self.metadata.get("generated", False)


def _declaration(ref: str, declared: str, raw_line: str,
                 origin: Literal["frontmatter", "comment"], chunk: str | None,
                 line: int | None, *, incomplete: bool = False) -> DeclaredSource:
    entity = parse_entity_uri(ref)
    bracketed = isinstance(ref, str) and ref.startswith('[') and ref.endswith(']')
    try:
        address = None if entity is not None or bracketed else parse_source_address(ref)
    except SourceAddressError:
        address = None
    if incomplete:
        address = None
    # UUID references have no syntactic path; the store resolver supplies it.
    valid_entity = not incomplete and entity is not None
    return DeclaredSource(ref, declared, raw_line, origin, chunk, line,
                          address, "not_a_ref" if address is None and not valid_entity else None)


@dataclass(frozen=True)
class _ProseLine:
    text: str
    line: int
    raw: str


def _link_space_end(text: str, position: int) -> int:
    """Skip horizontal whitespace and at most one original line ending."""
    while position < len(text) and text[position] in " \t":
        position += 1
    if position < len(text) and text[position] in "\r\n":
        position += 2 if text.startswith("\r\n", position) else 1
        while position < len(text) and text[position] in " \t":
            position += 1
    return position


def _inline_link_end(text: str, position: int) -> int | None:
    """Recognize only a complete destination/title after a matched label.

    Its source is opaque inline syntax, so neither a backtick nor an HTML
    comment in a title is prose. Failure leaves the source to the ordinary
    inline scanner; no malformed suffix is silently consumed.
    """
    if position >= len(text) or text[position] != "(":
        return None
    position = _link_space_end(text, position + 1)
    if position >= len(text):
        return None
    if text[position] == "<":
        position += 1
        while position < len(text) and text[position] != ">":
            character = text[position]
            if character in "<\r\n":
                return None
            position += 1
            if character == "\\" and position < len(text) and text[position] in _ESCAPABLE:
                position += 1
        if position == len(text):
            return None
        position += 1
    else:
        beginning, parentheses = position, 0
        while position < len(text):
            character = text[position]
            if character == "<":
                return None
            if ord(character) <= 32 or ord(character) == 127:
                break
            if character == "(":
                parentheses += 1
            elif character == ")":
                if not parentheses:
                    break
                parentheses -= 1
            position += 1
            if character == "\\" and position < len(text) and text[position] in _ESCAPABLE:
                position += 1
        if parentheses or (position == beginning and (position == len(text) or text[position] != ")")):
            return None
    destination_end = position
    position = _link_space_end(text, position)
    if position < len(text) and text[position] == ")":
        return position + 1
    if position == destination_end or position == len(text) or text[position] not in "\"'(":
        return None
    opening = text[position]
    closing = ")" if opening == "(" else opening
    position += 1
    while position < len(text):
        character = text[position]
        if character == closing:
            position = _link_space_end(text, position + 1)
            return position + 1 if position < len(text) and text[position] == ")" else None
        if opening == "(" and character == "(":
            return None
        position += 1
        if character == "\\" and position < len(text) and text[position] in _ESCAPABLE:
            position += 1
        elif character in "\r\n":
            if character == "\r" and position < len(text) and text[position] == "\n":
                position += 1
            next_content = position
            while next_content < len(text) and text[next_content] in " \t":
                next_content += 1
            if next_content < len(text) and text[next_content] in "\r\n":
                return None
    return None


@dataclass
class _LinkBracket:
    beginning: int
    image: bool = False
    active: bool = True
    bracket_after: bool = False


def _reference_label(text: str, position: int) -> tuple[str, int] | None:
    """Read a bounded raw label; punctuation escapes remain part of its key."""
    if position >= len(text) or text[position] != "[":
        return None
    beginning, characters = position + 1, 0
    position += 1
    while position < len(text):
        character = text[position]
        if character == "]":
            return text[beginning:position], position + 1
        if character == "[":
            return None
        characters += 1
        position += 1
        if character == "\\" and position < len(text) and text[position] in _ESCAPABLE:
            characters += 1
            position += 1
        elif character in "\r\n":
            if character == "\r" and position < len(text) and text[position] == "\n":
                position += 1
            next_content = position
            while next_content < len(text) and text[next_content] in " \t":
                next_content += 1
            if next_content < len(text) and text[next_content] in "\r\n":
                return None
        if characters > 999:
            return None
    return None


def _reference_key(label: str) -> str:
    # CommonMark normalizes raw labels, not their rendered or unescaped text.
    return re.sub(r"[ \t\r\n]+", " ", label.strip(" \t\r\n")).casefold()


def _reference_prefix(text: str) -> tuple[int, frozenset[str]]:
    """Return the exact character end and keys of leading valid definitions."""
    lines = _lines(text)
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line.text)
    first_prose, keys = 0, set()
    while first_prose < len(lines):
        ending = _link_reference_end(lines, first_prose)
        if ending is None:
            break
        label_start = starts[first_prose] + len(lines[first_prose].content) - len(lines[first_prose].content.lstrip(" "))
        label = _reference_label(text, label_start)
        if label is None:
            break
        keys.add(_reference_key(label[0]))
        first_prose = ending
    return (starts[first_prose] if first_prose < len(starts) else len(text)), frozenset(keys)


def _comments(fragment: list[_ProseLine], *, inline: bool,
              file: str, chunk_for_line: Mapping[int, str],
              diagnostics: list[DeclarationDiagnostic],
              reference_labels: frozenset[str]) -> list[tuple[str, DeclaredSource]]:
    """Read comments left to right; paired code spans hide their contents.

    The fragment is one block, so a backtick cannot match across a blank line,
    heading, list item, fence or block HTML boundary. Runs inside a comment are
    literal HTML; backslash escapes apply only outside an already-open span.
    """
    text = "".join(line.text for line in fragment)
    starts, offset = [], 0
    for line in fragment:
        starts.append(offset)
        offset += len(line.text)
    ticks: dict[int, list[tuple[int, int]]] = {}
    if inline:
        for match in _BACKTICKS.finditer(text):
            ticks.setdefault(len(match.group()), []).append((match.start(), match.end()))
    result, position = [], 0
    brackets: list[_LinkBracket] = []
    if inline:
        # Definitions are block syntax, valid only at the beginning of the
        # paragraph. Reuse the section parser's physical-line recognizer.
        position, _ = _reference_prefix(text)
    while position < len(text):
        if inline and text[position] == "\\" and position + 1 < len(text) and text[position + 1] in _ESCAPABLE:
            position += 2
            continue
        if inline and text[position] == "`":
            ending = position + 1
            while ending < len(text) and text[ending] == "`":
                ending += 1
            matches = ticks.get(ending - position, [])
            after = bisect_right(matches, (position, len(text) + 1))
            position = matches[after][1] if after < len(matches) else ending
            continue
        if inline and text.startswith("![", position):
            if brackets:
                brackets[-1].bracket_after = True
            brackets.append(_LinkBracket(position + 1, image=True))
            position += 2
            continue
        if inline and text[position] == "[":
            if brackets:
                brackets[-1].bracket_after = True
            brackets.append(_LinkBracket(position))
        elif inline and text[position] == "]" and brackets:
            opener = brackets.pop()
            ending = _inline_link_end(text, position + 1) if opener.active else None
            if ending is None and opener.active:
                explicit = _reference_label(text, position + 1)
                if explicit is not None and explicit[0]:
                    key, reference_end = _reference_key(explicit[0]), explicit[1]
                elif not opener.bracket_after:
                    key = _reference_key(text[opener.beginning + 1:position])
                    reference_end = position + 1 if explicit is None else explicit[1]
                else:
                    key, reference_end = "", position + 1
                if key and key in reference_labels:
                    ending = reference_end
            if ending is not None:
                if not opener.image:
                    for earlier in brackets:
                        if not earlier.image:
                            earlier.active = False
                position = ending
                continue
        if not text.startswith("<!--", position):
            tag = (_HTML_TAG.match(text, position) or _AUTOLINK.match(text, position)) if text[position] == "<" else None
            if tag is not None:
                position = tag.end()
                continue
            position += 1
            continue
        ending = text.find("-->", position + 4)
        header = _DECLARATION_HEADER.match(text, position)
        if header is not None:
            kind = header.group(1).lower()
            body_start, body_end = header.end(), len(text) if ending < 0 else ending
            if ending < 0:
                first = fragment[bisect_right(starts, position) - 1]
                diagnostics.append(DeclarationDiagnostic(file, f"{kind}_comment_unclosed",
                                   f"The {kind} comment has no closing delimiter.", line=first.line))
            relative = 0
            for piece in _lines(text[body_start:body_end]):
                declared = piece.content
                ref = declared.strip(" \t")
                if ref:
                    source = fragment[bisect_right(starts, body_start + relative) - 1]
                    result.append((kind, _declaration(ref, declared, source.raw, "comment",
                                                     chunk_for_line.get(source.line), source.line,
                                                     incomplete=ending < 0)))
                relative += len(piece.text)
        position = len(text) if ending < 0 else ending + 3
    return result


def _document_comments(document: MarkdownDocument, file: str,
                       diagnostics: list[DeclarationDiagnostic]) -> tuple[tuple[str, DeclaredSource], ...]:
    lines = _lines(document.text)
    # A leading unreadable YAML block remains source text for lossless storage,
    # but it is still a declaration block rather than a declaration comment.
    start = (document.frontmatter_span.line_end if document.frontmatter_span is not None else
             len(lines) if document.frontmatter_present else 0)
    chunk_for_line = {line: chunk.name for chunk in document.chunks
                      for line in range(chunk.span.line_start, chunk.span.line_end + 1)}
    fragment: list[_ProseLine] = []
    blocks: list[tuple[list[_ProseLine], bool]] = []
    container_context: tuple[tuple[str, int], ...] = ()
    fence_containers: tuple[tuple[str, int], ...] = ()
    fence_character, fence_length = None, 0
    html_kind: str | None = None
    html_containers: tuple[tuple[str, int], ...] = ()

    def flush(*, inline: bool = True) -> None:
        if fragment:
            blocks.append((fragment.copy(), inline))
            fragment.clear()

    for index in range(start, len(lines)):
        content = lines[index].content.removeprefix("\ufeff") if index == 0 else lines[index].content
        if fence_character is not None:
            view = _in_container(content, fence_containers)
            if view is None:
                fence_character, fence_length, container_context = None, 0, ()
            elif re.fullmatch(r" {0,3}" + re.escape(fence_character) + "{" + str(fence_length) + r",}[ \t]*", view):
                fence_character, fence_length = None, 0
                continue
            else:
                continue
        if html_kind is not None:
            view = _in_container(content, html_containers)
            if view is None:
                if html_kind in {"comment", "blank"}:
                    flush(inline=False)
                html_kind, container_context = None, ()
            else:
                if html_kind in {"comment", "blank"}:
                    fragment.append(_ProseLine(view + lines[index].text[len(lines[index].content):], index + 1, lines[index].text))
                if _html_ends(html_kind, view):
                    if html_kind in {"comment", "blank"}:
                        flush(inline=False)
                    html_kind = None
                continue
        inherited = _in_container(content, container_context)
        lazy_continuation = False
        if inherited is None:
            # A list/blockquote paragraph may continue without its marker or
            # full indentation. Preserve its inline-code fragment unless this
            # physical line starts another block. A missing marker on a setext
            # underline is plain paragraph text, not a heading in the container.
            _, new_containers = _container_prefix(content)
            possible_fence = _FENCE.fullmatch(content)
            starts_fence = (possible_fence is not None and
                            (possible_fence.group(1)[0] != "`" or "`" not in possible_fence.group(2)))
            lazy_continuation = bool(
                fragment and container_context and content.strip(" \t") and not new_containers
                and _ATX.fullmatch(content) is None and _THEMATIC.fullmatch(content) is None
                and not starts_fence
                and _html_block(content, can_start_type_seven=False) is None)
            if lazy_continuation:
                inherited = content
            else:
                flush()
                container_context, inherited = (), content
        view, explicit = _container_prefix(inherited)
        containers = container_context + explicit
        if explicit:
            flush()
            container_context = containers
        opener = _FENCE.fullmatch(view)
        if opener is not None:
            marker, info = opener.groups()
            if marker[0] != "`" or "`" not in info:
                flush()
                fence_character, fence_length, fence_containers = marker[0], len(marker), containers
                continue
        if not view.strip(" \t"):
            flush()
            continue
        if view.startswith(("    ", "\t")) and not fragment:
            continue
        block = _html_block(view, can_start_type_seven=not fragment)
        if block is not None:
            flush()
            if block in {"comment", "blank"}:
                fragment.append(_ProseLine(view + lines[index].text[len(lines[index].content):], index + 1, lines[index].text))
            if _html_ends(block, view):
                if block in {"comment", "blank"}:
                    flush(inline=False)
            else:
                html_kind, html_containers = block, containers
            continue
        single_line = (_ATX.fullmatch(view) or _THEMATIC.fullmatch(view)
                       or (not lazy_continuation and _SETEXT.fullmatch(view)))
        if single_line:
            flush()
        fragment.append(_ProseLine(view + lines[index].text[len(lines[index].content):], index + 1, lines[index].text))
        if single_line:
            flush()
    flush(inline=html_kind not in {"comment", "blank"})
    # Definitions may occur after their uses, in any eligible paragraph or
    # container. Collect their existence first; duplicate destinations/titles
    # do not affect whether a label binds and need no value interpretation.
    references: set[str] = set()
    for block, inline in blocks:
        if inline:
            references.update(_reference_prefix("".join(line.text for line in block))[1])
    reference_labels = frozenset(references)
    return tuple(ref for block, inline in blocks
                 for ref in _comments(block, inline=inline, file=file,
                                      chunk_for_line=chunk_for_line, diagnostics=diagnostics,
                                      reference_labels=reference_labels))


def read_document_declarations(document: MarkdownDocument, *, file: str) -> DocumentDeclarations:
    """Read trusted known YAML values and refs into immutable file results.

    Unknown metadata has no effect. Safe scalar Heartwood time pins remain
    free-form; no commit/date interpretation or guessed default role is added.
    Every text source or related entry survives parsing, including syntax
    failures. Relations remain separate from dependency source declarations.
    """
    if not isinstance(document, MarkdownDocument):
        raise TypeError("A parsed MarkdownDocument is required.")
    if not isinstance(file, str) or not file:
        raise ValueError("A file name is required for declaration diagnostics.")
    diagnostics = [DeclarationDiagnostic(file, diagnostic.code, diagnostic.message,
                                        line=diagnostic.line) for diagnostic in document.diagnostics]
    metadata: dict[str, Any] = {}
    frontmatter: list[DeclaredSource] = []
    settings = document.frontmatter if document.frontmatter_valid else {}

    def invalid(key: str, message: str, value: Any) -> None:
        diagnostics.append(DeclarationDiagnostic(file, "frontmatter_value", message, key=key, value=value))

    if "role" in settings:
        role = settings["role"]
        if isinstance(role, str) and role in {"authored", "derived"}:
            metadata["role"] = role
        else:
            invalid("role", "The role must be authored or derived.", role)
    if "status" in settings:
        status = settings["status"]
        if isinstance(status, str) and status == "heartwood":
            metadata["heartwood"] = True
        else:
            invalid("status", "The document status must be heartwood.", status)
    for key in ("implemented", "outdated"):
        if key in settings:
            value = settings[key]
            if (type(value) not in {str, bool, int, float, type(None)} or
                    (type(value) is float and not math.isfinite(value))):
                invalid(key, "The Heartwood time pin must be a safe YAML scalar.", value)
            elif metadata.get("heartwood"):
                metadata[key] = value
    if "generated" in settings:
        generated = settings["generated"]
        if type(generated) is bool:
            metadata["generated"] = generated
        else:
            invalid("generated", "The generated declaration must be a YAML boolean.", generated)
    if "sources" in settings:
        sources = settings["sources"]
        if not isinstance(sources, tuple):
            invalid("sources", "The sources declaration must be a YAML list of text references.", sources)
        else:
            metadata["sources"] = sources
            first_chunk = document.chunks[0].name if document.chunks else None
            for index, source in enumerate(sources):
                if not isinstance(source, str):
                    invalid(f"sources[{index}]", "Each sources entry must be a text reference.", source)
                else:
                    frontmatter.append(_declaration(source, source, source, "frontmatter", first_chunk, None))
    comments = _document_comments(document, file, diagnostics)
    by_chunk: dict[str, list[DeclaredSource]] = {chunk.name: [] for chunk in document.chunks}
    related: dict[str, list[DeclaredSource]] = {chunk.name: [] for chunk in document.chunks}
    for ref in frontmatter:
        if ref.chunk is not None:
            by_chunk[ref.chunk].append(ref)
    for kind, ref in comments:
        if ref.chunk is not None:
            (by_chunk if kind == "sources" else related)[ref.chunk].append(ref)
    grouped = tuple(ChunkSources(chunk.name, tuple(by_chunk[chunk.name])) for chunk in document.chunks)
    relations = tuple(ChunkRelations(chunk.name, tuple(related[chunk.name])) for chunk in document.chunks)
    return DocumentDeclarations(file, MappingProxyType(metadata), tuple(frontmatter), grouped,
                                tuple(diagnostics), relations)
