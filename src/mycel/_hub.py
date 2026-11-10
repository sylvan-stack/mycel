"""Manage the Instructions Hub copies used by new sessions (MYC-21.9–21.11)."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
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


def _read_state(paths: _Paths) -> _State:
    saved = _read(paths.state)
    if saved is None:
        return _adopt_state(paths)
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
