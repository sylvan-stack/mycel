"""Read-only, complete-byte corpus inputs for later transactional ingest.

This module discovers and captures; it never updates stored hashes, reconciles
identities, changes a checkout or opens the index store. A successful capture is
an observation, not permission to delete: the caller must also check prior disk
counts and complete parsing before applying absent-location removals.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, fields, replace
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from types import MappingProxyType
from typing import Any, Literal

from pathspec import GitIgnoreSpec
from pathspec.patterns.gitignore.spec import GitIgnoreSpecPattern

from . import _code, _markdown, _source_refs
from ._code import CodeChunk, chunk_code
from ._errors import MycelError
from ._markdown import (MarkdownChunk, MarkdownDecodeError, MarkdownDiagnostic,
                        MarkdownDocument, SourceSpan, split_markdown)
from ._safeguards import CompletedChild, STDOUT_LIMIT, run_git
from ._deadline import check_deadline
from ._scope import Repository, RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress, SourceAddressError


CAPTURE_REVISION = "mycel-capture-v1"
GIT_METADATA_LIMIT = STDOUT_LIMIT
GIT_READ_SECONDS = 10.0
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
Root = Literal["code", "artifact"]
Corpus = Literal["documents", "code"]
GitReader = Callable[..., CompletedChild]


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _parser_revision() -> str:
    # Cache reuse must change with parser code, its native grammar dependencies
    # or interpreter/Unicode behavior, even within an unreleased working Build.
    return sha256(_json({"capture": sha256(Path(__file__).read_bytes()).hexdigest(),
                         "code": sha256(Path(_code.__file__).read_bytes()).hexdigest(),
                         "markdown": sha256(Path(_markdown.__file__).read_bytes()).hexdigest(),
                         "declarations": sha256(Path(_source_refs.__file__).read_bytes()).hexdigest(),
                         "python": sys.version, "unicode": _markdown.UNICODE_VERSION,
                         "dependencies": {name: version(name) for name in
                             ("pathspec", "PyYAML", "tree-sitter", "tree-sitter-typescript", "tree-sitter-javascript")}})).hexdigest()


@dataclass(frozen=True, order=True)
class FileAlias:
    root: Root
    path: str

    def address(self, repository: str) -> str:
        return SourceAddress(repository, self.root, self.path).address


@dataclass(frozen=True, order=True)
class LocationId:
    kind: Literal["disk", "branch", "stash"]
    checkout: Root | None
    identity: str

    def record(self) -> dict[str, Any]:
        return {"kind": self.kind, "checkout": self.checkout, "identity": self.identity}


@dataclass(frozen=True)
class CaptureDiagnostic:
    code: str
    message: str
    location: LocationId | None = None
    alias: FileAlias | None = None


@dataclass(frozen=True)
class CapturedFile:
    primary: FileAlias
    aliases: tuple[FileAlias, ...]
    corpus: Corpus
    source: bytes = field(repr=False)
    file_hash: str
    parsed: MarkdownDocument | tuple[CodeChunk, ...] | None = field(repr=False)
    failure: str | None = None
    reused_parse: bool = field(default=False, compare=False)

    def record(self) -> dict[str, Any]:
        return {"root": self.primary.root, "path": self.primary.path,
                "aliases": [{"root": alias.root, "path": alias.path} for alias in self.aliases],
                "corpus": self.corpus, "fileHash": self.file_hash,
                "byteLength": len(self.source), "failure": self.failure}


@dataclass(frozen=True)
class CapturedLocation:
    id: LocationId
    commit: str | None
    files: tuple[CapturedFile, ...]
    complete: bool
    trees: tuple[str, ...] = ()
    reused: bool = field(default=False, compare=False)

    def record(self) -> dict[str, Any]:
        return {**self.id.record(), "commit": self.commit, "trees": list(self.trees),
                "complete": self.complete, "files": [file.record() for file in self.files]}


@dataclass(frozen=True)
class LocatedFile:
    location: LocationId
    file: CapturedFile


@dataclass(frozen=True)
class CaptureDelta:
    unchanged: tuple[LocatedFile, ...]
    changed: tuple[LocatedFile, ...]
    new: tuple[LocatedFile, ...]
    removed: tuple[LocatedFile, ...]
    added_locations: tuple[LocationId, ...]
    removed_locations: tuple[LocationId, ...]
    deletion_safe: bool


@dataclass(frozen=True)
class CaptureManifest:
    repository: str
    policy_hash: str
    locations: tuple[CapturedLocation, ...]
    complete: bool
    diagnostics: tuple[CaptureDiagnostic, ...] = ()

    @property
    def deletion_safe(self) -> bool:
        return self.complete and all(file.failure is None
                                     for location in self.locations for file in location.files)

    @property
    def disk(self) -> CapturedLocation:
        return next(location for location in self.locations if location.id.kind == "disk")

    def canonical_bytes(self) -> bytes:
        # This is a scan manifest, not MYC-16's pinned selection/request format.
        return _json({"revision": CAPTURE_REVISION, "repository": self.repository,
                      "policyHash": self.policy_hash, "complete": self.complete,
                      "deletionSafe": self.deletion_safe,
                      "locations": [location.record() for location in self.locations],
                      "diagnostics": [{"code": item.code, "message": item.message,
                                       "location": None if item.location is None else item.location.record(),
                                       "alias": None if item.alias is None else
                                       {"root": item.alias.root, "path": item.alias.path}}
                                      for item in self.diagnostics]})

    @property
    def manifest_hash(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()

    def delta(self, previous: CaptureManifest | None) -> CaptureDelta:
        if previous is not None and previous.repository != self.repository:
            raise MycelError("invalid_input", "Capture comparison requires the same exact repository.")
        old_locations = {} if previous is None else {location.id: location for location in previous.locations}
        unchanged, changed, new, removed = [], [], [], []
        for location in self.locations:
            old = old_locations.get(location.id)
            by_alias = {} if old is None else {alias: file for file in old.files for alias in file.aliases}
            retained = set()
            for file in location.files:
                prior = next((by_alias[alias] for alias in file.aliases if alias in by_alias), None)
                placed = LocatedFile(location.id, file)
                if prior is None:
                    new.append(placed)
                else:
                    retained.add(prior.primary)
                    (unchanged if self.policy_hash == previous.policy_hash and file.corpus == prior.corpus
                     and file.primary == prior.primary and file.file_hash == prior.file_hash and file.source == prior.source
                     else changed).append(placed)
            if self.deletion_safe and old is not None:
                removed.extend(LocatedFile(location.id, file) for file in old.files
                               if file.primary not in retained)
        current_ids = {location.id for location in self.locations}
        missing = tuple(identifier for identifier in old_locations if identifier not in current_ids)
        if self.deletion_safe:
            removed.extend(LocatedFile(identifier, file) for identifier in missing
                           for file in old_locations[identifier].files)
        return CaptureDelta(tuple(unchanged), tuple(changed), tuple(new), tuple(removed),
                            tuple(location.id for location in self.locations if location.id not in old_locations),
                            missing if self.deletion_safe else (), self.deletion_safe)

    def require_safe_reconciliation(self, previous: CaptureManifest | None, *,
                                    confirm_empty: bool = False) -> None:
        """Pure guard; a store-backed caller must establish the prior disk rows."""
        if not self.deletion_safe:
            raise MycelError("refused", "The capture did not completely read and parse every location; remove no absent rows.")
        if previous is None:
            return
        if previous.repository != self.repository:
            raise MycelError("invalid_input", "Capture comparison requires the same exact repository.")
        if confirm_empty:
            return
        for corpus in ("documents", "code"):
            if any(file.corpus == corpus for file in previous.disk.files) and not any(
                    file.corpus == corpus for file in self.disk.files):
                raise MycelError("refused", f"The on-disk {corpus} corpus became empty; explicit confirmation is required.")


_PARSE_TYPES = {kind.__name__: kind for kind in
                (MarkdownDocument, MarkdownChunk, MarkdownDiagnostic, SourceSpan, CodeChunk)}


def _parse_value(value: Any) -> Any:
    """Lossless JSON representation of only the parser's inert value types."""
    if type(value) is str:
        # Safe YAML can produce NUL and lone surrogate values from escapes.
        # PostgreSQL JSONB cannot hold them, and ordinary UTF-8 cannot encode
        # surrogates. Keep their exact inert value in a reversible safe tag.
        if "\0" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            return {"type": "str", "value": value.encode("utf-8", errors="surrogatepass").hex()}
        return value
    if type(value) in (int, bool) or value is None:
        return value
    if type(value) is float:
        return {"type": "float", "value": value.hex()}
    if type(value) is bytes:
        return {"type": "bytes", "value": value.hex()}
    if type(value).__name__ in _PARSE_TYPES and type(value) is _PARSE_TYPES[type(value).__name__]:
        return {"type": type(value).__name__, "value":
                {item.name: _parse_value(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, Mapping):
        return {"type": "mapping", "value": [[_parse_value(key), _parse_value(item)] for key, item in value.items()]}
    if type(value) in (tuple, frozenset):
        members = [_parse_value(item) for item in value]
        return {"type": type(value).__name__, "value": sorted(members, key=_json)
                if type(value) is frozenset else members}
    raise ValueError("Unsupported inert parser value.")


def _restore_parse_value(record: Any) -> Any:
    if type(record) in (str, int, bool) or record is None:
        return record
    if type(record) is not dict or set(record) != {"type", "value"}:
        raise ValueError("Invalid parser cache value.")
    kind, value = record["type"], record["value"]
    if kind == "str":
        return bytes.fromhex(value).decode("utf-8", errors="surrogatepass")
    if kind == "float":
        return float.fromhex(value)
    if kind == "bytes":
        return bytes.fromhex(value)
    if kind == "mapping":
        return MappingProxyType({_restore_parse_value(key): _restore_parse_value(item) for key, item in value})
    if kind in {"tuple", "frozenset"}:
        restored = (_restore_parse_value(item) for item in value)
        return tuple(restored) if kind == "tuple" else frozenset(restored)
    if kind in _PARSE_TYPES and type(value) is dict and set(value) == {item.name for item in fields(_PARSE_TYPES[kind])}:
        return _PARSE_TYPES[kind](**{key: _restore_parse_value(item) for key, item in value.items()})
    raise ValueError("Unknown parser cache value.")


def parse_history_record(captured: CapturedFile, policy_hash: str) -> dict[str, Any]:
    """Persist an independently validated parse with its full acquisition policy.

    This is inert JSON, never pickle or executable deserialization. Original
    bytes remain in the exact file version; a cache cannot publish new hashes.
    """
    value = _parse_value(captured.parsed)
    return {"revision": 1, "policyHash": policy_hash, "fileHash": captured.file_hash,
            "parsed": value, "parsedHash": sha256(_json(value)).hexdigest()}


def file_from_parse_history(source: bytes, corpus: Corpus, primary: FileAlias,
                            aliases: tuple[FileAlias, ...], record: Any) -> CapturedFile | None:
    """Ignore missing/incompatible/corrupt cache entries and obtain a fresh parse."""
    try:
        if (type(record) is not dict or record.get("revision") != 1
                or record["fileHash"] != sha256(source).hexdigest()
                or record["parsedHash"] != sha256(_json(record["parsed"])).hexdigest()
                or type(record["policyHash"]) is not str or primary not in aliases):
            return None
        parsed = _restore_parse_value(record["parsed"])
        line_ends = [match.end() for match in re.finditer(br"\r\n|\r|\n", source)]

        def span_matches(start, end, line_start, line_end):
            return (all(type(item) is int for item in (start, end, line_start, line_end))
                    and 0 <= start <= end <= len(source)
                    and line_start == bisect_right(line_ends, start) + 1
                    and line_end == bisect_right(line_ends, max(start, end - 1)) + 1)

        if corpus == "documents":
            if (not isinstance(parsed, MarkdownDocument) or parsed.source != source
                    or parsed.text.encode("utf-8") != source or parsed.file_hash != record["fileHash"]
                    or type(parsed.chunks) is not tuple or not isinstance(parsed.frontmatter, Mapping)):
                return None
            frontmatter = parsed.frontmatter_span
            if frontmatter is not None and (not isinstance(frontmatter, SourceSpan)
                    or not span_matches(frontmatter.byte_start, frontmatter.byte_end,
                                        frontmatter.line_start, frontmatter.line_end)
                    or source[frontmatter.byte_start:frontmatter.byte_end] != parsed.frontmatter_text.encode("utf-8")):
                return None
            cursor = frontmatter.byte_end if frontmatter is not None and parsed.frontmatter_valid else 0
            for chunk in parsed.chunks:
                if (not isinstance(chunk, MarkdownChunk) or not isinstance(chunk.span, SourceSpan)
                        or chunk.span.byte_start != cursor
                        or not span_matches(chunk.span.byte_start, chunk.span.byte_end,
                                            chunk.span.line_start, chunk.span.line_end)):
                    return None
                raw = source[chunk.span.byte_start:chunk.span.byte_end]
                if (raw != chunk.text.encode("utf-8") or not chunk.text.endswith(chunk.body)
                        or sha256(raw).hexdigest() != chunk.snapshot_hash
                        or _markdown.comparison_hash(chunk.body) != chunk.content_hash
                        or _markdown.comparison_hash(chunk.title or "") != chunk.title_hash
                        or chunk.comparison_revision != _markdown.COMPARISON_REVISION
                        or chunk.unicode_version != _markdown.UNICODE_VERSION):
                    return None
                cursor = chunk.span.byte_end
            if cursor != len(source):
                return None
        elif corpus == "code":
            if type(parsed) is not tuple or not parsed:
                return None
            cursor = 0
            for chunk in parsed:
                if (not isinstance(chunk, CodeChunk) or chunk.path != primary.path
                        or chunk.byte_start != cursor
                        or not span_matches(chunk.byte_start, chunk.byte_end, chunk.line_start, chunk.line_end)
                        or source[chunk.byte_start:chunk.byte_end] != chunk.text.encode("utf-8")
                        or chunk.language != _code.language_for_path(primary.path)):
                    return None
                if chunk.declaration_name_span is not None and (type(chunk.declaration_name_span) is not tuple
                        or len(chunk.declaration_name_span) != 2
                        or any(type(item) is not int for item in chunk.declaration_name_span)
                        or not 0 <= chunk.declaration_name_span[0] < chunk.declaration_name_span[1]
                        <= chunk.byte_end - chunk.byte_start):
                    return None
                cursor = chunk.byte_end
            if cursor != len(source):
                return None
        else:
            return None
        return CapturedFile(primary, aliases, corpus, source, record["fileHash"], parsed)
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        return None


@dataclass(frozen=True)
class _Binding:
    root: Root
    path: Path
    base: Path
    checkout: Path | None
    subfolders: tuple[str, ...] = ()

    @property
    def prefix(self) -> str:
        value = self.path.relative_to(self.base).as_posix()
        return "" if value == "." else value


@dataclass(frozen=True)
class _TreeFile:
    path: str
    oid: str
    size: int
    mode: str


class _CaptureFailure(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message


_POSIX_CLASSES = {
    "alnum": r"\x30-\x39\x41-\x5a\x61-\x7a", "alpha": r"\x41-\x5a\x61-\x7a",
    "blank": r"\x09\x20", "cntrl": r"\x00-\x1f\x7f", "digit": r"\x30-\x39",
    "graph": r"\x21-\x7e", "lower": r"\x61-\x7a", "print": r"\x20-\x7e",
    "punct": r"\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e", "space": r"\x09-\x0d\x20",
    "upper": r"\x41-\x5a", "xdigit": r"\x30-\x39\x41-\x46\x61-\x66",
}


_ASCII_FOLD = str.maketrans({value: value + 32 for value in range(65, 91)})
_CLASS_BYTES = {name: frozenset(value for value in range(256)
                if re.fullmatch("[" + expression + "]", chr(value)))
                for name, expression in _POSIX_CLASSES.items()}


def _byte_class(values: set[int]) -> str:
    if not values:
        return r"(?!)"
    intervals, start, last = [], None, None
    for value in sorted(values):
        if last is not None and value == last + 1:
            last = value
            continue
        if start is not None:
            intervals.append((start, last))
        start = last = value
    intervals.append((start, last))
    return "[" + "".join(r"\x" + format(start, "02x") +
                           (r"-\x" + format(end, "02x") if end != start else "")
                           for start, end in intervals) + "]"


class _GitPattern(GitIgnoreSpecPattern):
    ignorecase = False

    @classmethod
    def pattern_to_regex(cls, pattern: str) -> tuple[str | None, bool | None]:
        # Normalize only Git's actual line endings/trailing spaces. Appending a
        # temporary literal protects retained tabs and byte whitespace from the
        # dependency's Unicode rstrip; it is removed from the resulting regex.
        pattern = pattern.removesuffix("\r")
        kept, offset = 0, 0
        while offset < len(pattern):
            if pattern[offset] == "\\" and offset + 1 < len(pattern):
                offset += 2
                kept = offset
                continue
            if pattern[offset] != " ":
                kept = offset + 1
            offset += 1
        pattern = pattern[:kept]
        pattern = re.sub(r"(?<!\\)((?:\\\\)*)\\/", r"\1/", pattern)
        # A trailing **/ excludes directories below the prefix, never the
        # prefix directory itself. Parent exclusion handles deeper descent.
        pattern = re.sub(r"(?:\*\*/)+$", "*/", pattern)
        marker = "\ue000" if pattern and pattern[-1].isspace() else ""
        regex, include = super().pattern_to_regex(pattern + marker)
        return (None if regex is None else regex.replace(marker, "") if marker else regex), include

    @classmethod
    def _bracket(cls, pattern: str, offset: int) -> tuple[str, int]:
        offset += 1
        negated = offset < len(pattern) and pattern[offset] in "!^"
        offset += int(negated)
        selected: set[int] = set()
        previous = None
        while offset < len(pattern):
            char = pattern[offset]
            if char == "\\":
                offset += 1
                if offset == len(pattern):
                    return r"(?!)", offset
                previous = ord(pattern[offset])
                selected.add(previous)
            elif char == "-" and previous and offset + 1 < len(pattern) and pattern[offset + 1] != "]":
                offset += 1
                if pattern[offset] == "\\":
                    offset += 1
                    if offset == len(pattern):
                        return r"(?!)", offset
                values = set(range(previous, ord(pattern[offset]) + 1))
                if cls.ignorecase:
                    values.update(value + 32 for value in tuple(values) if 65 <= value <= 90)
                selected.update(values)
                previous = None
            elif char == "[" and pattern.startswith("[:", offset):
                end = pattern.find("]", offset + 2)
                if end == -1:
                    return r"(?!)", len(pattern)
                if pattern[end - 1] == ":":
                    name = pattern[offset + 2:end - 1]
                    if name not in _CLASS_BYTES:
                        return r"(?!)", len(pattern)
                    values = set(_CLASS_BYTES[name])
                    if cls.ignorecase and name == "upper":
                        values.update(range(97, 123))
                    selected.update(values)
                    previous = None
                    offset = end
                else:
                    previous = ord(char)
                    selected.add(previous)
            else:
                previous = ord(char)
                selected.add(previous)
            offset += 1
            if offset < len(pattern) and pattern[offset] == "]":
                selected = (set(range(1, 256)) - selected) if negated else selected
                selected.discard(ord("/"))
                return _byte_class(selected), offset + 1
        return r"(?!)", offset

    @classmethod
    def _translate_segment_glob(cls, pattern: str, range_error: str) -> str:
        # Keep pathspec's anchoring/negation/** decisions, with Git's bytewise
        # segment semantics. Inverted ranges retain their initial literal; an
        # escaped hyphen/closing bracket remains literal, not a regex range.
        converted, offset = [], 0
        while offset < len(pattern):
            char = pattern[offset]
            if char == "\\":
                if offset + 1 == len(pattern):
                    return r"(?!)"
                converted.append(re.escape(pattern[offset + 1]))
                offset += 2
                continue
            if char == "[":
                expression, offset = cls._bracket(pattern, offset)
                converted.append(expression)
                continue
            if char == "*":
                converted.append("[^/]*")
            elif char == "?":
                converted.append("[^/]")
            else:
                converted.append(re.escape(char.translate(_ASCII_FOLD) if cls.ignorecase else char))
            offset += 1
        return "".join(converted)


class _FoldGitPattern(_GitPattern):
    ignorecase = True


def _git_bytes(text: str) -> str:
    return text.encode("utf-8", errors="surrogateescape").decode("latin1")


class _IgnoreRules:
    def __init__(self, *, ignorecase: bool = False):
        self.rules: dict[str, GitIgnoreSpec] = {}
        self.ignorecase = ignorecase

    def pattern(self, line: str) -> GitIgnoreSpecPattern:
        return (_FoldGitPattern if self.ignorecase else _GitPattern)(line)

    def add(self, path: str, source: bytes) -> None:
        try:
            # Git does not read symlinked .gitignore files. These bytes were
            # obtained from a regular disk file or a regular Git tree blob.
            # Git's records end at LF; Unicode paragraph separators can be
            # literal filename characters and must not split a pattern.
            self.rules[_git_bytes(path)] = GitIgnoreSpec.from_lines(
                source.removeprefix(b"\xef\xbb\xbf").decode("latin1").split("\n"),
                pattern_factory=self.pattern, backend="simple")
        except (UnicodeError, ValueError):
            raise _CaptureFailure("ignore_failure", "A .gitignore file could not be interpreted completely.") from None

    def _decision(self, path: str) -> bool:
        excluded = False
        for base, rules in sorted(self.rules.items(), key=lambda item: (len(PurePosixPath(item[0]).parts), item[0])):
            prefix = base + "/" if base else ""
            if not path.startswith(prefix) or path == prefix:
                continue
            relative = path[len(prefix):]
            match = rules.check_file(relative.translate(_ASCII_FOLD) if self.ignorecase else relative,
                                     separators=("/",)).include
            if match is not None:
                excluded = match
        return excluded

    def ignored(self, path: str, *, directory: bool = False) -> bool:
        path = _git_bytes(path)
        parts = path.strip("/").split("/")
        # A child negation cannot rescue an excluded parent directory.
        for count in range(1, len(parts)):
            if self._decision("/".join(parts[:count]) + "/"):
                return True
        return self._decision(path.rstrip("/") + ("/" if directory else ""))


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Capture:
    def __init__(self, snapshot: SettingsSnapshot, repository: Repository,
                 previous: CaptureManifest | None, git: GitReader, cancelled: Callable[[], bool] | None):
        self.snapshot, self.repository, self.previous = snapshot, repository, previous
        self.git, self.cancelled = git, cancelled
        self.scan = snapshot.values["scan"]
        self.diagnostics: list[CaptureDiagnostic] = []
        self.complete = True
        self.observed: dict[Path, tuple[int, ...]] = {}
        self.blobs: dict[tuple[Path, str], bytes] = {}
        self.old_locations = {} if previous is None else {location.id: location for location in previous.locations}
        self.policy_hash = ""
        self.git_ignorecase: dict[Path, bool | None] = {}

    def cancel(self) -> None:
        check_deadline()
        if self.cancelled is not None and self.cancelled():
            raise KeyboardInterrupt()

    def observe(self, path: Path, info: os.stat_result) -> None:
        signature = _signature(info)
        if path in self.observed and self.observed[path] != signature:
            raise _CaptureFailure("changed_during_capture", "A disk input changed between overlapping observations.")
        self.observed[path] = signature

    def fault(self, error: _CaptureFailure, location: LocationId | None = None,
              alias: FileAlias | None = None) -> None:
        self.complete = False
        self.diagnostics.append(CaptureDiagnostic(error.code, error.message, location, alias))

    def read_git(self, args: tuple[str, ...], checkout: Path, *, limit: int = GIT_METADATA_LIMIT) -> bytes:
        self.cancel()
        try:
            child = self.git(args, cwd=checkout, stdout_limit=max(1, limit),
                             timeout_seconds=GIT_READ_SECONDS, cancelled=self.cancelled)
        except MycelError:
            raise _CaptureFailure("git_failure", "A required read-only Git operation could not be completed.") from None
        if child.returncode != 0:
            raise _CaptureFailure("git_failure", "A required read-only Git operation failed.")
        if len(child.stdout) > max(1, limit):
            raise _CaptureFailure("git_output_limit", "A Git read exceeded its complete-output limit; no truncated input was accepted.")
        return child.stdout

    def checkout(self, root: Path) -> Path | None:
        self.cancel()
        marker = any(os.path.lexists(parent / ".git") for parent in (root, *root.parents))
        try:
            child = self.git(("rev-parse", "--show-toplevel"), cwd=root,
                             stdout_limit=GIT_METADATA_LIMIT, timeout_seconds=GIT_READ_SECONDS,
                             cancelled=self.cancelled)
        except MycelError:
            raise _CaptureFailure("git_failure", "The configured folder's Git context could not be inspected.") from None
        if child.returncode:
            if marker:
                raise _CaptureFailure("git_failure", "A checkout marker exists but its Git context could not be read.")
            return None
        try:
            checkout = Path(child.stdout.decode("utf-8").removesuffix("\n")).resolve(strict=True)
            if not root.is_relative_to(checkout):
                raise ValueError()
            return checkout
        except (OSError, UnicodeError, ValueError):
            raise _CaptureFailure("git_failure", "Git returned an invalid checkout context.") from None

    def ignorecase(self, checkout: Path) -> bool:
        self.cancel()
        try:
            child = self.git(("config", "--bool", "--get", "core.ignorecase"), cwd=checkout,
                             stdout_limit=GIT_METADATA_LIMIT, timeout_seconds=GIT_READ_SECONDS,
                             cancelled=self.cancelled)
        except MycelError:
            raise _CaptureFailure("git_policy", "The checkout's ignore-case policy could not be read.") from None
        if child.returncode == 1 and not child.stdout:
            return False  # Git's default when the configuration is absent.
        if child.returncode == 0 and child.stdout in {b"true\n", b"false\n"}:
            return child.stdout == b"true\n"
        raise _CaptureFailure("git_policy", "The checkout returned an invalid ignore-case policy.")

    def rules(self, checkout: Path | None) -> _IgnoreRules:
        ignorecase = False if checkout is None else self.git_ignorecase.get(checkout)
        if ignorecase is None:
            raise _CaptureFailure("git_policy", "The checkout's ignore-case policy is unavailable.")
        return _IgnoreRules(ignorecase=ignorecase)

    def bindings(self) -> tuple[_Binding, ...]:
        folders = [("code", self.repository.code), ("artifact", self.repository.documents)]
        roots = []
        for kind, folder in folders:
            if folder is None:
                continue
            try:
                path = folder.path.resolve(strict=True)
                if not path.is_dir():
                    raise OSError()
                roots.append((kind, path, folder.subfolders, self.checkout(path)))
            except (OSError, RuntimeError):
                self.fault(_CaptureFailure("root_unavailable", f"The configured {kind} root could not be read."))
            except _CaptureFailure as error:
                # Preserve disk input but never infer that old Git locations
                # vanished because discovering their context failed.
                self.fault(error)
                roots.append((kind, path, folder.subfolders, None))
        result = []
        for kind, path, subfolders, checkout in roots:
            base = checkout or min((other for _, other, _, _ in roots if path.is_relative_to(other)),
                                   key=lambda other: len(other.parts))
            result.append(_Binding(kind, path, base, checkout, subfolders))
        return tuple(result)

    def alias(self, root: Root, path: str) -> FileAlias:
        result = FileAlias(root, path)
        try:
            result.address(self.repository.name)
        except (SourceAddressError, UnicodeError):
            raise _CaptureFailure("invalid_path", "A discovered path cannot be represented by a portable file address.") from None
        return result

    def corpus(self, alias: FileAlias, binding: _Binding) -> Corpus | None:
        if any(alias.path.endswith(ending) for ending in self.scan["document_endings"]):
            return "documents"
        if binding.root == "code" and any(alias.path.endswith(ending) for ending in self.scan["code_endings"]):
            if not binding.subfolders or any(folder == "." or alias.path == folder or alias.path.startswith(folder.rstrip("/") + "/")
                                             for folder in binding.subfolders):
                return "code"
        return None

    def skipped(self, path: str, *, directory: bool = False) -> bool:
        parts = PurePosixPath(path).parts
        return any(part in self.scan["skip_folders"] for part in (parts if directory else parts[:-1]))

    def read_disk(self, path: Path, *, parent: int | None = None, name: str | None = None) -> bytes:
        self.cancel()
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = None
        try:
            descriptor = os.open(path if parent is None else name, flags, dir_fd=parent)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise OSError()
            pieces = []
            while True:
                self.cancel()
                piece = os.read(descriptor, 1024 * 1024)
                if not piece:
                    break
                pieces.append(piece)
            after = os.fstat(descriptor)
            source = b"".join(pieces)
            if _signature(before) != _signature(after) or len(source) != after.st_size:
                raise _CaptureFailure("changed_during_capture", "A file changed while its complete bytes were being read.")
            self.observe(path, after)
            return source
        except OSError:
            raise _CaptureFailure("file_unavailable", "A required regular file could not be read safely.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def disk_rules(self, binding: _Binding) -> _IgnoreRules:
        rules = self.rules(binding.checkout)
        relative = binding.path.relative_to(binding.base)
        parts = relative.parts
        for depth in range(len(parts) + 1):
            directory = binding.base.joinpath(*parts[:depth])
            try:
                self.observe(directory, directory.lstat())
            except OSError:
                raise _CaptureFailure("ignore_failure", "An ancestor supplying .gitignore rules could not be inspected.") from None
            prefix = PurePosixPath(*parts[:depth]).as_posix() if depth else ""
            if prefix and (self.skipped(prefix, directory=True) or rules.ignored(prefix, directory=True)):
                break
            ignore = directory / ".gitignore"
            try:
                info = ignore.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                raise _CaptureFailure("ignore_failure", "A required .gitignore file could not be inspected.") from None
            if stat.S_ISREG(info.st_mode):
                rules.add(prefix, self.read_disk(ignore))
        return rules

    def disk_candidates(self, binding: _Binding) -> Iterator[tuple[Path, FileAlias, Corpus, bytes, tuple[int, int]]]:
        rules = self.disk_rules(binding)
        if binding.prefix and (self.skipped(binding.prefix, directory=True) or rules.ignored(binding.prefix, directory=True)):
            return

        def walk(directory: Path, descriptor: int, relative: str):
            self.cancel()
            before = os.fstat(descriptor)
            self.observe(directory, before)
            prefix = "/".join(part for part in (binding.prefix, relative) if part)
            if relative:
                try:
                    info = os.stat(".gitignore", dir_fd=descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    info = None
                except OSError:
                    raise _CaptureFailure("ignore_failure", "A required .gitignore file could not be inspected.") from None
                if info is not None and stat.S_ISREG(info.st_mode):
                    rules.add(prefix, self.read_disk(directory / ".gitignore", parent=descriptor, name=".gitignore"))
            try:
                with os.scandir(descriptor) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
                for entry in entries:
                    self.cancel()
                    if entry.name == ".git":
                        continue
                    local = "/".join(part for part in (relative, entry.name) if part)
                    path = "/".join(part for part in (binding.prefix, local) if part)
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        continue  # Never follow file/directory links, loops or escapes.
                    if stat.S_ISDIR(info.st_mode):
                        if entry.name in self.scan["skip_folders"] or rules.ignored(path, directory=True):
                            continue
                        child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                        try:
                            if (os.fstat(child).st_dev, os.fstat(child).st_ino) != (info.st_dev, info.st_ino):
                                raise _CaptureFailure("changed_during_capture", "A directory changed during enumeration.")
                            yield from walk(directory / entry.name, child, local)
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(info.st_mode) and not rules.ignored(path):
                        alias = FileAlias(binding.root, local)
                        corpus = self.corpus(alias, binding)
                        if corpus is not None:
                            alias = self.alias(binding.root, local)
                            source = self.read_disk(directory / entry.name, parent=descriptor, name=entry.name)
                            if self.observed[directory / entry.name][:2] != (info.st_dev, info.st_ino):
                                raise _CaptureFailure("changed_during_capture", "A file changed during enumeration.")
                            yield directory / entry.name, alias, corpus, source, (info.st_dev, info.st_ino)
                if _signature(before) != _signature(os.fstat(descriptor)):
                    raise _CaptureFailure("changed_during_capture", "A directory changed during enumeration.")
            except OSError:
                raise _CaptureFailure("scan_failure", "A corpus directory could not be enumerated completely.") from None

        descriptor = None
        try:
            descriptor = os.open(binding.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            yield from walk(binding.path, descriptor, "")
        except OSError:
            raise _CaptureFailure("root_unavailable", "A configured root could not be opened safely.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def parsed_file(self, location: LocationId, aliases: Mapping[FileAlias, int], corpus: Corpus,
                    source: bytes) -> CapturedFile:
        old = self.old_locations.get(location)
        prior = None if old is None else next((file for file in old.files if file.primary in aliases), None)
        primary = prior.primary if prior is not None else max(
            aliases, key=lambda alias: (aliases[alias], alias.root == "artifact", alias.path))
        digest = sha256(source).hexdigest()
        if self.previous is not None and self.previous.policy_hash == self.policy_hash \
                and prior is not None and prior.file_hash == digest and prior.source == source and prior.corpus == corpus \
                and prior.failure is None:
            return replace(prior, aliases=tuple(sorted(aliases)), reused_parse=True)
        failure, parsed = None, None
        try:
            parsed = split_markdown(source) if corpus == "documents" else chunk_code(primary.path, source.decode("utf-8"))
        except (UnicodeError, MarkdownDecodeError):
            failure = "invalid_utf8"
        except (ValueError, RuntimeError, RecursionError):
            failure = "parse_failure"
        if failure:
            self.diagnostics.append(CaptureDiagnostic(failure, "The exact file bytes were retained but could not be parsed.",
                                                      location, primary))
        return CapturedFile(primary, tuple(sorted(aliases)), corpus, source, digest, parsed, failure)

    def disk_capture(self, bindings: tuple[_Binding, ...]) -> CapturedLocation:
        location = LocationId("disk", None, "disk")
        candidates = {}
        complete = True
        for binding in bindings:
            try:
                for path, alias, corpus, source, identity in self.disk_candidates(binding):
                    aliases = {self.alias(other.root, path.relative_to(other.path).as_posix()): len(other.path.parts)
                               for other in bindings if path.is_relative_to(other.path)}
                    aliases[alias] = len(binding.path.parts)
                    if identity in candidates:
                        known_source, known_corpus, known_aliases = candidates[identity]
                        if source != known_source or corpus != known_corpus:
                            raise _CaptureFailure("changed_during_capture", "A physical file's overlapping inputs disagree.")
                        known_aliases.update(aliases)
                    else:
                        candidates[identity] = (source, corpus, aliases)
            except _CaptureFailure as error:
                complete = False
                self.fault(_CaptureFailure(error.code, f"{binding.root} root: {error.message}"), location)
        files = tuple(sorted((self.parsed_file(location, aliases, corpus, source)
                              for source, corpus, aliases in candidates.values()), key=lambda file: file.primary))
        return CapturedLocation(location, None, files, complete and len(bindings) == sum(
            folder is not None for folder in (self.repository.code, self.repository.documents)))

    def inventory(self, checkout: Path) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
        refs = self.read_git(("for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)",
                              "--sort=refname", "refs/heads/"), checkout)
        branches = []
        try:
            for row in refs.splitlines():
                name, oid, kind = row.decode("utf-8").split("\0")
                if not name.startswith("refs/heads/") or kind != "commit" or not _OID.fullmatch(oid):
                    raise ValueError()
                branches.append((name, oid))
            stashes = tuple(sorted(set(self.read_git(("stash", "list", "--format=%H"), checkout).decode("ascii").splitlines())))
            if any(not _OID.fullmatch(oid) for oid in stashes):
                raise ValueError()
        except (UnicodeError, ValueError):
            raise _CaptureFailure("git_inventory", "Local branch/stash enumeration returned invalid identities.") from None
        return tuple(sorted(branches)), stashes

    def tree(self, checkout: Path, commit: str) -> dict[str, _TreeFile]:
        result = {}
        raw = self.read_git(("ls-tree", "-r", "-l", "-z", "--full-tree", commit), checkout)
        try:
            for record in raw.split(b"\0"):
                if not record:
                    continue
                header, path = record.split(b"\t", 1)
                mode, kind, oid, size = header.decode("ascii").split()
                # Tree filenames are opaque until selected. An unrelated
                # non-UTF-8 filename must not obstruct eligible corpus bytes.
                path = path.decode("utf-8", errors="surrogateescape")
                if path in result or not _OID.fullmatch(oid):
                    raise ValueError()
                if kind == "blob" and mode in {"100644", "100755"}:
                    result[path] = _TreeFile(path, oid, int(size), mode)
                # Symlink blobs and gitlinks are intentional exclusions in all
                # locations; they are not substituted with current disk text.
        except (UnicodeError, ValueError):
            raise _CaptureFailure("git_tree", "A Git tree could not be enumerated completely.") from None
        return result

    def blob(self, checkout: Path, file: _TreeFile) -> bytes:
        key = (checkout, file.oid)
        if key not in self.blobs:
            source = self.read_git(("cat-file", "-p", file.oid), checkout, limit=file.size)
            if len(source) != file.size:
                raise _CaptureFailure("git_blob", "A Git blob's complete bytes could not be read.")
            self.blobs[key] = source
        return self.blobs[key]

    def git_capture(self, checkout: Path, bindings: tuple[_Binding, ...], identifier: LocationId,
                    commit: str, policy_hash: str) -> CapturedLocation:
        prior = self.old_locations.get(identifier)
        if self.previous is not None and self.previous.policy_hash == policy_hash and prior is not None \
                and prior.commit == commit and prior.complete and all(file.failure is None for file in prior.files):
            return replace(prior, reused=True)
        trees = (commit,)
        files = self.tree(checkout, commit)
        if identifier.kind == "stash":
            metadata = self.read_git(("cat-file", "-p", commit), checkout)
            try:
                parents = tuple(line[7:].decode("ascii") for line in metadata.split(b"\n\n", 1)[0].splitlines()
                                if line.startswith(b"parent "))
            except UnicodeError:
                raise _CaptureFailure("git_stash", "A stash has an invalid captured-tree structure.") from None
            if len(parents) not in {2, 3} or any(not _OID.fullmatch(oid) for oid in parents):
                raise _CaptureFailure("git_stash", "A stash has an invalid captured-tree structure.")
            if len(parents) == 3:
                trees = (commit, parents[2])
                for path, file in self.tree(checkout, parents[2]).items():
                    if path in files:
                        raise _CaptureFailure("git_stash", "A stash's tracked and untracked trees overlap unexpectedly.")
                    files[path] = file
        rules = self.rules(checkout)
        for path, file in sorted(files.items(), key=lambda item: (len(PurePosixPath(item[0]).parts), item[0])):
            if PurePosixPath(path).name != ".gitignore" or self.skipped(path):
                continue
            base = str(PurePosixPath(path).parent)
            base = "" if base == "." else base
            # Git still consumes a regular .gitignore that its own patterns
            # exclude as a file. Only an excluded ancestor prevents descent.
            if base and rules.ignored(base, directory=True):
                continue
            if any(not binding.prefix or base == binding.prefix or base.startswith(binding.prefix + "/")
                   or binding.prefix.startswith(base + "/") or not base for binding in bindings):
                rules.add(base, self.blob(checkout, file))
        captured = []
        for path, file in sorted(files.items()):
            self.cancel()
            if self.skipped(path) or rules.ignored(path):
                continue
            aliases = {}
            corpus = None
            eligible_bindings = []
            for binding in bindings:
                prefix = binding.prefix + "/" if binding.prefix else ""
                if not path.startswith(prefix):
                    continue
                alias = FileAlias(binding.root, path[len(prefix):])
                eligible_bindings.append((binding, alias))
                selected = self.corpus(alias, binding)
                if selected == "documents" or corpus is None:
                    corpus = selected
            if corpus is not None:
                aliases = {self.alias(binding.root, alias.path): len(binding.path.parts)
                           for binding, alias in eligible_bindings}
                captured.append(self.parsed_file(identifier, aliases, corpus, self.blob(checkout, file)))
        return CapturedLocation(identifier, commit, tuple(sorted(captured, key=lambda file: file.primary)), True, trees)

    def verify_disk(self) -> None:
        for path, expected in self.observed.items():
            self.cancel()
            try:
                if _signature(path.lstat()) != expected:
                    raise OSError()
            except OSError:
                self.fault(_CaptureFailure("changed_during_capture", "A disk input changed before capture finished."),
                           LocationId("disk", None, "disk"))
                return

    def capture(self) -> CaptureManifest:
        bindings = self.bindings()
        checkouts = {binding.checkout for binding in bindings if binding.checkout is not None}
        for checkout in sorted(checkouts, key=str):
            try:
                self.git_ignorecase[checkout] = self.ignorecase(checkout)
            except _CaptureFailure as error:
                self.git_ignorecase[checkout] = None
                self.fault(error)
        policy_hash = sha256(_json({"revision": CAPTURE_REVISION, "scan": dict(self.scan),
                                   "parsers": _parser_revision(),
                                   "roots": [{"root": binding.root, "path": str(binding.path),
                                              "base": str(binding.base), "subfolders": binding.subfolders}
                                             for binding in bindings],
                                   "gitIgnoreCase": [{"checkout": str(checkout), "value": self.git_ignorecase[checkout]}
                                                     for checkout in sorted(checkouts, key=str)]})).hexdigest()
        self.policy_hash = policy_hash
        locations = [self.disk_capture(bindings)]
        for checkout in sorted(checkouts, key=str):
            members = tuple(binding for binding in bindings if binding.checkout == checkout)
            anchor = "code" if any(binding.root == "code" for binding in members) else "artifact"
            try:
                inventory = self.inventory(checkout)
            except _CaptureFailure as error:
                self.fault(error)
                continue
            branches, stashes = inventory
            targets = [(LocationId("branch", anchor, name), commit) for name, commit in branches]
            targets += [(LocationId("stash", anchor, commit), commit) for commit in stashes]
            for identifier, commit in targets:
                try:
                    locations.append(self.git_capture(checkout, members, identifier, commit, policy_hash))
                except _CaptureFailure as error:
                    self.fault(error, identifier)
                    locations.append(CapturedLocation(identifier, commit, (), False))
            try:
                if inventory != self.inventory(checkout):
                    self.fault(_CaptureFailure("changed_during_capture", "Local branch/stash identities changed during capture."))
            except _CaptureFailure as error:
                self.fault(error)
        for checkout in sorted(checkouts, key=str):
            try:
                if self.git_ignorecase[checkout] != self.ignorecase(checkout):
                    self.fault(_CaptureFailure("changed_during_capture", "The checkout's ignore-case policy changed during capture."))
            except _CaptureFailure as error:
                self.fault(error)
        self.verify_disk()
        complete = self.complete and all(location.complete for location in locations)
        locations = [locations[0], *sorted(locations[1:], key=lambda location:
                     (location.id.kind == "stash", location.id.checkout != "code", location.id.identity))]
        return CaptureManifest(self.repository.name, policy_hash, tuple(locations), complete, tuple(self.diagnostics))


def capture_repository(snapshot: SettingsSnapshot, repository: Repository | str, *,
                       previous: CaptureManifest | None = None,
                       cancelled: Callable[[], bool] | None = None,
                       _git: GitReader = run_git) -> CaptureManifest:
    """Capture disk first, sorted local branches next, commit-named stashes last.

    The private reader seam is for memory fixtures; production always uses the
    safe read-only Git boundary. Configured root symlinks resolve once, while
    links below a root are excluded equally on disk and in Git trees. Unchanged
    immutable Git locations can reuse a prior complete capture under the exact
    same root/policy/parser fingerprint; disk bytes are always read again.
    Git metadata uses the safe child's ordinary output cap. Oversized metadata
    refuses completeness visibly, never truncates a tree or permits deletion.
    Blob reads have an exact finite cap from ls-tree's object byte count, retain
    every source byte, and share the child's finite deadline/cancellation.
    """
    snapshot.require_valid()
    if isinstance(repository, str):
        selected = RepositoryLocations(snapshot).named(repository)
        if len(selected) != 1 or selected[0].name != repository:
            raise MycelError("invalid_input", "Capture requires one configured repository, not an organization.")
        repository = selected[0]
    else:
        selected = RepositoryLocations(snapshot).named(repository.name)
        if len(selected) != 1 or selected[0] != repository:
            raise MycelError("invalid_input", "Capture folders must come from this invocation's settings snapshot.")
        repository = selected[0]
    repository.require_folders()
    if not repository.enabled:
        raise MycelError("refused", "The repository is disabled in these settings.")
    if previous is not None and previous.repository != repository.name:
        raise MycelError("invalid_input", "Capture comparison requires the same exact repository.")
    check_deadline()
    captured = _Capture(snapshot, repository, previous, _git, cancelled).capture()
    check_deadline()
    return captured
