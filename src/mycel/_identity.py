"""Finite whole-file identity plans, separate from exact versions and pins.

This pure layer neither allocates persisted IDs nor applies removals, writes
locations, copies evidence, confirms a claim or opens the store. Its two matching
rounds reserve names across the whole file before considering nonempty content.
"""

from __future__ import annotations

from collections import deque
from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

from ._code import CODE_IDENTITY_REVISION, CodeChunk, code_identity_key
from ._evidence import (ComparisonRecord, EvidenceError, document_comparisons,
                        exact_comparison)
from ._markdown import MarkdownChunk, normalize_comparison


def _invalid() -> None:
    raise EvidenceError("invalid_input")


def _label(value: object, *, empty: bool = False) -> None:
    if not isinstance(value, str) or (not empty and not value) or "\0" in value:
        _invalid()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _invalid()


@dataclass(frozen=True)
class ChunkInput:
    name: str
    kind: Literal["document", "code"]
    source: bytes = field(repr=False)
    comparison: ComparisonRecord
    body: str | None = field(default=None, repr=False)
    title: str | None = None
    title_comparison: ComparisonRecord | None = None
    code_rename_key: str | None = None
    _snapshot_hash: str = field(init=False, repr=False)
    _has_body: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _label(self.name, empty=True)
        if type(self.source) is not bytes or not isinstance(self.comparison, ComparisonRecord):
            _invalid()
        try:
            text = self.source.decode("utf-8")
        except UnicodeError:
            raise EvidenceError("insufficient_evidence") from None
        if self.kind == "document":
            if (not isinstance(self.body, str) or self.comparison.kind != "document_body"
                    or not isinstance(self.title_comparison, ComparisonRecord)
                    or self.title_comparison.kind != "document_title"):
                _invalid()
            try:
                body = self.body.encode("utf-8")
            except UnicodeError:
                raise EvidenceError("insufficient_evidence") from None
            if self.title is not None:
                _label(self.title, empty=True)
            if not self.source.endswith(body):
                _invalid()
            self.comparison.verify(self.body)
            self.title_comparison.verify(self.title or "")
        elif self.kind == "code":
            if (self.comparison.kind != "code_text" or self.body is not None
                    or self.title is not None or self.title_comparison is not None):
                _invalid()
            self.comparison.verify(self.source)
            if self.code_rename_key is not None and (not isinstance(self.code_rename_key, str)
                    or len(self.code_rename_key) != 64
                    or any(c not in "0123456789abcdef" for c in self.code_rename_key)):
                _invalid()
        else:
            _invalid()
        object.__setattr__(self, "_snapshot_hash", sha256(self.source).hexdigest())
        object.__setattr__(self, "_has_body", bool(normalize_comparison(self.body))
                           if self.kind == "document" else bool(text.strip()))

    @property
    def snapshot_hash(self) -> str:
        return self._snapshot_hash

    @property
    def has_body(self) -> bool:
        return self._has_body

    @property
    def identity_comparison(self):
        if self.code_rename_key is not None:
            return (CODE_IDENTITY_REVISION, self.code_rename_key)
        return self.comparison

    @classmethod
    def document(cls, chunk: MarkdownChunk) -> ChunkInput:
        if not isinstance(chunk, MarkdownChunk):
            _invalid()
        records = document_comparisons(chunk.body, chunk.title or "")
        try:
            source = chunk.text.encode("utf-8")
        except UnicodeError:
            raise EvidenceError("insufficient_evidence") from None
        body = ComparisonRecord.from_record(records["body"])
        title = ComparisonRecord.from_record(records["title"])
        # Reproduce, rather than silently repair, the parser's recorded hashes.
        if chunk.comparison_revision != body.revision or chunk.unicode_version != body.unicode_version:
            raise EvidenceError("unsupported_comparison")
        if (chunk.content_hash != body.hash or chunk.title_hash != title.hash
                or chunk.snapshot_hash != sha256(source).hexdigest()):
            raise EvidenceError("snapshot_corrupt")
        return cls(chunk.name, "document", source, body, chunk.body, chunk.title, title)

    @classmethod
    def code(cls, chunk: CodeChunk) -> ChunkInput:
        if not isinstance(chunk, CodeChunk):
            _invalid()
        try:
            source = chunk.text.encode("utf-8")
        except UnicodeError:
            raise EvidenceError("insufficient_evidence") from None
        # Names are within this already-resolved file. A path is file metadata,
        # not part of a symbol's logical name. The complete-code comparison
        # still includes the name; only identity's second round uses D38.
        return cls(chunk.symbol, "code", source, exact_comparison(source, "code_text"),
                   code_rename_key=code_identity_key(chunk))


@dataclass(frozen=True)
class KnownVersion:
    identifier: int
    chunk: ChunkInput
    historical_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.identifier) is not int or self.identifier <= 0 or not isinstance(self.chunk, ChunkInput):
            _invalid()
        if type(self.historical_names) is not tuple:
            _invalid()
        for name in self.historical_names:
            _label(name)
        object.__setattr__(self, "historical_names",
                           tuple(sorted(set(self.historical_names), key=lambda name: name.encode("utf-8"))))


@dataclass(frozen=True)
class KnownChunk:
    identifier: str
    current_version: int
    versions: tuple[KnownVersion, ...]
    _current: KnownVersion = field(init=False, repr=False)
    _preferred: tuple[KnownVersion, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _label(self.identifier)
        if (type(self.current_version) is not int or type(self.versions) is not tuple or not self.versions
                or any(not isinstance(version, KnownVersion) for version in self.versions)
                or len({version.identifier for version in self.versions}) != len(self.versions)
                or self.current_version not in {version.identifier for version in self.versions}
                or len({version.chunk.snapshot_hash for version in self.versions}) != len(self.versions)
                or len({version.chunk.kind for version in self.versions}) != 1):
            _invalid()
        object.__setattr__(self, "_current", next(version for version in self.versions
                                                if version.identifier == self.current_version))
        object.__setattr__(self, "_preferred", tuple(sorted(self.versions, key=lambda version:
                           (version.identifier != self.current_version, version.identifier))))

    @property
    def current(self) -> KnownVersion:
        return self._current

    def preferred_versions(self) -> tuple[KnownVersion, ...]:
        return self._preferred


@dataclass(frozen=True)
class IdentityDecision:
    incoming_index: int | None
    incoming: ChunkInput | None
    chunk_id: str | None
    reason: Literal["unchanged", "edited", "renamed", "new", "removed"]
    matched_by: Literal["current_name", "historical_name", "content"] | None = None
    reference_version: int | None = None
    version_id: int | None = None
    version_action: Literal["reuse_existing", "create_new"] | None = None
    pin_decision: Literal["restore_existing", "inherit_existing", "requires_authorized_capture"] | None = None
    pin_version: int | None = None
    reuse_vectors: bool = False


@dataclass(frozen=True)
class FileIdentityPlan:
    decisions: tuple[IdentityDecision, ...]
    removed: tuple[IdentityDecision, ...]


def _reference(known: KnownChunk, incoming: ChunkInput, phase: str) -> KnownVersion | None:
    if known.current.chunk.kind != incoming.kind:
        return None
    if phase == "current_name":
        return known.current if known.current.chunk.name == incoming.name else None
    for version in known.preferred_versions():
        chunk = version.chunk
        if phase == "historical_name" and (chunk.name == incoming.name or incoming.name in version.historical_names):
            return version
        if phase == "content" and incoming.has_body and chunk.has_body and chunk.identity_comparison == incoming.identity_comparison:
            return version
    return None


def _assign(adjacency: dict[int, tuple[int, ...]], incoming: tuple[ChunkInput, ...]) -> dict[int, int]:
    """Deterministic maximum assignment; iterative even for a large file.

    Augment only within one phase. In particular, a historical-name choice can
    never displace a current-name reservation or a content match steal a name.
    """
    by_old: dict[int, int] = {}
    by_new: dict[int, int] = {}
    for start in sorted(adjacency, key=lambda index: incoming[index].name.encode("utf-8")):
        queue, seen, parents = deque([start]), {start}, {}
        free = None
        while queue and free is None:
            index = queue.popleft()
            for old in adjacency[index]:
                if old in parents:
                    continue
                parents[old] = index
                if old not in by_old:
                    free = old
                    break
                occupied = by_old[old]
                if occupied not in seen:
                    seen.add(occupied)
                    queue.append(occupied)
        while free is not None:
            index = parents[free]
            previous = by_new.get(index)
            by_new[index], by_old[free] = free, index
            free = previous
    return by_new


def _decision(index: int, incoming: ChunkInput, known: KnownChunk | None,
              phase: str | None, reference: KnownVersion | None) -> IdentityDecision:
    if known is None:
        return IdentityDecision(index, incoming, None, "new", version_action="create_new",
                                pin_decision="requires_authorized_capture")
    # Inheritance belongs to the version selected by the identity match. A
    # substantive edit against the current-name reference cannot quietly adopt
    # an unrelated archived pin merely because an older body resembles it.
    equivalent = reference if reference.chunk.identity_comparison == incoming.identity_comparison else None
    exact = next((version for version in known.versions
                  if version.chunk.snapshot_hash == incoming.snapshot_hash and version.chunk.source == incoming.source), None)
    current = known.current.chunk
    if phase == "content" or (current.name != incoming.name and reference.chunk.identity_comparison == incoming.identity_comparison):
        reason = "renamed"
    else:
        reason = "unchanged" if current.comparison == incoming.comparison else "edited"
    if exact is not None:
        return IdentityDecision(index, incoming, known.identifier, reason, phase, reference.identifier,
                                exact.identifier, "reuse_existing", "restore_existing", exact.identifier, True)
    if equivalent is not None:
        return IdentityDecision(index, incoming, known.identifier, reason, phase, reference.identifier,
                                None, "create_new", "inherit_existing", equivalent.identifier)
    return IdentityDecision(index, incoming, known.identifier, reason, phase, reference.identifier,
                            None, "create_new", "requires_authorized_capture")


def reconcile_file(incoming: tuple[ChunkInput, ...], known: tuple[KnownChunk, ...]) -> FileIdentityPlan:
    """Plan one file, preserving caller order in output and touching no state.

    Round one reserves every current name, then historical names among what
    remains. Round two matches only nonempty comparisons. Ties use stable chunk
    IDs and version IDs; retained-version input order does not decide identity.
    Removed decisions mean absent from this file input, never permission to
    delete a chunk/version still present in another disk/branch/stash location.
    """
    if (type(incoming) is not tuple or type(known) is not tuple
            or any(not isinstance(chunk, ChunkInput) for chunk in incoming)
            or any(not isinstance(chunk, KnownChunk) for chunk in known)
            or len({chunk.name for chunk in incoming}) != len(incoming)
            or len({chunk.identifier for chunk in known}) != len(known)):
        _invalid()
    versions = [version.identifier for chunk in known for version in chunk.versions]
    if len(set(versions)) != len(versions):
        _invalid()
    unmatched_new, unmatched_old = set(range(len(incoming))), set(range(len(known)))
    assignments = {}
    indexes = {phase: defaultdict(set) for phase in ("current_name", "historical_name", "content")}
    for old, chunk in enumerate(known):
        indexes["current_name"][chunk.current.chunk.kind, chunk.current.chunk.name].add(old)
        for version in chunk.versions:
            indexes["historical_name"][version.chunk.kind, version.chunk.name].add(old)
            for name in version.historical_names:
                indexes["historical_name"][version.chunk.kind, name].add(old)
            if version.chunk.has_body:
                indexes["content"][version.chunk.kind, version.chunk.identity_comparison].add(old)
    for phase in ("current_name", "historical_name", "content"):
        references, adjacency = {}, {}
        for index in unmatched_new:
            candidates = []
            chunk = incoming[index]
            key = (chunk.kind, chunk.identity_comparison if phase == "content" else chunk.name)
            possible = indexes[phase].get(key, set()) if phase != "content" or chunk.has_body else set()
            for old in possible & unmatched_old:
                reference = _reference(known[old], incoming[index], phase)
                if reference is not None:
                    references[index, old] = reference
                    candidates.append(old)
            adjacency[index] = tuple(sorted(candidates, key=lambda old:
                (references[index, old].identifier != known[old].current_version,
                 known[old].identifier.encode("utf-8"))))
        for index, old in _assign(adjacency, incoming).items():
            assignments[index] = (old, phase, references[index, old])
            unmatched_new.remove(index)
            unmatched_old.remove(old)
    decisions = []
    for index, chunk in enumerate(incoming):
        assignment = assignments.get(index)
        decisions.append(_decision(index, chunk, None, None, None) if assignment is None else
                         _decision(index, chunk, known[assignment[0]], assignment[1], assignment[2]))
    removed = tuple(IdentityDecision(None, None, known[old].identifier, "removed",
                                    reference_version=known[old].current_version)
                    for old in sorted(unmatched_old, key=lambda old: known[old].identifier.encode("utf-8")))
    return FileIdentityPlan(tuple(decisions), removed)
