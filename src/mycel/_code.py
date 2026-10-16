"""Lossless structural code chunks; offsets address the original UTF-8 bytes.

Parsers determine boundaries only. Stored text is always an unchanged slice,
including comments, indentation, separators and line endings. Model input
limits have no part in determining these logical chunks.
"""

from __future__ import annotations

import ast
from bisect import bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256
import io
import re
import tokenize
from typing import Any


@dataclass(frozen=True)
class CodeChunk:
    path: str
    symbol: str
    kind: str
    language: str
    text: str
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    declaration_name_span: tuple[int, int] | None = None

    @property
    def name(self) -> str:
        return f"{self.path}#{self.symbol}"


CODE_IDENTITY_REVISION = "parsed-declaration-name-v1"


def code_identity_key(chunk: CodeChunk) -> str | None:
    """Conservative rename key; complete source/evidence hashes stay separate.

    Only the parser-located declaration identifier is erased. Signature, body,
    comments, indentation and separators remain exact. Length-prefixed parts
    avoid a source string colliding with an inserted placeholder.
    """
    span = chunk.declaration_name_span
    if span is None:
        return None
    raw = chunk.text.encode("utf-8")
    if (type(span) is not tuple or len(span) != 2 or any(type(i) is not int for i in span)
            or not 0 <= span[0] < span[1] <= len(raw)):
        raise ValueError("Invalid parsed declaration-name span.")
    h = sha256()
    for part in (CODE_IDENTITY_REVISION.encode(), chunk.language.encode(), chunk.kind.encode(),
                 raw[:span[0]], raw[span[1]:]):
        h.update(len(part).to_bytes(8, "big") + part)
    return h.hexdigest()


@dataclass(frozen=True)
class _Region:
    symbol: str
    kind: str
    start: int
    end: int
    name_span: tuple[int, int] | None = None


_ENDINGS = {
    ".py": "python", ".svelte": "svelte", ".ts": "typescript",
    ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".sh": "shell", ".bash": "shell",
    ".plist": "plist", ".plist.in": "plist", ".swift": "swift",
}
_NEWLINE = re.compile(b"\r\n|\r|\n")


def language_for_path(path: str) -> str:
    for ending, language in sorted(_ENDINGS.items(), key=lambda item: -len(item[0])):
        if path.endswith(ending):
            return language
    return "unknown"


def _chunk(path: str, language: str, raw: bytes, region: _Region,
           line_offsets: list[int] | None = None) -> CodeChunk:
    text = raw[region.start:region.end].decode("utf-8")
    offsets = _line_offsets(raw) if line_offsets is None else line_offsets
    line_start = bisect_right(offsets, region.start)
    line_end = bisect_right(offsets, max(region.start, region.end - 1))
    span = None if region.name_span is None else tuple(i - region.start for i in region.name_span)
    return CodeChunk(path, region.symbol, region.kind, language, text,
                     line_start, max(line_start, line_end), region.start, region.end, span)


def _whole_file(path: str, language: str, raw: bytes) -> tuple[CodeChunk, ...]:
    return (_chunk(path, language, raw, _Region("<file>", "file", 0, len(raw))),)


def _unique(base: str, reserved: set[str], used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    number = 2
    while f"{base}:{number}" in used or f"{base}:{number}" in reserved:
        number += 1
    name = f"{base}:{number}"
    used.add(name)
    return name


def _assemble(path: str, language: str, raw: bytes, regions: list[_Region], *,
              loose_kind: str = "module") -> tuple[CodeChunk, ...]:
    """Make a complete ordered partition, preserving even whitespace-only gaps."""
    regions.sort(key=lambda region: (region.start, region.end))
    if any(region.start < 0 or region.end > len(raw) or region.start >= region.end
           for region in regions):
        return _whole_file(path, language, raw)
    if any(left.end > right.start for left, right in zip(regions, regions[1:])):
        return _whole_file(path, language, raw)
    reserved = {region.symbol for region in regions}
    used: set[str] = set()
    regions = [replace(region, symbol=_unique(region.symbol, reserved, used)) for region in regions]
    reserved.update(region.symbol for region in regions)
    output: list[_Region] = []
    cursor = 0
    for region in regions:
        if cursor < region.start:
            gap = raw[cursor:region.start]
            if not gap.strip():
                if output:
                    output[-1] = replace(output[-1], end=region.start)
                else:
                    region = replace(region, start=cursor)
            else:
                base = f"<before {region.symbol}>"
                output.append(_Region(_unique(base, reserved, used), loose_kind, cursor, region.start))
        output.append(region)
        cursor = region.end
    if cursor < len(raw):
        if output and not raw[cursor:].strip():
            output[-1] = replace(output[-1], end=len(raw))
        else:
            output.append(_Region(_unique("<end>", reserved, used), loose_kind, cursor, len(raw)))
    if not output:
        output.append(_Region("<end>", loose_kind, 0, len(raw)))
    offsets = _line_offsets(raw)
    return tuple(_chunk(path, language, raw, region, offsets) for region in output)


def _line_offsets(raw: bytes) -> list[int]:
    offsets = [0]
    for match in _NEWLINE.finditer(raw):
        offsets.append(match.end())
    return offsets


def _line_end(raw: bytes, offset: int) -> int:
    newline = _NEWLINE.search(raw, offset)
    return len(raw) if newline is None else newline.end()


def _line_start(raw: bytes, offset: int) -> int:
    return max(raw.rfind(b"\n", 0, offset), raw.rfind(b"\r", 0, offset)) + 1


def _class_parts(name: str, first: int, last: int,
                 children: list[tuple[str, int, int, list[_Region]]], raw: bytes) -> list[_Region]:
    """Partition class-owned text without turning fields/braces into a module.

    Class continuations use the following member's symbol or <end>, so unrelated
    insertions do not renumber them. A nested class supplies its own partition.
    """
    if not children:
        return [_Region(name, "class", first, last)]
    output = [_Region(name, "class", first, children[0][1])]
    cursor = children[0][1]
    for symbol, start, end, pieces in children:
        if cursor < start:
            if not raw[cursor:start].strip():
                output[-1] = replace(output[-1], end=start)
            else:
                output.append(_Region(f"{name}.<before {symbol}>", "class", cursor, start))
        output.extend(pieces)
        cursor = end
    if cursor < last:
        if not raw[cursor:last].strip():
            output[-1] = replace(output[-1], end=last)
        else:
            output.append(_Region(f"{name}.<end>", "class", cursor, last))
    return output


def _python_regions(source: str, raw: bytes) -> list[_Region]:
    tree = ast.parse(source)
    offsets = _line_offsets(raw)
    lines = raw.splitlines(keepends=True)
    # Token columns remain line-relative; normalize terminators only for the
    # tokenizer, then translate its positions onto the original byte lines.
    tokens = list(tokenize.generate_tokens(io.StringIO(source.replace("\r\n", "\n").replace("\r", "\n")).readline))
    declarations: dict[int, list[tuple[int, str, Any]]] = {}
    for index, token in enumerate(tokens[:-1]):
        if token.type == tokenize.NAME and token.string in {"def", "class"}:
            declarations.setdefault(token.start[0], []).append((index, token.string, token))

    def name_span(node: ast.AST) -> tuple[int, int]:
        keyword = "class" if isinstance(node, ast.ClassDef) else "def"
        for index, spelling, token in declarations.get(node.lineno, ()):
            if spelling == keyword:
                # Python token columns count characters; AST offsets count bytes.
                column = len(lines[token.start[0]-1].decode("utf-8")[:token.start[1]].encode())
                if column < node.col_offset:
                    continue
                name = tokens[index+1]
                if name.type != tokenize.NAME:
                    raise ValueError("A parsed declaration has no identifier.")
                def offset(position):
                    line, char = position
                    return offsets[line-1] + len(lines[line-1].decode("utf-8")[:char].encode())
                return offset(name.start), offset(name.end)
        raise ValueError("A parsed declaration has no identifier span.")

    def start(node: ast.AST) -> int:
        first = min([node.lineno, *(decorator.lineno for decorator in getattr(node, "decorator_list", ()))])
        while first > 1 and lines[first - 2].lstrip().startswith(b"#"):
            first -= 1
        return offsets[first - 1]

    def end(node: ast.AST) -> int:
        return _line_end(raw, offsets[node.end_lineno - 1] + node.end_col_offset)

    def class_parts(node: ast.ClassDef, name: str) -> list[_Region]:
        children = []
        for member in node.body:
            symbol = f"{name}.{getattr(member, 'name', '')}"
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pieces = [_Region(symbol, "method", start(member), end(member), name_span(member))]
            elif isinstance(member, ast.ClassDef):
                pieces = class_parts(member, symbol)
            else:
                continue
            children.append((symbol, start(member), end(member), pieces))
        pieces = _class_parts(name, start(node), end(node), children, raw)
        pieces[0] = replace(pieces[0], name_span=name_span(node))
        return pieces

    regions: list[_Region] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            regions.append(_Region(node.name, "function", start(node), end(node), name_span(node)))
        elif isinstance(node, ast.ClassDef):
            regions.extend(class_parts(node, node.name))
    return regions


_DECLARATIONS = {
    "function_declaration": "function", "generator_function_declaration": "function",
    "function_signature": "function", "function_expression": "function",
    "generator_function": "function", "arrow_function": "function", "class_declaration": "class",
    "abstract_class_declaration": "class", "class": "class",
    "interface_declaration": "interface", "type_alias_declaration": "type",
    "enum_declaration": "enum", "internal_module": "namespace",
}
_FUNCTION_VALUES = {"arrow_function", "function_expression", "generator_function", "function"}
_VARIABLES = {"lexical_declaration", "variable_declaration"}


def _tree_parser(language: str):
    from tree_sitter import Language, Parser
    if language == "javascript":
        import tree_sitter_javascript as grammar
        capsule = grammar.language()
    else:
        import tree_sitter_typescript as grammar
        capsule = grammar.language_tsx() if language == "tsx" else grammar.language_typescript()
    return Parser(Language(capsule))


def _tree_name(node: Any, default: str = "<anonymous>") -> str:
    name = node.child_by_field_name("name")
    return name.text.decode("utf-8") if name is not None else default


def _leading_tree_start(node: Any, raw: bytes) -> int:
    start = node.start_byte
    previous = node.prev_named_sibling
    while previous is not None and previous.type in {"comment", "decorator"}:
        gap = raw[previous.end_byte:start]
        line_start = _line_start(raw, previous.start_byte)
        # A trailing comment after earlier code belongs to that earlier code.
        if (gap.strip() or len(re.findall(b"\r\n|\r|\n", gap)) > 1
                or (previous.type == "comment" and previous.prev_named_sibling is not None
                    and raw[line_start:previous.start_byte].strip())):
            break
        start = previous.start_byte
        previous = previous.prev_named_sibling
    line_start = _line_start(raw, start)
    return line_start if not raw[line_start:start].strip() else start


def _tree_regions(language: str, raw: bytes) -> list[_Region]:
    tree = _tree_parser(language).parse(raw)
    if tree.root_node.has_error:
        raise ValueError("Source could not be parsed.")
    regions: list[_Region] = []

    def declaration(node: Any) -> Any:
        while node.type in {"export_statement", "ambient_declaration", "expression_statement"}:
            candidates = [child for child in node.named_children
                          if child.type in _DECLARATIONS or child.type in _VARIABLES
                          or child.type in {"ambient_declaration"}]
            if not candidates:
                break
            node = candidates[-1]
        return node

    def name_span(node):
        name = node.child_by_field_name("name")
        return None if name is None else (name.start_byte, name.end_byte)

    def class_regions(node: Any, start: int, end: int, name: str, binding_span=None):
        body = node.child_by_field_name("body")
        methods = [member for member in (body.named_children if body is not None else ())
                   if member.type in {"method_definition", "abstract_method_signature", "method_signature"}]
        children = []
        for method in methods:
            symbol, first = f"{name}.{_tree_name(method)}", _leading_tree_start(method, raw)
            children.append((symbol, first, method.end_byte,
                             [_Region(symbol, "method", first, method.end_byte, name_span(method))]))
        pieces = _class_parts(name, start, end, children, raw)
        pieces[0] = replace(pieces[0], name_span=binding_span or name_span(node))
        regions.extend(pieces)

    def functional(value: Any) -> bool:
        if value is None:
            return False
        if value.type in _FUNCTION_VALUES:
            return True
        if value.type == "call_expression":
            arguments = value.child_by_field_name("arguments")
            return arguments is not None and any(child.type in _FUNCTION_VALUES for child in arguments.named_children)
        return False

    for outer in tree.root_node.named_children:
        node = declaration(outer)
        start = _leading_tree_start(outer, raw)
        end = outer.end_byte
        if node.type in _DECLARATIONS:
            name = _tree_name(node, "default" if outer.type == "export_statement" else "<anonymous>")
            kind = _DECLARATIONS[node.type]
            if kind == "class":
                class_regions(node, start, end, name)
            else:
                regions.append(_Region(name, kind, start, end, name_span(node)))
        elif node.type in _VARIABLES:
            members = [child for child in node.named_children if child.type == "variable_declarator"]
            for index, member in enumerate(members):
                value = member.child_by_field_name("value")
                member_start = start if index == 0 else member.start_byte
                member_end = members[index + 1].start_byte if index + 1 < len(members) else end
                if functional(value):
                    regions.append(_Region(_tree_name(member), "function", member_start, member_end, name_span(member)))
                elif value is not None and value.type == "class":
                    class_regions(value, member_start, member_end, _tree_name(member), name_span(member))
    return regions


_BLOCK_OPEN = re.compile(r"<\s*(script|style)\b", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(r"<\s*/\s*(script|style)\s*>", re.IGNORECASE)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.IGNORECASE)
_STYLE_CLOSE = re.compile(r"</style\s*>", re.IGNORECASE)
_LEXER_DEPTH = 256


def _quoted_end(source: str, start: int, *, template: bool = False, depth: int = 0) -> int:
    quote, cursor = source[start], start + 1
    while cursor < len(source):
        char = source[cursor]
        if char == "\\":
            cursor += 3 if source.startswith("\r\n", cursor + 1) else 2
        elif char == quote:
            return cursor + 1
        elif template and source.startswith("${", cursor):
            cursor = _expression_end(source, cursor + 1, depth=depth + 1)
        elif not template and char in "\r\n":
            raise ValueError("Source string could not be parsed.")
        else:
            cursor += 1
    raise ValueError("Source string could not be parsed.")


def _regexp_end(source: str, start: int) -> int:
    cursor, bracket = start + 1, False
    while cursor < len(source):
        char = source[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char in "\r\n":
            raise ValueError("Source regexp could not be parsed.")
        if char == "[":
            bracket = True
        elif char == "]":
            bracket = False
        elif char == "/" and not bracket:
            cursor += 1
            while cursor < len(source) and source[cursor].isalpha():
                cursor += 1
            return cursor
        cursor += 1
    raise ValueError("Source regexp could not be parsed.")


def _expression_end(source: str, start: int, *, depth: int = 0) -> int:
    """Skip a Svelte expression's strings/comments/templates in bounded space."""
    if depth > _LEXER_DEPTH:
        raise ValueError("Source expression nesting cannot be parsed reliably.")
    cursor, braces = start + 1, 1
    previous, word = "", ""
    # {/if}, {/each}, etc. are Svelte control tags rather than JS regexps.
    closing = re.match(r"/\s*[A-Za-z][A-Za-z0-9_]*\s*}", source[cursor:])
    if closing is not None:
        return cursor + closing.end()
    while cursor < len(source):
        char = source[cursor]
        if char.isspace():
            cursor += 1
            continue
        if char in "\"'`":
            cursor = _quoted_end(source, cursor, template=char == "`", depth=depth)
            previous, word = "value", ""
            continue
        if source.startswith("//", cursor):
            newline = re.search(r"\r\n|\r|\n", source[cursor + 2:])
            if newline is None:
                raise ValueError("Source expression could not be parsed.")
            cursor += 2 + newline.end()
            continue
        if source.startswith("/*", cursor):
            end = source.find("*/", cursor + 2)
            if end < 0:
                raise ValueError("Source expression comment could not be parsed.")
            cursor = end + 2
            continue
        if char == "/" and (not previous or previous in "=(:,[!&|?{;+-*%^<>"
                             or word in {"return", "throw", "yield", "case", "typeof", "void", "delete", "in", "of"}):
            cursor = _regexp_end(source, cursor)
            previous, word = "value", ""
            continue
        if char == "{":
            braces += 1
            if braces + depth > _LEXER_DEPTH:
                raise ValueError("Source expression nesting cannot be parsed reliably.")
        elif char == "}":
            braces -= 1
            if braces == 0:
                return cursor + 1
        if char.isalpha() or char in "_$":
            end = cursor + 1
            while end < len(source) and (source[end].isalnum() or source[end] in "_$"):
                end += 1
            word, previous, cursor = source[cursor:end], "word", end
        else:
            previous, word, cursor = char, "", cursor + 1
    raise ValueError("Source expression could not be parsed.")


def _html_quote_end(source: str, start: int) -> int:
    quote, cursor = source[start], start + 1
    while cursor < len(source):
        if source[cursor] == quote:
            return cursor + 1
        if source[cursor] == "{":
            cursor = _expression_end(source, cursor)
        else:
            cursor += 1
    raise ValueError("Source attribute could not be parsed.")


def _tag_end(source: str, start: int) -> int:
    cursor = start + 1
    while cursor < len(source):
        char = source[cursor]
        if char in "\"'":
            cursor = _html_quote_end(source, cursor)
        elif char == "{":
            cursor = _expression_end(source, cursor)
        elif char == ">":
            return cursor + 1
        else:
            cursor += 1
    raise ValueError("Source tag could not be parsed.")


def _style_end(source: str, start: int) -> int:
    """CSS quotes/comments/values may contain a literal closing style tag."""
    cursor, braces, parentheses = start, 0, 0
    while cursor < len(source):
        char = source[cursor]
        if source.startswith("/*", cursor) or source.startswith("<!--", cursor):
            opening, closing = (2, "*/") if source.startswith("/*", cursor) else (4, "-->")
            end = source.find(closing, cursor + opening)
            if end < 0:
                raise ValueError("Source style comment could not be parsed.")
            cursor = end + len(closing)
            continue
        if char in "\"'":
            cursor = _quoted_end(source, cursor)
            continue
        if char == "\\":
            cursor += 2
            continue
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        if min(braces, parentheses) < 0 or max(braces, parentheses) > _LEXER_DEPTH:
            raise ValueError("Source style nesting could not be parsed reliably.")
        if braces == 0 and parentheses == 0 and char == "<":
            close = _STYLE_CLOSE.match(source, cursor)
            if close is not None:
                return close.end()
        cursor += 1
    raise ValueError("Source style block could not be parsed.")


def _svelte_regions(source: str) -> list[_Region]:
    regions: list[_Region] = []
    cursor = 0
    previous_comments: list[tuple[int, int]] = []
    byte_offsets = [0]
    for character in source:
        byte_offsets.append(byte_offsets[-1] + len(character.encode("utf-8")))
    while cursor < len(source):
        if source[cursor] == "{":
            cursor = _expression_end(source, cursor)
            previous_comments = []
            continue
        if source[cursor] != "<":
            if not source[cursor].isspace():
                previous_comments = []
            cursor += 1
            continue
        first = cursor
        if source.startswith("<!--", cursor):
            end = source.find("-->", cursor + 4)
            if end < 0:
                raise ValueError("Source comment could not be parsed.")
            end += 3
            if previous_comments:
                gap = source[previous_comments[-1][1]:first]
                if gap.strip() or len(re.findall(r"\r\n|\r|\n", gap)) > 1:
                    previous_comments = []
            previous_comments.append((first, end))
            cursor = end
            continue
        end = _tag_end(source, cursor)
        token = source[first:end]
        opening = _BLOCK_OPEN.match(token)
        if opening is not None:
            tag = opening.group(1).lower()
            if token.rstrip().endswith("/>"):
                raise ValueError("Source block could not be parsed.")
            if tag == "script":
                close = _SCRIPT_CLOSE.search(source, end)
                if close is None:
                    raise ValueError("Source script block could not be parsed.")
                end = close.end()
            else:
                end = _style_end(source, end)
            start = first
            if previous_comments:
                gap = source[previous_comments[-1][1]:start]
                if not gap.strip() and len(re.findall(r"\r\n|\r|\n", gap)) <= 1:
                    start = previous_comments[0][0]
            regions.append(_Region(tag, tag, byte_offsets[start], byte_offsets[end]))
        elif _BLOCK_CLOSE.match(token):
            raise ValueError("Source block could not be parsed.")
        cursor = end
        previous_comments = []
    return regions


def chunk_code(path: str, source: str) -> tuple[CodeChunk, ...]:
    """Split one already-read UTF-8 file without filesystem or model access."""
    if not isinstance(path, str) or not isinstance(source, str):
        raise TypeError("A code chunker requires a path and UTF-8 source text.")
    raw = source.encode("utf-8")
    language = language_for_path(path)
    if language in {"shell", "plist", "swift", "unknown"}:
        return _whole_file(path, language, raw)
    try:
        if language == "python":
            regions = _python_regions(source, raw)
        elif language == "svelte":
            regions = _svelte_regions(source)
        else:
            regions = _tree_regions(language, raw)
    except (SyntaxError, ValueError, ImportError, RuntimeError, RecursionError):
        return _whole_file(path, language, raw)
    return _assemble(path, language, raw, regions,
                     loose_kind="markup" if language == "svelte" else "module")
