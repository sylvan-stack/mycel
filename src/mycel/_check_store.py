"""Native disposable-check backend; owner database names never reach libpq."""

from collections.abc import Iterator
from contextlib import contextmanager
import io
import os
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote, urlsplit, urlunsplit

from ._coverage import CoverageError, PostgresBackend, require_check_database
from ._credentials import Credentials
from ._database import store_connection
from ._safeguards import InvocationPolicy
from ._settings import SettingsSnapshot, _store_address_fault, load_settings


class NativePostgresBackend(PostgresBackend):
    """Use the product's private connection boundary without a psql process.

    Only admin postgres/template1 and generated mycel_check_ databases can be
    selected. Real-store checks still need the owner-configured server and
    ordinary database creation permission; this adapter supplies neither.
    """

    def __init__(self, owner_address: str, *, _credential_runner=None):
        if not isinstance(owner_address, str) or _store_address_fault(owner_address) is not None:
            raise CoverageError("store check server requires a valid password-free PostgreSQL address")
        parsed = urlsplit(owner_address)
        owner_database = unquote(parsed.path[1:])
        self._server = parsed._replace(path="")
        self._admin = "template1" if owner_database == "postgres" else "postgres"
        self._track_owner(owner_database)
        self._credential_runner = _credential_runner

    def _credentials(self, address: str) -> Credentials:
        # This private in-memory snapshot has only the validated server target.
        # No owner settings path is supplied to a test bootstrap or opened here.
        self._require_connection_address(address)
        settings = SettingsSnapshot(Path("<disposable-check-target>"),
                                    MappingProxyType({"store": MappingProxyType({"address": address})}),
                                    exists=True, readable=True)
        return Credentials(settings, InvocationPolicy("init"), _runner=self._credential_runner)

    def _require_connection_address(self, address: str) -> None:
        parsed = urlsplit(address)
        database = unquote(parsed.path[1:])
        if database == self._owner_database:
            raise CoverageError("store checks must never target the owner's database")
        if parsed._replace(path="") != self._server:
            raise CoverageError("store checks must use their configured test server")
        if database != self._admin:
            self._require_database(database, owned=True)

    @contextmanager
    def _connect(self, address: str) -> Iterator:
        self._require_connection_address(address)
        with store_connection(self._credentials(address)) as connection:
            # Test SQL and cleanup cannot wait indefinitely for another session.
            connection.execute("SET statement_timeout = '15s'")
            connection.execute("SET lock_timeout = '100ms'")
            yield connection

    @contextmanager
    def connection(self, database: str) -> Iterator:
        """A feature check's real connection, restricted to its generated DB."""
        self._require_database(database, owned=True)
        with self._connect(self.address(database)) as connection:
            yield connection

    def _execute(self, database: str, statement: str, *, administrative: bool = True) -> str:
        self._require_database(database, owned=not administrative)
        address = (urlunsplit(self._server._replace(path="/" + self._admin))
                   if administrative else self.address(database))
        try:
            with self._connect(address) as connection:
                cursor = connection.execute(statement)
                if administrative and statement == f'CREATE DATABASE "{database}"':
                    # The native execute has acknowledged success already. An
                    # interrupt while closing this admin session must not lose
                    # the fixture's proven cleanup permission.
                    self._acknowledge_creation(database)
                if cursor.description is None:
                    return ""
                rows = cursor.fetchall()
                def value(member):
                    return "" if member is None else "t" if member is True else "f" if member is False else str(member)
                return "\n".join("|".join(value(member) for member in row) for row in rows)
        except KeyboardInterrupt:
            raise
        except Exception:
            raise RuntimeError("temporary PostgreSQL database operation failed") from None

    def drop_database(self, database: str) -> None:
        name = self._require_database(database, owned=True)
        # Ordinary DROP holds the database lock while PostgreSQL waits up to
        # five seconds for closed clients and one-shot extension workers to
        # exit. FORCE can require privileges to signal those workers instead.
        self._execute(name, f'DROP DATABASE IF EXISTS "{name}"')
        del self._owned_databases[name]

    def initialize(self, settings_file: Path) -> None:
        from ._cli import run
        if os.environ.get("MYCEL_CONFIG") != str(settings_file):
            raise CoverageError("test initializer requires its selected private settings file")
        snapshot = load_settings(path=settings_file)
        try:
            snapshot.require_valid()
            address = snapshot.values["store"]["address"]
            database = self._require_database(unquote(urlsplit(address).path[1:]), owned=True)
            if address != self.address(database):
                raise CoverageError("test initializer must use its generated database target")
        except CoverageError:
            raise
        except Exception:
            raise CoverageError("test initializer requires private generated-store settings") from None
        # disposable_store already selects this private config for the invocation.
        # Capture both streams in memory; no subprocess sees the store target.
        if run(["init"], stdout=io.StringIO(), stderr=io.StringIO()) != 0:
            raise RuntimeError("mycel init failed for the disposable check database")
