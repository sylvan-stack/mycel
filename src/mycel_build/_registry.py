"""Short non-waiting registry mutations and durable never-reused allocation."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat

from ._core import BuildError, TARGETS, atomic_json, json_bytes, read_json, utc_now


def build_number(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9a-f][0-9a-f]*", value):
        raise BuildError("invalid_input", "A Build number must be canonical positive lowercase hexadecimal.")
    return int(value, 16)


def registry_path(root: Path | None = None) -> Path:
    path = Path.home() / ".mycel" / "builds" if root is None else Path(root).absolute()
    if path.is_symlink():
        raise BuildError("refused", "The Build registry cannot be a symbolic link.")
    return path


def _regular_lock(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BuildError("refused", "A distribution lock is not a private regular file.")


def _take_lock(fd: int, operation: int, busy_message: str) -> None:
    try:
        fcntl.flock(fd, operation | fcntl.LOCK_NB)
    except BlockingIOError:
        raise BuildError("busy", busy_message) from None
    except OSError:
        raise BuildError("refused", "The operating system could not establish the distribution lock.") from None


@contextmanager
def maintenance(root: Path):
    root = registry_path(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(root / ".registry.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        raise BuildError("refused", "The Build registry maintenance lock is missing or unsafe.") from None
    try:
        _regular_lock(fd)
        _take_lock(fd, fcntl.LOCK_EX, "Another release operation holds the Build registry lock.")
        yield
    finally:
        os.close(fd)


@contextmanager
def read_guard(root: Path):
    root = registry_path(root)
    try:
        fd = os.open(root / ".registry.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise BuildError("refused", "The Build registry read lock is missing or unsafe.") from None
    try:
        _regular_lock(fd)
        _take_lock(fd, fcntl.LOCK_SH, "Another release operation holds the Build registry lock.")
        yield
    finally:
        os.close(fd)


@contextmanager
def run_guard(root: Path, number: str, *, exclusive: bool = False):
    """Lock the retained inode read-only; callers also hold the registry lock.

    Selection holds its shared registry guard until this shared lock is acquired.
    Maintenance holds its exclusive registry guard for the complete prune. A
    launcher may make the yielded descriptor inheritable immediately before exec.
    """
    folder = _folder(registry_path(root), number)
    directory_fd = fd = None
    try:
        try:
            directory_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
            fd = os.open("run.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        except OSError:
            raise BuildError("refused", "This Build's retained run lock is missing or unsafe.") from None
        _regular_lock(fd)
        _take_lock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
                   "This Build is selected or running." if exclusive else "This Build is being pruned.")
        yield fd
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _ledger(root: Path) -> dict:
    path = root / ".allocations.json"
    if not path.exists():
        # Existing folders without the journal are never silently renumbered.
        if any(re.fullmatch(r"[1-9a-f][0-9a-f]*", p.name) for p in root.iterdir()):
            raise BuildError("refused", "The allocation journal is missing from a populated registry.")
        return {"schemaVersion": 1, "allocations": {}}
    ledger = read_json(path)
    try:
        if type(ledger["schemaVersion"]) is not int or ledger["schemaVersion"] != 1 or not isinstance(ledger["allocations"], dict):
            raise ValueError("journal schema")
        for number, record in ledger["allocations"].items():
            build_number(number)
            if record["build"] != number or record["status"] != "building":
                raise ValueError("journal identity")
    except (KeyError, TypeError, ValueError):
        raise BuildError("refused", "The immutable allocation journal is invalid.") from None
    return ledger


def _folder(root: Path, number: str) -> Path:
    build_number(number)
    path = root / number
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise BuildError("refused", "A Build folder escapes the registry.")
    return path


def _private_retained_file(path: Path, *, missing_ok: bool = False) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return missing_ok
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1


def _materialize(root: Path, number: str, initial: dict, *, recovered: bool = False) -> None:
    folder = _folder(root, number)
    folder.mkdir(exist_ok=True)
    record = dict(initial)
    if recovered:
        record.update(status="failed", finishedAt=utc_now(),
                      reason="Allocation was interrupted before its complete record was written.")
    atomic_json(folder / "build.json", record)
    atomic_json(folder / "checks.json", {"schemaVersion": 1, "results": [],
                                        "pending": ["all_unit", "all_store", "packaged_release", "publication"]})
    (folder / "build.log").write_text("Interrupted allocation recovered.\n" if recovered else "Build number allocated.\n")
    fd = os.open(folder / "run.lock", os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW, 0o444)
    os.close(fd)


def _recover_initial_allocation(root: Path, number: str, initial: dict) -> None:
    """Repair only an interrupted initial write; damage stays local and untouched."""
    members = {"build.json", "checks.json", "build.log", "run.lock"}
    try:
        folder = _folder(root, number)
        if folder.exists() and not folder.is_dir():
            return
        if folder.exists():
            paths = [folder / member for member in members]
            if all(_private_retained_file(path) for path in paths):
                return
            # Staged files or unsafe retained members cannot establish that this
            # was only the initial allocation write. Never replace their bytes.
            if any(path.name not in members for path in folder.iterdir()) or any(
                    not _private_retained_file(path, missing_ok=True) for path in paths):
                return
            record = folder / "build.json"
            if record.exists() and json_bytes(read_json(record)) != json_bytes(initial):
                return
            checks = folder / "checks.json"
            if checks.exists() and json_bytes(read_json(checks)) != json_bytes({
                    "schemaVersion": 1, "results": [],
                    "pending": ["all_unit", "all_store", "packaged_release", "publication"]}):
                return
            log = folder / "build.log"
            if log.exists() and log.read_bytes() != b"Build number allocated.\n":
                return
            lock = folder / "run.lock"
            if lock.exists() and lock.stat().st_size:
                return
        _materialize(root, number, initial, recovered=True)
    except (BuildError, OSError):
        # The journal still reserves this unavailable identity. Its damage or
        # failed recovery must not stop the next independent allocation.
        return


def allocate(root: Path, *, target: str, version: str, source: dict) -> dict:
    if target not in TARGETS or not isinstance(version, str) or not version:
        raise BuildError("invalid_input", "A Build needs a release target and package version.")
    if (set(source) != {"commit", "dirty", "inputsSha256"} or type(source["dirty"]) is not bool
            or not re.fullmatch(r"[0-9a-f]{64}", source["inputsSha256"])
            or not re.fullmatch(r"[0-9a-f]{40}|uncommitted", source["commit"])):
        raise BuildError("invalid_input", "A Build needs exact source-input identity.")
    root = registry_path(root)
    with maintenance(root):
        ledger = _ledger(root)
        for number, initial in ledger["allocations"].items():
            _recover_initial_allocation(root, number, initial)
        numbers = [build_number(n) for n in ledger["allocations"]]
        numbers += [build_number(p.name) for p in root.iterdir()
                    if re.fullmatch(r"[1-9a-f][0-9a-f]*", p.name)]
        number = format(max(numbers, default=0) + 1, "x")
        record = {"schemaVersion": 1, "build": number, "version": version, "target": target,
                  "status": "building", "startedAt": utc_now(), "source": source,
                  "checks": {"required": 0, "passed": 0, "failed": 0, "report": "checks.json"}}
        ledger["allocations"][number] = record
        # The fsynced journal is the allocation commit point. Even interruption
        # before folder creation reserves the identity and recovers as failed.
        atomic_json(root / ".allocations.json", ledger)
        _materialize(root, number, record)
    return record


def read_record(root: Path, number: str, *, _retained: bool = False) -> dict:
    folder = _folder(registry_path(root), number)
    if not all(_private_retained_file(folder / member)
               for member in ("build.json", "checks.json", "build.log", "run.lock")):
        raise BuildError("refused", "This Build has missing or unsafe retained metadata.")
    record = read_json(folder / "build.json")
    try:
        target = record["target"]
        # Retained metadata can outlive a supported target. Only the listing
        # reader accepts bounded historical labels; execution and mutations
        # retain the current release target restriction.
        retained_target = (_retained is True and isinstance(target, str)
                           and re.fullmatch(r"[a-z][a-z0-9]{0,15}-[a-z0-9][a-z0-9_]{0,31}", target))
        if (type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1 or record["build"] != number
                or (target not in TARGETS and not retained_target)
                or record["status"] not in {"building", "failed", "working", "withdrawn"}
                or record["checks"]["report"] != "checks.json" or ("program" in record and record["program"] != "program")):
            raise ValueError("record schema or paths")
        if (not isinstance(record["version"], str) or not record["version"]
                or not isinstance(record["startedAt"], str) or not isinstance(record["source"], dict)
                or type(record["source"]["dirty"]) is not bool
                or not re.fullmatch(r"[0-9a-f]{64}", record["source"]["inputsSha256"])
                or any(type(record["checks"][key]) is not int or record["checks"][key] < 0
                       for key in ("required", "passed", "failed"))):
            raise ValueError("record identity or checks")
        if "filesManifest" in record and record["filesManifest"] != "files.json":
            raise ValueError("manifest path")
        if "launcherBundle" in record and record["launcherBundle"] != "launcher-bundle":
            raise ValueError("launcher bundle path")
        if record["status"] == "withdrawn" and (
                not isinstance(record.get("reason"), str) or not record["reason"].strip()
                or any(not character.isprintable() for character in record["reason"])):
            raise ValueError("withdrawal reason")
        if "prunedAt" in record and (not isinstance(record["prunedAt"], str) or not record["prunedAt"].strip()):
            raise ValueError("pruning time")
        if "pruneComplete" in record and (type(record["pruneComplete"]) is not bool or "prunedAt" not in record):
            raise ValueError("pruning result")
    except (KeyError, TypeError, ValueError):
        raise BuildError("refused", "This Build record is damaged or unsafe.") from None
    return record


def update_staging(root: Path, number: str, *, fields: dict, checks: dict | None = None,
                   failed: bool = False) -> dict:
    """Staging cannot publish working/withdrawn records or alter allocation identity."""
    root = registry_path(root)
    forbidden = {"build", "schemaVersion", "version", "target", "source", "startedAt", "status", "prunedAt"}
    if forbidden.intersection(fields):
        raise BuildError("invalid_input", "A staging update would alter immutable record identity or publication state.")
    if ("program" in fields and fields["program"] != "program") or (
            "filesManifest" in fields and fields["filesManifest"] != "files.json") or (
            "launcherBundle" in fields and fields["launcherBundle"] != "launcher-bundle"):
        raise BuildError("invalid_input", "Staging paths must remain within their fixed Build folder.")
    with maintenance(root):
        record = read_record(root, number)
        if record["status"] != "building" or record.get("prunedAt"):
            raise BuildError("refused", "Only an unpruned building record accepts staging results.")
        if checks is not None:
            atomic_json(_folder(root, number) / "checks.json", checks)
        record.update(fields)
        if failed:
            record.update(status="failed", finishedAt=utc_now())
        atomic_json(_folder(root, number) / "build.json", record)
    return record


def list_records(root: Path) -> list[dict]:
    root = registry_path(root)
    if not root.exists():
        return []
    result = []
    numbers = sorted((p.name for p in root.iterdir() if re.fullmatch(r"[1-9a-f][0-9a-f]*", p.name)), key=build_number)
    with read_guard(root):
        for number in numbers:
            try:
                record = read_record(root, number, _retained=True)
                result.append(record if record["target"] in TARGETS else {**record, "targetSupported": False})
            except (BuildError, OSError):
                result.append({"build": number, "available": False, "reason": "Build record is missing or damaged."})
    return result
