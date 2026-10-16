"""Writer-only retention of activity rows and their attached audit details.

Each group is serialized by an existing store row inside the caller's short
transaction. No lock identity, transaction, background cleanup or evidence
ownership is created here. A pruning failure is an audit failure and must roll
back the caller's feature change with its activity entry.
"""
from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg import pq

from ._errors import MycelError
from ._locks import invocation_is_live


HISTORY_LIMIT = 1000


def _failure():
    return MycelError("internal", "The invocation's activity history could not be retained.")


class ActivityRetentionStore:
    def __init__(self, connection):
        self.connection = connection

    def guard_in_transaction(self, repository: str | None) -> None:
        """Serialize one group's writers without allocating or waiting.

        The caller owns structure/removal protection and its feature transaction.
        NO KEY UPDATE is compatible with ordinary foreign-key readers. Distinct
        repository groups use distinct rows; global init/remove use the store's
        singleton row. A concurrent group writer or repository deletion refuses
        immediately rather than allowing either writer to prune an old snapshot.
        READ COMMITTED gives every statement after the group lock a current
        committed snapshot. Older repeatable or serializable snapshots are
        refused instead of changing a feature row only to detect stale reads.
        """
        if (self.connection.autocommit is not True
                or self.connection.info.transaction_status != pq.TransactionStatus.INTRANS):
            raise MycelError("invalid_input", "Activity retention requires an active writer transaction.")
        if repository is not None:
            if not isinstance(repository, str) or not repository or "\0" in repository:
                raise MycelError("invalid_input", "Activity retention requires one exact repository or the global group.")
            try:
                repository.encode("utf-8")
            except UnicodeError:
                raise MycelError("invalid_input", "Activity retention requires exact UTF-8 repository text.") from None
        try:
            if self.connection.execute("SHOW transaction_isolation").fetchone() != ("read committed",):
                raise _failure()
            if repository is None:
                row = self.connection.execute("SELECT singleton FROM public.mycel_store "
                    "WHERE singleton=true FOR NO KEY UPDATE NOWAIT").fetchone()
                expected = (True,)
            else:
                row = self.connection.execute("SELECT repository FROM public.mycel_repository_state "
                    "WHERE repository=%s FOR NO KEY UPDATE NOWAIT", (repository,)).fetchone()
                expected = (repository,)
            if row != expected:
                raise _failure()
        except psycopg.Error:
            raise _failure() from None

    def prune_in_transaction(self, repository: str | None) -> tuple[int, ...]:
        """Keep the newest 1,000 first, then protect exact live invocations.

        All outcomes, including open entries from dead invocations, use the
        same start-time/ID order. A still-live invocation protects even an older
        entry it has just closed; the next opening or closing in that group can
        collect it after the exact liveness lock is released. Deleting activity
        cascades only its attached details, never the evidence those details
        merely reference.
        """
        self.guard_in_transaction(repository)
        try:
            candidates = self.connection.execute("SELECT id,invocation FROM public.mycel_activity "
                "WHERE repository IS NOT DISTINCT FROM %s "
                "ORDER BY started_at DESC,id DESC OFFSET %s FOR UPDATE NOWAIT",
                (repository, HISTORY_LIMIT)).fetchall()
            live = {}
            removable = []
            for identifier, invocation in candidates:
                if type(identifier) is not int or identifier <= 0 or not isinstance(invocation, UUID):
                    raise _failure()
                if invocation not in live:
                    try:
                        live[invocation] = invocation_is_live(self.connection, invocation)
                    except MycelError:
                        raise _failure() from None
                if not live[invocation]:
                    removable.append(identifier)
            if removable:
                deleted = self.connection.execute("DELETE FROM public.mycel_activity "
                    "WHERE id=ANY(%s::bigint[]) RETURNING id", (removable,)).fetchall()
                if {row[0] for row in deleted} != set(removable) or len(deleted) != len(removable):
                    raise _failure()
            return tuple(removable)
        except psycopg.Error:
            raise _failure() from None
