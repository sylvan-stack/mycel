"""Verified offline inputs, safe installation and exact distribution manifests."""

from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tarfile
import tempfile
import urllib.request
import unicodedata
from urllib.parse import urlparse
import zipfile


class BuildError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


TARGETS = {"macos-arm64"}
RUNTIME_HASHES = {
    "macos-arm64": "4632cb1a6edad9e73d3c81b6d2e69131637d995173e3e85005df14102b0592ba",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def read_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise BuildError("refused", "A distribution record is missing, unsafe or oversized.")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("non-JSON number")

    try:
        return json.loads(path.read_bytes(), object_pairs_hook=unique, parse_constant=invalid_constant)
    except (OSError, ValueError):
        raise BuildError("refused", "A distribution record could not be read.") from None


def atomic_json(path: Path, value) -> None:
    if path.is_symlink():
        raise BuildError("refused", "A distribution record is a symbolic link.")
    fd, temporary = tempfile.mkstemp(prefix=".record-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def relative_path(value: str) -> PurePosixPath:
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value
            or value.startswith("/") or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise BuildError("refused", "A distribution path is not a safe relative path.")
    return PurePosixPath(value)


def contained(root: Path, value: str) -> Path:
    path = root.joinpath(*relative_path(value).parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise BuildError("refused", "A distribution path escapes its folder.")
    return path


def _safe_parents(root: Path, path: Path) -> None:
    for parent in path.relative_to(root).parents:
        node = root / parent
        if node.is_symlink():
            raise BuildError("refused", "An archive writes through a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)


def _installation_paths(root: Path, names: list[str]) -> None:
    """Validate a complete installation before creating any archive members."""
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise BuildError("refused", "An installation root is not a real directory.")
    # Native macOS filesystems commonly fold case and Unicode normalization.
    # Refuse an ambiguous package on every development host, including fixtures.
    identities = {unicodedata.normalize("NFD", name).casefold() for name in names}
    if len(identities) != len(names):
        raise BuildError("refused", "Archive paths collide on a supported target filesystem.")
    for name in names:
        path = root.joinpath(*relative_path(name).parts)
        if path.exists() or path.is_symlink():
            raise BuildError("refused", "An archive collides with installed files.")
        for parent in path.relative_to(root).parents:
            if parent != Path(".") and unicodedata.normalize("NFD", parent.as_posix()).casefold() in identities:
                raise BuildError("refused", "An archive file is another member's parent.")
            node = root / parent
            if node.is_symlink() or (node.exists() and not node.is_dir()):
                raise BuildError("refused", "An archive writes through an unsafe parent.")


def _relative_link(name: str, target: str) -> str:
    if not target or "\\" in target or "\x00" in target or target.startswith("/"):
        raise BuildError("refused", "A distribution link is not relocatable.")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    if resolved == ".." or resolved.startswith("../"):
        raise BuildError("refused", "A distribution link escapes its folder.")
    return resolved


def load_lock(path: Path, target: str) -> tuple[dict, dict]:
    if target not in TARGETS:
        raise BuildError("invalid_input", "The release target is unsupported.")
    lock = read_json(path)
    try:
        row = lock["targets"][target]
        runtime = row["runtime"]
        if (type(lock["schemaVersion"]) is not int or lock["schemaVersion"] != 1 or lock["python"] != "3.14.7"
                or set(lock["targets"]) != TARGETS
                or runtime["python"] != "3.14.7" or runtime["sha256"] != RUNTIME_HASHES[target]
                or runtime["distribution"] != "python-build-standalone/20260901/install_only_stripped"):
            raise ValueError("runtime pin")
        names = set()
        for asset in [runtime, *row["dependencies"]]:
            relative_path(asset["filename"])
            url = urlparse(asset["url"])
            if ("/" in asset["filename"] or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
                    or url.scheme != "https" or url.username or url.password or not url.hostname
                    or not isinstance(asset["licenses"], list) or not asset["licenses"]):
                raise ValueError("asset pin")
            for licence in asset["licenses"]:
                p = contained(path.parent, licence["path"])
                if not p.is_file() or p.is_symlink() or digest(p.read_bytes()) != licence["sha256"]:
                    raise ValueError("licence pin")
        for dependency in row["dependencies"]:
            name = re.sub(r"[-_.]+", "-", dependency["name"]).lower()
            if name in names or not dependency["filename"].endswith(".whl"):
                raise ValueError("dependency pin")
            names.add(name)
        if not row["dependencies"]:
            raise ValueError("dependency closure")
    except (KeyError, TypeError, ValueError, OSError):
        raise BuildError("refused", "The checked-in release lock or licence digest is invalid.") from None
    return lock, row


def verify_asset(asset: dict, directory: Path) -> Path:
    path = contained(directory, asset["filename"])
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024
            or digest(path.read_bytes()) != asset["sha256"]):
        raise BuildError("refused", "A pinned archive or wheel is missing or has the wrong digest.")
    return path


def snapshot_asset(asset: dict, source_directory: Path, private_directory: Path) -> Path:
    """Install only a privately copied asset whose copied bytes match the lock."""
    source = verify_asset(asset, source_directory)
    destination = contained(private_directory, asset["filename"])
    if destination.exists() or destination.is_symlink():
        raise BuildError("refused", "A private asset snapshot already exists.")
    private_directory.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as input_stream, destination.open("xb") as output:
            if not stat.S_ISREG(os.fstat(input_stream.fileno()).st_mode):
                raise BuildError("refused", "A pinned asset changed before its private snapshot.")
            checksum = hashlib.sha256()
            size = 0
            while part := input_stream.read(1024 * 1024):
                size += len(part)
                if size > 256 * 1024 * 1024:
                    raise BuildError("refused", "A pinned asset exceeds its bounded size.")
                checksum.update(part)
                output.write(part)
        if checksum.hexdigest() != asset["sha256"]:
            raise BuildError("busy", "A pinned asset changed during its private snapshot.")
        destination.chmod(0o444)
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def prepare(lock_path: Path, target: str, directory: Path) -> dict:
    """The sole network preparation phase; staging itself never downloads."""
    _, row = load_lock(lock_path, target)
    directory.mkdir(parents=True, exist_ok=True)
    for asset in [row["runtime"], *row["dependencies"]]:
        path = contained(directory, asset["filename"])
        if path.exists() or path.is_symlink():
            verify_asset(asset, directory)
            continue
        fd, name = tempfile.mkstemp(prefix=".download-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as output, urllib.request.urlopen(asset["url"], timeout=30) as response:
                size = 0
                while part := response.read(1024 * 1024):
                    size += len(part)
                    if size > 256 * 1024 * 1024:
                        raise BuildError("refused", "A preparation download exceeds its bounded size.")
                    output.write(part)
            if digest(Path(name).read_bytes()) != asset["sha256"]:
                raise BuildError("refused", "A preparation download differs from its pinned digest.")
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    return {"target": target, "assets": len(row["dependencies"]) + 1, "verified": True}


def extract_runtime(archive: Path, destination: Path) -> None:
    """Unpack only the pinned python/ subtree, including contained relocatable links."""
    with tarfile.open(archive, "r:gz") as bundle:
        total = 0
        seen = set()
        files = []
        links = {}
        plan = []
        root_seen = False
        for member in bundle.getmembers():
            parts = relative_path(member.name.rstrip("/")).parts
            if parts[0] != "python":
                raise BuildError("refused", "The runtime archive contains an unexpected root.")
            if len(parts) == 1:
                if not member.isdir() or root_seen:
                    raise BuildError("refused", "The runtime archive root is not a unique directory.")
                root_seen = True
                continue
            name = "/".join(parts[1:])
            if name in seen:
                raise BuildError("refused", "The runtime archive repeats a path.")
            seen.add(name)
            total += member.size
            if member.size < 0 or total > 1024 * 1024 * 1024:
                raise BuildError("refused", "The expanded runtime exceeds its bounded size.")
            if member.isfile():
                files.append(name)
            elif member.issym():
                links[name] = _relative_link(name, member.linkname)
                files.append(name)
            elif not member.isdir():
                raise BuildError("refused", "The runtime contains an unsupported archive member.")
            plan.append((name, member))
        if len({unicodedata.normalize("NFD", name).casefold() for name in seen}) != len(seen):
            raise BuildError("refused", "Runtime paths collide on a supported target filesystem.")
        _installation_paths(destination, files)
        # A link can be a terminal archive member, never a parent of another
        # member. Follow link chains without consulting files outside the archive.
        terminal_paths = {unicodedata.normalize("NFD", name).casefold() for name in files}
        for name, member in plan:
            for parent in PurePosixPath(name).parents:
                if unicodedata.normalize("NFD", str(parent)).casefold() in terminal_paths:
                    raise BuildError("refused", "The runtime writes through an archive link or file.")
        for origin in links:
            visited = set()
            name = origin
            while name in links:
                if name in visited:
                    raise BuildError("refused", "The runtime contains a symbolic-link cycle.")
                visited.add(name)
                name = links[name]
            if name not in seen and name != ".":
                raise BuildError("refused", "The runtime contains a link without an archive target.")
        destination.mkdir()
        for name, member in plan:
            path = contained(destination, name)
            _safe_parents(destination, path)
            if member.isdir():
                path.mkdir(exist_ok=True)
            elif member.isfile():
                with bundle.extractfile(member) as source, path.open("xb") as output:
                    while part := source.read(1024 * 1024):
                        output.write(part)
                path.chmod(0o755 if member.mode & 0o111 else 0o644)
            elif member.issym():
                path.symlink_to(member.linkname)


def install_wheel(archive: Path, site: Path) -> None:
    """PEP 427 installation with RECORD verification; no resolver, scripts or editable links."""
    with zipfile.ZipFile(archive) as wheel:
        members = wheel.infolist()
        records = [m.filename for m in members if m.filename.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise BuildError("refused", "A wheel has no unique installation record.")
        try:
            rows = list(csv.reader(io.StringIO(wheel.read(records[0]).decode()), strict=True))
        except (UnicodeError, csv.Error, zipfile.BadZipFile):
            raise BuildError("refused", "A wheel installation record cannot be decoded.") from None
        recorded = {r[0]: r[1:] for r in rows if len(r) == 3}
        if len(recorded) != len(rows):
            raise BuildError("refused", "A wheel repeats or damages its installation record.")
        seen = set()
        entries = set()
        total = 0
        plan = []
        for member in members:
            name = str(relative_path(member.filename.rstrip("/") if member.is_dir() else member.filename))
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (name in entries or member.flag_bits & 1 or
                    kind not in ({0, stat.S_IFDIR} if member.is_dir() else {0, stat.S_IFREG})):
                raise BuildError("refused", "A wheel repeats a path or contains a special file.")
            entries.add(name)
            if member.is_dir():
                continue
            seen.add(name)
            total += member.file_size
            if total > 512 * 1024 * 1024:
                raise BuildError("refused", "An expanded wheel exceeds its bounded size.")
            try:
                raw = wheel.read(member)
            except zipfile.BadZipFile:
                raise BuildError("refused", "A wheel member cannot be read.") from None
            checksum, size = recorded.get(name, [None, None])
            if name != records[0]:
                actual = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
                if checksum != actual or size != str(len(raw)):
                    raise BuildError("refused", "A wheel member differs from its installation record.")
            elif checksum or size:
                raise BuildError("refused", "A wheel record improperly hashes itself.")
            parts = PurePosixPath(name).parts
            if parts[0].endswith(".data"):
                if len(parts) < 3 or parts[1] not in {"purelib", "platlib"}:
                    raise BuildError("refused", "A wheel requires unsupported external installation paths.")
                name = "/".join(parts[2:])
            if PurePosixPath(name).suffix in {".pth", ".pyc", ".pyo"}:
                raise BuildError("refused", "A wheel collides with installed files or injects an import path.")
            plan.append((name, member, mode))
        if seen != set(recorded):
            raise BuildError("refused", "A wheel record does not exactly cover its files.")
        _installation_paths(site, [name for name, _, _ in plan])
        site.mkdir(parents=True, exist_ok=True)
        for name, member, mode in plan:
            path = contained(site, name)
            _safe_parents(site, path)
            with path.open("xb") as output:
                output.write(wheel.read(member))
            path.chmod(0o755 if mode & 0o111 else 0o644)


def file_manifest(root: Path) -> list[dict]:
    if root.is_symlink() or not root.is_dir():
        raise BuildError("refused", "A distribution root is not a real directory.")
    result = [{"path": ".", "directory": True, "mode": stat.S_IMODE(root.stat().st_mode)}]
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        relative_path(name)
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            target = os.readlink(path)
            _relative_link(name, target)
            try:
                safe = path.resolve().is_relative_to(root.resolve()) and path.exists()
            except (OSError, RuntimeError):
                safe = False
            if not safe:
                raise BuildError("refused", "An installed symbolic link escapes or has no target.")
            result.append({"path": name, "link": target, "sha256": digest(target.encode())})
        elif path.is_file():
            result.append({"path": name, "sha256": digest(path.read_bytes()),
                           "size": path.stat().st_size, "mode": mode})
        elif path.is_dir():
            result.append({"path": name, "directory": True, "mode": mode})
        else:
            raise BuildError("refused", "An installed distribution contains a special file.")
    return result


def seal_program(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
    root.chmod(0o555)


def validate_manifest(root: Path, manifest: list[dict], expected: str) -> None:
    if (not isinstance(manifest, list) or digest(json_bytes(manifest)) != expected
            or file_manifest(root) != manifest or any(row.get("mode", 0) & 0o222 for row in manifest)):
        raise BuildError("refused", "Installed files differ from their immutable Build manifest.")
