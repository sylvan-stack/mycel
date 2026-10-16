"""Exact, dependant-owned evidence; no parser, provider or implicit repinning.

This layer consumes the resolver's recorded comparisons and exact body spans.
Pin callers supply a fresh observation under the checked nonblocking guards.
Ingest decides whether an edit or owner action authorizes a pin or inheritance.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Any, Iterator, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg import pq
from psycopg.types.json import Jsonb

from ._code import chunk_code, code_identity_key
from ._errors import MycelError
from ._locks import atomic_transaction, operation_guard, read_snapshot
from ._markdown import COMPARISON_REVISION, UNICODE_VERSION, comparison_hash
from ._resolver import Resolution, ResolvedChunk, ResolvedFile, SelectionMember, SourceResolver, SourceSelection
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress, parse_source_address
from ._store import checked_store, exact_bytes

EXACT_REVISION = "sha256-exact-v1"
FAMILY_REVISION = "sha256-canonical-family-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = {"document_body", "document_title", "code_text", "file_bytes", "family"}


class EvidenceError(ValueError):
    """A visible evidence fault, containing no native or source text details."""

    def __init__(self, status: str, addresses: tuple[str, ...] = ()):
        self.status = status
        self.addresses = tuple(sorted(set(addresses)))
        super().__init__(status)


def _fail(status: str = "snapshot_corrupt") -> None:
    raise EvidenceError(status)


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail()
    return value


def _integer(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail()
    return value


def _text(value: Any, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        _fail()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _fail()
    return value


def canonical_json(value: Any) -> bytes:
    """MYC-16 canonical UTF-8 JSON; floats and non-JSON values are refused."""
    active: set[int] = set()

    def plain(item):
        if item is None or type(item) in {bool, int}:
            return item
        if isinstance(item, str):
            return _text(item, empty=True)
        if isinstance(item, Mapping) or type(item) in {tuple, list}:
            if id(item) in active:
                _fail()
            active.add(id(item))
            try:
                if isinstance(item, Mapping):
                    if any(not isinstance(key, str) for key in item):
                        _fail()
                    return {_text(key, empty=True): plain(member) for key, member in item.items()}
                return [plain(member) for member in item]
            finally:
                active.remove(id(item))
        _fail()

    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _frozen(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(member) for key, member in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(member) for member in value)
    return value


def _place(place: SourceAddress) -> dict[str, Any]:
    if not isinstance(place, SourceAddress) or place.root not in {"code", "artifact"}:
        _fail()
    address = place.address
    result = {"repository": place.repository, "root": place.root, "path": place.path, "address": address}
    if place.name is not None:
        result["name"] = place.name
    return result


def _read_place(value) -> SourceAddress:
    if not isinstance(value, dict) or set(value) not in (
            {"repository", "root", "path", "address"}, {"repository", "root", "path", "address", "name"}):
        _fail()
    try:
        place = parse_source_address(value["address"])
        if _place(place) != value:
            _fail()
        return place
    except (TypeError, ValueError):
        _fail()


@dataclass(frozen=True)
class ComparisonRecord:
    kind: str
    revision: str
    hash: str
    unicode_version: str | None = None

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in _KINDS:
            _fail()
        _text(self.revision)
        _hash(self.hash)
        if self.kind.startswith("document_"):
            _text(self.unicode_version)
        elif self.unicode_version is not None:
            _fail()

    def as_dict(self) -> dict:
        result = {"kind": self.kind, "revision": self.revision, "hash": self.hash}
        if self.unicode_version is not None:
            result["unicodeVersion"] = self.unicode_version
        return result

    @classmethod
    def from_record(cls, record) -> ComparisonRecord:
        if not isinstance(record, Mapping) or set(record) not in (
                {"kind", "revision", "hash"}, {"kind", "revision", "hash", "unicodeVersion"}):
            _fail("unsupported_comparison")
        try:
            return cls(record["kind"], record["revision"], record["hash"], record.get("unicodeVersion"))
        except (TypeError, KeyError):
            _fail("unsupported_comparison")

    def require_supported(self) -> None:
        expected = (COMPARISON_REVISION if self.kind.startswith("document_") else
                    FAMILY_REVISION if self.kind == "family" else EXACT_REVISION)
        if self.revision != expected or (self.kind.startswith("document_") and self.unicode_version != UNICODE_VERSION):
            _fail("unsupported_comparison")

    def verify(self, source: bytes | str | tuple) -> None:
        self.require_supported()
        if self.kind.startswith("document_"):
            if isinstance(source, bytes):
                try:
                    source = source.decode("utf-8")
                except UnicodeError:
                    _fail("insufficient_evidence")
            digest = comparison_hash(_text(source, empty=True))
        elif self.kind == "family":
            digest = sha256(canonical_json(source)).hexdigest()
        else:
            if type(source) is not bytes:
                _fail()
            if self.kind == "code_text":
                try:
                    source.decode("utf-8")
                except UnicodeError:
                    _fail("insufficient_evidence")
            digest = sha256(source).hexdigest()
        if digest != self.hash:
            _fail()


def document_comparisons(body: str, title: str) -> Mapping[str, Mapping]:
    """Record current parser projections; never used to repair a missing pin."""
    return _frozen({kind: ComparisonRecord(f"document_{kind}", COMPARISON_REVISION,
                   comparison_hash(_text(text, empty=True)), UNICODE_VERSION).as_dict()
                   for kind, text in (("body", body), ("title", title))})


def exact_comparison(source: bytes, kind: Literal["code_text", "file_bytes"]) -> ComparisonRecord:
    record = ComparisonRecord(kind, EXACT_REVISION, sha256(source).hexdigest())
    record.verify(source)
    return record


def chunk_comparison(chunk: ResolvedChunk) -> ComparisonRecord:
    """Validate recorded projections, including title independently of body."""
    if chunk.kind == "document":
        if not isinstance(chunk.comparison, Mapping) or set(chunk.comparison) != {"body", "title"} or chunk.body is None:
            _fail("unsupported_comparison")
        body = ComparisonRecord.from_record(chunk.comparison["body"])
        title = ComparisonRecord.from_record(chunk.comparison["title"])
        if body.kind != "document_body" or title.kind != "document_title":
            _fail("unsupported_comparison")
        body.verify(chunk.body)
        title.verify(chunk.title or "")
        return body
    record = ComparisonRecord.from_record(chunk.comparison)
    if record.kind != "code_text":
        _fail("unsupported_comparison")
    record.verify(chunk.source)
    return record


@dataclass(frozen=True)
class SnapshotEvidence:
    hash: str
    byte_count: int
    encoding: Literal["utf-8", "bytes"]
    comparison: ComparisonRecord | None = None
    place: SourceAddress | None = None
    file_hash: str | None = None
    span: tuple[int, int] | None = None
    comparison_span: tuple[int, int] | None = None

    def __post_init__(self):
        _hash(self.hash)
        _integer(self.byte_count)
        if not isinstance(self.encoding, str) or self.encoding not in {"utf-8", "bytes"}:
            _fail()
        if self.comparison is not None and (not isinstance(self.comparison, ComparisonRecord)
                                           or self.comparison.kind == "document_title"):
            _fail()
        if self.place is not None:
            _place(self.place)
        if self.file_hash is not None:
            _hash(self.file_hash)
        if self.span is not None:
            if (type(self.span) is not tuple or len(self.span) != 2 or self.file_hash is None
                    or _integer(self.span[1]) < _integer(self.span[0])):
                _fail()
            if self.span[1] - self.span[0] != self.byte_count:
                _fail()
        if self.comparison is not None and self.comparison.kind == "document_body":
            if (type(self.comparison_span) is not tuple or len(self.comparison_span) != 2
                    or not 0 <= _integer(self.comparison_span[0]) <= _integer(self.comparison_span[1]) <= self.byte_count):
                _fail()
        elif self.comparison_span is not None:
            _fail()

    def as_dict(self) -> dict:
        result = {"snapshot": f"snapshot:{self.hash}", "hash": self.hash,
                  "bytes": self.byte_count, "encoding": self.encoding}
        if self.comparison is not None:
            result["comparison"] = self.comparison.as_dict()
        if self.place is not None:
            result["place"] = _place(self.place)
        if self.file_hash is not None:
            result["fileHash"] = self.file_hash
        if self.span is not None:
            result["span"] = {"start": self.span[0], "end": self.span[1]}
        if self.comparison_span is not None:
            result["comparisonSpan"] = {"start": self.comparison_span[0], "end": self.comparison_span[1]}
        return result

    @classmethod
    def from_record(cls, value) -> SnapshotEvidence:
        required = {"snapshot", "hash", "bytes", "encoding"}
        if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {
                "comparison", "place", "fileHash", "span", "comparisonSpan"}:
            _fail()
        if value["snapshot"] != f"snapshot:{value['hash']}":
            _fail()
        span = value.get("span")
        if span is not None:
            if not isinstance(span, dict) or set(span) != {"start", "end"}:
                _fail()
            span = (span["start"], span["end"])
        comparison_span = value.get("comparisonSpan")
        if comparison_span is not None:
            if not isinstance(comparison_span, dict) or set(comparison_span) != {"start", "end"}:
                _fail()
            comparison_span = (comparison_span["start"], comparison_span["end"])
        return cls(value["hash"], value["bytes"], value["encoding"],
                   ComparisonRecord.from_record(value["comparison"]) if "comparison" in value else None,
                   _read_place(value["place"]) if "place" in value else None, value.get("fileHash"), span, comparison_span)

    def verify(self, source: bytes, *, limit: int | None = None, textual: bool = False) -> bytes:
        if type(source) is not bytes or len(source) != self.byte_count or sha256(source).hexdigest() != self.hash:
            _fail()
        if limit is not None and len(source) > _integer(limit):
            _fail("input_too_large")
        if textual or self.encoding == "utf-8":
            try:
                source.decode("utf-8")
            except UnicodeError:
                _fail("insufficient_evidence")
        if self.comparison is not None:
            self.comparison.require_supported()
            if self.comparison.kind == "document_body":
                self.comparison.verify(source[slice(*self.comparison_span)])
            elif self.comparison.kind in {"code_text", "file_bytes"}:
                self.comparison.verify(source)
        return source


@dataclass(frozen=True)
class Snapshot:
    evidence: SnapshotEvidence
    source: bytes = field(repr=False)

    def __post_init__(self):
        self.evidence.verify(self.source)


def snapshot(source: bytes, *, comparison: ComparisonRecord | None = None,
             place: SourceAddress | None = None, file_source: bytes | None = None,
             span: tuple[int, int] | None = None, comparison_span: tuple[int, int] | None = None) -> Snapshot:
    if type(source) is not bytes:
        _fail()
    try:
        source.decode("utf-8")
        encoding = "utf-8"
    except UnicodeError:
        encoding = "bytes"
    file_hash = None
    if file_source is not None:
        if type(file_source) is not bytes:
            _fail()
        file_hash = sha256(file_source).hexdigest()
        if span is not None and (len(span) != 2 or type(span[0]) is not int or type(span[1]) is not int
                                or not 0 <= span[0] <= span[1] <= len(file_source)
                                or file_source[slice(*span)] != source):
            _fail()
    return Snapshot(SnapshotEvidence(sha256(source).hexdigest(), len(source), encoding,
                    comparison, place, file_hash, span, comparison_span), source)


def reconstruct(evidence: SnapshotEvidence, candidates: tuple[bytes, ...]) -> bytes:
    """Candidates are exact blobs/full files, never a newer-version fallback."""
    for candidate in candidates:
        if type(candidate) is not bytes:
            continue
        if evidence.span is not None:
            if sha256(candidate).hexdigest() != evidence.file_hash:
                continue
            candidate = candidate[slice(*evidence.span)]
        elif evidence.file_hash is not None and sha256(candidate).hexdigest() != evidence.file_hash:
            continue
        if len(candidate) == evidence.byte_count and sha256(candidate).hexdigest() == evidence.hash:
            return evidence.verify(candidate)
    _fail("baseline_missing")


@dataclass(frozen=True)
class CaptureLocation:
    kind: Literal["disk", "branch", "stash", "generated"]
    commit: str | None = None

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in {"disk", "branch", "stash", "generated"}:
            _fail()
        if self.kind in {"branch", "stash"} and self.commit is None:
            _fail()
        if self.commit is not None and (not isinstance(self.commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.commit)):
            _fail()

    def as_dict(self):
        return {"kind": self.kind, **({"commit": self.commit} if self.commit is not None else {})}


@dataclass(frozen=True)
class BaselineManifest:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        # Own a deeply immutable copy; no caller dictionary can change identity.
        encoded = canonical_json(self.payload)
        value = json.loads(encoded)
        required = {"schema", "ownerRepository", "dependantId", "dependantVersion", "dependant", "kind",
                    "source", "selection", "members", "pinnedHash", "selectionComparison", "capturedAt", "location"}
        if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {"ref"} or type(value["schema"]) is not int or value["schema"] != 1:
            _fail()
        for key in ("ownerRepository", "dependantId", "dependantVersion"):
            _text(value[key])
        if not re.fullmatch(r"[1-9][0-9]*", value["dependantVersion"]):
            _fail()
        if (not isinstance(value["kind"], str) or value["kind"] not in {"declared", "asserted", "related", "generated"}
                or not isinstance(value["selection"], str) or value["selection"] not in {"file", "chunk", "family"}):
            _fail()
        if "ref" in value:
            _text(value["ref"], empty=True)
        source = _read_place(value["source"])
        dependant = SnapshotEvidence.from_record(value["dependant"])
        if (dependant.place is None or dependant.place.repository != value["ownerRepository"]
                or dependant.place.name is None or dependant.comparison is None
                or dependant.comparison.kind not in {"document_body", "code_text"}
                or dependant.file_hash is None or dependant.span is None):
            _fail()
        _hash(value["pinnedHash"])
        try:
            captured = datetime.fromisoformat(value["capturedAt"].replace("Z", "+00:00"))
            if captured.tzinfo is None:
                _fail()
        except (ValueError, TypeError, AttributeError):
            _fail()
        location = value["location"]
        if not isinstance(location, dict) or set(location) not in ({"kind"}, {"kind", "commit"}):
            _fail()
        CaptureLocation(location["kind"], location.get("commit"))
        if not isinstance(value["members"], list) or not value["members"]:
            _fail()
        identities, identifiers, order = set(), set(), []
        for member in value["members"]:
            if not isinstance(member, dict) or set(member) not in ({"place", "evidence"}, {"id", "place", "evidence"}):
                _fail()
            place = _read_place(member["place"])
            evidence = SnapshotEvidence.from_record(member["evidence"])
            identifier = _text(member["id"]) if "id" in member else ""
            if (place.repository != source.repository or place.root != source.root or place.path != source.path
                    or evidence.place != place or place.address in identities or (identifier and identifier in identifiers)
                    or evidence.comparison is None or evidence.file_hash is None):
                _fail()
            if value["selection"] == "file":
                if (source.name is not None or place != source or evidence.span is not None
                        or evidence.comparison.kind != "file_bytes" or evidence.comparison.hash != evidence.hash
                        or evidence.file_hash != evidence.hash):
                    _fail()
            else:
                if (source.name is None or place.name is None or evidence.span is None
                        or evidence.comparison.kind not in {"document_body", "code_text"}
                        or (evidence.comparison.kind == "code_text" and evidence.comparison.hash != evidence.hash)):
                    _fail()
                if value["selection"] == "chunk" and place != source:
                    _fail()
                if value["selection"] == "family" and (evidence.comparison.kind != "code_text"
                        or not (place.name == source.name or place.name.startswith(source.name + "."))):
                    _fail()
            identities.add(place.address)
            if identifier:
                identifiers.add(identifier)
            order.append((place.address, identifier))
        if order != sorted(order) or (value["selection"] in {"file", "chunk"} and len(order) != 1):
            _fail()
        if value["selection"] == "family":
            if sum(item["place"] == value["source"] for item in value["members"]) != 1:
                _fail()
            selected_hash = sha256(canonical_json(_family_projection(value["members"]))).hexdigest()
            selected_comparison = ComparisonRecord("family", FAMILY_REVISION, selected_hash)
        else:
            selected_hash = value["members"][0]["evidence"]["comparison"]["hash"]
            selected_comparison = ComparisonRecord.from_record(value["members"][0]["evidence"]["comparison"])
        if selected_hash != value["pinnedHash"]:
            _fail()
        recorded = ComparisonRecord.from_record(value["selectionComparison"])
        recorded.require_supported()
        if recorded != selected_comparison:
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def identifier(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()

    def as_dict(self) -> dict:
        return {"id": self.identifier, **json.loads(self.canonical_bytes)}

    @classmethod
    def from_bytes(cls, source: bytes, digest: str) -> BaselineManifest:
        if type(source) is not bytes or sha256(source).hexdigest() != _hash(digest):
            _fail()
        try:
            value = json.loads(source)
            result = cls(value)
        except EvidenceError:
            raise
        except (ValueError, UnicodeError, TypeError):
            _fail()
        if result.canonical_bytes != source:
            _fail()
        return result


@dataclass(frozen=True)
class BaselineCapture:
    manifest: BaselineManifest
    snapshots: tuple[Snapshot, ...] = field(repr=False)

    def __post_init__(self):
        descriptors = [self.manifest.payload["dependant"], *(member["evidence"] for member in self.manifest.payload["members"])]
        by_hash = {blob.evidence.hash: blob for blob in self.snapshots}
        if len(by_hash) != len(self.snapshots):
            _fail()
        if set(by_hash) != {value["hash"] for value in descriptors}:
            _fail()
        for descriptor in descriptors:
            SnapshotEvidence.from_record(json.loads(canonical_json(descriptor))).verify(by_hash[descriptor["hash"]].source)


def _verified_code_rename(baseline: BaselineCapture, dependant: SelectionMember,
                          dependant_file: ResolvedFile, previous_file_source: bytes | None,
                          authorization: str | None) -> None:
    """Verify D38 using complete parsed files; exact comparisons stay distinct."""
    prior = SnapshotEvidence.from_record(json.loads(canonical_json(baseline.manifest.payload['dependant'])))
    if (authorization != 'recognized_rename' or prior.comparison.kind != 'code_text'
            or prior.place is None or prior.span is None or prior.file_hash is None
            or type(previous_file_source) is not bytes
            or sha256(previous_file_source).hexdigest() != prior.file_hash
            or type(dependant_file.source) is not bytes
            or sha256(dependant_file.source).hexdigest() != dependant_file.snapshot_hash):
        _fail('invalid_input')
    old_source = next(blob.source for blob in baseline.snapshots if blob.evidence.hash == prior.hash)
    if previous_file_source[slice(*prior.span)] != old_source:
        _fail('invalid_input')
    prior.verify(old_source)

    def parsed(source, path, span, raw, name, kind=None):
        try:
            matches = [chunk for chunk in chunk_code(path, source.decode('utf-8', errors='strict'))
                       if (chunk.byte_start, chunk.byte_end) == span
                       and chunk.text.encode('utf-8') == raw and chunk.symbol == name
                       and (kind is None or chunk.kind == kind)]
        except (UnicodeError, ValueError, TypeError):
            _fail('invalid_input')
        if len(matches) != 1 or code_identity_key(matches[0]) is None:
            _fail('invalid_input')
        return matches[0]

    previous = parsed(previous_file_source, prior.place.path, prior.span, old_source, prior.place.name)
    current = parsed(dependant_file.source, dependant.place.path, dependant.chunk.span,
                     dependant.chunk.source, dependant.chunk.name, dependant.chunk.kind)
    if code_identity_key(previous) != code_identity_key(current):
        _fail('invalid_input')


def inherit_baseline(baseline: BaselineCapture, dependant: SelectionMember,
                     dependant_file: ResolvedFile, *, authorization: str | None = None,
                     previous_file_source: bytes | None = None) -> BaselineCapture:
    """Carry the identical source pin to an authorized new dependant version.

    The ingest identity reconciler must establish the recognized rename or
    normalized-equivalent edit. This function never reads current source text.
    Original source declaration, capture location/time, members and comparisons
    are preserved; the new exact dependant bytes receive their own descriptor.
    """
    if (dependant.chunk.identifier != baseline.manifest.payload["dependantId"]
            or dependant.place.repository != baseline.manifest.payload["ownerRepository"]):
        _fail("invalid_input")
    dep = _chunk_snapshot(dependant, dependant_file)
    payload = json.loads(baseline.manifest.canonical_bytes)
    previous_comparison = ComparisonRecord.from_record(payload["dependant"]["comparison"])
    if previous_comparison != dep.evidence.comparison:
        _verified_code_rename(baseline, dependant, dependant_file, previous_file_source, authorization)
    payload["dependantVersion"] = str(dependant.chunk.version)
    payload["dependant"] = dep.evidence.as_dict()
    source_hashes = {member["evidence"]["hash"] for member in payload["members"]}
    blobs = {blob.evidence.hash: blob for blob in baseline.snapshots if blob.evidence.hash in source_hashes}
    blobs[dep.evidence.hash] = dep
    return BaselineCapture(BaselineManifest(payload), tuple(blobs[key] for key in sorted(blobs)))


def _chunk_snapshot(member: SelectionMember, file: ResolvedFile) -> Snapshot:
    chunk = member.chunk
    if chunk.span is None or member.place.repository != file.repository:
        _fail("insufficient_evidence")
    if chunk.kind == "document" and (chunk.body_span is None or chunk.source[slice(*chunk.body_span)] != chunk.body):
        _fail("insufficient_evidence")
    return snapshot(chunk.source, comparison=chunk_comparison(chunk), place=member.place,
                    file_source=file.source, span=chunk.span,
                    comparison_span=chunk.body_span if chunk.kind == "document" else None)


def _family_projection(members) -> tuple[dict, ...]:
    # Internal identifiers are audit evidence, not natural semantic membership.
    return tuple({"place": member["place"], "comparison": member["evidence"]["comparison"]} for member in members)


def capture_baseline(owner_repository: str, dependant: SelectionMember, dependant_file: ResolvedFile,
                     selection: SourceSelection, *, kind: str, declaration: str | None,
                     captured_at: str, location: CaptureLocation) -> BaselineCapture:
    if selection.kind not in {"file", "chunk", "family"} or selection.file is None:
        _fail("insufficient_evidence")
    if selection.kind != "file" and not selection.members:
        _fail("insufficient_evidence")
    if owner_repository != dependant.place.repository:
        _fail()
    dep = _chunk_snapshot(dependant, dependant_file)
    if selection.kind == "file":
        blob = snapshot(selection.file.source, comparison=exact_comparison(selection.file.source, "file_bytes"),
                        place=selection.place, file_source=selection.file.source)
        members = [{"id": selection.file.identifier, "place": _place(selection.place), "evidence": blob.evidence.as_dict()}]
        blobs = [dep, blob]
        pinned = blob.evidence.comparison.hash
        selected_comparison = blob.evidence.comparison
    else:
        ordered = tuple(sorted(selection.members, key=lambda member: (member.place.address, member.chunk.identifier)))
        blobs = [dep, *(_chunk_snapshot(member, selection.file) for member in ordered)]
        members = [{"id": member.chunk.identifier, "place": _place(member.place), "evidence": blob.evidence.as_dict()}
                   for member, blob in zip(ordered, blobs[1:], strict=True)]
        projection = _family_projection(members)
        pinned = (sha256(canonical_json(projection)).hexdigest() if selection.kind == "family"
                  else blobs[1].evidence.comparison.hash)
        selected_comparison = (ComparisonRecord("family", FAMILY_REVISION, pinned) if selection.kind == "family"
                               else blobs[1].evidence.comparison)
    payload = {"schema": 1, "ownerRepository": owner_repository, "dependantId": dependant.chunk.identifier,
               "dependantVersion": str(dependant.chunk.version), "dependant": dep.evidence.as_dict(), "kind": kind,
               "source": _place(selection.place), "selection": selection.kind, "members": members,
               "pinnedHash": pinned, "selectionComparison": selected_comparison.as_dict(),
               "capturedAt": captured_at, "location": location.as_dict()}
    if declaration is not None:
        payload["ref"] = declaration
    unique = {blob.evidence.hash: blob for blob in blobs}
    return BaselineCapture(BaselineManifest(payload), tuple(unique[key] for key in sorted(unique)))


@dataclass(frozen=True)
class PinInputs:
    settings: SettingsSnapshot = field(repr=False)
    dependant: SelectionMember
    dependant_file: ResolvedFile = field(repr=False)
    selection: SourceSelection = field(repr=False)
    location: CaptureLocation
    resolution: Resolution = field(repr=False)
    catalog: SourceResolver = field(repr=False)
    guards: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), repr=False)

    def __post_init__(self):
        self.settings.require_valid(require_store=False)
        if (self.selection.file is None or self.selection.kind not in {"file", "chunk", "family"}
                or self.dependant not in tuple(SelectionMember(SourceAddress(self.dependant_file.repository,
                      self.dependant_file.primary.root, self.dependant_file.primary.path, chunk.name), chunk)
                      for chunk in self.dependant_file.chunks)):
            _fail("insufficient_evidence")
        for repository in self.repositories:
            configured = self.settings.values["repos"].get(repository)
            if configured is None or not configured.get("enabled"):
                _fail("invalid_input")
        for file in (self.dependant_file, self.selection.file):
            if type(file.source) is not bytes or sha256(file.source).hexdigest() != file.snapshot_hash:
                _fail()
        if (not isinstance(self.catalog, SourceResolver) or self.catalog.settings.values != self.settings.values
                or not isinstance(self.resolution, Resolution) or self.resolution.state != "resolved"
                or self.resolution.selection != self.selection):
            _fail("invalid_input")
        selected = self.catalog.resolve(self.resolution.declaration, purpose="source")
        if selected != self.resolution or selected.selection != self.selection:
            _fail("insufficient_evidence")
        dependant = self.catalog.resolve(self.dependant.place.address, purpose="endpoint")
        if (dependant.state != "resolved" or dependant.selection.members != (self.dependant,)
                or dependant.selection.file != self.dependant_file):
            _fail("insufficient_evidence")
        canonical_json(self.guards)
        object.__setattr__(self, "guards", _frozen(self.guards))

    @property
    def repositories(self) -> tuple[str, ...]:
        return tuple(sorted({self.dependant.place.repository, self.selection.place.repository}))

    @property
    def addresses(self) -> tuple[str, ...]:
        return tuple(sorted({self.dependant.place.address, self.selection.place.address,
                             self.dependant_file.primary.address, self.selection.file.primary.address}))

    @property
    def identity(self) -> bytes:
        def member(item):
            chunk = item.chunk
            return {"id": chunk.identifier, "version": chunk.version, "place": _place(item.place),
                    "snapshot": chunk.snapshot_hash, "comparison": chunk.comparison,
                    "body": sha256(chunk.body).hexdigest() if chunk.body is not None else None,
                    "bodySpan": chunk.body_span, "span": chunk.span,
                    "kind": chunk.kind, "title": chunk.title, "family": chunk.family}
        def file_identity(file):
            return {'id': file.identifier, 'hash': file.snapshot_hash, 'primary': _place(file.primary),
                    'aliases': [_place(alias) for alias in file.aliases]}
        return canonical_json({"dependant": member(self.dependant), "dependantFile": file_identity(self.dependant_file),
                 "declaration": self.resolution.declaration,
                 "source": _place(self.selection.place), "sourceFile": file_identity(self.selection.file),
                 "selection": self.selection.kind, "members": [member(item) for item in self.selection.members],
                 "location": self.location.as_dict(), "guards": self.guards})


@dataclass(frozen=True)
class InheritanceInputs:
    """Fresh dependant observation; retained sources need not still exist.

    The original declaration is resolved only to guard current observation.
    It never supplies replacement before-text or authorizes a fresh capture.
    """

    settings: SettingsSnapshot = field(repr=False)
    dependant: SelectionMember
    dependant_file: ResolvedFile = field(repr=False)
    location: CaptureLocation
    resolution: Resolution = field(repr=False)
    catalog: SourceResolver = field(repr=False)
    guards: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), repr=False)

    def __post_init__(self):
        self.settings.require_valid(require_store=False)
        repository = self.dependant.place.repository
        configured = self.settings.values['repos'].get(repository)
        if (configured is None or not configured.get('enabled')
                or not isinstance(self.catalog, SourceResolver)
                or self.catalog.settings.values != self.settings.values
                or not isinstance(self.resolution, Resolution)
                or self.catalog.resolve(self.resolution.declaration, purpose='source') != self.resolution):
            _fail('invalid_input')
        dependant = self.catalog.resolve(self.dependant.place.address, purpose='endpoint')
        if (dependant.state != 'resolved' or dependant.selection.members != (self.dependant,)
                or dependant.selection.file != self.dependant_file):
            _fail('insufficient_evidence')
        canonical_json(self.guards)
        object.__setattr__(self, 'guards', _frozen(self.guards))

    @classmethod
    def from_pin(cls, inputs: PinInputs) -> InheritanceInputs:
        return cls(inputs.settings, inputs.dependant, inputs.dependant_file, inputs.location,
                   inputs.resolution, inputs.catalog, inputs.guards)

    @property
    def repositories(self) -> tuple[str, ...]:
        # Source rows are not touched: old evidence belongs to the dependant.
        return (self.dependant.place.repository,)

    @property
    def addresses(self) -> tuple[str, ...]:
        addresses = {self.dependant.place.address, self.dependant_file.primary.address}
        if self.resolution.selection is not None:
            addresses.add(self.resolution.selection.place.address)
        return tuple(sorted(addresses))

    @property
    def identity(self) -> bytes:
        chunk = self.dependant.chunk
        selection = self.resolution.selection
        return canonical_json({'dependant': {'id': chunk.identifier, 'version': chunk.version,
                  'place': _place(self.dependant.place), 'snapshot': chunk.snapshot_hash,
                  'comparison': chunk.comparison, 'body': sha256(chunk.body).hexdigest() if chunk.body is not None else None,
                  'bodySpan': chunk.body_span, 'span': chunk.span, 'kind': chunk.kind,
                  'title': chunk.title, 'family': chunk.family},
                  'file': {'id': self.dependant_file.identifier, 'hash': self.dependant_file.snapshot_hash,
                           'primary': _place(self.dependant_file.primary),
                           'aliases': [_place(alias) for alias in self.dependant_file.aliases]},
                  'resolution': {'declaration': self.resolution.declaration, 'state': self.resolution.state,
                                 'fault': self.resolution.fault, 'candidates': self.resolution.candidates,
                                 'count': self.resolution.candidate_count,
                                 'kind': None if selection is None else selection.kind,
                                 'place': None if selection is None else _place(selection.place),
                                 'fileHash': None if selection is None or selection.file is None else selection.file.snapshot_hash,
                                 'members': [] if selection is None else [
                                     {'id': member.chunk.identifier, 'version': member.chunk.version,
                                      'place': _place(member.place), 'hash': member.chunk.snapshot_hash}
                                     for member in selection.members]},
                  'location': self.location.as_dict(), 'guards': self.guards})


@dataclass
class _CheckedPin:
    connection: Any = field(repr=False)
    inputs: PinInputs | InheritanceInputs = field(repr=False)
    active: bool = True


@contextmanager
def checked_input_guard(connection, expected: PinInputs | InheritanceInputs,
                        reread: Callable[[], PinInputs | InheritanceInputs]) -> Iterator[_CheckedPin]:
    """Hold sorted writer/removal guards, then require a fresh exact observation.

    The callback uses the invocation settings snapshot and rereads disk/retained
    locations, indexed versions and typed resolution. Returning an old catalog
    is not a supported adapter.
    Its failure or mismatch occurs before any evidence write or transaction.
    """
    if not isinstance(expected, (PinInputs, InheritanceInputs)) or not callable(reread):
        _fail("invalid_input")
    with checked_store(connection), ExitStack() as stack:
        for repository in expected.repositories:
            stack.enter_context(operation_guard(connection, repository, "pass"))
        try:
            current = reread()
        except (EvidenceError, OSError, ValueError, TypeError, KeyError, psycopg.Error):
            raise EvidenceError("changed_since_ingest", expected.addresses) from None
        if (type(current) is not type(expected) or current.settings.values != expected.settings.values
                or current.identity != expected.identity):
            raise EvidenceError("changed_since_ingest", expected.addresses)
        token = _CheckedPin(connection, current)
        try:
            yield token
        finally:
            token.active = False


@contextmanager
def checked_transaction_input_guard(connection, expected: PinInputs | InheritanceInputs,
                                    reread: Callable[[], PinInputs | InheritanceInputs]) -> Iterator[_CheckedPin]:
    """Check prospective exact inputs inside an already guarded publication.

    The caller acquires every involved pass/removal guard before opening its
    transaction and freshly rereads physical or retained captures, settings and
    the prospective catalog here. No lock allocation, savepoint or prefix commit
    occurs. Cached observations remain a test seam, not a production rereader.
    """
    from ._locks import require_transaction_guards
    if not isinstance(expected, (PinInputs, InheritanceInputs)) or not callable(reread):
        _fail('invalid_input')
    require_transaction_guards(connection, expected.repositories)
    try:
        current = reread()
    except (EvidenceError, OSError, ValueError, TypeError, KeyError, psycopg.Error):
        raise EvidenceError('changed_since_ingest', expected.addresses) from None
    if (type(current) is not type(expected) or current.settings.values != expected.settings.values
            or current.identity != expected.identity):
        raise EvidenceError('changed_since_ingest', expected.addresses)
    token = _CheckedPin(connection, current)
    try:
        yield token
    finally:
        token.active = False


def _uuid(value) -> UUID:
    try:
        result = UUID(str(value))
        if str(result) != str(value):
            _fail("invalid_input")
        return result
    except (ValueError, TypeError, AttributeError):
        _fail("invalid_input")


def _validate_inheritance(previous_id: UUID, previous, baseline: BaselineCapture,
                          owner, refs, version) -> None:
    """Validate the old owning graph and its retained exact dependant only."""
    payload, manifest = baseline.manifest.payload, baseline.manifest.identifier
    expected_owner = (previous[0], "baseline", f"{previous_id}:{manifest}")
    expected_refs = ((0, None, manifest), *(
        (number, blob.evidence.hash, None) for number, blob in enumerate(baseline.snapshots, 1)))
    if (owner != expected_owner or refs != expected_refs
            or payload['dependantVersion'] != str(previous[1])
            or payload.get('ref') != previous[2] or payload['kind'] != previous[4]
            or version is None or str(version[0]) != payload['dependantVersion']
            or str(version[1]) != payload['dependantId'] or version[2] != payload['ownerRepository']):
        _fail()
    descriptor = SnapshotEvidence.from_record(json.loads(canonical_json(payload['dependant'])))
    source = exact_bytes(version[5])
    if version[4] != descriptor.hash or source != next(
            blob.source for blob in baseline.snapshots if blob.evidence.hash == descriptor.hash):
        _fail()
    descriptor.verify(source)
    comparison = version[6]
    if descriptor.comparison.kind == 'document_body':
        if not isinstance(comparison, Mapping) or set(comparison) != {'body', 'title'}:
            _fail()
        comparison = comparison['body']
    if ComparisonRecord.from_record(comparison) != descriptor.comparison:
        _fail()


def _inheritance_version(row):
    if row is None:
        return None
    return _frozen((*row[:5], exact_bytes(row[5]), row[6]))


class EvidenceStore:
    """Owner-scoped immutable blobs and version-scoped dependency pins."""

    def __init__(self, connection):
        self.connection = connection

    def _transaction_input(self, token: _CheckedPin) -> PinInputs | InheritanceInputs:
        """Require the caller's live guard and already-open native transaction.

        Acquire/recheck inputs before opening that transaction. These apply
        methods never allocate locks, open a savepoint, or commit a prefix.
        """
        if (not isinstance(token, _CheckedPin) or not token.active
                or token.connection is not self.connection
                or not isinstance(token.inputs, (PinInputs, InheritanceInputs))
                or self.connection.autocommit is not True
                or self.connection.info.transaction_status != pq.TransactionStatus.INTRANS):
            _fail('invalid_input')
        return token.inputs

    def _inheritance_file(self, baseline: BaselineCapture, version, inputs, *, lock: bool = False) -> bytes | None:
        """Read the prior complete file only for a changed code dependant."""
        descriptor = SnapshotEvidence.from_record(json.loads(canonical_json(baseline.manifest.payload['dependant'])))
        if (descriptor.comparison.kind != 'code_text'
                or descriptor.comparison == chunk_comparison(inputs.dependant.chunk)):
            return None
        if version is None or descriptor.file_hash is None:
            _fail('baseline_missing')
        row = self.connection.execute(_FILE_VERSION_SQL if lock else _FILE_VERSION_READ_SQL,
                                      (version[3], descriptor.file_hash)).fetchone()
        if row is None or row[0] != inputs.dependant.place.repository:
            _fail('baseline_missing')
        source = exact_bytes(row[1])
        if sha256(source).hexdigest() != descriptor.file_hash:
            _fail()
        return source

    def pin_in_transaction(self, token: _CheckedPin, *, dependency_id: UUID | str,
                           kind: Literal['declared', 'asserted', 'generated'], declaration: str,
                           captured_at: str,
                           authorization: Literal['initial_resolution', 'dependant_edit', 'owner_confirmation'],
                           expected_owner: UUID | str | None = None) -> str:
        """Apply exact capture with newly inserted versions in the caller's change.

        The same validation and owner CAS as pin() applies. An exception must
        escape the caller's atomic transaction to roll back its file/graph work.
        """
        self._transaction_input(token)
        return self._pin(token, dependency_id=dependency_id, kind=kind, declaration=declaration,
                         captured_at=captured_at, authorization=authorization, expected_owner=expected_owner)

    def inherit_in_transaction(self, token: _CheckedPin, *, previous_dependency: UUID | str,
                               dependency_id: UUID | str,
                               authorization: Literal['recognized_rename', 'normalized_equivalent_edit']) -> str:
        """Copy selected retained evidence inside the complete caller change.

        Lock and validate every previous owning reference, manifest, snapshot
        and exact dependant version before writing. Missing current sources
        never substitute bytes or prevent valid dependant-owned inheritance.
        """
        inputs = self._transaction_input(token)
        previous_id, identifier = _uuid(previous_dependency), _uuid(dependency_id)
        if previous_id == identifier or authorization not in {'recognized_rename', 'normalized_equivalent_edit'}:
            _fail('invalid_input')
        previous = self.connection.execute(_DEPENDENCY_SQL, (previous_id,)).fetchone()
        if previous is None or previous[5] is None or previous[0] != inputs.dependant.place.repository:
            _fail('baseline_missing')
        if previous[2] != inputs.resolution.declaration:
            _fail('invalid_input')
        if self.connection.execute(_DEPENDENCY_SQL, (identifier,)).fetchone() is not None:
            raise EvidenceError('changed_since_ingest', inputs.addresses)
        owner = self.connection.execute(_INHERITANCE_OWNER_SQL, (previous[5],)).fetchone()
        refs = tuple(self.connection.execute(_INHERITANCE_REFERENCES_SQL, (previous[5], previous[0])).fetchall())
        if not refs or refs[0][0:2] != (0, None) or refs[0][2] is None:
            _fail('baseline_missing')
        baseline = self._read_baseline(previous[0], refs[0][2], lock=True)
        version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL, (previous[1],)).fetchone())
        _validate_inheritance(previous_id, previous, baseline, owner, refs, version)
        previous_file = self._inheritance_file(baseline, version, inputs, lock=True)
        capture = inherit_baseline(baseline, inputs.dependant, inputs.dependant_file,
                                   authorization=authorization, previous_file_source=previous_file)
        new_owner = self._write(token, capture, f'{identifier}:{capture.manifest.identifier}', include_sources=False)
        selection = inputs.resolution.selection
        binding = (inputs.dependant.place.repository, inputs.dependant.chunk.version, previous[2],
                   selection.place.address if selection is not None else previous[3], previous[4])
        self.connection.execute(_INSERT_DEPENDENCY_SQL, (identifier, *binding, Jsonb({}), new_owner))
        return capture.manifest.identifier

    def _write(self, token: _CheckedPin, capture: BaselineCapture, identity: str, *, include_sources: bool = True) -> UUID:
        if not isinstance(token, _CheckedPin) or not token.active or token.connection is not self.connection:
            _fail("invalid_input")
        repository = capture.manifest.payload["ownerRepository"]
        if repository != token.inputs.dependant.place.repository:
            _fail("invalid_input")
        if (capture.manifest.payload["dependantId"] != token.inputs.dependant.chunk.identifier
                or capture.manifest.payload["dependantVersion"] != str(token.inputs.dependant.chunk.version)):
            _fail("invalid_input")
        bindings = [(token.inputs.dependant, token.inputs.dependant_file)]
        if include_sources:
            if not isinstance(token.inputs, PinInputs):
                _fail('invalid_input')
            bindings.extend((member, token.inputs.selection.file) for member in token.inputs.selection.members)
        versions = {}
        for item, file in bindings:
            binding = (item.chunk, item.place.repository, file.identifier)
            if item.chunk.version in versions and versions[item.chunk.version] != binding:
                _fail()
            versions[item.chunk.version] = binding
        files = [token.inputs.dependant_file]
        if include_sources:
            files.append(token.inputs.selection.file)
        for file in {item.identifier: item for item in files}.values():
            row = self.connection.execute(_FILE_VERSION_SQL, (file.identifier, file.snapshot_hash)).fetchone()
            if row is None or row[0] != file.repository or bytes(row[1]) != file.source:
                raise EvidenceError("changed_since_ingest", token.inputs.addresses)
        rows = self.connection.execute(_VERSIONS_SQL, (sorted(versions),)).fetchall()
        if len(rows) != len(versions):
            raise EvidenceError("changed_since_ingest", token.inputs.addresses)
        for number, identifier, owner, file_id, digest, text, comparison in rows:
            binding = versions.get(number)
            if binding is None:
                raise EvidenceError("changed_since_ingest", token.inputs.addresses)
            chunk, expected_repository, expected_file = binding
            if (str(identifier) != chunk.identifier or digest != chunk.snapshot_hash
                    or exact_bytes(text) != chunk.source
                    or _frozen(comparison) != chunk.comparison
                    or owner != expected_repository or str(file_id) != expected_file):
                raise EvidenceError("changed_since_ingest", token.inputs.addresses)
        for blob in capture.snapshots:
            metadata = {"schema": 1, "bytes": len(blob.source), "encoding": blob.evidence.encoding}
            self.connection.execute(_INSERT_SNAPSHOT_SQL, (repository, blob.evidence.hash, blob.source, Jsonb(metadata)))
            row = self.connection.execute(_SNAPSHOT_SQL, (repository, blob.evidence.hash)).fetchone()
            if row is None or bytes(row[0]) != blob.source or row[1] != metadata:
                _fail()
        manifest = capture.manifest
        self.connection.execute(_INSERT_MANIFEST_SQL, (repository, manifest.identifier, "baseline", manifest.canonical_bytes, Jsonb({"schema": 1})))
        row = self.connection.execute(_MANIFEST_SQL, (repository, manifest.identifier)).fetchone()
        if row is None or row[0] != "baseline" or bytes(row[1]) != manifest.canonical_bytes or row[2] != {"schema": 1}:
            _fail()
        owner_id = uuid4()
        self.connection.execute(_INSERT_OWNER_SQL, (owner_id, repository, "baseline", identity))
        owner_id = self.connection.execute(_OWNER_ID_SQL, (repository, "baseline", identity)).fetchone()[0]
        expected_refs = [(None, manifest.identifier)] + [(blob.evidence.hash, None) for blob in capture.snapshots]
        existing = self.connection.execute(_REFERENCES_SQL, (owner_id, repository)).fetchall()
        if existing:
            if existing != [(number, *ref) for number, ref in enumerate(expected_refs)]:
                _fail()
        else:
            for number, (snapshot_hash, manifest_hash) in enumerate(expected_refs):
                self.connection.execute(_INSERT_REFERENCE_SQL, (owner_id, repository, snapshot_hash, manifest_hash, number))
        return owner_id

    def pin(self, inputs: PinInputs, reread: Callable[[], PinInputs], *, dependency_id: UUID | str,
            kind: Literal["declared", "asserted", "generated"], declaration: str, captured_at: str,
            authorization: Literal["initial_resolution", "dependant_edit", "owner_confirmation"],
            expected_owner: UUID | str | None = None) -> str:
        """Atomic capture + link CAS; caller proves the MYC-D12 authorization."""
        self._pin_options(inputs, dependency_id, kind, declaration, authorization, expected_owner)
        with checked_input_guard(self.connection, inputs, reread) as token, atomic_transaction(self.connection):
            return self._pin(token, dependency_id=dependency_id, kind=kind, declaration=declaration,
                             captured_at=captured_at, authorization=authorization, expected_owner=expected_owner)

    @staticmethod
    def _pin_options(inputs, dependency_id, kind, declaration, authorization, expected_owner):
        """Refuse invalid capture arguments before taking guards or rereading."""
        identifier = _uuid(dependency_id)
        previous = _uuid(expected_owner) if expected_owner is not None else None
        if (authorization not in {"initial_resolution", "dependant_edit", "owner_confirmation"}
                or kind not in {"declared", "asserted", "generated"}
                or (authorization == "initial_resolution" and previous is not None)
                or not isinstance(inputs, PinInputs) or declaration != inputs.resolution.declaration):
            _fail("invalid_input")
        return identifier, previous

    def _pin(self, token: _CheckedPin, *, dependency_id, kind, declaration, captured_at,
             authorization, expected_owner=None) -> str:
        inputs = token.inputs
        identifier, previous = self._pin_options(inputs, dependency_id, kind, declaration, authorization, expected_owner)
        capture = capture_baseline(inputs.dependant.place.repository, inputs.dependant, inputs.dependant_file,
                   inputs.selection, kind=kind, declaration=declaration, captured_at=captured_at, location=inputs.location)
        old = self.connection.execute(_DEPENDENCY_SQL, (identifier,)).fetchone()
        binding = (inputs.dependant.place.repository, inputs.dependant.chunk.version, declaration, inputs.selection.place.address, kind)
        if old is not None and (tuple(old[:5]) != binding or old[5] != previous):
            raise EvidenceError("changed_since_ingest", inputs.addresses)
        if old is None and previous is not None:
            _fail("baseline_missing")
        owner = self._write(token, capture, f"{identifier}:{capture.manifest.identifier}")
        if old is None:
            self.connection.execute(_INSERT_DEPENDENCY_SQL, (identifier, *binding, Jsonb({}), owner))
        else:
            self.connection.execute(_UPDATE_DEPENDENCY_SQL, (owner, identifier))
            if previous is not None and previous != owner:
                self.connection.execute(_RELEASE_OWNER_SQL, (previous, binding[0]))
                self._collect(binding[0])
        return capture.manifest.identifier

    def _collect(self, repository: str) -> None:
        """Only called inside a completed writer's guarded atomic change."""
        self.connection.execute(_COLLECT_SNAPSHOTS_SQL, (repository,))
        self.connection.execute(_COLLECT_MANIFESTS_SQL, (repository,))

    def inherit_pin(self, inputs: PinInputs | InheritanceInputs,
                    reread: Callable[[], PinInputs | InheritanceInputs], *,
                    previous_dependency: UUID | str, dependency_id: UUID | str,
                    authorization: Literal["recognized_rename", "normalized_equivalent_edit"]) -> str:
        """Preserve an existing source baseline; never use today's source bytes."""
        previous_id, identifier = _uuid(previous_dependency), _uuid(dependency_id)
        if previous_id == identifier or authorization not in {"recognized_rename", "normalized_equivalent_edit"}:
            _fail("invalid_input")
        with checked_input_guard(self.connection, inputs, reread) as token:
            with read_snapshot(self.connection):
                previous = self.connection.execute(_DEPENDENCY_READ_SQL, (previous_id,)).fetchone()
                if previous is None or previous[5] is None or previous[0] != inputs.dependant.place.repository:
                    _fail("baseline_missing")
                if previous[2] != inputs.resolution.declaration:
                    _fail("invalid_input")
                refs = tuple(self.connection.execute(_REFERENCES_SQL, (previous[5], previous[0])).fetchall())
                if not refs or refs[0][0:2] != (0, None) or refs[0][2] is None:
                    _fail("baseline_missing")
                baseline_id = refs[0][2]
                baseline = self._read_baseline(previous[0], baseline_id)
                prior_owner = self.connection.execute(_INHERITANCE_OWNER_READ_SQL, (previous[5],)).fetchone()
                prior_version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_READ_SQL, (previous[1],)).fetchone())
                _validate_inheritance(previous_id, previous, baseline, prior_owner, refs, prior_version)
                prior_file = self._inheritance_file(baseline, prior_version, inputs)
            capture = inherit_baseline(baseline, inputs.dependant, inputs.dependant_file,
                                       authorization=authorization, previous_file_source=prior_file)
            with atomic_transaction(self.connection):
                observed = self.connection.execute(_DEPENDENCY_SQL, (previous_id,)).fetchone()
                if observed != previous or self.connection.execute(_DEPENDENCY_SQL, (identifier,)).fetchone() is not None:
                    raise EvidenceError("changed_since_ingest", inputs.addresses)
                locked_owner = self.connection.execute(_INHERITANCE_OWNER_SQL, (previous[5],)).fetchone()
                locked_refs = tuple(self.connection.execute(_INHERITANCE_REFERENCES_SQL, (previous[5], previous[0])).fetchall())
                locked_version = _inheritance_version(self.connection.execute(_INHERITANCE_VERSION_SQL, (previous[1],)).fetchone())
                if (locked_owner != prior_owner or locked_refs != refs or locked_version != prior_version):
                    raise EvidenceError("changed_since_ingest", inputs.addresses)
                _validate_inheritance(previous_id, previous, baseline, locked_owner, locked_refs, locked_version)
                locked_baseline = self._read_baseline(previous[0], baseline_id, lock=True)
                if locked_baseline != baseline:
                    raise EvidenceError('changed_since_ingest', inputs.addresses)
                if self._inheritance_file(locked_baseline, locked_version, inputs, lock=True) != prior_file:
                    raise EvidenceError('changed_since_ingest', inputs.addresses)
                owner = self._write(token, capture, f"{identifier}:{capture.manifest.identifier}", include_sources=False)
                current_selection = inputs.resolution.selection
                binding = (inputs.dependant.place.repository, inputs.dependant.chunk.version, previous[2],
                           current_selection.place.address if current_selection is not None else previous[3], previous[4])
                self.connection.execute(_INSERT_DEPENDENCY_SQL, (identifier, *binding, Jsonb({}), owner))
            return capture.manifest.identifier

    def restore_snapshot(self, inputs: PinInputs, reread: Callable[[], PinInputs], evidence: SnapshotEvidence,
                         candidates: tuple[bytes, ...]) -> bytes:
        """Restore only the exact descriptor; no manifest or pin is changed."""
        source = reconstruct(evidence, candidates)
        repository = inputs.dependant.place.repository
        metadata = {"schema": 1, "bytes": evidence.byte_count, "encoding": evidence.encoding}
        with checked_input_guard(self.connection, inputs, reread), atomic_transaction(self.connection):
            # A caller cannot introduce an unowned random blob as reconstruction.
            if not self.connection.execute(_OWNED_SNAPSHOT_SQL, (repository, evidence.hash)).fetchone():
                _fail("baseline_missing")
            self.connection.execute(_INSERT_SNAPSHOT_SQL, (repository, evidence.hash, source, Jsonb(metadata)))
            row = self.connection.execute(_SNAPSHOT_SQL, (repository, evidence.hash)).fetchone()
            if row is None or bytes(row[0]) != source or row[1] != metadata:
                _fail()
        return source

    def read_snapshot(self, repository: str, evidence: SnapshotEvidence, *, limit: int | None = None,
                      textual: bool = False) -> bytes:
        with checked_store(self.connection), read_snapshot(self.connection):
            row = self.connection.execute(_SNAPSHOT_SQL, (repository, evidence.hash)).fetchone()
        if row is None:
            _fail("baseline_missing")
        metadata = row[1]
        if metadata != {"schema": 1, "bytes": evidence.byte_count, "encoding": evidence.encoding}:
            _fail()
        return evidence.verify(bytes(row[0]), limit=limit, textual=textual)

    def read_baseline(self, repository: str, identifier: str) -> BaselineCapture:
        _hash(identifier)
        with checked_store(self.connection), read_snapshot(self.connection):
            return self._read_baseline(repository, identifier)

    def _read_baseline(self, repository: str, identifier: str, *, lock: bool = False) -> BaselineCapture:
        """Read within the caller's checked snapshot, without a nested transaction."""
        row = self.connection.execute(_MANIFEST_LOCK_SQL if lock else _MANIFEST_SQL, (repository, identifier)).fetchone()
        if row is None:
            _fail("baseline_missing")
        if row[0] != "baseline" or row[2] != {"schema": 1}:
            _fail()
        manifest = BaselineManifest.from_bytes(bytes(row[1]), identifier)
        if manifest.payload["ownerRepository"] != repository:
            _fail()
        descriptors = [manifest.payload["dependant"], *(item["evidence"] for item in manifest.payload["members"])]
        blobs = {}
        for value in descriptors:
            evidence = SnapshotEvidence.from_record(json.loads(canonical_json(value)))
            row = self.connection.execute(_SNAPSHOT_LOCK_SQL if lock else _SNAPSHOT_SQL, (repository, evidence.hash)).fetchone()
            if row is None:
                _fail("baseline_missing")
            if row[1] != {"schema": 1, "bytes": evidence.byte_count, "encoding": evidence.encoding}:
                _fail()
            blobs[evidence.hash] = Snapshot(evidence, bytes(row[0]))
        return BaselineCapture(manifest, tuple(blobs[key] for key in sorted(blobs)))


_VERSIONS_SQL = """SELECT v.id, c.id, c.repository, c.file_id, v.snapshot_hash, v.source_bytes, v.comparison
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id = v.chunk_id
WHERE v.id = ANY(%s) FOR SHARE OF v, c NOWAIT"""
_FILE_VERSION_READ_SQL = """SELECT f.repository, v.source_bytes FROM public.mycel_file_versions v
JOIN public.mycel_files f ON f.id = v.file_id
WHERE v.file_id = %s AND v.snapshot_hash = %s"""
_FILE_VERSION_SQL = _FILE_VERSION_READ_SQL + " FOR SHARE OF v, f NOWAIT"
_SNAPSHOT_SQL = "SELECT bytes, metadata FROM public.mycel_snapshots WHERE repository = %s AND hash = %s"
_MANIFEST_SQL = "SELECT kind, bytes, metadata FROM public.mycel_manifests WHERE repository = %s AND hash = %s"
_MANIFEST_LOCK_SQL = _MANIFEST_SQL + " FOR SHARE NOWAIT"
_SNAPSHOT_LOCK_SQL = _SNAPSHOT_SQL + " FOR SHARE NOWAIT"
_INSERT_SNAPSHOT_SQL = "INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING"
_INSERT_MANIFEST_SQL = "INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"
_INSERT_OWNER_SQL = "INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL) ON CONFLICT (repository,kind,identity) DO NOTHING"
_OWNER_ID_SQL = "SELECT id FROM public.mycel_evidence_owners WHERE repository = %s AND kind = %s AND identity = %s"
_REFERENCES_SQL = "SELECT ordinal,snapshot_hash,manifest_hash FROM public.mycel_evidence_references WHERE owner = %s AND repository = %s ORDER BY ordinal"
_INSERT_REFERENCE_SQL = "INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)"
_DEPENDENCY_SQL = "SELECT repository,dependant_version,declaration,source_place,kind,baseline_owner FROM public.mycel_dependencies WHERE id = %s FOR UPDATE NOWAIT"
_DEPENDENCY_READ_SQL = "SELECT repository,dependant_version,declaration,source_place,kind,baseline_owner FROM public.mycel_dependencies WHERE id = %s"
_INHERITANCE_OWNER_READ_SQL = "SELECT repository,kind,identity FROM public.mycel_evidence_owners WHERE id = %s"
_INHERITANCE_OWNER_SQL = _INHERITANCE_OWNER_READ_SQL + " FOR UPDATE NOWAIT"
_INHERITANCE_REFERENCES_SQL = _REFERENCES_SQL + " FOR SHARE NOWAIT"
_INHERITANCE_VERSION_READ_SQL = """SELECT v.id,c.id,c.repository,c.file_id,v.snapshot_hash,v.source_bytes,v.comparison
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE v.id=%s"""
_INHERITANCE_VERSION_SQL = _INHERITANCE_VERSION_READ_SQL + " FOR SHARE OF v,c NOWAIT"
_OWNED_SNAPSHOT_SQL = "SELECT 1 FROM public.mycel_evidence_references WHERE repository = %s AND snapshot_hash = %s LIMIT 1"
_INSERT_DEPENDENCY_SQL = "INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
_UPDATE_DEPENDENCY_SQL = "UPDATE public.mycel_dependencies SET baseline_owner = %s WHERE id = %s"
_RELEASE_OWNER_SQL = """DELETE FROM public.mycel_evidence_owners o
WHERE o.id = %s AND o.repository = %s AND o.kind = 'baseline' AND o.invocation IS NULL
AND NOT EXISTS (SELECT 1 FROM public.mycel_dependencies d WHERE d.baseline_owner = o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_relations r WHERE r.baseline_owner = o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_drifts d WHERE d.evidence_owner = o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_classification_work w WHERE w.evidence_owner = o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_verifications v WHERE v.evidence_owner = o.id)"""
_COLLECT_SNAPSHOTS_SQL = """DELETE FROM public.mycel_snapshots s WHERE s.repository = %s
AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r
                WHERE r.repository = s.repository AND r.snapshot_hash = s.hash)"""
_COLLECT_MANIFESTS_SQL = """DELETE FROM public.mycel_manifests m WHERE m.repository = %s
AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r
                WHERE r.repository = m.repository AND r.manifest_hash = m.hash)"""
