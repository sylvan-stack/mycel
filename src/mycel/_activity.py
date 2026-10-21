"""Internal transaction-bound mutation audit preparation.

The injected caller owns actual feature writes and their operation/pass guards.
This substrate owns removal protection, exact invocation liveness, atomic audit
details and final outcomes. It exposes no product library or command handler.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg import pq
from psycopg.types.json import Jsonb

from ._activity_retention import ActivityRetentionStore
from ._errors import ErrorCode, MycelError
from ._locks import (InvocationIdentity, LockNamespace, atomic_transaction, invocation_guard,
                     invocation_is_live, mutation_guard, read_snapshot)
from ._source_refs import (SourceAddress, SourceAddressError, format_source_address,
                          parse_source_address)
from ._store import checked_store


KINDS = frozenset({"ingest", "embed", "derive", "relate", "confirm", "justify", "origins", "remove", "init",
                   "summaries_build", "summaries_regenerate", "summaries_remove", "classify"})
OUTCOMES = frozenset({"done", "refused", "failed", "stopped"})
EntryKey = tuple[str | None, str]


def _invalid(message: str) -> None:
    raise MycelError("invalid_input", message)


def _text(value: object, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value) or "\0" in value:
        _invalid("Activity labels must be NUL-free text.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        _invalid("Activity labels must be exact UTF-8 text.")
    return value


def _key(repository: str | None, kind: str) -> EntryKey:
    if not isinstance(kind, str) or kind not in KINDS:
        _invalid("The activity kind is unsupported.")
    if (repository is None) != (kind in {"init", "remove"}):
        _invalid("Only init and remove activity belong to no repository.")
    if repository is not None:
        _text(repository)
    return repository, kind


def _json_object(value: object) -> dict:
    if not isinstance(value, Mapping):
        _invalid("Activity counts must be a JSON object.")
    # Copy the complete reply portion now, including nested values. Reject
    # unsupported types/NaN rather than allowing later caller mutation.
    def plain(item):
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                _invalid("Activity JSON object keys must be strings.")
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        if item is None or type(item) in {bool, int, float, str}:
            return item
        _invalid("Activity counts must contain only JSON values.")
    try:
        encoded = json.dumps(plain(value), ensure_ascii=False, allow_nan=False).encode("utf-8")
        result = json.loads(encoded)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _invalid("Activity counts must contain finite exact JSON values.")
    def no_nul(item):
        if isinstance(item, str) and "\0" in item:
            _invalid("Activity JSON text cannot contain NUL.")
        if isinstance(item, dict):
            for key, child in item.items():
                no_nul(key)
                no_nul(child)
        elif isinstance(item, list):
            for child in item:
                no_nul(child)
    no_nul(result)
    return result


def _file(root: str, path: str, location: str) -> None:
    if not isinstance(root, str) or root not in {"code", "artifact"}:
        _invalid("Activity files require a code or artifact root.")
    try:
        format_source_address(SourceAddress("activity", root, path))
    except (SourceAddressError, TypeError):
        _invalid("Activity file paths must be relative qualified paths.")
    _text(location)


@dataclass(frozen=True)
class FileChange:
    root: Literal["code", "artifact"]
    path: str
    location: str
    change: Literal["added", "changed", "removed"]

    def __post_init__(self):
        _file(self.root, self.path, self.location)
        if not isinstance(self.change, str) or self.change not in {"added", "changed", "removed"}:
            _invalid("The activity file change is unsupported.")


@dataclass(frozen=True)
class IdentityChange:
    root: Literal["code", "artifact"]
    path: str
    location: str
    chunk_id: UUID
    decision: Literal["unchanged", "edited", "renamed", "new", "removed"]
    name: str
    previous_name: str | None = None

    def __post_init__(self):
        _file(self.root, self.path, self.location)
        if not isinstance(self.chunk_id, UUID):
            _invalid("An applied identity decision requires its persisted chunk UUID.")
        if not isinstance(self.decision, str) or self.decision not in {"unchanged", "edited", "renamed", "new", "removed"}:
            _invalid("The activity identity decision is unsupported.")
        _text(self.name, empty=True)  # The unnamed introductory document chunk.
        if self.decision == "renamed":
            _text(self.previous_name, empty=True)
        elif self.previous_name is not None:
            _invalid("Only a renamed decision has a previous name.")


@dataclass(frozen=True)
class ClassificationReference:
    bundle: str
    dependant: SourceAddress
    outcome: str

    def __post_init__(self):
        _text(self.bundle)
        _text(self.outcome)
        try:
            format_source_address(self.dependant)
        except (SourceAddressError, TypeError):
            _invalid("A classification detail requires a valid dependant Place.")
        if self.dependant.root is None or self.dependant.name is None:
            _invalid("A classification dependant must identify a qualified chunk.")


@dataclass(frozen=True)
class AppliedMutation:
    """One committed change and its cumulative repository reply counts.

    The caller returns changed=False only when it made no feature write. File
    details describe only added/changed/removed files. Decisions include every
    applied chunk decision, even unchanged chunks in an applied file.
    """
    changed: bool
    counts: Mapping[str, Any] = field(default_factory=dict)
    files: tuple[FileChange, ...] = ()
    decisions: tuple[IdentityChange, ...] = ()
    classifications: tuple[ClassificationReference, ...] = ()

    def __post_init__(self):
        if type(self.changed) is not bool:
            _invalid("An applied mutation must explicitly report whether it changed state.")
        def frozen(value):
            if isinstance(value, dict):
                return MappingProxyType({key: frozen(child) for key, child in value.items()})
            if isinstance(value, list):
                return tuple(frozen(child) for child in value)
            return value
        object.__setattr__(self, "counts", frozen(_json_object(self.counts)))
        for values, item_type in ((self.files, FileChange), (self.decisions, IdentityChange),
                                  (self.classifications, ClassificationReference)):
            if type(values) is not tuple or any(not isinstance(value, item_type) for value in values):
                _invalid("Activity details must be typed immutable tuples.")
        if not self.changed and (self.files or self.decisions or self.classifications):
            _invalid("A no-op mutation cannot contain applied details.")
        file_keys = {(value.root, value.path, value.location) for value in self.files}
        if any((value.root, value.path, value.location) not in file_keys for value in self.decisions):
            _invalid("Identity decisions must belong to a file applied in this transaction.")


def _audit_failure() -> MycelError:
    return MycelError("internal", "The invocation's mutation activity could not be recorded.")


def _execute(connection, sql: str, parameters=None):
    try:
        return connection.execute(sql, parameters)
    except psycopg.Error:
        # Audit failure is part of the command failure, never best-effort logging.
        raise _audit_failure() from None


_BOUND_SQL = """SELECT EXISTS (
    SELECT 1 FROM public.mycel_invocations i
    JOIN pg_catalog.pg_stat_activity a ON a.pid = i.backend_pid AND a.backend_start = i.backend_start
    JOIN public.mycel_store s ON s.singleton = true AND s.index_generation = i.index_generation
    WHERE i.id = %s AND i.liveness_key = %s AND i.backend_pid = %s
      AND i.backend_start = %s AND i.index_generation = %s
      AND a.pid = pg_catalog.pg_backend_pid()
)"""
_ENTRY_SQL = """SELECT id FROM public.mycel_activity
    WHERE invocation = %s AND repository IS NOT DISTINCT FROM %s AND kind = %s
    FOR UPDATE NOWAIT"""
_OPEN_SQL = """INSERT INTO public.mycel_activity
    (repository, invocation, index_generation, kind, trigger, build, started_at, counts)
    VALUES (%s, %s, %s, %s, %s, %s, clock_timestamp(), %s) RETURNING id"""
_COUNTS_SQL = "UPDATE public.mycel_activity SET counts = %s WHERE id = %s AND outcome IS NULL RETURNING id"
_GUARDED_SQL = """SELECT EXISTS (
    SELECT 1 FROM pg_catalog.pg_locks
    WHERE locktype = 'advisory' AND granted AND mode IN ('ShareLock', 'ExclusiveLock')
      AND pid = pg_catalog.pg_backend_pid() AND classid = 2147483648::oid
      AND objid = 0::oid AND objsubid = 2
      AND database = (SELECT oid FROM pg_catalog.pg_database
                      WHERE datname = pg_catalog.current_database())
) AND (%s::text IS NULL OR EXISTS (
    SELECT 1 FROM public.mycel_lock_keys k JOIN pg_catalog.pg_locks l
      ON l.classid::bigint = (k.key >> 32) AND l.objid::bigint = (k.key & 4294967295)
    WHERE k.namespace = %s AND k.identity = %s
      AND l.locktype = 'advisory' AND l.objsubid = 1 AND l.granted
      AND l.mode IN ('ShareLock', 'ExclusiveLock') AND l.pid = pg_catalog.pg_backend_pid()
      AND l.database = (SELECT oid FROM pg_catalog.pg_database
                        WHERE datname = pg_catalog.current_database())
))"""
_CLOSE_ROWS_SQL = "SELECT id, repository, kind FROM public.mycel_activity WHERE invocation = %s AND outcome IS NULL FOR UPDATE NOWAIT"
_CLOSE_SQL = """UPDATE public.mycel_activity SET ended_at = clock_timestamp(), outcome = %s, error = %s,
    counts = COALESCE(%s, counts) WHERE id = %s AND outcome IS NULL RETURNING id"""


class MutationActivity:
    def __init__(self, connection, *, build: int, started_by: str = "command"):
        if type(build) is not int or build <= 0:
            _invalid("Activity requires a positive numeric Build identifier.")
        if not isinstance(started_by, str) or started_by not in {"command", "freshness_check"}:
            _invalid("The activity starter is unsupported.")
        self.connection, self.build, self.started_by = connection, build, started_by
        self.invocation: InvocationIdentity | None = None
        self._closed = False

    @contextmanager
    def session(self, *, invocation_id: UUID | str | None = None) -> Iterator[MutationActivity]:
        """Hold exact liveness until every final outcome transaction completes."""
        if self.invocation is not None:
            raise MycelError("internal", "A mutation activity session cannot be nested.")
        with checked_store(self.connection), invocation_guard(self.connection, invocation_id=invocation_id) as invocation:
            self.invocation, self._closed = invocation, False
            try:
                try:
                    yield self
                except BaseException as error:
                    if not self._closed:
                        if isinstance(error, (KeyboardInterrupt, SystemExit)):
                            self.finish("stopped", error={"code": "refused", "message": "Stopped by the caller."})
                        elif isinstance(error, MycelError):
                            outcome = "refused" if error.code in {"refused", "busy"} else "failed"
                            self.finish(outcome, error={"code": error.code.value, "message": error.message})
                        else:
                            self.finish("failed", error={"code": "internal", "message": "The invocation failed."})
                    raise
                else:
                    if not self._closed:
                        self.finish("done")
            finally:
                self.invocation = None

    def _active(self) -> InvocationIdentity:
        if self.invocation is None or self._closed:
            raise MycelError("internal", "Mutation audit writes require an active invocation session.")
        return self.invocation

    def _bound(self) -> InvocationIdentity:
        invocation = self._active()
        row = _execute(self.connection, _BOUND_SQL, (invocation.id, invocation.liveness_key,
            invocation.backend_pid, invocation.backend_start, invocation.index_generation)).fetchone()
        try:
            live = invocation_is_live(self.connection, invocation)
        except MycelError:
            raise _audit_failure() from None
        if row is None or row[0] is not True or not live:
            raise MycelError("internal", "Mutation audit requires its exact live owning store connection.")
        return invocation

    def apply(self, repository: str | None, kind: str,
              mutation: Callable[[Any], AppliedMutation], *, verify: Callable[[], None] | None = None) -> AppliedMutation:
        """Atomically apply the injected write and its complete audit payload.

        Callers hold their required operation/pass guard before entering. The
        callback receives this exact connection inside an atomic transaction;
        it must not own/nest transactions, do model work, or commit independently.
        """
        _key(repository, kind)
        self._active()
        if not callable(mutation) or verify is not None and not callable(verify):
            _invalid("A mutation audit requires an injected transaction caller.")
        result = None
        guard = mutation_guard(self.connection, repository) if repository is not None else nullcontext()
        try:
            with guard, atomic_transaction(self.connection):
                self._bound()
                result = mutation(self.connection)
                self.record_in_transaction(repository, kind, result)
                if verify is not None:
                    verify()
        except MycelError as error:
            if isinstance(result, AppliedMutation) and result.changed and error.code == "store_unavailable":
                raise _audit_failure() from None
            raise
        return result

    def record_in_transaction(self, repository: str | None, kind: str,
                              result: AppliedMutation) -> None:
        """Attach an applied result to the caller's guarded transaction.

        The caller owns feature writes and the transaction's rollback boundary.
        It must retain its operation/pass guards and this connection's structure
        and repository removal protection. This method allocates no lock
        identity, opens no transaction and never commits; activity retention
        takes a nonblocking lock on the existing group's row. Any failure must
        escape the outer transaction so feature writes and all affected
        repository audits roll back together. Counts remain the caller's exact
        cumulative reply.
        """
        _key(repository, kind)
        self._active()
        if not isinstance(result, AppliedMutation):
            raise MycelError("internal", "The transaction caller returned no typed mutation result.")
        if (self.connection.autocommit is not True
                or self.connection.info.transaction_status != pq.TransactionStatus.INTRANS):
            _invalid("Mutation audit attachment requires an active guarded transaction.")
        invocation = self._bound()
        guarded = _execute(self.connection, _GUARDED_SQL,
            (repository, LockNamespace.MUTATION.value, repository)).fetchone()
        if guarded != (True,):
            _invalid("Mutation audit attachment lacks its connection-owned removal protection.")
        if not result.changed:
            return
        if (result.files or result.decisions) and kind != "ingest":
            _invalid("Only ingest entries hold applied file and identity details.")
        if result.classifications and kind != "classify":
            _invalid("Classification bundle details require classify activity.")
        if any(value.dependant.repository != repository for value in result.classifications):
            _invalid("Classification details must belong to the entry's repository.")
        retention = ActivityRetentionStore(self.connection)
        retention.guard_in_transaction(repository)
        rows = _execute(self.connection, _ENTRY_SQL, (invocation.id, repository, kind)).fetchall()
        if len(rows) > 1:
            raise _audit_failure()
        if rows:
            identifier = rows[0][0]
            updated = _execute(self.connection, _COUNTS_SQL,
                (Jsonb(_json_object(result.counts)), identifier)).fetchone()
            if updated is None:
                raise _audit_failure()
        else:
            opened = _execute(self.connection, _OPEN_SQL, (repository, invocation.id,
                invocation.index_generation, kind, self.started_by, self.build,
                Jsonb(_json_object(result.counts)))).fetchone()
            if opened is None:
                raise _audit_failure()
            identifier = opened[0]
        self._details(identifier, result)
        if not rows:
            retention.prune_in_transaction(repository)

    def _details(self, identifier: int, result: AppliedMutation) -> None:
        specifications = (
            ("mycel_activity_files", "root,path,location,change", result.files,
             lambda item: (item.root, item.path, item.location, item.change)),
            ("mycel_identity_decisions", "root,path,location,chunk_id,decision,old_name,new_name", result.decisions,
             lambda item: (item.root, item.path, item.location, item.chunk_id, item.decision,
                           item.previous_name if item.decision == "renamed" else item.name if item.decision == "removed" else None,
                           None if item.decision == "removed" else item.name)),
            ("mycel_activity_classifications", "bundle,dependant,outcome", result.classifications,
             lambda item: (item.bundle, format_source_address(item.dependant), item.outcome)),
        )
        for table, columns, values, row in specifications:
            if not values:
                continue
            ordinal = _execute(self.connection, f"SELECT COALESCE(MAX(ordinal), -1) + 1 FROM public.{table} WHERE activity = %s",
                               (identifier,)).fetchone()
            if ordinal is None or type(ordinal[0]) is not int:
                raise _audit_failure()
            for offset, value in enumerate(values):
                parameters = (identifier, ordinal[0] + offset, *row(value))
                placeholders = ",".join("%s" for _ in parameters)
                _execute(self.connection, f"INSERT INTO public.{table} (activity,ordinal,{columns}) VALUES ({placeholders})", parameters)

    def finish(self, outcome: str, *, error: Mapping | None = None,
               counts: Mapping[EntryKey, Mapping] | None = None) -> None:
        """Close existing entries with exact final replies; never create one.

        The producer supplies its final repository reply, including completed
        checks that changed nothing after an earlier mutation. Reply portions
        for scopes that never changed are accepted without creating entries.
        Validate and copy the whole payload before changing any existing row.
        """
        self._active()
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            _invalid("The final activity outcome is unsupported.")
        if outcome == "done":
            if error is not None:
                _invalid("Completed activity cannot carry an error.")
        else:
            if not isinstance(error, Mapping) or set(error) != {"code", "message"}:
                _invalid("Incomplete activity requires an error code and message.")
            _text(error["code"])
            _text(error["message"])
            try:
                ErrorCode(error["code"])
            except ValueError:
                _invalid("Activity errors must use the closed command error vocabulary.")
        copied_error = None if error is None else _json_object(error)
        if counts is not None and not isinstance(counts, Mapping):
            _invalid("Final activity counts must be a repository/kind mapping.")
        final = {}
        for key, value in (() if counts is None else counts.items()):
            if type(key) is not tuple or len(key) != 2:
                _invalid("Final activity counts must be keyed by repository and kind.")
            final[_key(*key)] = _json_object(value)
        try:
            with atomic_transaction(self.connection):
                invocation = self._bound()
                rows = _execute(self.connection, _CLOSE_ROWS_SQL, (invocation.id,)).fetchall()
                repositories = sorted({repository for _, repository, _ in rows},
                                      key=lambda value: (value is not None, value or ""))
                retention = ActivityRetentionStore(self.connection)
                for repository in repositories:
                    retention.guard_in_transaction(repository)
                for identifier, repository, kind in rows:
                    values = final.get((repository, kind))
                    closed = _execute(self.connection, _CLOSE_SQL,
                        (outcome, None if copied_error is None else Jsonb(copied_error),
                         None if values is None else Jsonb(values), identifier)).fetchone()
                    if closed is None:
                        raise _audit_failure()
                for repository in repositories:
                    retention.prune_in_transaction(repository)
        except MycelError as failure:
            if failure.code in {"busy", "store_unavailable"}:
                raise _audit_failure() from None
            raise
        self._closed = True


def effective_outcome(connection, *, invocation: UUID, outcome: str | None) -> str:
    """Read exact invocation liveness without rewriting an open activity row."""
    if outcome is not None:
        if outcome not in OUTCOMES:
            raise MycelError("internal", "The store returned an invalid activity outcome.")
        return outcome
    return "running" if invocation_is_live(connection, invocation) else "unfinished"


def record_initialization(connection, invocation: InvocationIdentity, *, build: int,
                          counts: Mapping) -> None:
    """Record actual init inside its schema transaction, before publication.

    Its outer caller retains exact invocation liveness until this transaction
    commits. Empty-store schema, dimension change and audit either all commit
    or all roll back. A compatible no-op never calls this boundary.
    """
    audit = MutationActivity(connection, build=build)
    audit.invocation = invocation
    audit._bound()
    copied = Jsonb(_json_object(counts))
    retention = ActivityRetentionStore(connection)
    retention.guard_in_transaction(None)
    row = _execute(connection, _OPEN_SQL, (None, invocation.id,
        invocation.index_generation, "init", "command", build, copied)).fetchone()
    if row is None:
        raise _audit_failure()
    retention.prune_in_transaction(None)
    closed = _execute(connection, _CLOSE_SQL, ("done", None, copied, row[0])).fetchone()
    if closed is None:
        raise _audit_failure()
    retention.prune_in_transaction(None)


def activity_state(connection, identifier: int) -> dict | None:
    """Read one internal diagnostic entry; public history/filtering is later."""
    if type(identifier) is not int or identifier <= 0:
        _invalid("An activity identifier must be a positive integer.")
    with checked_store(connection), read_snapshot(connection):
        row = connection.execute("SELECT id,repository,invocation,index_generation,kind,trigger,build,started_at,ended_at,outcome,counts,error "
            "FROM public.mycel_activity WHERE id = %s", (identifier,)).fetchone()
        if row is None:
            return None  # Public missing/pruned-entry errors belong to history.
        keys = ("id", "repository", "invocation", "indexGeneration", "kind", "startedBy", "build",
                "startedAt", "endedAt", "outcome", "counts", "error")
        result = dict(zip(keys, row))
        result["outcome"] = effective_outcome(connection, invocation=row[2], outcome=row[9])
        result["files"] = [dict(zip(("root", "path", "location", "change"), values)) for values in connection.execute(
            "SELECT root,path,location,change FROM public.mycel_activity_files WHERE activity = %s ORDER BY root,path,location,ordinal", (identifier,)).fetchall()]
        result["decisions"] = [dict(zip(("root", "path", "location", "chunkId", "decision", "previousName", "name"), values))
            for values in connection.execute("SELECT root,path,location,chunk_id,decision,CASE WHEN decision='renamed' THEN old_name END,"
                "COALESCE(new_name,old_name) FROM public.mycel_identity_decisions WHERE activity = %s ORDER BY root,path,location,COALESCE(new_name,old_name),ordinal",
                (identifier,)).fetchall()]
        result["classifications"] = [dict(zip(("bundle", "dependant", "outcome"), values)) for values in connection.execute(
            "SELECT bundle,dependant,outcome FROM public.mycel_activity_classifications WHERE activity = %s ORDER BY ordinal", (identifier,)).fetchall()]
        for detail in result["classifications"]:
            try:
                place = parse_source_address(detail["dependant"])
            except SourceAddressError:
                raise MycelError("internal", "The store returned an invalid classification dependant.") from None
            if place.root is None or place.name is None:
                raise MycelError("internal", "The store returned an unqualified classification dependant.")
            detail["dependant"] = {"repository": place.repository, "root": place.root, "path": place.path,
                                   "name": place.name, "address": format_source_address(place)}
        return result
