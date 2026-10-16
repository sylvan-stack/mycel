"""Private, immutable summary inputs and invocation-owned retained evidence.

This boundary records exactly what a configured command reads and prints. It
publishes no chunks, vectors or generated edges, and releases no evidence owner.
The summary lifecycle caller owns publication and eventual lease transfer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._embedding_plan import document_place_line
from ._evidence import (ComparisonRecord, EvidenceError, Snapshot, SnapshotEvidence,
                        canonical_json, chunk_comparison, snapshot)
from ._locks import (InvocationIdentity, atomic_transaction, invocation_is_live,
                     operation_guard, read_snapshot, require_transaction_guards)
from ._resolver import SelectionMember
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address
from ._store import checked_store, exact_bytes


PROTOCOL = "mycel-summary-generation-v1"
CUT_NOTICE = "\n\n[Mycel: source text cut at request limit]"
REQUEST_CHARACTERS = 48_000
_KIND = "summary_generation"


def _fail(status: str = "snapshot_corrupt") -> None:
    raise EvidenceError(status)


def _text(value: Any, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value) or "\0" in value:
        _fail()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _fail()
    return value


def _bytes(value: Any) -> bytes:
    if type(value) is not bytes:
        _fail()
    try:
        value.decode("utf-8")
    except UnicodeError:
        _fail("insufficient_evidence")
    return value


def _frozen(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if type(value) in {tuple, list}:
        return tuple(_frozen(item) for item in value)
    return value


def _place(place: SourceAddress) -> dict:
    try:
        if (not isinstance(place, SourceAddress) or place.root not in {"code", "artifact", "index"}
                or place.name is None or (place.root == "index" and place.path != "summaries")):
            _fail()
        return {"repository": place.repository, "root": place.root, "path": place.path,
                "name": place.name, "address": place.address}
    except (SourceAddressError, TypeError, ValueError):
        _fail()


def _read_place(value) -> SourceAddress:
    if not isinstance(value, dict) or set(value) != {"repository", "root", "path", "name", "address"}:
        _fail()
    try:
        place = parse_source_address(value["address"])
        if _place(place) != value:
            _fail()
        return place
    except (SourceAddressError, TypeError, ValueError):
        _fail()


def _cut(source: bytes, sent: bytes, cut: bool) -> None:
    _bytes(source)
    _bytes(sent)
    if type(cut) is not bool:
        _fail()
    if cut:
        notice = CUT_NOTICE.encode("utf-8")
        if not sent.endswith(notice):
            _fail()
        prefix = sent[:-len(notice)]
        if not prefix or prefix == source or not source.startswith(prefix):
            _fail()
    elif sent != source:
        _fail()


@dataclass(frozen=True)
class GenerationMember:
    member: SelectionMember
    sent_text: bytes = field(repr=False)
    cut: bool = False
    position: int | None = None

    def __post_init__(self):
        if not isinstance(self.member, SelectionMember):
            _fail("invalid_input")
        place, chunk = self.member.place, self.member.chunk
        _place(place)
        _text(chunk.identifier)
        if (type(chunk.version) is not int or chunk.version < 1 or place.name != chunk.name
                or chunk.kind not in {"document", "summary"}
                or (place.root == "index") != (chunk.kind == "summary")
                or sha256(_bytes(chunk.source)).hexdigest() != chunk.snapshot_hash):
            _fail()
        _cut(chunk.source, self.sent_text, self.cut)
        if chunk.kind == "document":
            chunk_comparison(chunk)
            if (chunk.body_span is None or chunk.body is None
                    or chunk.source[slice(*chunk.body_span)] != chunk.body):
                _fail()
        position = self.position
        if position is None:
            position = chunk.span[0] if chunk.span is not None else 0
        if type(position) is not int or position < 0:
            _fail()
        object.__setattr__(self, "position", position)

    @property
    def source(self) -> bytes:
        return self.member.chunk.source


def _render(instruction: bytes, task: bytes, members: list[dict], blobs: Mapping[str, bytes]) -> bytes:
    instruction_text, task_text = _bytes(instruction).decode().strip(), _bytes(task).decode().strip()
    if not instruction_text or task_text.count("$sections") != 1:
        _fail()
    sections = "\n\n---\n\n".join(
        document_place_line(member["place"]["path"], member["place"]["name"])
        + "\n" + _bytes(blobs[member["sent"]["hash"]]).decode()
        for member in members)
    return (instruction_text + "\n\n" + task_text.replace("$sections", sections)).encode("utf-8")


@dataclass(frozen=True)
class GenerationManifest:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = json.loads(canonical_json(self.payload))
        required = {"schema", "protocol", "ownerRepository", "request", "instruction", "task",
                    "command", "commandHash", "members"}
        if (not isinstance(value, dict) or not required <= set(value)
                or set(value) - required - {"promptProfile", "response"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or value["protocol"] != PROTOCOL):
            _fail()
        _text(value["ownerRepository"])
        if "promptProfile" in value:
            _text(value["promptProfile"])
        command = value["command"]
        if (not isinstance(command, list) or not command
                or any(not isinstance(argument, str) for argument in command)):
            _fail()
        for number, argument in enumerate(command):
            _text(argument, empty=number > 0)
        if value["commandHash"] != sha256(canonical_json(command)).hexdigest():
            _fail()
        for key in ("request", "instruction", "task", "response"):
            if key in value:
                descriptor = SnapshotEvidence.from_record(value[key])
                if descriptor.encoding != "utf-8" or descriptor != snapshot_shape(descriptor):
                    _fail()
        members = value["members"]
        if not isinstance(members, list) or not members:
            _fail()
        identities, places, order = set(), set(), []
        for member in members:
            if (not isinstance(member, dict) or set(member) != {
                    "id", "version", "place", "position", "kind", "title", "comparison", "source", "sent", "cut"}):
                _fail()
            place = _read_place(member["place"])
            _text(member["id"])
            if (type(member["version"]) is not int or member["version"] < 1
                    or type(member["position"]) is not int or member["position"] < 0
                    or member["kind"] not in {"document", "summary"}
                    or (place.root == "index") != (member["kind"] == "summary")
                    or type(member["cut"]) is not bool
                    or member["id"] in identities or place.address in places
                    or not isinstance(member["comparison"], dict)):
                _fail()
            if member["title"] is not None:
                _text(member["title"], empty=True)
            source = SnapshotEvidence.from_record(member["source"])
            sent = SnapshotEvidence.from_record(member["sent"])
            if source.encoding != "utf-8" or sent.encoding != "utf-8" or sent != snapshot_shape(sent):
                _fail()
            if (source.place is not None or source.file_hash is not None or source.span is not None):
                _fail()
            if member["kind"] == "document":
                comparison = member["comparison"]
                if set(comparison) != {"body", "title"}:
                    _fail()
                body = ComparisonRecord.from_record(comparison["body"])
                title = ComparisonRecord.from_record(comparison["title"])
                if (body.kind != "document_body" or title.kind != "document_title"
                        or source.comparison != body):
                    _fail()
                title.verify(member["title"] or "")
            elif source.comparison is not None:
                _fail()
            identities.add(member["id"])
            places.add(place.address)
            order.append((place.root, place.path, member["position"], place.address, member["id"]))
        if order != sorted(order):
            _fail()
        if any(member["cut"] for member in members) and len(members) != 1:
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def identifier(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()

    @classmethod
    def from_bytes(cls, source: bytes, identifier: str) -> GenerationManifest:
        if type(source) is not bytes or sha256(source).hexdigest() != identifier:
            _fail()
        try:
            result = cls(json.loads(source))
        except (ValueError, UnicodeError, TypeError):
            _fail()
        if result.canonical_bytes != source:
            _fail()
        return result


def snapshot_shape(descriptor: SnapshotEvidence) -> SnapshotEvidence:
    """The request, prompt, sent text and response descriptors have no extraction."""
    return SnapshotEvidence(descriptor.hash, descriptor.byte_count, "utf-8")


def _descriptors(manifest: GenerationManifest) -> tuple[SnapshotEvidence, ...]:
    payload = json.loads(manifest.canonical_bytes)
    values = [payload[key] for key in ("request", "instruction", "task", "response") if key in payload]
    values.extend(member[key] for member in payload["members"] for key in ("source", "sent"))
    return tuple(SnapshotEvidence.from_record(value) for value in values)


@dataclass(frozen=True)
class GenerationCapture:
    manifest: GenerationManifest
    snapshots: tuple[Snapshot, ...] = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.manifest, GenerationManifest) or type(self.snapshots) is not tuple
                or any(not isinstance(blob, Snapshot) for blob in self.snapshots)):
            _fail()
        blobs = {blob.evidence.hash: blob.source for blob in self.snapshots}
        if len(blobs) != len(self.snapshots):
            _fail()
        descriptors = _descriptors(self.manifest)
        if set(blobs) != {descriptor.hash for descriptor in descriptors}:
            _fail()
        for descriptor in descriptors:
            descriptor.verify(blobs[descriptor.hash], textual=True)
        value = json.loads(self.manifest.canonical_bytes)
        for member in value["members"]:
            _cut(blobs[member["source"]["hash"]], blobs[member["sent"]["hash"]], member["cut"])
        request = blobs[value["request"]["hash"]]
        if (request != _render(blobs[value["instruction"]["hash"]], blobs[value["task"]["hash"]],
                              value["members"], blobs)
                or len(request.decode("utf-8")) > REQUEST_CHARACTERS):
            _fail()

    def with_response(self, response: bytes) -> GenerationCapture:
        _bytes(response)
        if not response.decode("utf-8").strip():
            _fail("invalid_input")
        value = json.loads(self.manifest.canonical_bytes)
        blob = snapshot(response)
        if "response" in value and value["response"] != blob.evidence.as_dict():
            _fail("invalid_input")
        value["response"] = blob.evidence.as_dict()
        snapshots = {item.evidence.hash: item for item in self.snapshots}
        snapshots.setdefault(blob.evidence.hash, blob)
        return GenerationCapture(GenerationManifest(value), tuple(snapshots[key] for key in sorted(snapshots)))


def capture_generation(owner_repository: str, members: tuple[GenerationMember, ...], *, request: bytes,
                       instruction: bytes, task: bytes, command: tuple[str, ...],
                       prompt_profile: str | None = None, response: bytes | None = None) -> GenerationCapture:
    """Capture a fully rendered request; retain uncut sources and exact sent text."""
    if (type(members) is not tuple or not members or any(not isinstance(item, GenerationMember) for item in members)
            or type(command) is not tuple):
        _fail("invalid_input")
    blobs: dict[str, Snapshot] = {}

    def remember(source, **options):
        blob = snapshot(_bytes(source), **options)
        blobs.setdefault(blob.evidence.hash, snapshot(blob.source))
        return blob.evidence.as_dict()

    value = {"schema": 1, "protocol": PROTOCOL, "ownerRepository": owner_repository,
             "request": remember(request), "instruction": remember(instruction), "task": remember(task),
             "command": list(command), "commandHash": sha256(canonical_json(command)).hexdigest(), "members": []}
    if prompt_profile is not None:
        value["promptProfile"] = prompt_profile
    for item in members:
        member, chunk = item.member, item.member.chunk
        comparison = chunk_comparison(chunk) if chunk.kind == "document" else None
        value["members"].append({"id": chunk.identifier, "version": chunk.version, "place": _place(member.place),
               "position": item.position, "kind": chunk.kind, "title": chunk.title,
               "comparison": json.loads(canonical_json(chunk.comparison)),
               "source": remember(chunk.source, comparison=comparison,
                                  comparison_span=chunk.body_span if comparison is not None else None),
               "sent": remember(item.sent_text), "cut": item.cut})
    capture = GenerationCapture(GenerationManifest(value), tuple(blobs[key] for key in sorted(blobs)))
    return capture.with_response(response) if response is not None else capture


@dataclass(frozen=True)
class GenerationLease:
    owner_id: UUID
    repository: str
    invocation: InvocationIdentity
    request_manifest: str
    manifest_hash: str
    request_identity: str | None = None

    @property
    def identity(self):
        """A private tree gives each actual request its own invocation-owned lease."""
        base = f"{self.invocation.id}:{self.request_manifest}"
        if self.request_identity is None:
            return base
        try:
            prefix, suffix = self.request_identity.rsplit(':', 1)
            if prefix != base or str(UUID(suffix)) != suffix:
                _fail('invalid_input')
        except (AttributeError, TypeError, ValueError):
            _fail('invalid_input')
        return self.request_identity


_BOUND_SQL = """SELECT EXISTS (
    SELECT 1 FROM public.mycel_invocations i
    JOIN pg_catalog.pg_stat_activity a ON a.pid=i.backend_pid AND a.backend_start=i.backend_start
    JOIN public.mycel_store s ON s.singleton=true AND s.index_generation=i.index_generation
    WHERE i.id=%s AND i.liveness_key=%s AND i.backend_pid=%s AND i.backend_start=%s
      AND i.index_generation=%s AND a.pid=pg_catalog.pg_backend_pid()
)"""
_REPOSITORY_SQL = "SELECT repository FROM public.mycel_repository_state WHERE repository=%s FOR SHARE NOWAIT"
_VERSIONS_SQL = """SELECT v.id,c.id,c.repository,c.kind,v.snapshot_hash,v.source_bytes,v.comparison,v.metadata
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
WHERE v.id=ANY(%s) FOR SHARE OF v,c NOWAIT"""
_BINDINGS_SQL = """SELECT l.kind,l.metadata,f.root,f.path,fl.metadata
FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id
LEFT JOIN public.mycel_files f ON f.id=c.file_id
LEFT JOIN public.mycel_file_locations fl ON fl.id=l.file_location
WHERE v.id=%s AND l.kind IN ('disk','index')"""
_ALIASES_SQL = """SELECT a.root,a.path FROM public.mycel_file_aliases a
JOIN public.mycel_chunks c ON c.file_id=a.file_id
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id WHERE v.id=%s"""
_SNAPSHOT_SQL = "SELECT bytes,metadata FROM public.mycel_snapshots WHERE repository=%s AND hash=%s"
_MANIFEST_SQL = "SELECT kind,bytes,metadata FROM public.mycel_manifests WHERE repository=%s AND hash=%s"
_INSERT_SNAPSHOT_SQL = "INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING"
_INSERT_MANIFEST_SQL = "INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"
_INSERT_OWNER_SQL = """INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)
ON CONFLICT (repository,kind,identity) DO NOTHING"""
_OWNER_SQL = """SELECT id,repository,kind,identity,invocation FROM public.mycel_evidence_owners
WHERE repository=%s AND kind=%s AND identity=%s FOR UPDATE NOWAIT"""
_REFERENCES_SQL = """SELECT ordinal,snapshot_hash,manifest_hash FROM public.mycel_evidence_references
WHERE owner=%s AND repository=%s ORDER BY ordinal"""
_INSERT_REFERENCE_SQL = "INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)"


class GenerationEvidenceStore:
    def __init__(self, connection):
        self.connection = connection

    def _invocation(self, invocation: InvocationIdentity) -> None:
        if not isinstance(invocation, InvocationIdentity):
            _fail("invalid_input")
        row = self.connection.execute(_BOUND_SQL, (invocation.id, invocation.liveness_key,
             invocation.backend_pid, invocation.backend_start, invocation.index_generation)).fetchone()
        if row != (True,) or not invocation_is_live(self.connection, invocation):
            _fail("invalid_input")

    def _inputs(self, capture: GenerationCapture) -> None:
        payload = capture.manifest.payload
        repository = payload["ownerRepository"]
        if self.connection.execute(_REPOSITORY_SQL, (repository,)).fetchone() != (repository,):
            _fail("invalid_input")
        members = {member["version"]: member for member in payload["members"]}
        if len(members) != len(payload["members"]):
            _fail("invalid_input")
        rows = self.connection.execute(_VERSIONS_SQL, (sorted(members),)).fetchall()
        if len(rows) != len(members):
            _fail("inputs_changed")
        blobs = {blob.evidence.hash: blob.source for blob in capture.snapshots}
        for version, identifier, repository, kind, digest, source, comparison, metadata in rows:
            member = members.get(version)
            if (member is None or str(identifier) != member["id"] or repository != member["place"]["repository"]
                    or kind != member["kind"] or digest != member["source"]["hash"]
                    or exact_bytes(source) != blobs[member["source"]["hash"]]
                    or canonical_json(comparison) != canonical_json(member["comparison"])):
                _fail("inputs_changed")
            bindings = self.connection.execute(_BINDINGS_SQL, (version,)).fetchall()
            aliases = self.connection.execute(_ALIASES_SQL, (version,)).fetchall()
            matched = False
            for location, located, root, path, file_metadata in bindings:
                if not isinstance(located, dict) or not isinstance(metadata, dict):
                    _fail()
                current = {**metadata, **located}
                if location == "index":
                    addresses = [("index", current.get("path"))]
                elif isinstance(file_metadata, dict) and "aliases" in file_metadata:
                    addresses = [(alias.get("root"), alias.get("path")) for alias in file_metadata["aliases"]]
                else:
                    addresses = [(root, path), *aliases]
                if ((member["place"]["root"], member["place"]["path"]) in addresses
                        and current.get("name") == member["place"]["name"]
                        and (kind != "document" or current.get("title") == member["title"])
                        and (kind != "document" or current.get("span", {}).get("start") == member["position"])):
                    matched = True
            if not matched:
                _fail("inputs_changed")

    def _write(self, capture: GenerationCapture) -> None:
        repository = capture.manifest.payload["ownerRepository"]
        for blob in capture.snapshots:
            metadata = {"schema": 1, "bytes": len(blob.source), "encoding": "utf-8"}
            self.connection.execute(_INSERT_SNAPSHOT_SQL, (repository, blob.evidence.hash, blob.source, Jsonb(metadata)))
            row = self.connection.execute(_SNAPSHOT_SQL, (repository, blob.evidence.hash)).fetchone()
            if row is None or exact_bytes(row[0]) != blob.source or row[1] != metadata:
                _fail()
        manifest = capture.manifest
        metadata = {"schema": 1, "protocol": PROTOCOL}
        self.connection.execute(_INSERT_MANIFEST_SQL,
             (repository, manifest.identifier, _KIND, manifest.canonical_bytes, Jsonb(metadata)))
        row = self.connection.execute(_MANIFEST_SQL, (repository, manifest.identifier)).fetchone()
        if row is None or row[0] != _KIND or exact_bytes(row[1]) != manifest.canonical_bytes or row[2] != metadata:
            _fail()

    @staticmethod
    def _refs(capture: GenerationCapture):
        return [(None, capture.manifest.identifier)] + [(blob.evidence.hash, None) for blob in capture.snapshots]

    def retain(self, invocation: InvocationIdentity, capture: GenerationCapture) -> GenerationLease:
        """Commit the request's private owning lease before a model is started."""
        if not isinstance(capture, GenerationCapture) or "response" in capture.manifest.payload:
            _fail("invalid_input")
        repository = capture.manifest.payload["ownerRepository"]
        with checked_store(self.connection), operation_guard(self.connection, repository, "pass"), atomic_transaction(self.connection):
            return self._retain_in_transaction(invocation, capture)

    def retain_in_transaction(self, invocation: InvocationIdentity, capture: GenerationCapture) -> GenerationLease:
        """Adopt exact prepared inputs inside a caller-owned publication transaction.

        This starts no writer. The caller holds checked_store and every input
        repository's pass guard; successful prospective lower summaries can be
        members of a preproduced higher request. External generation and hidden
        staging remain the summary lifecycle caller's responsibility.
        """
        if not isinstance(capture, GenerationCapture) or "response" in capture.manifest.payload:
            _fail("invalid_input")
        repositories = {capture.manifest.payload["ownerRepository"],
                        *(member["place"]["repository"] for member in capture.manifest.payload["members"])}
        require_transaction_guards(self.connection, tuple(sorted(repositories)))
        return self._retain_in_transaction(invocation, capture)

    def _retain_in_transaction(self, invocation, capture):
        repository, digest = capture.manifest.payload["ownerRepository"], capture.manifest.identifier
        self._invocation(invocation)
        self._inputs(capture)
        self._write(capture)
        identity = f"{invocation.id}:{digest}"
        self.connection.execute(_INSERT_OWNER_SQL, (uuid4(), repository, _KIND, identity, invocation.id))
        row = self.connection.execute(_OWNER_SQL, (repository, _KIND, identity)).fetchone()
        if row is None or row[1:] != (repository, _KIND, identity, invocation.id):
            _fail()
        owner = row[0]
        refs = self._refs(capture)
        existing = self.connection.execute(_REFERENCES_SQL, (owner, repository)).fetchall()
        expected = [(number, *ref) for number, ref in enumerate(refs)]
        if existing and existing != expected:
            _fail()
        if not existing:
            for number, (snapshot_hash, manifest_hash) in enumerate(refs):
                self.connection.execute(_INSERT_REFERENCE_SQL, (owner, repository, snapshot_hash, manifest_hash, number))
        return GenerationLease(owner, repository, invocation, digest, digest)

    def retain_response(self, invocation: InvocationIdentity, lease: GenerationLease, response: bytes) -> GenerationLease:
        """Attach an immutable response capture to this exact live request lease."""
        if not isinstance(lease, GenerationLease) or invocation != lease.invocation:
            _fail("invalid_input")
        with checked_store(self.connection), operation_guard(self.connection, lease.repository, "pass"), atomic_transaction(self.connection):
            return self._retain_response_in_transaction(invocation, lease, response)

    def retain_response_in_transaction(self, invocation: InvocationIdentity, lease: GenerationLease,
                                       response: bytes) -> GenerationLease:
        """Adopt an already produced complete response with no call or commit."""
        if not isinstance(lease, GenerationLease) or invocation != lease.invocation:
            _fail("invalid_input")
        require_transaction_guards(self.connection, (lease.repository,))
        return self._retain_response_in_transaction(invocation, lease, response)

    def _retain_response_in_transaction(self, invocation, lease, response):
        self._invocation(invocation)
        identity = lease.identity
        owner = self.connection.execute(_OWNER_SQL, (lease.repository, _KIND, identity)).fetchone()
        if owner != (lease.owner_id, lease.repository, _KIND, identity, invocation.id):
            _fail("invalid_input")
        capture = self._read(lease.repository, lease.manifest_hash)
        refs = self.connection.execute(_REFERENCES_SQL, (lease.owner_id, lease.repository)).fetchall()
        hashes = {(snapshot_hash, manifest_hash) for _, snapshot_hash, manifest_hash in refs}
        if (not refs or [number for number, _, _ in refs] != list(range(len(refs)))
                or len(hashes) != len(refs)
                or hashes != ({(None, lease.request_manifest)} | set(self._refs(capture)))):
            _fail()
        completed = capture.with_response(response)
        self._write(completed)
        for snapshot_hash, manifest_hash in self._refs(completed):
            if (snapshot_hash, manifest_hash) not in hashes:
                self.connection.execute(_INSERT_REFERENCE_SQL,
                    (lease.owner_id, lease.repository, snapshot_hash, manifest_hash, len(refs)))
                refs.append((len(refs), snapshot_hash, manifest_hash))
                hashes.add((snapshot_hash, manifest_hash))
        return GenerationLease(lease.owner_id, lease.repository, invocation, lease.request_manifest,
                               completed.manifest.identifier, lease.request_identity)

    def _read(self, repository: str, identifier: str) -> GenerationCapture:
        row = self.connection.execute(_MANIFEST_SQL, (repository, identifier)).fetchone()
        if row is None:
            _fail("baseline_missing")
        if row[0] != _KIND or row[2] != {"schema": 1, "protocol": PROTOCOL}:
            _fail()
        manifest = GenerationManifest.from_bytes(exact_bytes(row[1]), identifier)
        if manifest.payload["ownerRepository"] != repository:
            _fail()
        blobs = {}
        for descriptor in _descriptors(manifest):
            row = self.connection.execute(_SNAPSHOT_SQL, (repository, descriptor.hash)).fetchone()
            if row is None:
                _fail("baseline_missing")
            if row[1] != {"schema": 1, "bytes": descriptor.byte_count, "encoding": "utf-8"}:
                _fail()
            descriptor.verify(exact_bytes(row[0]), textual=True)
            blobs.setdefault(descriptor.hash, Snapshot(snapshot_shape(descriptor), exact_bytes(row[0])))
        return GenerationCapture(manifest, tuple(blobs[key] for key in sorted(blobs)))

    def read(self, repository: str, identifier: str) -> GenerationCapture:
        with checked_store(self.connection), read_snapshot(self.connection):
            return self._read(repository, identifier)
