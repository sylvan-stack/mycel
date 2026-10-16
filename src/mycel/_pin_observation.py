"""Fresh disk observations for the private checked evidence-pin boundary.

One invocation SettingsSnapshot is reused verbatim. Every call reads a new
store catalog and complete current capture; it never caches or reconciles IDs.
Only disk inputs are supported. This is not a public pin or ingest command.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
import os
import stat
from typing import Any

from ._capture import CapturedFile, CaptureManifest, capture_repository
from ._code import CodeChunk
from ._evidence import CaptureLocation, EvidenceError, InheritanceInputs, PinInputs, chunk_comparison, document_comparisons
from ._markdown import MarkdownDocument
from ._resolver import ResolvedFile, SourceResolver
from ._scope import Repository, RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address

OBSERVATION_REVISION = "mycel-disk-pin-observation-v1"


def _changed(addresses=()) -> None:
    raise EvidenceError("changed_since_ingest", tuple(addresses))


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _aliases(repository: str, file: CapturedFile) -> tuple[SourceAddress, ...]:
    return tuple(sorted((SourceAddress(repository, alias.root, alias.path) for alias in file.aliases),
                        key=lambda address: address.address))


def _path_matches(address: SourceAddress, manifest: CaptureManifest) -> tuple[CapturedFile, ...]:
    # CapturedFile already represents one physical file, including its aliases.
    # No new stable chunk/file identity is assigned to unindexed disk input.
    return tuple(file for file in manifest.disk.files if any(alias.path == address.path and
                 (address.root is None or alias.root == address.root) for alias in file.aliases))


def _path_slots(repository: Repository, address: SourceAddress,
                cancelled: Callable[[], bool] | None = None) -> tuple[dict, ...]:
    """Observe every configured spelling a raw path can reach, including absence.

    This closes a collision/deletion window while the complete scan and required
    file reads run. Directory/file symlinks below a root are observed as excluded,
    never followed. Changes after the final check remain ordinary later work.
    """
    slots = []
    for kind, folder in (("code", repository.code), ("artifact", repository.documents)):
        if cancelled is not None and cancelled():
            raise KeyboardInterrupt()
        if folder is None or (address.root is not None and address.root != kind):
            continue
        descriptors = []
        root = None
        signature = None
        try:
            root = folder.path.resolve(strict=True)
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            parts = address.path.split("/")
            for part in parts[:-1]:
                if cancelled is not None and cancelled():
                    raise KeyboardInterrupt()
                descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                descriptors.append(descriptor)
            info = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            signature = list(_signature(info))
        except (OSError, RuntimeError):
            # A missing or excluded path is an observation, not substitute text.
            # The complete capture independently diagnoses unreadable roots.
            pass
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
        slots.append({"address": SourceAddress(repository.name, kind, address.path).address,
                      "root": str(root) if root is not None else None, "signature": signature})
    return tuple(slots)


def _verify_chunks(indexed: ResolvedFile, captured: CapturedFile, *, require_chunks: bool) -> None:
    address = indexed.primary.address
    if captured.failure is not None or captured.parsed is None:
        if require_chunks or indexed.chunks:
            _changed((address,))
        return  # A complete binary file selection can retain bytes, never text.
    parsed = captured.parsed
    if isinstance(parsed, MarkdownDocument):
        if len(parsed.chunks) != len(indexed.chunks):
            _changed((address,))
        by_name = {chunk.name: chunk for chunk in parsed.chunks}
        for chunk in indexed.chunks:
            current = by_name.get(chunk.name)
            if current is None or (chunk.kind != "document" or chunk.source != current.text.encode("utf-8")
                    or chunk.snapshot_hash != current.snapshot_hash
                    or chunk.span != (current.span.byte_start, current.span.byte_end)
                    or chunk.title != current.title or chunk.family is not None
                    or chunk.body != current.body.encode("utf-8")
                    or chunk.body_span != (len(chunk.source) - len(current.body.encode("utf-8")), len(chunk.source))):
                _changed((address,))
            chunk_comparison(chunk)  # Unsupported recorded revisions stay unsupported.
            if chunk.comparison != document_comparisons(current.body, current.title or ""):
                _changed((address,))
    elif isinstance(parsed, tuple) and all(isinstance(chunk, CodeChunk) for chunk in parsed):
        if len(parsed) != len(indexed.chunks):
            _changed((address,))
        by_name = {chunk.symbol: chunk for chunk in parsed}
        for chunk in indexed.chunks:
            current = by_name.get(chunk.name)
            if current is None or (chunk.kind != current.kind or chunk.source != current.text.encode("utf-8")
                    or chunk.snapshot_hash != sha256(current.text.encode("utf-8")).hexdigest()
                    or chunk.span != (current.byte_start, current.byte_end)
                    or chunk.title is not None or chunk.body is not None or chunk.body_span is not None):
                _changed((address,))
            if chunk.family is not None and not chunk.name.startswith(chunk.family + "."):
                _changed((address,))
            chunk_comparison(chunk)
    else:
        _changed((address,))


def _read_alias(repository: Repository, address: SourceAddress, expected: bytes,
                cancelled: Callable[[], bool] | None) -> dict:
    """Reread every byte through no-follow parent descriptors, then guard it."""
    folder = repository.code if address.root == "code" else repository.documents
    if folder is None:
        _changed((address.address,))
    descriptors = []
    try:
        root = folder.path.resolve(strict=True)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        root_info = os.fstat(descriptor)
        parts = address.path.split("/")
        for part in parts[:-1]:
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(descriptor)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _changed((address.address,))
        pieces = []
        while True:
            if cancelled is not None and cancelled():
                raise KeyboardInterrupt()
            piece = os.read(descriptor, 1024 * 1024)
            if not piece:
                break
            pieces.append(piece)
        after = os.fstat(descriptor)
        source = b"".join(pieces)
        if _signature(before) != _signature(after) or source != expected or len(source) != after.st_size:
            _changed((address.address,))
        # Also reject a configured root alias that retargeted during this read.
        if folder.path.resolve(strict=True) != root:
            _changed((address.address,))
        return {"address": address.address, "root": str(root),
                "rootIdentity": [root_info.st_dev, root_info.st_ino], "fileIdentity": list(_signature(after))}
    except (OSError, RuntimeError, ValueError):
        _changed((address.address,))
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@dataclass(frozen=True)
class DiskPinObservation:
    """Factory/callback for one raw dependant endpoint and source declaration.

    ``expected = observation.observe()`` then pass ``observation.reread`` to
    EvidenceStore.pin. Its checked guard calls reread under repository locks.
    Both calls use exactly the same immutable invocation settings object.
    """

    connection: Any = field(repr=False)
    settings: SettingsSnapshot = field(repr=False)
    dependant_ref: str
    declaration: str
    kind: str = "disk"
    cancelled: Callable[[], bool] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if (self.kind != "disk" or not isinstance(self.settings, SettingsSnapshot)
                or (self.cancelled is not None and not callable(self.cancelled))):
            raise EvidenceError("invalid_input")
        self.settings.require_valid(require_store=False)
        if not isinstance(self.declaration, str):
            raise EvidenceError("invalid_input")
        for raw in (self.dependant_ref,):
            try:
                address = parse_source_address(raw)
            except (SourceAddressError, TypeError):
                raise EvidenceError("invalid_input") from None
            configured = self.settings.values["repos"].get(address.repository)
            if address.root == "index" or configured is None or not configured["enabled"]:
                raise EvidenceError("invalid_input")

    def _require_source(self) -> None:
        try:
            address = parse_source_address(self.declaration)
        except (SourceAddressError, TypeError):
            raise EvidenceError("invalid_input") from None
        configured = self.settings.values["repos"].get(address.repository)
        if address.root == "index" or configured is None or not configured["enabled"]:
            raise EvidenceError("invalid_input")

    def _cancel(self) -> None:
        if self.cancelled is not None and self.cancelled():
            raise KeyboardInterrupt()

    def observe(self) -> PinInputs:
        self._cancel()
        self._require_source()
        catalog = SourceResolver.from_store(self.connection, self.settings, kind="disk")
        self._cancel()
        dependant = catalog.resolve(self.dependant_ref, purpose="endpoint")
        source = catalog.resolve(self.declaration, purpose="source")
        known = tuple(result.selection.place.address for result in (dependant, source) if result.selection is not None)
        if (dependant.state != "resolved" or source.state != "resolved" or dependant.selection.file is None
                or source.selection.file is None or len(dependant.selection.members) != 1):
            _changed((*known, *dependant.candidates, *source.candidates))
        owner_file, source_file = dependant.selection.file, source.selection.file
        repositories = tuple(sorted({owner_file.repository, source_file.repository}))
        locations = RepositoryLocations(self.settings)
        captures = {}
        resolved = {}
        for name in repositories:
            selected = locations.named(name)
            if len(selected) != 1 or selected[0].name != name or not selected[0].enabled:
                _changed(known)
            resolved[name] = selected[0]
        raw_addresses = tuple(parse_source_address(raw) for raw in (self.dependant_ref, self.declaration))
        slots = tuple(_path_slots(resolved[address.repository], address, self.cancelled) for address in raw_addresses)
        for name in repositories:
            self._cancel()
            manifest = capture_repository(self.settings, resolved[name], cancelled=self.cancelled)
            self._cancel()
            # Conservative until capture exposes an independent disk-only entry.
            if not manifest.complete or not manifest.disk.complete:
                _changed(known)
            captures[name] = manifest
        observations = {}
        for raw, indexed, require_chunks in ((self.dependant_ref, owner_file, True),
                                            (self.declaration, source_file, source.selection.kind != "file")):
            self._cancel()
            address = parse_source_address(raw)
            matches = _path_matches(address, captures[indexed.repository])
            if len(matches) != 1:
                candidates = tuple(place.address for file in matches for place in _aliases(indexed.repository, file)
                                   if place.path == address.path and (address.root is None or place.root == address.root))
                _changed((*known, *candidates))
            current = matches[0]
            aliases = _aliases(indexed.repository, current)
            if (set(aliases) != set(indexed.aliases) or indexed.primary not in aliases
                    or current.file_hash != indexed.snapshot_hash or current.source != indexed.source):
                _changed((*known, indexed.primary.address, *(alias.address for alias in aliases)))
            _verify_chunks(indexed, current, require_chunks=require_chunks)
            if raw == self.declaration and source.selection.kind == "family":
                if not isinstance(current.parsed, tuple):
                    _changed(known)
                expected_members = {chunk.symbol for chunk in current.parsed if
                                    chunk.symbol == source.selection.place.name or
                                    chunk.symbol.startswith(source.selection.place.name + ".")}
                if {member.chunk.name for member in source.selection.members} != expected_members:
                    _changed(known)
            if indexed.identifier not in observations:
                physical = [_read_alias(resolved[indexed.repository], alias, current.source, self.cancelled)
                            for alias in aliases]
                if len({tuple(item["fileIdentity"][:2]) for item in physical}) != 1:
                    _changed((*known, indexed.primary.address))
                observations[indexed.identifier] = {"repository": indexed.repository,
                    "file": indexed.identifier, "primary": indexed.primary.address,
                    "aliases": [alias.address for alias in aliases], "fileHash": current.file_hash,
                    "policyHash": captures[indexed.repository].policy_hash, "physical": physical}
        self._cancel()
        current_slots = tuple(_path_slots(resolved[address.repository], address, self.cancelled) for address in raw_addresses)
        self._cancel()
        if current_slots != slots:
            _changed(known)
        result = PinInputs(self.settings, dependant.selection.members[0], owner_file, source.selection,
                         CaptureLocation("disk"), source, catalog,
                         {"revision": OBSERVATION_REVISION, "locationIdentity": "disk",
                          "dependantDeclaration": self.dependant_ref,
                          "rawPaths": current_slots,
                          "files": [observations[key] for key in sorted(observations)]})
        self._cancel()
        return result

    def reread(self) -> PinInputs:
        return self.observe()

    def observe_inheritance(self) -> InheritanceInputs:
        """Guard only a current dependant; retained source evidence stays old.

        Fresh source resolution is fault/guard metadata. Missing, disabled or
        invalid source declarations do not turn into a current-byte capture.
        """
        self._cancel()
        catalog = SourceResolver.from_store(self.connection, self.settings, kind="disk")
        self._cancel()
        dependant = catalog.resolve(self.dependant_ref, purpose="endpoint")
        source = catalog.resolve(self.declaration, purpose="source")
        if (dependant.state != "resolved" or dependant.selection.file is None
                or len(dependant.selection.members) != 1):
            _changed(dependant.candidates)
        file = dependant.selection.file
        known = (dependant.selection.place.address, file.primary.address)
        selected = RepositoryLocations(self.settings).named(file.repository)
        if len(selected) != 1 or selected[0].name != file.repository or not selected[0].enabled:
            _changed(known)
        repository = selected[0]
        address = parse_source_address(self.dependant_ref)
        slots = _path_slots(repository, address, self.cancelled)
        manifest = capture_repository(self.settings, repository, cancelled=self.cancelled)
        self._cancel()
        if not manifest.complete or not manifest.disk.complete:
            _changed(known)
        matches = _path_matches(address, manifest)
        if len(matches) != 1:
            candidates = tuple(alias.address for current in matches for alias in _aliases(file.repository, current))
            _changed((*known, *candidates))
        current = matches[0]
        aliases = _aliases(file.repository, current)
        if (set(aliases) != set(file.aliases) or file.primary not in aliases
                or current.file_hash != file.snapshot_hash or current.source != file.source):
            _changed((*known, *(alias.address for alias in aliases)))
        _verify_chunks(file, current, require_chunks=True)
        physical = [_read_alias(repository, alias, current.source, self.cancelled) for alias in aliases]
        self._cancel()
        if len({tuple(item["fileIdentity"][:2]) for item in physical}) != 1:
            _changed(known)
        current_slots = _path_slots(repository, address, self.cancelled)
        self._cancel()
        if current_slots != slots:
            _changed(known)
        result = InheritanceInputs(self.settings, dependant.selection.members[0], file, CaptureLocation("disk"),
                source, catalog, {"revision": OBSERVATION_REVISION, "mode": "inheritance",
                    "locationIdentity": "disk", "dependantDeclaration": self.dependant_ref,
                    "rawPaths": current_slots, "files": [{"repository": file.repository,
                        "file": file.identifier, "primary": file.primary.address,
                        "aliases": [alias.address for alias in aliases], "fileHash": current.file_hash,
                        "policyHash": manifest.policy_hash, "physical": physical}]})
        self._cancel()
        return result

    def reread_inheritance(self) -> InheritanceInputs:
        return self.observe_inheritance()
