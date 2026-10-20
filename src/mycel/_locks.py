"""Connection-owned nonblocking locks and explicit transaction preparation.

Identities are allocated by the store, never hashed. Paid work composes an
invocation guard and operation guard, taking a short pass guard only around
input capture or guarded publication. Activity/evidence callers are separate.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

import psycopg
from psycopg import pq

from ._errors import MycelError
from ._deadline import check_deadline, deadline_suspended


# The two-int and single-bigint advisory key spaces are disjoint. Only these
# fixed two-int protocol keys are reserved. Repository/invocation identities
# receive distinct positive bigints from the store's single registry sequence.
STRUCTURE_LOCK = (-2147483648, 0)
ALLOCATOR_LOCK = (-2147483648, 1)


class LockNamespace(StrEnum):
    PASS = "repository.pass"
    EMBED = "repository.embed"
    CLASSIFY = "repository.classify"
    SUMMARIES = "repository.summaries"
    MUTATION = "repository.mutation"
    INVOCATION = "invocation.liveness"


_OPERATIONS = {"pass": LockNamespace.PASS, "embed": LockNamespace.EMBED,
               "classify": LockNamespace.CLASSIFY, "summaries": LockNamespace.SUMMARIES}


def postgres_detail(error) -> str:
    """Name the PostgreSQL error class and SQLSTATE; never its native text.

    Native messages can carry a URI or password; the class and state carry the
    diagnosis, such as QueryCanceled 57014 for a statement timeout.
    """
    if not isinstance(error, psycopg.Error):
        return ""
    state = getattr(error, "sqlstate", None)
    name = type(error).__name__
    return f" (psycopg {name}" + (f", SQLSTATE {state})" if isinstance(state, str) and state else ")")


def _database_failure(error=None) -> MycelError:
    return MycelError("store_unavailable", "The index store could not complete the lock or transaction operation"
                      + postgres_detail(error) + ".")


def _identity(value: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise MycelError("invalid_input", "A store lock identity must be nonempty NUL-free text.")
    return value


def _key(value) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise MycelError("internal", "The store returned an invalid allocated lock key.")
    return value


def _idle(connection) -> None:
    # Beginning inside another transaction cannot promise this helper's own
    # isolation or commit boundary. Product store connections autocommit.
    if connection.autocommit is not True or connection.info.transaction_status != pq.TransactionStatus.IDLE:
        raise MycelError("internal", "A store transaction requires an idle autocommit connection.")


@contextmanager
def _transaction(connection, *, readonly: bool) -> Iterator[None]:
    check_deadline()
    _idle(connection)
    try:
        with connection.transaction():
            if readonly:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL search_path = pg_catalog, public")
            # Try-advisory/NOWAIT provide immediate refusal where PostgreSQL
            # supports it. Uniqueness, foreign-key and relation locks have no
            # universal NOWAIT clause; use its minimum positive timeout. Zero
            # would disable the timeout and allow an unbounded wait.
            connection.execute("SET LOCAL lock_timeout = '1ms'")
            # One statement of a real repository's pass or status can take
            # longer than five seconds on a loaded server: on 20 October 2026
            # three passes and the suite together cancelled `status` and the
            # pass's own counts (QueryCanceled, SQLSTATE 57014). A minute keeps
            # a runaway statement finite without cutting ordinary work (SYL-232).
            connection.execute("SET LOCAL statement_timeout = '60000ms'")
            yield
            check_deadline()
    except (psycopg.errors.LockNotAvailable, psycopg.errors.DeadlockDetected,
            psycopg.errors.SerializationFailure):
        raise MycelError("busy", "Another invocation prevents this transaction; no change was committed.") from None
    except psycopg.Error as error:
        raise _database_failure(error) from None


@contextmanager
def atomic_transaction(connection) -> Iterator[None]:
    """Commit the complete supplied change, or roll it all back on any exit."""
    with _transaction(connection, readonly=False):
        yield


@contextmanager
def snapshot_transaction(connection) -> Iterator[None]:
    """Read one committed state, with writes rejected by PostgreSQL."""
    with _transaction(connection, readonly=True):
        yield


def _unlock(connection, statement: str, parameters, *, preserve_error: bool) -> None:
    if getattr(connection, "closed", False):
        return  # Disconnection has already released every session lock.
    try:
        with deadline_suspended():
            row = connection.execute(statement, parameters).fetchone()
        if row is None or row[0] is not True:
            raise MycelError("internal", "The owning connection could not release its store lock.")
    except (psycopg.Error, MycelError):
        # An unwrapped aborted SQL transaction cannot execute an unlock. End
        # the owning connection rather than retaining a lock after an error.
        try:
            connection.close()
        except Exception:
            try:
                connection.pgconn.finish()
            except Exception:
                pass
        if not preserve_error:
            raise _database_failure() from None


@contextmanager
def _session_guard(connection, key: int | tuple[int, int], *, shared: bool,
                   message: str) -> Iterator[None]:
    acquire = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
    release = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
    parameters = key if isinstance(key, tuple) else (_key(key),)
    placeholders = "%s, %s" if isinstance(key, tuple) else "%s::bigint"
    try:
        row = connection.execute(f"SELECT pg_catalog.{acquire}({placeholders})", parameters).fetchone()
    except psycopg.Error as error:
        raise _database_failure(error) from None
    if row is None or row[0] is not True:
        raise MycelError("busy", message)
    failed = False
    try:
        check_deadline()
        yield
    except BaseException:
        failed = True
        raise
    finally:
        _unlock(connection, f"SELECT pg_catalog.{release}({placeholders})", parameters,
                preserve_error=failed)


@contextmanager
def structure_guard(connection, *, exclusive: bool = False) -> Iterator[None]:
    with _session_guard(connection, STRUCTURE_LOCK, shared=not exclusive,
                        message="Another invocation is changing or using the index structure."):
        yield


@contextmanager
def read_snapshot(connection) -> Iterator[None]:
    """Hold structure stable while a reporting command reads one state."""
    with structure_guard(connection), snapshot_transaction(connection):
        yield


def allocate_key(connection, namespace: LockNamespace | str, identity: str) -> int:
    """Find/allocate one immutable identity without waiting on peer allocators."""
    try:
        namespace = LockNamespace(namespace)
    except (TypeError, ValueError):
        raise MycelError("invalid_input", "The store lock namespace is unsupported.") from None
    identity = _identity(identity)
    select = "SELECT key FROM public.mycel_lock_keys WHERE namespace = %s AND identity = %s"
    parameters = (namespace.value, identity)
    with atomic_transaction(connection):
        row = connection.execute(select, parameters).fetchone()
    if row is not None:
        return _key(row[0])
    with _session_guard(connection, ALLOCATOR_LOCK, shared=False,
                        message="Another invocation is allocating a store lock identity."):
        with atomic_transaction(connection):
            # Recheck after the advisory guard. ON CONFLICT also bounds a
            # concurrent writer that does not follow the advisory protocol.
            row = connection.execute(select, parameters).fetchone()
            if row is None:
                row = connection.execute(
                    "INSERT INTO public.mycel_lock_keys (namespace, identity) VALUES (%s, %s) "
                    "ON CONFLICT (namespace, identity) DO NOTHING RETURNING key", parameters).fetchone()
                if row is None:
                    row = connection.execute(select, parameters).fetchone()
            if row is None:
                raise MycelError("internal", "The store did not allocate the requested lock identity.")
            key = _key(row[0])
        return key


@contextmanager
def _repository_lock(connection, repository: str, namespace: LockNamespace, *, shared: bool,
                     message: str) -> Iterator[int]:
    key = allocate_key(connection, namespace, repository)
    with _session_guard(connection, key, shared=shared, message=message):
        yield key


@contextmanager
def mutation_guard(connection, repository: str) -> Iterator[int]:
    """Protect every operation, owning evidence lease or pin from removal.

    Capture/repin and publication also take operation_guard's short pass lock
    around their atomic transaction, never around a model call.
    """
    repository = _identity(repository)
    with structure_guard(connection), _repository_lock(
            connection, repository, LockNamespace.MUTATION, shared=True,
            message="This repository is being removed by another invocation.") as key:
        yield key


@contextmanager
def removal_guard(connection, repository: str) -> Iterator[int]:
    repository = _identity(repository)
    with structure_guard(connection), _repository_lock(
            connection, repository, LockNamespace.MUTATION, shared=False,
            message="This repository has an active operation or evidence mutation.") as key:
        yield key


@contextmanager
def operation_guard(connection, repository: str, operation: str) -> Iterator[int]:
    try:
        namespace = _OPERATIONS[operation]
    except (KeyError, TypeError):
        raise MycelError("invalid_input", "The repository lock operation is unsupported.") from None
    repository = _identity(repository)
    with mutation_guard(connection, repository), _repository_lock(
            connection, repository, namespace, shared=False,
            message=f"Another {operation} operation is running for this repository.") as key:
        yield key


def require_transaction_guards(connection, repositories: tuple[str, ...]) -> None:
    """Check already-held pass/removal/structure guards without allocating locks.

    Transaction handoffs must acquire guards on an idle connection first.
    Checking the actual granted locks prevents an adapter from accidentally
    publishing through an unguarded caller transaction or a foreign session.
    """
    if (connection.autocommit is not True
            or connection.info.transaction_status != pq.TransactionStatus.INTRANS
            or type(repositories) is not tuple or not repositories):
        raise MycelError("invalid_input", "The handoff requires an active guarded transaction.")
    repositories = tuple(sorted({_identity(name) for name in repositories}))
    structure = connection.execute("""SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
        WHERE locktype='advisory' AND granted AND mode IN ('ShareLock','ExclusiveLock')
          AND pid=pg_catalog.pg_backend_pid() AND classid=2147483648::oid
          AND objid=0::oid AND objsubid=2
          AND database=(SELECT oid FROM pg_catalog.pg_database
                        WHERE datname=pg_catalog.current_database()))""").fetchone()
    held = connection.execute("""SELECT k.namespace,k.identity,l.mode
        FROM public.mycel_lock_keys k JOIN pg_catalog.pg_locks l
          ON l.classid::bigint=(k.key >> 32) AND l.objid::bigint=(k.key & 4294967295)
        WHERE l.locktype='advisory' AND l.objsubid=1 AND l.granted
          AND l.pid=pg_catalog.pg_backend_pid()
          AND l.database=(SELECT oid FROM pg_catalog.pg_database
                          WHERE datname=pg_catalog.current_database())
          AND k.identity=ANY(%s)""", (list(repositories),)).fetchall()
    held = set(held)
    if (structure != (True,) or any(
            (LockNamespace.PASS.value, name, 'ExclusiveLock') not in held
            or not any((LockNamespace.MUTATION.value, name, mode) in held
                       for mode in ('ShareLock', 'ExclusiveLock'))
            for name in repositories)):
        raise MycelError("invalid_input", "The handoff lacks its connection-owned pass/removal guards.")


@dataclass(frozen=True)
class InvocationIdentity:
    id: UUID
    liveness_key: int
    backend_pid: int
    backend_start: datetime
    index_generation: UUID


def _record_invocation(connection, identifier: UUID, key: int) -> InvocationIdentity:
    row = connection.execute(
        "SELECT a.pid, a.backend_start, s.index_generation "
        "FROM pg_catalog.pg_stat_activity a CROSS JOIN public.mycel_store s "
        "WHERE a.pid = pg_catalog.pg_backend_pid() AND s.singleton = true").fetchone()
    if (row is None or type(row[0]) is not int or row[0] <= 0
            or not isinstance(row[1], datetime) or not isinstance(row[2], UUID)):
        raise MycelError("internal", "The store could not identify this invocation's exact session.")
    invocation = InvocationIdentity(identifier, key, *row)
    inserted = connection.execute(
        "INSERT INTO public.mycel_invocations "
        "(id, liveness_key, backend_pid, backend_start, index_generation) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING RETURNING id",
        (identifier, key, *row)).fetchone()
    if inserted is None:
        raise MycelError("invalid_input", "An invocation identifier has already been used.")
    return invocation


@contextmanager
def bootstrap_invocation_guard(connection) -> Iterator[InvocationIdentity]:
    """Register init in its newly created, still uncommitted store.

    The initializer owns the exclusive structure guard and transaction. Its
    ExitStack keeps this session lock until after the schema/audit commit.
    Ordinary invocations must use invocation_guard on an idle connection.
    """
    if connection.info.transaction_status != pq.TransactionStatus.INTRANS:
        raise MycelError("internal", "Initialization liveness requires its schema transaction.")
    row = connection.execute("""SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
        WHERE locktype='advisory' AND mode='ExclusiveLock' AND granted
          AND pid=pg_catalog.pg_backend_pid() AND classid=2147483648::oid
          AND objid=0::oid AND objsubid=2
          AND database=(SELECT oid FROM pg_catalog.pg_database
                        WHERE datname=pg_catalog.current_database()))""").fetchone()
    if row is None or row[0] is not True:
        raise MycelError("internal", "Initialization has no structure guard.")
    identifier = uuid4()
    key = _key(connection.execute(
        "INSERT INTO public.mycel_lock_keys (namespace, identity) VALUES (%s, %s) RETURNING key",
        (LockNamespace.INVOCATION.value, str(identifier))).fetchone()[0])
    with _session_guard(connection, key, shared=False,
                        message="This exact initialization is already running."):
        yield _record_invocation(connection, identifier, key)


@contextmanager
def invocation_guard(connection, *, invocation_id: UUID | str | None = None) -> Iterator[InvocationIdentity]:
    """Hold exact invocation liveness through the final activity transaction.

    The registry/session identity is infrastructure, not an activity entry.
    Activity opens only on an actual operation change. IDs cannot be reused.
    """
    try:
        identifier = uuid4() if invocation_id is None else UUID(str(invocation_id))
    except (TypeError, ValueError, AttributeError):
        raise MycelError("invalid_input", "An invocation identity must be a UUID.") from None
    with structure_guard(connection):
        key = allocate_key(connection, LockNamespace.INVOCATION, str(identifier))
        with _session_guard(connection, key, shared=False,
                            message="This exact invocation is already running."):
            with atomic_transaction(connection):
                invocation = _record_invocation(connection, identifier, key)
            yield invocation


_LIVENESS_SQL = """SELECT EXISTS (
    SELECT 1 FROM public.mycel_invocations i
    JOIN public.mycel_lock_keys k ON k.key = i.liveness_key
    JOIN public.mycel_store s ON s.singleton = true AND s.index_generation = i.index_generation
    JOIN pg_catalog.pg_stat_activity a ON a.pid = i.backend_pid AND a.backend_start = i.backend_start
    JOIN pg_catalog.pg_locks l ON l.pid = a.pid
    WHERE i.id = %s AND k.namespace = 'invocation.liveness' AND k.identity = i.id::text
      AND l.locktype = 'advisory' AND l.mode = 'ExclusiveLock' AND l.granted
      AND l.database = (SELECT oid FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database())
      AND l.classid::bigint = (i.liveness_key >> 32)
      AND l.objid::bigint = (i.liveness_key & 4294967295) AND l.objsubid = 1
)"""


def invocation_is_live(connection, invocation: InvocationIdentity | UUID | str) -> bool:
    """Read granted-lock ownership for this UUID, PID/start and generation."""
    try:
        identifier = invocation.id if isinstance(invocation, InvocationIdentity) else UUID(str(invocation))
    except (TypeError, ValueError, AttributeError):
        raise MycelError("invalid_input", "An invocation identity must be a UUID.") from None
    try:
        row = connection.execute(_LIVENESS_SQL, (identifier,)).fetchone()
    except psycopg.Error:
        raise _database_failure() from None
    if row is None or type(row[0]) is not bool:
        raise MycelError("internal", "The store returned invalid invocation liveness.")
    return row[0]
