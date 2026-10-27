"""One read-only, validated settings snapshot per command invocation.

This module only reads local data. Repository membership and folder availability
are resolved by the repository layer; credentials belong to their own adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from difflib import get_close_matches
from importlib.resources import files
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
import tomllib
from typing import Any, TypedDict
from urllib.parse import parse_qsl, unquote, urlsplit

from ._errors import ErrorCode, MycelError


class SettingsFault(TypedDict, total=False):
    key: str
    line: int
    message: str


class SettingsReport(TypedDict):
    file: str
    exists: bool
    readable: bool
    unknownKeys: list[str]
    faults: list[SettingsFault]


@dataclass(frozen=True)
class _Fault:
    message: str
    key: str | None = None
    line: int | None = None
    unknown: bool = False
    missing_store: bool = False

    def report(self) -> SettingsFault:
        result: SettingsFault = {"message": self.message}
        if self.key is not None:
            result["key"] = self.key
        if self.line is not None:
            result["line"] = self.line
        return result


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(member) for key, member in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(member) for member in value)
    return value


@dataclass(frozen=True)
class SettingsSnapshot:
    file: Path
    values: Mapping[str, Any] = field(repr=False)
    exists: bool
    readable: bool
    _faults: tuple[_Fault, ...] = field(default=(), repr=False)
    _home: Path | None = field(default=None, compare=False, repr=False)
    _cwd: Path | None = field(default=None, compare=False, repr=False)

    @property
    def valid(self) -> bool:
        return self.exists and self.readable and not self._faults

    def report(self) -> SettingsReport:
        """Return a fresh JSON-ready diagnostic copy without supplied values."""
        return {
            "file": str(self.file),
            "exists": self.exists,
            "readable": self.readable,
            "unknownKeys": [fault.key for fault in self._faults
                            if fault.unknown and fault.key is not None],
            "faults": [fault.report() for fault in self._faults],
        }

    def require_valid(self, require_store: bool = True) -> None:
        faults = tuple(fault for fault in self._faults
                       if require_store or not fault.missing_store)
        if not self.exists or not self.readable or faults:
            details = []
            for fault in faults:
                location = fault.key or "settings"
                if fault.line is not None:
                    location += f" (line {fault.line})"
                details.append(f"{location}: {fault.message}")
            if not details:
                details.append("settings file is unavailable")
            raise MycelError(ErrorCode.SETTINGS,
                             f"Settings file {self.file}: " + "; ".join(details))

    def require_current(self) -> None:
        """Guard mutation inputs using the original path normalization home.

        Formatting changes may preserve the effective settings; changed or
        unreadable settings cannot authorize a write from an older snapshot.
        This reads only the single settings file and exposes none of its values.
        """
        self.require_valid(require_store=False)
        current = load_settings(path=self.file, home=self._home)
        try:
            current.require_valid(require_store=False)
        except MycelError:
            raise MycelError(ErrorCode.INVALID_INPUT, "The settings changed during publication.") from None
        if current.values != self.values:
            raise MycelError(ErrorCode.INVALID_INPUT, "The settings changed during publication.")


_DEFAULTS = {
    "store": {},
    "embedding": {"model": "voyage-code-4", "dimensions": 1024, "attempts": 5},
    "scan": {},
    "search": {"freshness_seconds": 5},
    "discussions": {},
    "drifts": {"debounce_seconds": 300, "model": "jev-1.13.0",
               "confidence_floor": 0.7, "candidates": 100, "at_once": 2,
               "seconds": 300, "jev_timeout_seconds": 10,
               "review_timeout_seconds": 120, "attempts": 2,
               "max_input_bytes": 24000, "review_max_input_bytes": 1048576,
               # Without a reviewer, the probability of the label with an
               # effect must reach the question's floor (SYL-289).
               "origin_floor": 0.5, "conformance_floor": 0.5, "consistency_floor": 0.5,
               "ambiguity_floor": 0.5},
    "summaries": {"at_once": 4},
    "organizations": {},
    "repos": {},
}
_SCHEMA = {
    "store": {"address": "address"},
    "embedding": {"model": "text", "dimensions": "positive_int",
                  "key_command": "texts", "attempts": "positive_int"},
    "scan": {"document_endings": "texts", "code_endings": "texts", "skip_folders": "texts"},
    "search": {"shared_documents": "shared_documents", "freshness_seconds": "positive_number"},
    "discussions": {"address": "address"},
    "drifts": {"debounce_seconds": "nonnegative_int", "model": "jev_model",
               "confidence_floor": "fraction", "candidates": "positive_int",
               "at_once": "positive_int", "seconds": "positive_number",
               "jev_timeout_seconds": "positive_number", "review_timeout_seconds": "positive_number",
               "attempts": "positive_int", "max_input_bytes": "positive_int",
               "review_max_input_bytes": "positive_int", "origin_floor": "fraction",
               "conformance_floor": "fraction", "consistency_floor": "fraction", "ambiguity_floor": "fraction",
               "review_command": "review_command",
               "review_provider": "identity", "review_model": "review_model",
               "review_revision": "revision"},
    "summaries": {"command": "texts", "at_once": "positive_int", "instructions": "folder"},
}
_ORGANIZATION_SCHEMA = {"root": "folder", "artifact_root": "folder"}
_REPO_SCHEMA = {"enabled": "boolean", "code_root": "folder", "artifact_root": "folder",
                "code_subdirs": "relative_paths", "code_clones": "folders",
                "readonly_root": "folder", "test_patterns": "texts",
                "generated_patterns": "texts", "evaluation": "relative_path"}
_REVIEW_FIELDS = ("review_command", "review_provider", "review_model", "review_revision")
_JEV_MODEL = re.compile(r"jev-[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}\Z", re.ASCII)


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(member) for key, member in value.items()}
    if isinstance(value, list):
        return [_copy(member) for member in value]
    return value


def _defaults() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read packaged default data without registering any repository."""
    data = json.loads(files("mycel").joinpath("data/settings-defaults.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("invalid packaged settings defaults")
    settings = _copy(_DEFAULTS)
    settings["scan"].update(data["scan"])
    settings["search"].update(data["search"])
    repositories = {"enabled": False, "code_subdirs": [], **data["repositories"]}
    return settings, repositories


def _qualified(path: tuple[str | int, ...]) -> str:
    result = ""
    for member in path:
        if isinstance(member, int):
            result += f"[{member}]"
        else:
            name = member if re.fullmatch(r"[A-Za-z0-9_-]+", member) else json.dumps(member)
            result += ("." if result else "") + name
    return result


@dataclass(frozen=True)
class _Token:
    text: str
    line: int
    quoted: bool = False


def _tokens(source: str) -> list[_Token]:
    """Locate TOML keys while skipping comments and whole string values."""
    result = []
    offset, line = 0, 1
    while offset < len(source):
        char = source[offset]
        if char in " \t\r":
            offset += 1
        elif char == "\n":
            result.append(_Token("\n", line))
            line += 1
            offset += 1
        elif char == "#":
            ending = source.find("\n", offset)
            offset = len(source) if ending < 0 else ending
        elif char in "'\"":
            start, start_line = offset, line
            delimiter = char * (3 if source.startswith(char * 3, offset) else 1)
            offset += len(delimiter)
            while offset < len(source):
                if source.startswith(delimiter, offset):
                    offset += len(delimiter)
                    # TOML permits one or two final quotes in multiline strings.
                    if len(delimiter) == 3:
                        while offset < len(source) and source[offset] == char:
                            offset += 1
                    break
                if source[offset] == "\n":
                    line += 1
                if char == '"' and source[offset] == "\\":
                    offset += 1
                    if offset < len(source) and source[offset] == "\n":
                        line += 1
                offset += 1
            result.append(_Token(source[start:offset], start_line, True))
        elif char in "[]{}.,=":
            result.append(_Token(char, line))
            offset += 1
        else:
            start = offset
            while offset < len(source) and source[offset] not in " \t\r\n#'\"[]{}.,=":
                offset += 1
            result.append(_Token(source[start:offset], line))
    return result


def _key_parts(tokens: list[_Token]) -> tuple[str, ...]:
    parts = []
    for token in tokens:
        if token.text == ".":
            continue
        if token.quoted:
            parts.append(tomllib.loads("key = " + token.text)["key"])
        else:
            parts.append(token.text)
    return tuple(parts)


def _key_lines(source: str) -> dict[tuple[str | int, ...], int]:
    """Index dotted, quoted, inline and array-table keys without re-reading."""
    tokens = _tokens(source)
    positions: dict[tuple[str | int, ...], int] = {}
    array_tables: dict[tuple[str | int, ...], int] = {}

    def remember(path: tuple[str | int, ...], line: int) -> None:
        # Implicit parent tables are also fully qualified schema keys.
        for length in range(1, len(path) + 1):
            positions.setdefault(path[:length], line)

    def current_array_members(path: tuple[str, ...]) -> tuple[str | int, ...]:
        expanded: tuple[str | int, ...] = ()
        for part in path:
            expanded += (part,)
            if expanded in array_tables:
                expanded += (array_tables[expanded],)
        return expanded

    def value(index: int, path: tuple[str | int, ...]) -> int:
        while index < len(tokens) and tokens[index].text == "\n":
            index += 1
        if index >= len(tokens):
            return index
        if tokens[index].text == "{":
            index += 1
            while index < len(tokens) and tokens[index].text != "}":
                if tokens[index].text in {",", "\n"}:
                    index += 1
                    continue
                start = index
                while index < len(tokens) and tokens[index].text != "=":
                    index += 1
                child = path + _key_parts(tokens[start:index])
                remember(child, tokens[start].line)
                index = value(index + 1, child)
            return index + 1
        if tokens[index].text == "[":
            index += 1
            member = 0
            while index < len(tokens) and tokens[index].text != "]":
                if tokens[index].text in {",", "\n"}:
                    index += 1
                    continue
                index = value(index, path + (member,))
                member += 1
            return index + 1
        while index < len(tokens) and tokens[index].text not in {"\n", ",", "]", "}"}:
            index += 1
        return index

    index, table = 0, ()
    while index < len(tokens):
        if tokens[index].text == "\n":
            index += 1
            continue
        if tokens[index].text == "[":
            start = index
            is_array = index + 1 < len(tokens) and tokens[index + 1].text == "["
            index += 2 if is_array else 1
            key_start = index
            while index < len(tokens) and tokens[index].text != "]":
                index += 1
            path = _key_parts(tokens[key_start:index])
            index += 2 if is_array else 1
            if is_array:
                array_path = current_array_members(path[:-1]) + (path[-1],)
                count = array_tables.get(array_path, -1) + 1
                array_tables[array_path] = count
                table = array_path + (count,)
            else:
                table = current_array_members(path)
            remember(table, tokens[start].line)
            continue
        start = index
        while index < len(tokens) and tokens[index].text != "=":
            index += 1
        path = table + _key_parts(tokens[start:index])
        remember(path, tokens[start].line)
        index = value(index + 1, path)
    return positions


def _relative_path(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and "\0" not in value
            and not value.startswith("~") and not PurePosixPath(value).is_absolute()
            and ".." not in PurePosixPath(value).parts)


def _folder(value: str, home: Path) -> str | None:
    if not value or "\0" in value:
        return None
    if value == "~":
        value = str(home)
    elif value.startswith("~/"):
        value = str(home / value[2:])
    elif value.startswith("~"):
        return None
    return value if Path(value).is_absolute() else None


def _store_address_fault(address: str) -> str | None:
    # This first address contract accepts explicit PostgreSQL URIs. libpq
    # service/passfile/keyword forms can introduce other credential sources.
    # Even an empty password field is a forbidden plaintext credential field.
    if re.search(r"(?:^|\s)password\s*=", address, re.IGNORECASE):
        return "Store address must not contain a password; use the Mycel store-password Keychain item."
    try:
        parsed = urlsplit(address)
        if parsed.password is not None:
            return "Store address must not contain a password; use the Mycel store-password Keychain item."
        options = parse_qsl(parsed.query, keep_blank_values=True)
        if any(unquote(key).lower() in {"password", "passfile", "service", "servicefile"}
               for key, _ in options):
            return "Store credentials must come from the Mycel store-password Keychain item; password, passfile and service options are unsupported."
        database = unquote(parsed.path).removeprefix("/")
        if (parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname
                or not parsed.username or not database or "/" in database
                or "#" in address or re.search(r"[\x00-\x20\x7f]", address)
                or (parsed.port is not None and parsed.port < 1)):
            return "Expected a PostgreSQL URI naming user, host and database, with an optional port."
        if any(key not in {"sslmode", "connect_timeout"} for key, _ in options):
            return "Unsupported store URI option. Accepted options: sslmode, connect_timeout."
    except ValueError:
        return "Expected a PostgreSQL URI naming user, host and database, with an optional port."
    return None


def _models() -> Mapping[str, Any]:
    catalog = json.loads(files("mycel").joinpath("data/embedding-models.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("models"), dict):
        raise ValueError("invalid packaged embedding model catalog")
    return catalog["models"]


class _Validator:
    def __init__(self, source: str, home: Path, defaults: dict[str, Any],
                 repository_defaults: dict[str, Any]):
        self.lines = _key_lines(source)
        self.home = home
        self.defaults = defaults
        self.repository_defaults = repository_defaults
        self.faults: list[_Fault] = []

    def fault(self, path: tuple[str | int, ...], message: str, *,
              unknown: bool = False, missing_store: bool = False) -> None:
        self.faults.append(_Fault(message, _qualified(path), self.lines.get(path),
                                  unknown=unknown, missing_store=missing_store))

    def unknown(self, path: tuple[str | int, ...], value: Any, accepted: tuple[str, ...]) -> None:
        candidates = get_close_matches(str(path[-1]), accepted, n=2, cutoff=0.72)
        correction = (f"Use the supported key {candidates[0]}." if len(candidates) == 1
                      else "Accepted keys: " + ", ".join(accepted) + "." if accepted
                      else "This table is unsupported; remove the key.")
        self.fault(path, "Unsupported settings key. " + correction, unknown=True)
        self.unknown_descendants(path, value)

    def unknown_descendants(self, path: tuple[str | int, ...], value: Any) -> None:
        if isinstance(value, dict):
            for key, member in value.items():
                self.unknown(path + (key,), member, ())
        elif isinstance(value, list):
            for index, member in enumerate(value):
                self.unknown_descendants(path + (index,), member)

    def check(self, path: tuple[str | int, ...], value: Any, kind: str) -> tuple[bool, Any]:
        okay, result = False, value
        message = "Invalid settings value."
        if kind == "text":
            okay, message = isinstance(value, str), "Expected text."
        elif kind in {"identity", "review_model", "revision", "jev_model", "address", "folder"}:
            okay = isinstance(value, str) and bool(value.strip()) and "\0" not in value
            message = "Expected nonempty NUL-free text."
            if okay and kind == "jev_model":
                okay = bool(_JEV_MODEL.fullmatch(value))
                message = "Expected an exact versioned Jev model ID: jev-<major>.<minor>.<patch>."
            elif okay and kind == "revision":
                okay = bool(_REVISION.fullmatch(value))
                message = "Expected 1–128 ASCII letters, digits or . _ : + -, starting with a letter or digit."
            elif okay and kind == "review_model":
                lowered = value.strip().lower()
                okay = (lowered not in {"latest", "current", "default"}
                        and not lowered.endswith(("-latest", ":latest", "/latest")))
                message = "Expected an exact model-version identity, not a moving alias."
            elif okay and kind == "address":
                address_fault = _store_address_fault(value)
                okay = address_fault is None
                if address_fault is not None:
                    message = address_fault
            elif okay and kind == "folder":
                result = _folder(value, self.home)
                okay = result is not None
                message = "Expected an absolute folder path or a path beginning ~/ for the home folder."
        elif kind == "boolean":
            okay, message = type(value) is bool, "Expected true or false."
        elif kind in {"positive_int", "nonnegative_int"}:
            minimum = 1 if kind == "positive_int" else 0
            okay = type(value) is int and value >= minimum
            message = f"Expected a whole number of {minimum} or more; booleans are not integers."
        elif kind in {"positive_number", "fraction"}:
            if type(value) in {int, float}:
                # math.isfinite on a huge Python integer can overflow its cast.
                finite = type(value) is int or math.isfinite(value)
                okay = finite and (value > 0 if kind == "positive_number" else 0 <= value <= 1)
            message = ("Expected a finite number above 0." if kind == "positive_number"
                       else "Expected a finite number from 0 to 1 inclusive.")
        elif kind == "folders":
            okay = isinstance(value, list)
            message = "Expected a list of absolute or ~/ checkout folders."
            if okay:
                result = []
                for index, member in enumerate(value):
                    valid, folder = self.check(path + (index,), member, "folder")
                    if valid:
                        result.append(folder)
        elif kind == "texts":
            okay = isinstance(value, list) and all(isinstance(member, str) for member in value)
            message = "Expected a list of texts."
        elif kind in {"relative_path", "relative_paths"}:
            okay = (_relative_path(value) if kind == "relative_path" else
                    isinstance(value, list) and all(_relative_path(member) for member in value))
            message = "Expected a relative path inside its configured root, without ~, NUL or parent traversal."
        elif kind == "review_command":
            okay = (isinstance(value, list) and bool(value)
                    and all(isinstance(member, str) and bool(member) and "\0" not in member for member in value))
            if okay:
                executable = value[0]
                okay = Path(executable).is_absolute() or executable.startswith("~/")
                if okay:
                    result = [str(self.home / executable[2:]) if executable.startswith("~/") else executable,
                              *value[1:]]
            message = "Expected nonempty NUL-free argv with an absolute executable path or one beginning ~/."
        elif kind == "shared_documents":
            okay = isinstance(value, list)
            message = "Expected a list of tables with repo and paths."
            if okay:
                result = []
                for index, member in enumerate(value):
                    member_path = path + (index,)
                    if not isinstance(member, dict):
                        self.fault(member_path, "Expected a table with repo and paths.")
                        self.unknown_descendants(member_path, member)
                        continue
                    result.append(self.table(member_path, member, {"repo": "identity", "paths": "relative_paths"},
                                             required=("repo", "paths")))
        if not okay:
            self.fault(path, message)
        return okay, result

    def table(self, path: tuple[str | int, ...], supplied: Any, schema: Mapping[str, str], *,
              defaults: Mapping[str, Any] | None = None, required: tuple[str, ...] = ()) -> dict[str, Any]:
        result = _copy(dict(defaults or {}))
        if not isinstance(supplied, dict):
            self.fault(path, "Expected a settings table. Accepted keys: " + ", ".join(schema) + ".")
            self.unknown_descendants(path, supplied)
            return result
        for key, value in supplied.items():
            key_path = path + (key,)
            if key not in schema:
                self.unknown(key_path, value, tuple(schema))
            else:
                okay, checked = self.check(key_path, value, schema[key])
                if okay:
                    result[key] = checked
                else:
                    # Nested keys in a value of the wrong shape are still
                    # unsupported schema members, not silently ignored.
                    self.unknown_descendants(key_path, value)
        for key in required:
            if key not in supplied:
                self.fault(path + (key,), "Required settings key is absent.")
        return result

    def validate(self, supplied: dict[str, Any]) -> dict[str, Any]:
        result = _copy(self.defaults)
        accepted = tuple(_DEFAULTS)
        for table, value in supplied.items():
            if table not in _DEFAULTS:
                self.unknown((table,), value, accepted)
            elif table in {"organizations", "repos"}:
                if not isinstance(value, dict):
                    self.fault((table,), "Expected a table of named settings tables.")
                    self.unknown_descendants((table,), value)
                    continue
                for name, member in value.items():
                    path = (table, name)
                    if table == "organizations":
                        checked = self.table(path, member, _ORGANIZATION_SCHEMA, required=("root",))
                        if "root" in checked and isinstance(member, dict) and "artifact_root" not in member:
                            checked["artifact_root"] = str(self.home / "Artifacts" / Path(checked["root"]).name)
                    else:
                        checked = self.table(path, member, _REPO_SCHEMA,
                                             defaults=self.repository_defaults)
                    result[table][name] = checked
            else:
                result[table] = self.table((table,), value, _SCHEMA[table], defaults=self.defaults[table])
        store = supplied.get("store", {})
        if isinstance(store, dict) and "address" not in store:
            self.fault(("store", "address"), "Required for commands other than info and grep.", missing_store=True)
        embedding = result["embedding"]
        models = _models()
        if embedding["model"] not in models:
            self.fault(("embedding", "model"), "Unsupported embedding model. Supported models: " + ", ".join(models) + ".")
        elif embedding["dimensions"] not in models[embedding["model"]]["dimensions"]:
            dimensions = ", ".join(str(number) for number in models[embedding["model"]]["dimensions"])
            self.fault(("embedding", "dimensions"), "Unsupported model/dimension pair. Supported dimensions for the configured model: " + dimensions + ".")
        drifts = supplied.get("drifts", {})
        if isinstance(drifts, dict):
            present = [key for key in _REVIEW_FIELDS if key in drifts]
            if present and len(present) != len(_REVIEW_FIELDS):
                for key in _REVIEW_FIELDS:
                    if key not in drifts:
                        self.fault(("drifts", key), "Reviewer command, provider, model and revision must be supplied together or all absent.")
        return result


def load_settings(*, path: Path | str | None = None, home: Path | None = None) -> SettingsSnapshot:
    resolved_home = (Path.home() if home is None else Path(home)).absolute()
    selected = path if path is not None else os.environ.get("MYCEL_CONFIG")
    if selected is None:
        settings_file = resolved_home / ".mycel" / "config.toml"
    else:
        text = str(selected)
        if text == "~":
            settings_file = resolved_home
        elif text.startswith("~/"):
            settings_file = resolved_home / text[2:]
        else:
            settings_file = Path(text)
        settings_file = settings_file.absolute()
    default_values, repository_defaults = _defaults()
    defaults = _freeze(_copy(default_values))
    try:
        content = settings_file.read_bytes()
    except FileNotFoundError:
        return SettingsSnapshot(settings_file, defaults, False, False,
                                (_Fault("Settings file does not exist."),))
    except OSError:
        return SettingsSnapshot(settings_file, defaults, True, False,
                                (_Fault("Settings file cannot be read."),))
    try:
        source = content.decode("utf-8")
        supplied = tomllib.loads(source)
    except UnicodeDecodeError as error:
        return SettingsSnapshot(settings_file, defaults, True, False,
                                (_Fault("Settings file is not valid UTF-8 TOML.",
                                        line=content[:error.start].count(b"\n") + 1),))
    except tomllib.TOMLDecodeError as error:
        # The parser's message can include quoted user content. Preserve only
        # its numeric location, never its message or the source line.
        line = getattr(error, "lineno", None)
        if line is None:
            location = re.search(r"\(at line (\d+), column \d+\)", str(error))
            if location:
                line = int(location.group(1))
            elif "at end of document" in str(error):
                line = source.count("\n") + 1
        return SettingsSnapshot(settings_file, defaults, True, False,
                                (_Fault("Settings file is not valid TOML.", line=line),))
    validator = _Validator(source, resolved_home, default_values, repository_defaults)
    values = validator.validate(supplied)
    return SettingsSnapshot(settings_file, _freeze(values), True, True, tuple(validator.faults), resolved_home)
