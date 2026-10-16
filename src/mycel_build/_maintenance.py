"""Explicit withdrawal and program-only pruning under distribution locks."""

from __future__ import annotations

import os
from pathlib import Path
import stat

from ._core import BuildError, atomic_json, utc_now
from ._registry import _folder, build_number, maintenance, read_record, registry_path, run_guard


def _target(root: Path, number: str) -> tuple[Path, Path]:
    build_number(number)
    root = registry_path(root)
    folder = _folder(root, number)
    if not root.is_dir() or not folder.exists():
        raise BuildError("invalid_input", "Unknown Build number.")
    return root, folder


def _reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise BuildError("invalid_input", "Withdrawal needs a nonempty reason.")
    cleaned = " ".join("".join(character if character.isprintable() else " " for character in reason).split())
    if not cleaned:
        raise BuildError("invalid_input", "Withdrawal needs a nonempty reason.")
    return cleaned


def withdraw(root: Path, number: str, reason: str) -> dict:
    """Withdraw only a working record; existing invocations keep their Build."""
    reason = _reason(reason)
    root, folder = _target(root, number)
    with maintenance(root):
        record = read_record(root, number)
        if record["status"] != "working" or record.get("prunedAt"):
            raise BuildError("refused", "Only an unpruned working Build can be withdrawn.")
        record = {**record, "status": "withdrawn", "reason": reason}
        try:
            atomic_json(folder / "build.json", record)
        except BaseException as error:
            # Atomic replacement can have committed before its directory fsync
            # fails or is interrupted. Report the actual retained state and
            # never restore a possibly persisted working/default selection.
            try:
                partial = read_record(root, number)
            except (BuildError, OSError):
                partial = {"build": number, "available": False}
            if isinstance(error, KeyboardInterrupt):
                error.partialResult = partial
                raise
            failure = BuildError("internal", "Withdrawal did not finish; inspect the retained record before retrying this Build.")
            failure.partialResult = partial
            raise failure from None
    return record


def _clear_directory(fd: int) -> None:
    """Delete children relative to opened directories, never through symlinks."""
    info = os.fstat(fd)
    os.fchmod(fd, stat.S_IMODE(info.st_mode) | stat.S_IWUSR | stat.S_IXUSR)
    for name in os.listdir(fd):
        child = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(child.st_mode):
            child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                opened = os.fstat(child_fd)
                if (child.st_dev, child.st_ino) != (opened.st_dev, opened.st_ino):
                    raise BuildError("refused", "The program directory changed during pruning.")
                _clear_directory(child_fd)
                current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    raise BuildError("refused", "The program directory changed during pruning.")
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=fd)
        else:
            # Unlinking a leaf also removes dangling/internal/outside symlinks
            # without opening or changing their targets. Hardlinked file bytes
            # are never chmodded or rewritten.
            os.unlink(name, dir_fd=fd)


def _remove_program(folder: Path) -> None:
    folder_fd = program_fd = None
    restore_mode = None
    try:
        folder_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.stat("program", dir_fd=folder_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISDIR(info.st_mode):
            raise BuildError("refused", "The Build program is not a real directory.")
        program_fd = os.open("program", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=folder_fd)
        opened = os.fstat(program_fd)
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise BuildError("refused", "The Build program changed during pruning.")
        parent_mode = stat.S_IMODE(os.fstat(folder_fd).st_mode)
        if not parent_mode & stat.S_IWUSR:
            # Build-local launcher bundles are sealed too. Open their fixed
            # parent for deletion, then restore its retained metadata mode.
            restore_mode = parent_mode
            os.fchmod(folder_fd, parent_mode | stat.S_IWUSR | stat.S_IXUSR)
        _clear_directory(program_fd)
        current = os.stat("program", dir_fd=folder_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise BuildError("refused", "The Build program changed during pruning.")
        os.rmdir("program", dir_fd=folder_fd)
        os.fsync(folder_fd)
    finally:
        try:
            if program_fd is not None:
                os.close(program_fd)
        finally:
            if folder_fd is not None:
                try:
                    if restore_mode is not None:
                        os.fchmod(folder_fd, restore_mode)
                finally:
                    os.close(folder_fd)


def prune(root: Path, number: str) -> dict:
    """Prune one named, unused failed/withdrawn Build, retaining all metadata.

    The first atomic record change makes incomplete deletion unavailable too.
    A later explicit retry finishes that same target without changing its first
    pruning time. No directory scan or implicit cleanup chooses another Build.
    """
    root, folder = _target(root, number)
    with maintenance(root):
        record = read_record(root, number)
        if record["status"] not in {"failed", "withdrawn"}:
            raise BuildError("refused", "Pruning requires an explicitly named failed or withdrawn Build.")
        with run_guard(root, number, exclusive=True):
            parents = [folder]
            bundle = folder / "launcher-bundle"
            if record.get("launcherBundle") == "launcher-bundle":
                if bundle.is_symlink() or (bundle.exists() and not bundle.is_dir()):
                    raise BuildError("refused", "The Build-local launcher bundle is not a real directory.")
                if bundle.is_dir():
                    parents.append(bundle)
            elif os.path.lexists(bundle):
                raise BuildError("refused", "An unrecorded launcher bundle cannot be pruned by guessing its ownership.")
            # Refuse an unsafe top-level program path before changing metadata.
            for parent in parents:
                program = parent / "program"
                if program.is_symlink() or (program.exists() and not program.is_dir()):
                    raise BuildError("refused", "The Build program is not a real directory.")
            record = {**record, "prunedAt": record.get("prunedAt") or utc_now(), "pruneComplete": False}
            try:
                atomic_json(folder / "build.json", record)
                for parent in parents:
                    _remove_program(parent)
                record = {**record, "pruneComplete": True}
                atomic_json(folder / "build.json", record)
            except BaseException as error:
                # Keep the authentic on-disk state in the partial result even
                # if atomic replacement succeeded but its directory fsync did
                # not. Never turn an interrupted deletion back into a runnable
                # record or guess that all program files were removed.
                try:
                    partial = read_record(root, number)
                except (BuildError, OSError):
                    partial = {"build": number, "available": False}
                if isinstance(error, KeyboardInterrupt):
                    error.partialResult = partial
                    raise
                failure = BuildError("internal", "Pruning did not complete; inspect the retained record before retrying this Build.")
                failure.partialResult = partial
                raise failure from None
    return record
