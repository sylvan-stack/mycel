"""Private, bounded in-process PostgreSQL connections from one settings target.

No URI or credential is passed to a child process, a file, an environment or a
diagnostic. libpq receives explicit parameters after ambient PG settings have
been removed under an internal guard and restored on every exit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
import ipaddress
import math
import os
import queue
import selectors
import socket
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

import psycopg
from psycopg import conninfo, pq

from ._credentials import Credentials
from ._errors import ErrorCode, MycelError
from ._settings import _store_address_fault


CONNECTION_TIMEOUT_SECONDS = 5.0
_POLL_SECONDS = 0.05
_ENVIRONMENT_GUARD = threading.RLock()
_REQUIRED_AUTH = "password,md5,scram-sha-256,none"
_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
_UNIT_NETWORK_FORBIDDEN = ContextVar("mycel_unit_network_forbidden", default=False)


@contextmanager
def _forbid_native_network() -> Iterator[None]:
    """Internal automatic-check scope; never selected by settings or CLI."""
    token = _UNIT_NETWORK_FORBIDDEN.set(True)
    try:
        yield
    finally:
        _UNIT_NETWORK_FORBIDDEN.reset(token)


def _unavailable() -> MycelError:
    return MycelError(ErrorCode.STORE_UNAVAILABLE, "The configured store could not be reached or authenticated.")


def _check(deadline: float, cancel_event: threading.Event | None) -> float:
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _unavailable()
    return remaining


def _timeout(value: Any) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = float(value)
        if not math.isfinite(result) or result <= 0:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise MycelError(ErrorCode.SETTINGS, "The store connection timeout must be a finite positive number.") from None
    return min(result, CONNECTION_TIMEOUT_SECONDS)


def _parameters(address: str) -> tuple[dict[str, Any], float]:
    fault = _store_address_fault(address)
    if fault is not None:
        raise MycelError(ErrorCode.SETTINGS, fault)
    parsed = urlsplit(address)
    values = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = values.get("sslmode", "prefer")
    if sslmode not in _SSL_MODES:
        raise MycelError(ErrorCode.SETTINGS, "The store address has an unsupported sslmode.")
    host, user, database = unquote(parsed.hostname), unquote(parsed.username), unquote(parsed.path[1:])
    if any("\0" in member for member in (host, user, database)) or host.startswith("/") or "," in host:
        raise MycelError(ErrorCode.SETTINGS, "The store address must name one NUL-free TCP host, user and database.")
    requested = _timeout(values.get("connect_timeout", CONNECTION_TIMEOUT_SECONDS))
    return {
        "host": host,
        "port": str(parsed.port or 5432),
        "user": user,
        "dbname": database,
        "password": "",
        # libpq warns to native stderr for a non-regular /dev/null passfile.
        # A child of that device cannot exist and causes no warning or read.
        "passfile": os.devnull + "/mycel-passfile",
        "options": "",
        "sslmode": sslmode,
        "sslcertmode": "disable",
        "sslkeylogfile": "",
        "gssencmode": "disable",
        "require_auth": _REQUIRED_AUTH,
    }, requested


def _lookup(host: str, port: int) -> Sequence[str]:
    return tuple(result[4][0] for result in socket.getaddrinfo(
        host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP))


def _host_addresses(host: str, port: int, deadline: float, cancel_event: threading.Event | None,
                    resolver: Callable[[str, int], Sequence[str]]) -> tuple[str, ...]:
    _check(deadline, cancel_event)
    try:
        return (str(ipaddress.ip_address(host)),)
    except ValueError:
        pass
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result = (True, resolver(host, port))
        except BaseException:
            result = (False, None)
        result_queue.put_nowait(result)

    # A timed-out platform resolver cannot be killed. Its daemon is allowed
    # to finish independently, and it has no connection/credential callback.
    worker = threading.Thread(target=resolve, name="mycel-store-dns", daemon=True)
    worker.start()
    while True:
        remaining = _check(deadline, cancel_event)
        try:
            okay, result = result_queue.get(timeout=min(_POLL_SECONDS, remaining))
        except queue.Empty:
            continue
        _check(deadline, cancel_event)
        if not okay:
            raise _unavailable()
        try:
            addresses = {ipaddress.ip_address(value) for value in result}
        except (TypeError, ValueError):
            raise _unavailable() from None
        if not addresses:
            raise _unavailable()
        # Preserve every resolved endpoint. libpq can try another route after
        # a transport failure, while a server authentication refusal ends the
        # attempt. All addresses share the same native polling deadline.
        return tuple(str(address) for address in sorted(addresses,
                     key=lambda address: (address.version, int(address))))


def _ambient_parameter(name: str) -> bool:
    return name.startswith("PG") or name == "SSLKEYLOGFILE"


@contextmanager
def _without_libpq_environment(deadline: float, cancel_event: threading.Event | None) -> Iterator[None]:
    while not _ENVIRONMENT_GUARD.acquire(timeout=min(_POLL_SECONDS, _check(deadline, cancel_event))):
        pass
    saved = None
    try:
        saved = {name: value for name, value in os.environ.items() if _ambient_parameter(name)}
        _check(deadline, cancel_event)
        for name in saved:
            os.environ.pop(name, None)
        yield
    finally:
        if saved is not None:
            for name in tuple(os.environ):
                if _ambient_parameter(name):
                    os.environ.pop(name, None)
            os.environ.update(saved)
        _ENVIRONMENT_GUARD.release()


def _native_connect(*, timeout_seconds: float, cancel_event: threading.Event | None = None,
                    _pgconn_factory: Callable[[bytes], Any] | None = None,
                    _connection_factory: Callable[[Any], Any] | None = None,
                    **parameters: Any) -> psycopg.Connection:
    """Poll libpq without DNS or an uninterruptible minimum timeout."""
    if _UNIT_NETWORK_FORBIDDEN.get() and _pgconn_factory is None:
        raise RuntimeError("network access is forbidden in an automatic unit check")
    deadline = time.monotonic() + timeout_seconds
    _check(deadline, cancel_event)
    connection = None
    pgconn = None
    try:
        # make_conninfo only quotes explicit in-process parameters. No URI
        # parser, environment service, passfile or hidden address is involved.
        private_conninfo = conninfo.make_conninfo("", **parameters)
        _check(deadline, cancel_event)
        pgconn = (_pgconn_factory or pq.PGconn.connect_start)(private_conninfo.encode("utf-8"))
        while True:
            remaining = _check(deadline, cancel_event)
            status = pgconn.connect_poll()
            if status == pq.PollingStatus.OK:
                _check(deadline, cancel_event)
                pgconn.nonblocking = 1
                connection = (_connection_factory or psycopg.Connection)(pgconn)
                connection.autocommit = True
                return connection
            if status == pq.PollingStatus.FAILED:
                # Preserve just enough native state for the outer boundary to
                # detect a real server password challenge before closing it.
                raise psycopg.OperationalError("The store connection failed.", pgconn=pgconn)
            if status not in {pq.PollingStatus.READING, pq.PollingStatus.WRITING}:
                raise _unavailable()
            event = selectors.EVENT_READ if status == pq.PollingStatus.READING else selectors.EVENT_WRITE
            with selectors.DefaultSelector() as selector:
                selector.register(pgconn.socket, event)
                selector.select(timeout=min(_POLL_SECONDS, _check(deadline, cancel_event)))
    except psycopg.OperationalError as error:
        # The outer boundary examines needs_password and owns this failed
        # PGconn. Other exits below finish it before they propagate.
        if pgconn is not None and getattr(error, "pgconn", None) is not pgconn:
            pgconn.finish()
        raise
    except BaseException:
        if pgconn is not None:
            pgconn.finish()
        raise


def _close_connection(connection: Any) -> None:
    try:
        connection.close()
    except Exception:
        # Closing must not copy native error bodies or credentials into an
        # otherwise successful or already failing operation's output.
        try:
            connection.pgconn.finish()
        except Exception:
            pass


def _finish_failed(error: BaseException) -> bool:
    pgconn = getattr(error, "pgconn", None)
    needs_password = False
    if pgconn is not None:
        try:
            needs_password = isinstance(error, psycopg.OperationalError) and bool(pgconn.needs_password)
        except Exception:
            pass
        finally:
            try:
                pgconn.finish()
            except Exception:
                pass
    return needs_password


def _attempt(parameters: dict[str, Any], deadline: float, cancel_event: threading.Event | None,
             connector: Callable[..., Any]) -> tuple[Any | None, bool]:
    try:
        with _without_libpq_environment(deadline, cancel_event):
            remaining = _check(deadline, cancel_event)
            parameters = {**parameters, "connect_timeout": str(max(1, math.ceil(remaining)))}
            connection = connector(timeout_seconds=remaining, cancel_event=cancel_event, **parameters)
            try:
                _check(deadline, cancel_event)
            except BaseException:
                _close_connection(connection)
                raise
            return connection, False
    except KeyboardInterrupt:
        raise
    except Exception as error:
        return None, _finish_failed(error)


@contextmanager
def store_connection(credentials: Credentials, *, timeout_seconds: float = CONNECTION_TIMEOUT_SECONDS,
                     cancel_event: threading.Event | None = None,
                     _connector: Callable[..., Any] | None = None,
                     _resolver: Callable[[str, int], Sequence[str]] | None = None) -> Iterator[psycopg.Connection]:
    """Connect without a password first, then acquire one only when challenged.

    Test seams inject memory-only connectors/resolvers. Runtime uses native
    libpq in this process. The successful connection closes on every exit.
    """
    timeout_seconds = _timeout(timeout_seconds)
    _check(time.monotonic() + timeout_seconds, cancel_event)
    target = credentials.store_target()
    parameters, requested = _parameters(target.address)
    deadline = time.monotonic() + min(timeout_seconds, requested)
    addresses = _host_addresses(parameters["host"], int(parameters["port"]), deadline,
                                cancel_event, _resolver or _lookup)
    parameters["hostaddr"] = ",".join(addresses)
    parameters["host"] = ",".join(parameters["host"] for _ in addresses)
    connection, password_requested = _attempt(parameters, deadline, cancel_event, _connector or _native_connect)
    if connection is None and password_requested:
        remaining = _check(deadline, cancel_event)
        try:
            selected = credentials.store_target(password_requested=True, timeout_seconds=remaining,
                                                cancelled=cancel_event.is_set if cancel_event is not None else None)
        except MycelError:
            raise
        except Exception:
            raise _unavailable() from None
        _check(deadline, cancel_event)
        if selected.address != target.address:
            raise MycelError(ErrorCode.SETTINGS, "The store target changed during credential acquisition.")
        if selected.password is not None:
            parameters = {**parameters, "password": selected.password.reveal()}
            connection, _ = _attempt(parameters, deadline, cancel_event, _connector or _native_connect)
    if connection is None:
        raise _unavailable() from None
    try:
        yield connection
    finally:
        _close_connection(connection)
