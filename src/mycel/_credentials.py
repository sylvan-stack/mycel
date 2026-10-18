"""Lazy, private credential acquisition for internal provider/store adapters.

Only the in-process adapter that needs a credential may reveal it. Child
programs run through the bounded transport with a new, complete environment;
neither a store target nor a credential is an input to that transport.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import getpass
import math
from pathlib import Path
import warnings

from ._errors import MycelError
from ._safeguards import (
    ChildProcessFailure, CompletedChild, InvocationPolicy, require_model_call,
    resolve_command, run_child,
)
from ._settings import SettingsSnapshot, _store_address_fault


SECURITY = "/usr/bin/security"
KEYCHAIN_SERVICE = "mycel"
_ACCOUNTS = {
    "embedding": "voyage-api-key",
    "store": "store-password",
    "jev": "jev-api-key",
}
CREDENTIAL_TIMEOUT_SECONDS = 10.0
CREDENTIAL_WRITE_TIMEOUT_SECONDS = 60.0
CREDENTIAL_STDOUT_LIMIT = 64 * 1024
CREDENTIAL_STDERR_LIMIT = 4 * 1024
_API_KEY_PURPOSES = {"voyage": "embedding", "jev": "jev"}
_SECURITY_DUPLICATE_ITEM = 45  # errSecDuplicateItem (-25299), as an exit status
_SECURITY_LINE_BYTES = 4096


@dataclass(frozen=True)
class Secret:
    """A private memory-only value whose ordinary formatting never reveals it."""

    _value: str = field(repr=False)

    def __repr__(self) -> str:
        return "Secret(<private>)"

    def __str__(self) -> str:
        return "<private credential>"

    def reveal(self) -> str:
        """Use only at an in-process provider or database connection boundary."""
        return self._value


@dataclass(frozen=True)
class StoreTarget:
    address: str = field(repr=False)
    password: Secret | None = field(default=None, repr=False)

    @property
    def location(self) -> str:
        """The exact specified password-free address for init/info diagnostics."""
        return self.address


class CredentialUnavailable(Exception):
    """A selected classification authentication fault, not a global CLI code."""

    code = "authentication"
    message = "The Jev credential is unavailable."

    def __init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def configured_store_address(settings: SettingsSnapshot) -> str:
    """Use the invocation snapshot alone, never libpq/legacy environment data."""
    settings.require_valid()
    address = settings.values["store"].get("address")
    if not isinstance(address, str):
        raise MycelError("settings", "The store.address setting is required.")
    # Defend this boundary even if an internal caller constructed a snapshot.
    fault = _store_address_fault(address)
    if fault is not None:
        raise MycelError("settings", fault)
    return address


def _output_secret(result: CompletedChild) -> Secret | None:
    if result.returncode != 0:
        return None
    output = result.stdout
    if output.endswith(b"\r\n"):
        output = output[:-2]
    elif output.endswith((b"\n", b"\r")):
        output = output[:-1]
    try:
        value = output.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return Secret(value) if value and "\0" not in value else None


class Credentials:
    """One invocation's lazy access; retrying work never repeats access prompts."""

    def __init__(
        self, settings: SettingsSnapshot, policy: InvocationPolicy, *,
        home: Path | None = None, timeout_seconds: float = CREDENTIAL_TIMEOUT_SECONDS,
        _runner: Callable[..., CompletedChild] | None = None,
    ):
        self._settings = settings
        self._policy = policy
        self._home = (home or Path.home()).resolve()
        self._timeout_seconds = timeout_seconds
        self._runner = _runner
        self._resolved: dict[str, Secret | None] = {}

    def _read(self, argv: tuple[str, ...], *, timeout_seconds: float | None = None,
              cancelled: Callable[[], bool] | None = None) -> Secret | None:
        try:
            budget = self._timeout_seconds
            if timeout_seconds is not None:
                if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
                    return None
                budget = min(budget, timeout_seconds)
            if isinstance(budget, bool) or not math.isfinite(budget) or budget <= 0:
                return None
            result = (self._runner or run_child)(
                argv, timeout_seconds=budget, home=self._home,
                stdout_limit=CREDENTIAL_STDOUT_LIMIT,
                stderr_limit=CREDENTIAL_STDERR_LIMIT,
                cancelled=cancelled,
            )
        except ChildProcessFailure:
            # OS messages and either child stream can contain arbitrary secret
            # data. Neither is suitable for an operation's diagnostics.
            return None
        return _output_secret(result)

    def _keychain(self, purpose: str, *, timeout_seconds: float | None = None,
                  cancelled: Callable[[], bool] | None = None) -> Secret | None:
        if purpose in self._resolved:
            return self._resolved[purpose]
        account = _ACCOUNTS[purpose]
        # Selecting the login Keychain avoids a search-list fallback to another
        # keychain containing the same service/account identity.
        login = self._home / "Library" / "Keychains" / "login.keychain-db"
        value = self._read((SECURITY, "find-generic-password", "-s", KEYCHAIN_SERVICE,
                            "-a", account, "-w", str(login)), timeout_seconds=timeout_seconds,
                            cancelled=cancelled)
        self._resolved[purpose] = value
        return value

    def store_target(self, *, password_requested: bool = False,
                     timeout_seconds: float | None = None,
                     cancelled: Callable[[], bool] | None = None) -> StoreTarget:
        address = configured_store_address(self._settings)
        # A missing item means no password is sent. The connection layer alone
        # translates a refused/rejected connection to store_unavailable.
        password = self._keychain("store", timeout_seconds=timeout_seconds,
                                  cancelled=cancelled) if password_requested else None
        return StoreTarget(address, password)

    def embedding_key(self) -> Secret | None:
        require_model_call(self._policy, "embedding")
        self._settings.require_valid()
        if "embedding" in self._resolved:
            return self._resolved["embedding"]
        command = self._settings.values["embedding"].get("key_command")
        if command is None:
            return self._keychain("embedding")
        try:
            # Resolve the explicitly named executable only; every subsequent
            # member is literal argv, including shell syntax and leading ~.
            argv = resolve_command(command, home=self._home, allow_path_search=True)
        except ChildProcessFailure:
            self._resolved["embedding"] = None
            return None
        value = self._read(argv)
        self._resolved["embedding"] = value
        return value

    def require_embedding_key(self) -> Secret:
        key = self.embedding_key()
        if key is None:
            raise MycelError("refused", "The embedding credential is unavailable.")
        return key

    def jev_key(self, *, timeout_seconds: float | None = None,
                cancelled: Callable[[], bool] | None = None) -> Secret | None:
        require_model_call(self._policy, "jev")
        self._settings.require_valid()
        return self._keychain("jev", timeout_seconds=timeout_seconds, cancelled=cancelled)

    def require_jev_key(self, *, timeout_seconds: float | None = None,
                        cancelled: Callable[[], bool] | None = None) -> Secret:
        key = self.jev_key(timeout_seconds=timeout_seconds, cancelled=cancelled)
        if key is None:
            raise CredentialUnavailable()
        return key


def prompt_api_key(provider: str) -> Secret:
    """Accept a secret only from a controlling terminal with echo disabled."""
    if provider not in _API_KEY_PURPOSES:
        raise MycelError("invalid_input", "Use mycel api-key voyage|jev.")
    try:
        # getpass opens /dev/tty itself. This preflight and warning guard forbid
        # its fallback to an echoed stdin read when terminal access fails.
        with open("/dev/tty", "w", encoding="utf-8") as terminal:
            if not terminal.isatty():
                raise OSError
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(f"{provider.capitalize()} API key: ", stream=terminal)
    except (OSError, EOFError, getpass.GetPassWarning):
        raise MycelError("invalid_input", "An API key requires a terminal with hidden input.") from None
    if not value or any(not " " <= character <= "~" for character in value):
        raise MycelError("invalid_input", "An API key must be one nonempty line of printable ASCII text.")
    return Secret(value)


def _security_token(value: str) -> str:
    # security's interactive parser is not a shell. Double quotes plus escapes
    # protect spaces, apostrophes, backslashes and quotes in the login path.
    if any(character in value for character in "\0\r\n"):
        raise MycelError("invalid_input", "The Keychain item path is invalid.")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def store_api_key(provider: str, secret: Secret, *, home: Path | None = None,
                  _runner: Callable[..., CompletedChild] | None = None) -> dict:
    """Write one named item without putting the secret in any OS argument."""
    if provider not in _API_KEY_PURPOSES:
        raise MycelError("invalid_input", "Use mycel api-key voyage|jev.")
    value = secret.reveal()
    if not value or any(not " " <= character <= "~" for character in value):
        raise MycelError("invalid_input", "An API key must be one nonempty line of printable ASCII text.")
    user_home = (home or Path.home()).resolve()
    account = _ACCOUNTS[_API_KEY_PURPOSES[provider]]
    login = user_home / "Library" / "Keychains" / "login.keychain-db"
    encoded = value.encode("ascii").hex()
    base = (f"add-generic-password -s {_security_token(KEYCHAIN_SERVICE)} "
            f"-a {_security_token(account)} -T {_security_token(SECURITY)} "
            f"-X {encoded} {_security_token(str(login))}")
    # The native interpreter reads a 4096-byte line. Check the longer update
    # before either attempt, so a long key cannot be split into commands.
    if len((base + " -U\n").encode("utf-8")) >= _SECURITY_LINE_BYTES:
        raise MycelError("invalid_input", "The API key is too long for secure Keychain input.")

    def write(*, update: bool = False) -> CompletedChild:
        # Exactly one command and EOF: a following quit/blank command could
        # overwrite the native interpreter's last-command failure status.
        command = base.replace("add-generic-password", "add-generic-password -U", 1) if update else base
        return (_runner or run_child)((SECURITY, "-q", "-i"), (command + "\n").encode("utf-8"),
            timeout_seconds=CREDENTIAL_WRITE_TIMEOUT_SECONDS, home=user_home,
            stdout_limit=CREDENTIAL_STDOUT_LIMIT, stderr_limit=CREDENTIAL_STDERR_LIMIT)

    try:
        result = write()
        replaced = result.returncode == _SECURITY_DUPLICATE_ITEM
        if replaced:
            result = write(update=True)
        if result.returncode:
            raise ChildProcessFailure("transport")
    except ChildProcessFailure:
        # Neither native output nor an exception can become a CLI diagnostic.
        raise MycelError("refused", "The API key could not be stored in the login Keychain.") from None
    return {"stored": provider, "item": {"service": KEYCHAIN_SERVICE, "account": account},
            "replaced": replaced}
