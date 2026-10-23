"""Automatic Build checks and explicitly requested on-demand checks.

A check's kind is its class's `check_kind`: `unit` unless the class says
`store`, `eval` or `live`. Which requirement a check rests on is an Origin Link
in the Index Store (MYC-17), not a declaration on the test.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import multiprocessing
import os
from pathlib import Path
import re
import queue
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from typing import Callable, Iterator, Protocol, Sequence
import unittest
from unittest.mock import patch
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit
from uuid import uuid4


KINDS = frozenset({"unit", "store", "eval", "live"})
AUTOMATIC_KINDS = frozenset({"unit", "store"})
REQUIREMENT_ID = re.compile(r"MYC-(?:[0-9]|1[0-7])\.[1-9][0-9]*\Z")
CHECK_DATABASE = re.compile(r"mycel_check_[a-z0-9_]+\Z")
_WORKER_CANCEL_GRACE = 30
_WORKER_TERMINATE_GRACE = 5


class CoverageError(ValueError):
    """A check, its kind or the check run cannot be trusted."""


@dataclass(frozen=True)
class CheckDeclaration:
    requirements: tuple[str, ...]
    kind: str


def iter_checks(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_checks(item)
        elif isinstance(item, unittest.TestCase):
            yield item
        else:
            raise CoverageError("check suite contains an unsupported callable")


def check_kind(check: unittest.TestCase) -> str:
    """The class's `check_kind`, `unit` when the class names none."""
    kind = getattr(check, "check_kind", "unit")
    if kind not in KINDS:
        raise CoverageError(f"unknown check kind: {check.id()}")
    return kind


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: str
    requirements: tuple[str, ...]
    status: str
    detail: str | None = None


@dataclass(frozen=True)
class OnDemandProofs:
    """Executed acceptance bound to one immutable Build."""

    implementation_identity: str
    checks: tuple[CheckResult, ...]


@dataclass(frozen=True)
class CoverageReport:
    checks: tuple[CheckResult, ...]
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors and all(check.status == "passed" for check in self.checks)

    def to_dict(self) -> dict:
        return {"schema_version": 2, "passed": self.passed,
                "checks": [asdict(check) for check in self.checks], "errors": list(self.errors)}


@contextmanager
def no_network():
    """Unit checks fail immediately if Python attempts a network connection."""
    import psycopg
    from ._database import _forbid_native_network

    def refused(*args, **kwargs):
        raise RuntimeError("network access is forbidden in an automatic unit check")

    class RefusedPGconn:
        connect = staticmethod(refused)
        connect_start = staticmethod(refused)

    # Patch mutable Python connection generators as well as public bindings:
    # previously imported psycopg.connect bound methods still reach these.
    with _forbid_native_network(), \
         patch.object(socket, "create_connection", refused), \
         patch.object(socket.socket, "connect", refused), \
         patch.object(socket.socket, "connect_ex", refused), \
         patch.object(socket, "getaddrinfo", refused), \
         patch.object(psycopg.Connection, "connect", refused), \
         patch.object(psycopg.Connection, "_get_connection_params", refused), \
         patch.object(psycopg.Connection, "_connect_gen", refused), \
         patch.object(psycopg.AsyncConnection, "connect", refused), \
         patch.object(psycopg.AsyncConnection, "_get_connection_params", refused), \
         patch.object(psycopg.AsyncConnection, "_connect_gen", refused), \
         patch.object(psycopg, "connect", refused), \
         patch.object(psycopg.pq, "PGconn", RefusedPGconn):
        yield


def require_check_database(name: str) -> str:
    if not isinstance(name, str) or not CHECK_DATABASE.fullmatch(name) or len(name) > 63:
        raise CoverageError("store checks require a database named mycel_check_ followed by a safe unique suffix")
    return name


class StoreBackend(Protocol):
    """Hooks never receive the owner's database address or settings file."""

    real_store: bool

    def address(self, database: str) -> str: ...
    def create_database(self, database: str) -> None: ...
    def initialize(self, settings_file: Path) -> None: ...
    def drop_database(self, database: str) -> None: ...


@dataclass(frozen=True)
class StoreFixture:
    database: str
    settings_file: Path
    root: Path
    backend: StoreBackend


@contextmanager
def disposable_store(backend: StoreBackend, *,
                     initialize: Callable[[StoreBackend, Path], None] | None = None):
    """Create/init/remove one database and privately owned settings per check."""
    database = require_check_database("mycel_check_" + uuid4().hex)
    with tempfile.TemporaryDirectory(prefix="mycel_check_") as directory:
        root = Path(directory)
        config = root / "config.toml"
        address = backend.address(database)
        parsed = urlsplit(address)
        if (parsed.scheme not in {"postgres", "postgresql"} or parsed.password is not None
                or parsed.path != "/" + database or parsed.fragment):
            raise CoverageError("store check backend must address the generated disposable database")
        # A JSON string is also a TOML basic string for a password-free URI.
        config.write_text("[store]\naddress = " + json.dumps(address) + "\n", encoding="utf-8")
        config.chmod(0o600)
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}):
            created = False
            begin_creation = getattr(backend, "_begin_creation", None)
            if begin_creation is not None:
                begin_creation(database)
            try:
                backend.create_database(database)
                created = True
                if initialize is None:
                    backend.initialize(config)
                else:
                    # Test-only bootstraps can prove the gate before product init
                    # exists. Feature fixtures retain the normal Mycel initializer.
                    initialize(backend, config)
                yield StoreFixture(database, config, root, backend)
            finally:
                # A failed CREATE never grants permission to drop an existing
                # database. Native/psql backends can additionally attest an
                # acknowledged creation interrupted before this caller resumed.
                acknowledged = getattr(backend, "creation_owned", lambda name: False)(database)
                if created or acknowledged:
                    backend.drop_database(database)


class PostgresBackend:
    """Optional psql backend; admin connections exclude the owner's database.

    Its address comes from the configured server. Authentication environment and
    user psql startup/password files are not inherited. Local trust or a later
    dedicated test credential adapter can provide server authentication.
    """

    real_store = True

    def __init__(self, owner_address: str, *, psql: str | None = None,
                 init_command: Sequence[str] | None = None):
        parsed = urlsplit(owner_address)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or parsed.password is not None:
            raise CoverageError("store check server must be a password-free PostgreSQL address")
        if parsed.fragment or any(key not in {"sslmode", "connect_timeout"} for key, _ in parse_qsl(parsed.query)):
            raise CoverageError("unsupported store check server URI options")
        owner_database = unquote(parsed.path).removeprefix("/")
        if not owner_database or "/" in owner_database:
            raise CoverageError("store check server address must identify the owner database")
        self._server = parsed
        self._admin = "template1" if owner_database == "postgres" else "postgres"
        self._track_owner(owner_database)
        executable = psql or shutil.which("psql")
        if not executable:
            raise CoverageError("PostgreSQL check runner is unavailable: psql was not found")
        self._psql = str(Path(executable).resolve())
        self._init = tuple(init_command or (sys.executable, "-m", "mycel", "init"))

    def address(self, database: str) -> str:
        self._require_database(database)
        return urlunsplit(self._server._replace(path="/" + database))

    def _track_owner(self, owner_database: str) -> None:
        self._owner_database = owner_database
        # One atomic ownership record also identifies the creating thread and
        # its current attempt. A failed collision cannot inherit an earlier
        # fixture's permission to drop the same name.
        self._owned_databases: dict[str, tuple[int, object]] = {}
        self._creation_attempts: dict[tuple[int, str], object] = {}

    def _require_database(self, database: str, *, owned: bool = False) -> str:
        name = require_check_database(database)
        if name == self._owner_database:
            raise CoverageError("store checks must never target the owner's database")
        if owned and name not in self._owned_databases:
            raise CoverageError("store checks may use or drop only a database this backend created")
        return name

    def _begin_creation(self, database: str) -> None:
        name = self._require_database(database)
        self._creation_attempts[(threading.get_ident(), name)] = uuid4()

    def creation_owned(self, database: str) -> bool:
        name = self._require_database(database)
        identity = threading.get_ident()
        return self._owned_databases.get(name) == (identity, self._creation_attempts.get((identity, name)))

    def _acknowledge_creation(self, database: str) -> None:
        name = self._require_database(database)
        identity = threading.get_ident()
        attempt = self._creation_attempts.get((identity, name))
        if attempt is not None:
            self._owned_databases[name] = (identity, attempt)

    def owns_database(self, database: str) -> bool:
        return self._require_database(database) in self._owned_databases

    def _execute(self, database: str, statement: str, *, administrative: bool = True) -> str:
        self._require_database(database, owned=not administrative)
        address = urlunsplit(self._server._replace(path="/" + self._admin)) if administrative else self.address(database)
        try:
            with tempfile.TemporaryDirectory(prefix="mycel_check_admin_") as directory:
                completed = subprocess.run(
                    [self._psql, "--no-psqlrc", "--no-password", "--tuples-only", "--no-align", "--dbname", address,
                     "--set", "ON_ERROR_STOP=1", "--command", statement],
                    env={"HOME": directory, "LC_ALL": "C", "PGCONNECT_TIMEOUT": "5"},
                    cwd=directory, capture_output=True, timeout=15, check=False,
                )
        except KeyboardInterrupt:
            raise
        except Exception:
            raise RuntimeError("temporary PostgreSQL database operation failed") from None
        if completed.returncode:
            # Provider or authentication bodies never become report content.
            raise RuntimeError("temporary PostgreSQL database operation failed")
        if administrative and statement == f'CREATE DATABASE "{database}"':
            self._acknowledge_creation(database)
        return completed.stdout.decode("utf-8").strip()

    def query(self, database: str, statement: str) -> str:
        """Test SQL is confined to a generated database, never the owner DB."""
        self._require_database(database, owned=True)
        if not isinstance(statement, str) or not statement.strip() or "\\" in statement or "\0" in statement:
            raise CoverageError("test queries require SQL without psql meta-commands")
        return self._execute(database, statement, administrative=False)

    def database_exists(self, database: str) -> bool:
        name = self._require_database(database)
        result = self._execute(name, f"SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{name}')")
        if result not in {"t", "f"}:
            raise RuntimeError("temporary PostgreSQL database presence check failed")
        return result == "t"

    def create_database(self, database: str) -> None:
        name = self._require_database(database)
        self._begin_creation(name)
        if self.database_exists(name):
            raise CoverageError("the generated check database already exists; it was not created or removed")
        try:
            self._execute(name, f'CREATE DATABASE "{name}"')
        except KeyboardInterrupt as error:
            if not self.creation_owned(name):
                error.add_note("Temporary database creation was interrupted before ownership was acknowledged; no unowned database was removed.")
            raise
        except Exception:
            if self.creation_owned(name):
                raise
            try:
                remains = self.database_exists(name)
            except Exception:
                remains = True
            if remains:
                raise CoverageError("Temporary database creation was not acknowledged; a database may remain and was not removed because ownership is unconfirmed.") from None
            raise
        self._acknowledge_creation(name)

    def drop_database(self, database: str) -> None:
        name = self._require_database(database, owned=True)
        self._execute(name, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        del self._owned_databases[name]

    def initialize(self, settings_file: Path) -> None:
        try:
            settings = tomllib.loads(settings_file.read_text(encoding="utf-8"))
            address = settings["store"]["address"]
            name = self._require_database(unquote(urlsplit(address).path[1:]), owned=True)
            if address != self.address(name):
                raise CoverageError("test initializer must use its generated database target")
        except CoverageError:
            raise
        except Exception:
            raise CoverageError("test initializer requires private generated-store settings") from None
        completed = subprocess.run(
            self._init,
            env={"MYCEL_CONFIG": str(settings_file), "HOME": str(settings_file.parent),
                 "PATH": os.defpath, "LC_ALL": "C"},
            cwd=settings_file.parent, capture_output=True, timeout=30, check=False,
        )
        if completed.returncode:
            raise RuntimeError("mycel init failed for the disposable check database")


def _execute_check(check: unittest.TestCase, proof: CheckDeclaration, backend: StoreBackend | None) -> CheckResult:
    result = unittest.TestResult()
    try:
        if proof.kind == "store":
            if backend is None:
                raise CoverageError("store check has no disposable database backend")
            if getattr(backend, "real_store", False) is not True:
                raise CoverageError("a simulated backend cannot qualify a real store check")
            with disposable_store(backend, initialize=getattr(check, "initialize_store", None)) as fixture:
                check.store_fixture = fixture
                unittest.TestSuite([check]).run(result)
        elif proof.kind == "unit":
            with no_network():
                unittest.TestSuite([check]).run(result)
        else:
            unittest.TestSuite([check]).run(result)
    except Exception as error:
        return CheckResult(check.id(), proof.kind, proof.requirements, "failed", f"{type(error).__name__}: {error}")
    problems = result.failures + result.errors
    if problems:
        return CheckResult(check.id(), proof.kind, proof.requirements, "failed", problems[0][1])
    if result.skipped:
        return CheckResult(check.id(), proof.kind, proof.requirements, "skipped", result.skipped[0][1])
    if result.expectedFailures or result.unexpectedSuccesses:
        return CheckResult(check.id(), proof.kind, proof.requirements, "failed", "expected-failure checks cannot prove implementation")
    if result.testsRun != 1:
        return CheckResult(check.id(), proof.kind, proof.requirements, "failed", "check did not execute exactly once")
    return CheckResult(check.id(), proof.kind, proof.requirements, "passed")


def discover_checks(directory: Path | str) -> unittest.TestSuite:
    """Use the same top-level test names as plain unittest discovery."""
    return unittest.TestLoader().discover(str(Path(directory).resolve()))


def select_checks(suite: unittest.TestSuite, selectors: Sequence[str]) -> unittest.TestSuite:
    checks = list(iter_checks(suite))
    if not selectors:
        return unittest.TestSuite(checks)
    selected = []
    for selector in selectors:
        prefix = selector.removesuffix(".py")
        matches = [check for check in checks if check.id() == prefix or check.id().startswith(prefix + ".")]
        if not matches:
            raise CoverageError(f"no checks match {selector}")
        selected.extend(matches)
    names = {check.id(): check for check in selected}
    return unittest.TestSuite(names.values())


def _check_worker(jobs, replies, canceled, directory: str, backend: StoreBackend | None) -> None:
    # Environment and native network policy are process-local. Never use threads
    # to execute checks: fixtures change MYCEL_CONFIG and patch socket/libpq.
    sys.path.insert(0, directory)
    interrupted = False

    def interrupt(signum, frame):
        nonlocal interrupted
        # Product checks deliberately deliver and catch SIGINT. Only a real
        # runner cancellation may suppress repeated signals during cleanup.
        if canceled.value:
            if interrupted:
                return
            interrupted = True
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)

    def watch_cancellation():
        # An Event/Condition can deadlock in notify_all when a crashed process
        # leaves a counted waiter behind. A shared byte has no orphanable lock.
        while not canceled.value:
            time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGINT)

    threading.Thread(target=watch_cancellation, daemon=True).start()
    try:
        while not canceled.value:
            task = jobs.get()
            if task is None:
                return
            index, name, proof = task
            try:
                loaded = list(iter_checks(unittest.TestLoader().loadTestsFromName(name)))
                if len(loaded) != 1 or loaded[0].id() != name or check_kind(loaded[0]) != proof.kind:
                    raise CoverageError("worker did not load the declared check")
                result = _execute_check(loaded[0], proof, backend)
            except KeyboardInterrupt:
                result = CheckResult(name, proof.kind, proof.requirements, "failed", "check interrupted")
                replies.put((index, result))
                return
            except BaseException as error:
                result = CheckResult(name, proof.kind, proof.requirements, "failed",
                                     f"worker could not execute check: {type(error).__name__}")
            replies.put((index, result))
    except KeyboardInterrupt:
        return


def _parallel_checks(selected, backend, workers: int, directory: Path | str):
    context = multiprocessing.get_context("spawn")
    jobs, replies, canceled = context.Queue(), context.Queue(), context.Value("b", False, lock=False)
    processes = [context.Process(target=_check_worker,
                                args=(jobs, replies, canceled, str(Path(directory).resolve()), backend))
                 for _ in range(min(workers, len(selected)))]
    results = {}
    submitted = 0
    try:
        for process in processes:
            process.start()
        for _ in processes:
            check, proof = selected[submitted]
            jobs.put((submitted, check.id(), proof))
            submitted += 1
        while len(results) < len(selected):
            try:
                index, result = replies.get(timeout=0.1)
            except queue.Empty:
                if any(process.exitcode is not None for process in processes):
                    raise CoverageError("check worker exited before returning every named result")
                continue
            check, proof = selected[index]
            if (index in results or result.name != check.id() or result.kind != proof.kind
                    or result.requirements != proof.requirements):
                raise CoverageError("check worker returned a mismatched or repeated result")
            results[index] = result
            if len(selected) >= 100 and len(results) % 100 == 0:
                print(f"Checks: {len(results)}/{len(selected)} complete", file=sys.stderr, flush=True)
            if submitted < len(selected):
                check, proof = selected[submitted]
                jobs.put((submitted, check.id(), proof))
                submitted += 1
        for _ in processes:
            jobs.put(None)
    finally:
        try:
            # A second Ctrl-C must not interrupt cleanup of an acknowledged DB.
            previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                if len(results) != len(selected):
                    canceled.value = True
                deadline = time.monotonic() + _WORKER_CANCEL_GRACE
                for process in processes:
                    if process.pid is not None:
                        process.join(max(0, deadline - time.monotonic()))
                for process in processes:
                    if process.pid is not None and process.is_alive():
                        process.terminate()
                        process.join(_WORKER_TERMINATE_GRACE)
                    if process.pid is not None and process.is_alive():
                        process.kill()
                        process.join(_WORKER_TERMINATE_GRACE)
                    if process.pid is not None and process.is_alive():
                        raise CoverageError("check worker could not be stopped; cleanup requires a stopped worker")
            finally:
                signal.signal(signal.SIGINT, previous)
        finally:
            jobs.cancel_join_thread()
            replies.cancel_join_thread()
            jobs.close()
            replies.close()
    return tuple(results[index] for index in range(len(selected)))


def run_on_demand_checks(checks: Sequence[tuple[unittest.TestCase, str, Sequence[str]]], *,
                         implementation_identity: str) -> OnDemandProofs:
    """Explicitly execute eval/live checks; never called by the Build gate.

    Each check is given with its kind and the requirements it proves. The caller
    supplies the immutable Build manifest identity; the proofs count only for
    that same Build.
    """
    if not isinstance(implementation_identity, str) or not implementation_identity:
        raise CoverageError("on-demand acceptance requires an immutable implementation identity")
    results = []
    seen = set()
    for check, kind, requirements in checks:
        requirements = tuple(requirements)
        if (kind not in {"eval", "live"} or not requirements or len(set(requirements)) != len(requirements)
                or any(not isinstance(identifier, str) or not REQUIREMENT_ID.fullmatch(identifier)
                       for identifier in requirements)):
            raise CoverageError(f"an on-demand check needs an eval or live kind and distinct requirements: {check.id()}")
        if check.id() in seen:
            raise CoverageError(f"duplicate check: {check.id()}")
        seen.add(check.id())
        results.append(_execute_check(check, CheckDeclaration(requirements, kind), None))
    if not results:
        raise CoverageError("no requested on-demand acceptance checks executed")
    return OnDemandProofs(implementation_identity, tuple(results))


def run_checks(suite: unittest.TestSuite, *, store_backend: StoreBackend | None = None,
               kinds: frozenset[str] = AUTOMATIC_KINDS, workers: int = 1,
               tests_directory: Path | str | None = None) -> CoverageReport:
    """Execute every discovered unit and store check by its class kind.

    The automatic gate never selects eval/live checks; those run only when
    explicitly requested through `run_on_demand_checks`.
    """
    if kinds != AUTOMATIC_KINDS:
        raise CoverageError("the Build gate must select every unit and store check, and no eval/live checks")
    if type(workers) is not int or workers < 1:
        raise CoverageError("check workers must be a positive integer")
    if workers > 1 and tests_directory is None:
        raise CoverageError("process workers require the canonical tests directory")
    errors: list[str] = []
    selected: list[tuple[unittest.TestCase, CheckDeclaration]] = []
    seen = set()
    for check in iter_checks(suite):
        name = check.id()
        if name in seen:
            errors.append(f"duplicate check: {name}")
            continue
        seen.add(name)
        try:
            kind = check_kind(check)
        except CoverageError as error:
            errors.append(str(error))
            continue
        if kind in kinds:
            selected.append((check, CheckDeclaration((), kind)))
    results = (_parallel_checks(selected, store_backend, workers, tests_directory)
               if workers > 1 and selected else
               tuple(_execute_check(check, proof, store_backend) for check, proof in selected))
    if not results:
        errors.append("no automatic checks executed")
    return CoverageReport(results, tuple(errors))
