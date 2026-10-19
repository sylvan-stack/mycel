"""The discussion of a decision: its chats, read as data from the discussion database (MYC-17).

A Discussion cell holds chat Entity URIs. `mycel read` of the decision shows
each chat's title and messages, read from the database the `[discussions]`
settings name in one read-only transaction, or `available: false` with the
reason. Mycel writes nothing there, and a read never fails because of it.
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from ._credentials import Credentials
from ._database import discussion_connection
from ._errors import MycelError
from ._source_refs import parse_entity_uri

_CHAT_SQL = "SELECT title FROM chats WHERE id = %s"
_MESSAGES_SQL = """SELECT m.role, m.text FROM exchanges e JOIN messages m ON m.exchange_id = e.id
WHERE e.chat_id = %s AND e.replaced_by IS NULL ORDER BY e.number, m.position"""


def _unavailable(uri: str, reason: str) -> dict:
    return {"uri": uri, "available": False, "reason": reason}


def read_discussions(settings, uris: Sequence[str], *, credentials: Credentials | None = None,
                     deadline=None, _connect=None) -> list[dict]:
    """One entry per URI, in the cell's order; never raises for the database."""
    uris = [uri for uri in uris if isinstance(uri, str)]
    if not uris:
        return []
    parsed = [(uri, parse_entity_uri(uri)) for uri in uris]
    address = settings.values.get("discussions", {}).get("address") if settings.valid else None
    if not isinstance(address, str):
        return [_unavailable(uri, "The settings name no discussions.address.") for uri in uris]
    if credentials is None:
        return [_unavailable(uri, "No credentials were available for the discussion database.") for uri in uris]
    results = []
    try:
        connect = _connect or discussion_connection
        with connect(credentials) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                connection.execute("SET LOCAL statement_timeout = '5000ms'")
                for uri, entity in parsed:
                    if entity is None or entity.kind != "cht":
                        results.append(_unavailable(uri, "The Discussion cell holds a value that is no chat Entity URI."))
                        continue
                    if deadline is not None:
                        deadline.check()
                    row = connection.execute(_CHAT_SQL, (entity.uuid,)).fetchone()
                    if row is None:
                        results.append(_unavailable(uri, "The discussion database has no chat with that UUID."))
                        continue
                    messages = [{"role": role, "text": text} for role, text in
                                connection.execute(_MESSAGES_SQL, (entity.uuid,)).fetchall()]
                    results.append({"uri": uri, "available": True, "title": row[0], "messages": messages})
    except (psycopg.Error, MycelError, OSError) as error:
        reason = ("The discussion database could not be reached." if not isinstance(error, MycelError)
                  else f"The discussion database could not be read: {error.code}.")
        done = {item["uri"] for item in results}
        results.extend(_unavailable(uri, reason) for uri in uris if uri not in done)
    return results
