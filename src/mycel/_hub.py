"""Manage the Instructions Hub copies used by new sessions (MYC-21.9–21.11)."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import tomllib

from ._errors import ErrorCode, MycelError
from ._settings import SettingsSnapshot


_CODEX_KEY = "developer_instructions"
_LEGACY_IMPORT = "@~/Artifacts/mycel/README.md"
_ACTIVE_IMPORT = "@~/.mycel/hub/active.md"
_HEADER = (
    "These are the contents of the Instructions Hub, the file "
    "~/Artifacts/mycel/README.md. Links in it are relative to ~/Artifacts/mycel/. "
    "This copy is rewritten whenever that file changes: change the file, "
    "never this copy.\n\n"
)
_MODES = ("on", "off")
_STATE_VERSION = 1


@dataclass(frozen=True)
class _Paths:
    root: Path
    source: Path
    codex: Path
    agents: Path
    claude: Path

    @classmethod
    def from_settings(cls, settings: SettingsSnapshot) -> "_Paths":
        home = settings._home or Path.home()
        return cls(home / ".mycel/hub", home / "Artifacts/mycel/README.md",
                   home / ".codex/config.toml", home / ".agents/AGENTS.md",
                   home / ".claude/CLAUDE.md")

    @property
    def active(self) -> Path:
        return self.root / "active.md"

    @property
    def state(self) -> Path:
        return self.root / "state.json"


@dataclass(frozen=True)
class _File:
    contents: bytes
    mode: int


@dataclass(frozen=True)
class _State:
    mode: str
    last_sync: str | None = None
    pending: bool = False

    def reply(self) -> dict:
        return {"state": self.mode, "last_sync": self.last_sync, "pending": self.pending}


def _read(path: Path) -> _File | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        mode = os.fstat(stream.fileno()).st_mode
        if not stat.S_ISREG(mode):
            raise OSError("The Hub expects a regular file.")
        return _File(stream.read(), stat.S_IMODE(mode))


def _text(snapshot: _File | None) -> str:
    return snapshot.contents.decode("utf-8") if snapshot is not None else ""


def _codex_config(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise MycelError(ErrorCode.IO, "Codex settings are not valid TOML.") from None


def _imports(paths: _Paths) -> set[str]:
    return set(map(str.strip, _text(_read(paths.claude)).splitlines())) & {_LEGACY_IMPORT, _ACTIVE_IMPORT}


def _adopt_state(paths: _Paths) -> _State:
    imports = _imports(paths)
    active = _text(_read(paths.active))
    codex = _codex_config(_text(_read(paths.codex))).get(_CODEX_KEY)
    agents = _text(_read(paths.agents))
    claude_on = _LEGACY_IMPORT in imports or (_ACTIVE_IMPORT in imports and bool(active))
    codex_on = isinstance(codex, str) and codex.startswith(_HEADER)
    if len(imports) <= 1:
        if claude_on and codex_on and agents.startswith(_HEADER):
            return _State("on")
        if not claude_on and codex is None and not agents:
            return _State("off")
    raise MycelError(ErrorCode.REFUSED, "The Hub copies disagree. Select hub on or hub off to align them.")


def _saved_state(paths: _Paths) -> _State | None:
    saved = _read(paths.state)
    if saved is None:
        return None
    try:
        value = json.loads(saved.contents)
        if isinstance(value, dict):
            mode, stamp, pending = value.get("state"), value.get("last_sync"), value.get("pending")
            if (type(value.get("version")) is int and value["version"] == _STATE_VERSION
                    and mode in _MODES and (stamp is None or isinstance(stamp, str))
                    and isinstance(pending, bool)):
                return _State(mode, stamp, pending)
    except (ValueError, RecursionError):
        pass
    raise MycelError(ErrorCode.IO, "The Hub state record cannot be read.")


_CODEX_ASSIGNMENT = re.compile(
    r"""^[ \t]*(developer_instructions|'developer_instructions'|"(?:[^"\\\r\n]|\\.)*")[ \t]*=""",
    re.MULTILINE,
)
_LINE_END = re.compile(r"\r?\n|\Z")
_COMMENT = re.compile(r"#")


def _try_toml(text: str) -> dict | None:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def _codex_assignment(text: str, old: str, without_key: dict) -> tuple[int, int, str, str]:
    """Find the assignment whose removal leaves exactly the rest of the parsed config."""
    wanted = {_CODEX_KEY: old}
    for start in _CODEX_ASSIGNMENT.finditer(text):
        if _try_toml(f"{start[1]} = true") != {_CODEX_KEY: True}:
            continue
        for ending in _LINE_END.finditer(text, start.end()):
            assignment = _try_toml(text[start.start():ending.end()])
            if assignment is None:
                continue
            if assignment == wanted and _try_toml(text[:start.start()] + text[ending.end():]) == without_key:
                last_line = text.rfind("\n", start.end(), ending.start()) + 1
                for mark in _COMMENT.finditer(text, max(last_line, start.end()), ending.start()):
                    prefix = text[start.start():mark.start()]
                    if _try_toml(prefix) == wanted:
                        suffix = text[start.start() + len(prefix.rstrip(" \t")):ending.start()]
                        return start.start(), ending.end(), suffix, ending[0]
                return start.start(), ending.end(), "", ending[0]
            break
    raise MycelError(ErrorCode.REFUSED, "The top-level Codex Hub setting could not be edited safely.")


def _codex_copy(before: str, value: str | None) -> str:
    expected = _codex_config(before)
    old = expected.pop(_CODEX_KEY, None)
    if old == value:
        return before
    if old is not None and not isinstance(old, str):
        raise MycelError(ErrorCode.REFUSED, "The top-level Codex Hub setting is not a string.")
    line = ""
    if value is not None:
        literal = json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
        line = f"{_CODEX_KEY} = {literal}"
    if old is None:
        after = line + "\n" + before
    else:
        first, last, comment, ending = _codex_assignment(before, old, expected)
        replacement = line + comment
        after = before[:first] + (replacement + ending if replacement else "") + before[last:]
    if value is not None:
        expected[_CODEX_KEY] = value
    if _codex_config(after) != expected:
        raise MycelError(ErrorCode.REFUSED, "Editing the Hub would change another Codex setting.")
    return after


def _with_header(hub: str) -> str:
    normalized = hub.replace("\r\n", "\n")
    if normalized.startswith("---\n"):
        end = normalized.find("\n---\n", 4)
        if end != -1:
            normalized = normalized[end + 5:]
    return _HEADER + normalized.strip() + "\n"


@dataclass(frozen=True)
class _Change:
    path: Path
    previous: _File | None
    contents: bytes
    initial_mode: int
    backup: Path

    @property
    def mode(self) -> int:
        return self.previous.mode if self.previous is not None else self.initial_mode


def _copy_changes(paths: _Paths, mode: str) -> list[_Change]:
    source = _read(paths.source) if mode == "on" else None
    if mode == "on" and source is None:
        raise MycelError(ErrorCode.IO, "The Instructions Hub source could not be read.")
    headed = _with_header(_text(source)) if source is not None else None
    active, codex, agents = _read(paths.active), _read(paths.codex), _read(paths.agents)
    encoded = b"" if headed is None else headed.encode("utf-8")
    backup = paths.root / "backups"
    changes = [
        _Change(paths.active, active, source.contents if source is not None else b"", 0o644, backup / "active.md"),
        _Change(paths.agents, agents, encoded, 0o644, backup / "agents-AGENTS.md"),
    ]
    if codex is not None or headed is not None:
        replacement = _codex_copy(_text(codex), headed).encode("utf-8")
        changes.append(_Change(paths.codex, codex, replacement, 0o600, backup / "codex-config.toml"))
    return [change for change in changes if change.previous is None or change.contents != change.previous.contents]


def _temporary(path: Path, contents: bytes, mode: int) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    scratch = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise
    return scratch


def _backup(change: _Change) -> None:
    if change.previous is None or change.backup.exists():
        return
    scratch = _temporary(change.backup, change.previous.contents, 0o600)
    try:
        os.link(scratch, change.backup)
    except FileExistsError:
        pass
    else:
        _fsync_parent(change.backup)
    finally:
        scratch.unlink(missing_ok=True)


@contextmanager
def _staged_copies(changes: list[_Change]):
    with ExitStack() as cleanup:
        staged = []
        for change in changes:
            scratch = _temporary(change.path, change.contents, change.mode)
            cleanup.callback(scratch.unlink, missing_ok=True)
            _backup(change)
            staged.append((change, scratch))
        yield staged


def _read_state(paths: _Paths) -> _State:
    return _saved_state(paths) or _adopt_state(paths)


@contextmanager
def _hub_lock(paths: _Paths):
    paths.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(paths.root / "sync.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MycelError(ErrorCode.BUSY, "Another invocation is syncing the Instructions Hub.") from None
        yield
    finally:
        os.close(descriptor)


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace(scratch: Path, path: Path) -> None:
    os.replace(scratch, path)
    _fsync_parent(path)


def _save_state(paths: _Paths, state: _State) -> None:
    payload = {"version": _STATE_VERSION, **state.reply()}
    scratch = _temporary(paths.state, (json.dumps(payload) + "\n").encode("utf-8"), 0o600)
    try:
        _replace(scratch, paths.state)
    finally:
        scratch.unlink(missing_ok=True)


def _apply_mode(paths: _Paths, state: _State, mode: str) -> _State:
    if _imports(paths) != {_ACTIVE_IMPORT}:
        raise MycelError(ErrorCode.REFUSED, "Complete the Claude Code Hub import cutover before switching modes.")
    changes = _copy_changes(paths, mode)
    with _staged_copies(changes) as staged:
        for change, _ in staged:
            _require_unchanged(change)
        if changes:
            _save_state(paths, _State(mode, state.last_sync, pending=True))
        for change, scratch in staged:
            _require_unchanged(change)
            _replace(scratch, change.path)
    settled = _State(mode, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _save_state(paths, settled)
    return settled


def _require_unchanged(change: _Change) -> None:
    if _read(change.path) != change.previous:
        raise MycelError(ErrorCode.BUSY, "A Hub copy changed while it was being prepared. Retry the sync.")


def _switch(paths: _Paths, mode: str) -> _State:
    with _hub_lock(paths):
        return _apply_mode(paths, _saved_state(paths) or _State(mode), mode)


def _refresh_copies(paths: _Paths) -> _State:
    with _hub_lock(paths):
        state = _read_state(paths)
        if state.pending or state.mode == "on":
            return _apply_mode(paths, state, state.mode)
        return state


def _sync(paths: _Paths, settings: SettingsSnapshot) -> dict:
    """One scheduled pass keeps the Hub copies and Cue Card catalog current."""
    from ._cues import compile_catalog

    state, copy_problem = None, None
    try:
        state = _refresh_copies(paths)
    except MycelError as error:
        copy_problem = error
    except (OSError, UnicodeError):
        copy_problem = MycelError(ErrorCode.IO, "The Instructions Hub copies could not be synced.")
    catalog = compile_catalog(settings)
    if copy_problem is not None:
        raise copy_problem from None
    assert state is not None
    return {"hub": state.reply(), "catalog": catalog}
