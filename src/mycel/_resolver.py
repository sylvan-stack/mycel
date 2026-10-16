"""One immutable, location-specific catalog for natural source selections.

Resolution never guesses a physical root, chooses another branch, expands a
mutation endpoint, or treats disabled stored text as eligible. The PostgreSQL
reader retains complete file bytes and exact located chunk texts. Callers that
pin evidence must additionally hold operation locks and reread current inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import re
from contextlib import nullcontext
from types import MappingProxyType
from typing import Any
from typing import Literal

import psycopg
from psycopg import pq

from ._errors import MycelError
from ._locks import read_snapshot, require_transaction_guards
from ._settings import SettingsSnapshot, _freeze
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address
from ._store import checked_store, exact_bytes, exact_text


_CLASS_CONTINUATION = re.compile(r".+\.<(?:end|before [^\r\n]+)>(?::(?:[2-9]|[1-9][0-9]+))?\Z")


@dataclass(frozen=True)
class ResolvedChunk:
    identifier: str
    version: int
    name: str
    kind: str
    source: bytes = field(repr=False)
    snapshot_hash: str
    span: tuple[int, int] | None = None
    title: str | None = None
    family: str | None = None
    comparison: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    body: bytes | None = field(default=None, repr=False)
    body_span: tuple[int, int] | None = None

    def __post_init__(self):
        if isinstance(self.comparison, Mapping):
            object.__setattr__(self, "comparison", _freeze(dict(self.comparison)))


@dataclass(frozen=True)
class ResolvedFile:
    identifier: str
    repository: str
    primary: SourceAddress
    aliases: tuple[SourceAddress, ...]
    source: bytes = field(repr=False)
    snapshot_hash: str
    chunks: tuple[ResolvedChunk, ...]
    recognized_moves: tuple[SourceAddress, ...] = ()


@dataclass(frozen=True)
class SelectionMember:
    place: SourceAddress
    chunk: ResolvedChunk


@dataclass(frozen=True)
class SourceSelection:
    kind: Literal["file", "chunk", "family", "index"]
    place: SourceAddress
    file: ResolvedFile | None
    members: tuple[SelectionMember, ...]


@dataclass(frozen=True)
class Resolution:
    declaration: str
    state: Literal["resolved", "unresolved", "invalid"]
    selection: SourceSelection | None = None
    fault: str | None = None
    candidates: tuple[str, ...] = ()
    candidate_count: int = 0


def _bad_catalog() -> MycelError:
    return MycelError("store_format", "The indexed source catalog has incompatible exact inputs.")


def _exact(source: bytes, digest: str) -> bool:
    return type(source) is bytes and sha256(source).hexdigest() == digest


def _validate_chunk(chunk: ResolvedChunk) -> None:
    if (not isinstance(chunk.identifier, str) or not chunk.identifier
            or type(chunk.version) is not int or chunk.version < 1
            or not isinstance(chunk.name, str) or not chunk.name
            or not isinstance(chunk.kind, str) or not chunk.kind
            or (chunk.title is not None and not isinstance(chunk.title, str))
            or (chunk.family is not None and (not isinstance(chunk.family, str) or not chunk.family))
            or not isinstance(chunk.comparison, Mapping)
            or (chunk.body is not None and type(chunk.body) is not bytes)
            or not _exact(chunk.source, chunk.snapshot_hash)):
        raise _bad_catalog()
    if chunk.body_span is not None:
        if (type(chunk.body_span) is not tuple or len(chunk.body_span) != 2
                or any(type(offset) is not int for offset in chunk.body_span)
                or not 0 <= chunk.body_span[0] <= chunk.body_span[1] <= len(chunk.source)
                or chunk.source[slice(*chunk.body_span)] != chunk.body):
            raise _bad_catalog()


def _ambiguous(declaration: str, fault: str, candidates) -> Resolution:
    ordered = tuple(sorted(set(candidates)))
    return Resolution(declaration, "unresolved", fault=fault, candidates=ordered[:20],
                      candidate_count=len(ordered))


class SourceResolver:
    """A finite retained catalog, suitable for every source/ref/read consumer.

    `purpose='source'` expands classes into their recorded family;
    `purpose='read'` selects their header; `purpose='endpoint'` requires exactly
    one chunk and rejects a file or index namespace before any mutation.
    """

    def __init__(self, settings: SettingsSnapshot, files: tuple[ResolvedFile, ...], *,
                 index: tuple[tuple[SourceAddress, ResolvedChunk], ...] = ()):
        settings.require_valid(require_store=False)
        self.settings = settings
        self.files = tuple(files)
        self.index = tuple(index)
        identifiers = set()
        for file in self.files:
            if (file.identifier in identifiers or file.primary.repository != file.repository
                    or file.primary.root not in {"code", "artifact"} or file.primary.name is not None
                    or not _exact(file.source, file.snapshot_hash) or not file.aliases
                    or file.primary not in file.aliases or len(set(file.aliases)) != len(file.aliases)):
                raise _bad_catalog()
            identifiers.add(file.identifier)
            for alias in file.aliases:
                try:
                    alias.address
                except SourceAddressError:
                    raise _bad_catalog() from None
                if (alias.repository != file.repository or alias.root not in {"code", "artifact"}
                        or alias.name is not None):
                    raise _bad_catalog()
            for prior in file.recognized_moves:
                if (prior.repository != file.repository or prior.root not in {"code", "artifact"}
                        or prior.name is not None):
                    raise _bad_catalog()
                try:
                    prior.address
                except SourceAddressError:
                    raise _bad_catalog() from None
            chunk_ids, names = set(), set()
            for chunk in file.chunks:
                _validate_chunk(chunk)
                if (not isinstance(chunk.name, str) or not chunk.name or chunk.name in names
                        or chunk.identifier in chunk_ids or type(chunk.version) is not int or chunk.version < 1
                        or not _exact(chunk.source, chunk.snapshot_hash)):
                    raise _bad_catalog()
                chunk_ids.add(chunk.identifier)
                names.add(chunk.name)
                if chunk.span is not None:
                    start, end = chunk.span
                    if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(file.source)
                            or file.source[start:end] != chunk.source):
                        raise _bad_catalog()
                try:
                    self._place(file, chunk).address
                except SourceAddressError:
                    raise _bad_catalog() from None
        for place, chunk in self.index:
            _validate_chunk(chunk)
            if (place.root != "index" or place.name != chunk.name
                    or not _exact(chunk.source, chunk.snapshot_hash)):
                raise _bad_catalog()
            try:
                place.address
            except SourceAddressError:
                raise _bad_catalog() from None

    @staticmethod
    def _place(file: ResolvedFile, chunk: ResolvedChunk) -> SourceAddress:
        return SourceAddress(file.repository, file.primary.root, file.primary.path, chunk.name)

    @classmethod
    def _members(cls, file: ResolvedFile, chunks: tuple[ResolvedChunk, ...]) -> tuple[SelectionMember, ...]:
        return tuple(sorted((SelectionMember(cls._place(file, chunk), chunk) for chunk in chunks),
                            key=lambda item: (item.place.address, item.chunk.identifier)))

    def resolve(self, declaration: str, *, purpose: Literal["source", "read", "endpoint"] = "source") -> Resolution:
        if purpose not in {"source", "read", "endpoint"}:
            raise MycelError("invalid_input", "The source selection purpose is unsupported.")
        try:
            address = parse_source_address(declaration)
        except SourceAddressError:
            return Resolution(declaration, "invalid", fault="invalid_ref")
        repositories = self.settings.values["repos"]
        if address.repository not in repositories:
            return Resolution(declaration, "invalid", fault="unregistered_repository")
        if not repositories[address.repository]["enabled"]:
            return Resolution(declaration, "invalid", fault="disabled_repository")
        if address.root == "index":
            if purpose != "read":
                # Generic legacy index rows retain their original ineligibility
                # fault. A published typed namespace is generated text even
                # when the requested readable section no longer exists.
                generated = any(place.repository == address.repository and place.path == address.path
                                and chunk.kind in {"summary", "overview"} for place, chunk in self.index)
                return Resolution(declaration, "invalid",
                                  fault="generated_text" if generated else "ineligible_index")
            matches = tuple((place, chunk) for place, chunk in self.index
                            if place.repository == address.repository and place.path == address.path
                            and (address.name is None or place.name == address.name))
            if not matches:
                return Resolution(declaration, "unresolved", fault="missing_name" if address.name else "missing_file")
            if address.name is not None and len(matches) != 1:
                return _ambiguous(declaration, "ambiguous_name", (place.address for place, _ in matches))
            members = tuple(SelectionMember(place, chunk) for place, chunk in sorted(
                matches, key=lambda item: (item[0].address, item[1].identifier)))
            return Resolution(declaration, "resolved", SourceSelection("index", address, None, members))
        files = tuple(file for file in self.files if file.repository == address.repository and any(
            alias.path == address.path and (address.root is None or alias.root == address.root)
            for alias in file.aliases))
        if purpose == "read" and address.root is None and files and address.path in {"summaries", "overview"}:
            indexed = tuple(place for place, _chunk in self.index
                            if place.repository == address.repository and place.path == address.path)
            if indexed:
                # A name cannot break a namespace/path tie. Legacy generated
                # aliases are usable only without a colliding physical file.
                candidates = tuple(place.address for place in indexed
                                   if address.name is None or place.name == address.name)
                if not candidates:
                    candidates = (SourceAddress(address.repository, "index", address.path).address,)
                return _ambiguous(declaration, "ambiguous_path",
                                  (*candidates, *(file.primary.address for file in files)))
        if not files:
            if address.root is None and address.path in {"summaries", "overview"} and any(
                    place.repository == address.repository and place.path == address.path for place, _ in self.index):
                qualified = SourceAddress(address.repository, "index", address.path, address.name)
                return replace_resolution(self.resolve(qualified.address, purpose=purpose), declaration)
            return Resolution(declaration, "unresolved", fault="missing_file")
        if len(files) != 1:
            return _ambiguous(declaration, "ambiguous_path", (file.primary.address for file in files))
        file = files[0]
        if address.name is None:
            if purpose == "endpoint":
                return Resolution(declaration, "invalid", fault="one_chunk_required")
            return Resolution(declaration, "resolved", SourceSelection("file", file.primary, file,
                                                                        self._members(file, file.chunks)))
        # Exact canonical names take precedence. Bare heading/method shortcuts
        # are accepted only when no canonical name matches and they are unique.
        matches = tuple(chunk for chunk in file.chunks if chunk.name == address.name)
        if not matches:
            matches = tuple(chunk for chunk in file.chunks if chunk.title == address.name or
                            (chunk.kind == "method" and chunk.name.rsplit(".", 1)[-1] == address.name))
        if not matches:
            return Resolution(declaration, "unresolved", fault="missing_name")
        if len(matches) != 1:
            return _ambiguous(declaration, "ambiguous_name", (self._place(file, chunk).address for chunk in matches))
        chunk = matches[0]
        kind = "chunk"
        chosen = (chunk,)
        # Nested headers belong to their containing class and still introduce
        # their own source family. Class-owned synthetic text is a single chunk.
        if purpose == "source" and chunk.kind == "class" and not _CLASS_CONTINUATION.fullmatch(chunk.name):
            kind = "family"
            chosen = tuple(member for member in file.chunks if member.identifier == chunk.identifier
                           or (member.family is not None and (member.family == chunk.name
                               or member.family.startswith(chunk.name + "."))))
        return Resolution(declaration, "resolved", SourceSelection(kind, self._place(file, chunk), file,
                                                                    self._members(file, chosen)))

    def resolve_retained(self, declaration: str, anchor: str | None = None) -> Resolution:
        """Follow an explicitly recognized file move for an existing binding.

        New refs always use ordinary resolution. A now ambiguous or ineligible
        declaration never follows its former anchor. The original spelling is
        kept while the returned place uses the current canonical binding.
        """
        result = self.resolve(declaration)
        if anchor is None or result.fault != "missing_file":
            return result
        address = parse_source_address(declaration)
        matches = tuple(file for file in self.files if any(
            prior.repository == address.repository and prior.path == address.path
            and address.root in {None, prior.root} for prior in file.recognized_moves)
            and (file.identifier == anchor if address.name is None else any(
                chunk.identifier == anchor for chunk in file.chunks)))
        if len(matches) != 1:
            return result
        file = matches[0]
        name = None if address.name is None else next(
            chunk.name for chunk in file.chunks if chunk.identifier == anchor)
        current = SourceAddress(file.repository, file.primary.root, file.primary.path, name)
        return replace_resolution(self.resolve(current.address), declaration)

    @classmethod
    def from_store(cls, connection, settings: SettingsSnapshot, *,
                   kind: Literal["disk", "branch", "stash"] = "disk", location: str | None = None,
                   _in_transaction: bool = False,
                   _read_transaction: bool = False,
                   _observation_guards: tuple[str, ...] | None = None) -> SourceResolver:
        """Read one checked repeatable snapshot without DDL or source substitution.

        Version metadata owns `name`, `kind`, optional `title`, `family`,
        `span: {start, end}` and relative `bodySpan`. Located metadata overrides
        address/extraction fields; recorded comparison revisions remain on the
        exact version. The forthcoming ingest reconciler writes that
        metadata; seeded exact-version fixtures can already consume this API.
        Branch/stash callers must explicitly identify their retained location.
        """
        settings.require_valid(require_store=False)
        if kind not in {"disk", "branch", "stash"} or (kind != "disk" and not location):
            raise MycelError("invalid_input", "A branch or stash source needs its exact retained location.")
        eligible = [name for name, repository in settings.values["repos"].items() if repository["enabled"]]
        try:
            if _in_transaction:
                if _read_transaction:
                    require_read_transaction(connection)
                else:
                    require_transaction_guards(connection, tuple(settings.values['repos'])
                        if _observation_guards is None else _observation_guards)
            with (nullcontext() if _in_transaction else checked_store(connection)), (nullcontext() if _in_transaction else read_snapshot(connection)):
                # One SQL statement gives all four projections the same MVCC
                # snapshot, including inside a writing READ COMMITTED pass.
                # An unguarded disjoint owner may publish concurrently without
                # pairing yesterday's full-file bytes with today's chunks.
                observed = connection.execute(_CATALOG_SQL,
                    (kind, location, eligible)).fetchall()
                portions = {'file': [], 'alias': [], 'chunk': [], 'index': []}
                for category, values in observed:
                    values = list(values)
                    byte_position = {'file': 5, 'chunk': 6, 'index': 4}.get(category)
                    if byte_position is not None:
                        values[byte_position] = bytes.fromhex(values[byte_position])
                    portions[category].append(tuple(values))
                file_rows, aliases, chunks, indices = (portions[key] for key in ('file', 'alias', 'chunk', 'index'))
            by_file: dict[str, list[SourceAddress]] = {}
            for identifier, repository, root, path in aliases:
                by_file.setdefault(str(identifier), []).append(SourceAddress(repository, root, path))
            members: dict[str, list[ResolvedChunk]] = {}
            for file_id, file_repository, chunk_repository, identifier, version, digest, text, comparison, metadata, located in chunks:
                if chunk_repository != file_repository:
                    raise _bad_catalog()
                members.setdefault(str(file_id), []).append(_chunk(identifier, version, digest, text,
                                                                  _located(metadata, located), comparison))
            files = []
            for identifier, repository, root, path, digest, source, located in file_rows:
                if not isinstance(located, dict):
                    raise _bad_catalog()
                if "root" in located or "path" in located or "aliases" in located:
                    primary = SourceAddress(repository, located["root"], located["path"])
                    bindings = [SourceAddress(repository, alias["root"], alias["path"])
                                for alias in located["aliases"]]
                else:
                    primary = SourceAddress(repository, root, path)
                    bindings = by_file.get(str(identifier), []) + [primary]
                files.append(ResolvedFile(str(identifier), repository, primary,
                             tuple(sorted(set(bindings), key=lambda alias: alias.address)), bytes(source), digest,
                             tuple(members.get(str(identifier), ())),
                             tuple(SourceAddress(repository, prior["root"], prior["path"])
                                   for prior in located.get("recognizedMoves", ()))))
            index = tuple((SourceAddress(repository, "index", metadata["path"], metadata["name"]),
                           _chunk(identifier, version, digest, text, metadata, comparison))
                          for repository, identifier, version, digest, text, comparison, metadata in indices)
            return cls(settings, tuple(files), index=index)
        except psycopg.Error:
            raise MycelError("store_unavailable", "The indexed source catalog could not be read.") from None
        except (KeyError, TypeError, ValueError, SourceAddressError):
            raise _bad_catalog() from None

    @classmethod
    def from_transaction(cls, connection, settings: SettingsSnapshot, *,
                         kind: Literal["disk", "branch", "stash"] = "disk", location: str | None = None,
                         guarded_repositories: tuple[str, ...] | None = None) -> SourceResolver:
        """Read prospective rows in the caller's checked, guarded transaction.

        This reader acquires no locks, opens no savepoint and never commits.
        The writing producer must hold checked_store and the complete involved
        repositories' pass/removal guards before opening its transaction.
        """
        return cls.from_store(connection, settings, kind=kind, location=location, _in_transaction=True,
                              _observation_guards=guarded_repositories)

    @classmethod
    def from_read_transaction(cls, connection, settings: SettingsSnapshot) -> SourceResolver:
        """Read disk/index selections in the caller's existing read snapshot.

        The caller holds checked_store and one read-only repeatable-read
        transaction throughout resolution and retrieval. This handoff does not
        allocate repository lock identities, open savepoints or end the caller's
        transaction. PostgreSQL rejects every attempted write in that snapshot.
        """
        return cls.from_store(connection, settings, _in_transaction=True,
                              _read_transaction=True)

    @classmethod
    def from_observation_transaction(cls, connection, settings: SettingsSnapshot, *,
                                    guarded_repositories: tuple[str, ...]) -> SourceResolver:
        """Read prospective disk selections for mechanical observation only.

        The detector holds every writing owner's guards and verifies its complete
        catalog again before commit. Other owners can be busy: their rows supply
        observations, never a mutation or a pin through this reader. Ordinary
        dependency/evidence producers retain the stricter complete-guard reader.
        """
        return cls.from_store(connection, settings, _in_transaction=True,
                              _observation_guards=guarded_repositories)


def _chunk(identifier, version, digest, source, metadata, comparison) -> ResolvedChunk:
    if not isinstance(metadata, dict) or not isinstance(comparison, dict):
        raise _bad_catalog()
    source = exact_bytes(source)
    exact_text(source)
    span = metadata.get("span")
    if span is not None:
        span = (span["start"], span["end"])
    body_span = metadata.get("bodySpan")
    body = None
    if body_span is not None:
        start, end = body_span["start"], body_span["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(source):
            raise _bad_catalog()
        body = source[start:end]
        try:
            body.decode("utf-8", errors="strict")
        except UnicodeError:
            raise _bad_catalog() from None
        body_span = (start, end)
    return ResolvedChunk(str(identifier), version, metadata["name"], metadata["kind"],
                         source, digest, span, metadata.get("title"), metadata.get("family"),
                         _freeze(comparison), body, body_span)


def _located(metadata, located):
    if not isinstance(metadata, dict) or not isinstance(located, dict):
        raise _bad_catalog()
    # Paths, names and extraction spans can change while exact text retains its
    # version. Located metadata therefore owns its current address/extraction.
    return {**metadata, **{key: value for key, value in located.items()
                          if key in {"name", "kind", "title", "family", "span", "bodySpan"}}}


def replace_resolution(result: Resolution, declaration: str) -> Resolution:
    return Resolution(declaration, result.state, result.selection, result.fault,
                      result.candidates, result.candidate_count)


def require_read_transaction(connection) -> None:
    """Validate an existing connection-owned read snapshot without writes."""
    if (connection.autocommit is not True
            or connection.info.transaction_status != pq.TransactionStatus.INTRANS):
        raise MycelError("invalid_input", "The read handoff requires an active read-only index snapshot.")
    try:
        mode = connection.execute("SELECT pg_catalog.current_setting('transaction_read_only'), "
                                  "pg_catalog.current_setting('transaction_isolation')").fetchone()
        held = connection.execute("""SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
            WHERE locktype='advisory' AND granted AND mode IN ('ShareLock','ExclusiveLock')
              AND pid=pg_catalog.pg_backend_pid() AND classid=2147483648::oid
              AND objid=0::oid AND objsubid=2
              AND database=(SELECT oid FROM pg_catalog.pg_database
                            WHERE datname=pg_catalog.current_database()))""").fetchone()
    except psycopg.Error:
        raise MycelError("store_unavailable", "The read snapshot guards could not be checked.") from None
    if mode != ('on', 'repeatable read') or held != (True,):
        raise MycelError("invalid_input", "The read handoff lacks its read-only repeatable snapshot or structure guard.")


_LOCATION_FILTER = "l.kind = %s AND (%s::text IS NULL OR l.location = %s) AND f.repository = ANY(%s)"
_FILES_SQL = """SELECT DISTINCT f.id, f.repository, f.root, f.path, v.snapshot_hash, v.source_bytes, l.metadata
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id = f.id
JOIN public.mycel_file_locations l ON l.file_version = v.id WHERE """ + _LOCATION_FILTER
_ALIASES_SQL = """SELECT DISTINCT f.id, f.repository, a.root, a.path
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id = f.id
JOIN public.mycel_file_locations l ON l.file_version = v.id
JOIN public.mycel_file_aliases a ON a.file_id = f.id WHERE """ + _LOCATION_FILTER
_CHUNKS_SQL = """SELECT DISTINCT f.id, f.repository, c.repository, c.id, v.id, v.snapshot_hash, v.source_bytes, v.comparison, v.metadata, l.metadata
FROM public.mycel_files f JOIN public.mycel_chunks c ON c.file_id = f.id
JOIN public.mycel_chunk_versions v ON v.chunk_id = c.id
JOIN public.mycel_locations l ON l.chunk_version = v.id
JOIN public.mycel_file_locations fl ON fl.id = l.file_location
JOIN public.mycel_file_versions fv ON fv.id = fl.file_version AND fv.file_id = f.id
WHERE fl.kind = l.kind AND fl.location = l.location AND """ + _LOCATION_FILTER
_INDEX_SQL = """SELECT DISTINCT c.repository, c.id, v.id, v.snapshot_hash, v.source_bytes, v.comparison, v.metadata
FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id = c.id
JOIN public.mycel_locations l ON l.chunk_version = v.id
WHERE c.file_id IS NULL AND l.kind = 'index' AND c.repository = ANY(%s)"""

_CATALOG_SQL = """WITH scope AS (SELECT %s::text AS kind,%s::text AS location,%s::text[] AS eligible)
SELECT DISTINCT 'file' AS category,jsonb_build_array(f.id,f.repository,f.root,f.path,v.snapshot_hash,
    encode(v.source_bytes,'hex'),l.metadata) AS values
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
JOIN public.mycel_file_locations l ON l.file_version=v.id CROSS JOIN scope s
WHERE l.kind=s.kind AND (s.location IS NULL OR l.location=s.location) AND f.repository=ANY(s.eligible)
UNION ALL
SELECT DISTINCT 'alias',jsonb_build_array(f.id,f.repository,a.root,a.path)
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
JOIN public.mycel_file_locations l ON l.file_version=v.id
JOIN public.mycel_file_aliases a ON a.file_id=f.id CROSS JOIN scope s
WHERE l.kind=s.kind AND (s.location IS NULL OR l.location=s.location) AND f.repository=ANY(s.eligible)
UNION ALL
SELECT DISTINCT 'chunk',jsonb_build_array(f.id,f.repository,c.repository,c.id,v.id,v.snapshot_hash,
    encode(v.source_bytes,'hex'),v.comparison,v.metadata,l.metadata)
FROM public.mycel_files f JOIN public.mycel_chunks c ON c.file_id=f.id
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id
JOIN public.mycel_file_locations fl ON fl.id=l.file_location
JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=f.id CROSS JOIN scope s
WHERE fl.kind=l.kind AND fl.location=l.location AND l.kind=s.kind
    AND (s.location IS NULL OR l.location=s.location) AND f.repository=ANY(s.eligible)
UNION ALL
SELECT DISTINCT 'index',jsonb_build_array(c.repository,c.id,v.id,v.snapshot_hash,
    encode(v.source_bytes,'hex'),v.comparison,v.metadata)
FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
JOIN public.mycel_locations l ON l.chunk_version=v.id CROSS JOIN scope s
WHERE c.file_id IS NULL AND l.kind='index' AND c.repository=ANY(s.eligible)"""
