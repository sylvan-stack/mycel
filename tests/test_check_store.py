"""Runner isolation checks do not qualify actual store acceptance."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psycopg.errors import ObjectInUse

from mycel._check_store import NativePostgresBackend
from mycel._coverage import CoverageError, PostgresBackend, disposable_store, proves


class NativeCheckRunnerTests(unittest.TestCase):
    @staticmethod
    def backends(owner="owner"):
        address = "postgresql://fixture@localhost/" + owner
        return (NativePostgresBackend(address), PostgresBackend(address, psql="/fictional/psql"))

    @proves("MYC-13.15")
    def test_owner_database_never_reaches_native_boundary_and_unsafe_names_refuse_first(self):
        for owner, admin in (("owner", "postgres"), ("postgres", "template1"), ("%70ostgres", "template1")):
            backend = NativePostgresBackend("postgresql://fixture@localhost/" + owner)
            calls = []
            class Cursor:
                def __init__(self, presence=False):
                    self.description = [("exists",)] if presence else None
                def fetchall(self):
                    return [(False,)]
            class Connection:
                def execute(self, statement):
                    calls.append(statement)
                    return Cursor(statement.startswith("SELECT EXISTS"))
            @contextmanager
            def connect(credentials):
                calls.append(credentials.store_target().address)
                yield Connection()
            with patch("mycel._check_store.store_connection", connect), patch("subprocess.Popen") as child:
                backend.create_database("mycel_check_safe")
                with backend.connection("mycel_check_safe"):
                    pass
                backend.drop_database("mycel_check_safe")
                child.assert_not_called()
            addresses = [member for member in calls if member.startswith("postgresql:")]
            self.assertEqual(addresses, ["postgresql://fixture@localhost/" + admin]*2
                             + ["postgresql://fixture@localhost/mycel_check_safe"]
                             + ["postgresql://fixture@localhost/" + admin])
            with patch("mycel._check_store.store_connection") as connection:
                for unsafe in ("owner", "mycel_check_", "mycel_check_a;DROP"):
                    with self.assertRaises(CoverageError):
                        backend.query(unsafe, "SELECT 1")
                    with self.assertRaises(CoverageError):
                        with backend.connection(unsafe):
                            pass
                connection.assert_not_called()

    @proves("MYC-13.15")
    def test_native_failure_bodies_and_credentials_never_enter_check_reports(self):
        backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
        with patch.object(backend, "_execute", side_effect=["f", ""]):
            backend.create_database("mycel_check_safe")
        with patch("mycel._check_store.store_connection", side_effect=RuntimeError("private-provider-sentinel")):
            with self.assertRaises(RuntimeError) as error:
                backend.query("mycel_check_safe", "SELECT 1")
        self.assertNotIn("private-provider-sentinel", str(error.exception))
        for address in ("postgresql://fixture:private@localhost/owner", "postgresql://localhost/owner",
                        "postgresql://fixture@localhost/owner?service=x", "postgresql://fixture@localhost/owner#x"):
            with self.assertRaises(CoverageError):
                NativePostgresBackend(address)

    @proves("MYC-13.15")
    def test_prefix_valid_and_percent_encoded_owner_targets_refuse_before_every_boundary(self):
        for spelling in ("mycel_check_owner", "mycel_check_%6fwner"):
            for backend in self.backends(spelling):
                name = "mycel_check_owner"
                with tempfile.TemporaryDirectory() as directory:
                    config = Path(directory) / "config.toml"
                    address = "postgresql://fixture@localhost/" + name
                    config.write_text('[store]\naddress=' + json.dumps(address) + '\n')
                    operations = (
                        lambda: backend.address(name),
                        lambda: backend.create_database(name),
                        lambda: backend.drop_database(name),
                        lambda: backend.query(name, "SELECT 1"),
                        lambda: backend.database_exists(name),
                        lambda: backend._execute(name, "SELECT 1"),
                        lambda: backend.initialize(config),
                    )
                    with patch("mycel._check_store.store_connection") as native, \
                            patch("subprocess.run") as child, \
                            patch.dict("os.environ", {"MYCEL_CONFIG": str(config)}):
                        for operation in operations:
                            with self.assertRaises(CoverageError):
                                operation()
                        if isinstance(backend, NativePostgresBackend):
                            with self.assertRaises(CoverageError):
                                with backend.connection(name):
                                    pass
                            with self.assertRaises(CoverageError):
                                with backend._connect(address):
                                    pass
                            with self.assertRaises(CoverageError):
                                backend._credentials(address)
                        native.assert_not_called()
                        child.assert_not_called()

    @proves("MYC-13.15")
    def test_unowned_prefix_valid_databases_cannot_be_queried_connected_or_dropped(self):
        for backend in self.backends():
            with patch("mycel._check_store.store_connection") as native, patch("subprocess.run") as child:
                for operation in (lambda: backend.query("mycel_check_existing", "SELECT 1"),
                                  lambda: backend.drop_database("mycel_check_existing")):
                    with self.assertRaises(CoverageError):
                        operation()
                if isinstance(backend, NativePostgresBackend):
                    with self.assertRaises(CoverageError):
                        with backend.connection("mycel_check_existing"):
                            pass
                native.assert_not_called()
                child.assert_not_called()

    @proves("MYC-13.15")
    def test_preexisting_or_previously_owned_collision_is_never_removed_by_failed_creation(self):
        for already_owned in (False, True):
            for backend in self.backends():
                calls = []
                exists = already_owned
                def execute(database, statement, **kwargs):
                    nonlocal exists
                    calls.append(statement)
                    if statement.startswith("SELECT EXISTS"):
                        return "t" if exists else "f"
                    if statement.startswith("CREATE"):
                        exists = True
                        return ""
                    if statement.startswith("DROP"):
                        self.fail("dropped a preexisting/colliding database")
                with patch.object(backend, "_execute", side_effect=execute):
                    if already_owned:
                        exists = False
                        backend.create_database("mycel_check_collision")
                    else:
                        exists = True
                    calls.clear()
                    with patch("mycel._coverage.uuid4", return_value=SimpleNamespace(hex="collision")):
                        with self.assertRaisesRegex(CoverageError, "already exists"):
                            with disposable_store(backend, initialize=lambda *_: None):
                                self.fail("ran against preexisting database")
                    self.assertTrue(exists)
                    self.assertTrue(all(statement.startswith("SELECT EXISTS") for statement in calls))

    @proves("MYC-13.15")
    def test_failed_unacknowledged_create_never_deletes_a_database_that_appears_afterward(self):
        for server_created in (False, True):
            for backend in self.backends():
                calls, exists = [], False
                def execute(database, statement, **kwargs):
                    nonlocal exists
                    calls.append(statement)
                    if statement.startswith("SELECT EXISTS"):
                        return "t" if exists else "f"
                    if statement.startswith("CREATE"):
                        exists = server_created
                        raise RuntimeError("temporary PostgreSQL database operation failed")
                    self.fail("unacknowledged CREATE permitted DROP or query")
                with patch.object(backend, "_execute", side_effect=execute):
                    with self.assertRaises(CoverageError if server_created else RuntimeError) as error:
                        with disposable_store(backend, initialize=lambda *_: None):
                            self.fail("failed create initialized")
                self.assertFalse(any(statement.startswith("DROP") for statement in calls))
                if server_created:
                    self.assertIn("ownership is unconfirmed", str(error.exception))
                    self.assertTrue(exists)

    @proves("MYC-13.15")
    def test_acknowledged_creation_is_cleaned_after_body_init_and_immediate_cancellation(self):
        for failure in (RuntimeError("body failed"), KeyboardInterrupt()):
            for backend in self.backends():
                databases, calls = set(), []
                def execute(database, statement, **kwargs):
                    calls.append(statement)
                    if statement.startswith("SELECT EXISTS"):
                        return "t" if database in databases else "f"
                    if statement.startswith("CREATE"):
                        databases.add(database)
                    elif statement.startswith("DROP"):
                        databases.remove(database)
                    return ""
                original = backend.create_database
                def interrupted(database):
                    original(database)
                    raise failure
                with patch.object(backend, "_execute", side_effect=execute), \
                        patch.object(backend, "create_database", side_effect=interrupted):
                    with self.assertRaises(type(failure)):
                        with disposable_store(backend, initialize=lambda *_: None):
                            self.fail("interrupted create continued")
                self.assertFalse(databases)
                self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 1)

    @proves("MYC-13.15")
    def test_cancellation_before_create_acknowledgement_retains_no_cleanup_permission(self):
        for backend in self.backends():
            calls = []
            def execute(database, statement, **kwargs):
                calls.append(statement)
                if statement.startswith("SELECT EXISTS"):
                    return "f"
                raise KeyboardInterrupt()
            with patch.object(backend, "_execute", side_effect=execute):
                with self.assertRaises(KeyboardInterrupt) as error:
                    with disposable_store(backend, initialize=lambda *_: None):
                        pass
            self.assertTrue(any("no unowned database was removed" in note for note in error.exception.__notes__))
            self.assertFalse(any(statement.startswith("DROP") for statement in calls))

    @proves("MYC-13.15")
    def test_native_acknowledgement_survives_interrupt_while_closing_admin_session(self):
        backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
        databases, calls = set(), []
        class Cursor:
            description = None
            def fetchall(self):
                return [(False,)]
        class Connection:
            created = False
            def execute(self, statement):
                calls.append(statement)
                cursor = Cursor()
                if statement.startswith("SELECT EXISTS"):
                    cursor.description = [("exists",)]
                elif statement.startswith("CREATE"):
                    databases.add("mycel_check_native_ack")
                    self.created = True
                elif statement.startswith("DROP"):
                    databases.remove("mycel_check_native_ack")
                return cursor
        @contextmanager
        def connect(address):
            connection = Connection()
            yield connection
            if connection.created:
                raise KeyboardInterrupt()
        with patch.object(backend, "_connect", connect), \
                patch("mycel._coverage.uuid4", return_value=SimpleNamespace(hex="native_ack")):
            with self.assertRaises(KeyboardInterrupt):
                with disposable_store(backend, initialize=lambda *_: None):
                    self.fail("interrupted admin close continued")
        self.assertFalse(databases)
        self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 1)

    @proves("MYC-13.15")
    def test_native_cleanup_refusal_keeps_owned_fixture_and_failure_bodies_private(self):
        backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
        exists, occupied = True, True
        calls = []
        backend._begin_creation("mycel_check_busy")
        backend._acknowledge_creation("mycel_check_busy")

        class Connection:
            def execute(self, statement):
                nonlocal exists
                calls.append(statement)
                if statement.startswith("SELECT EXISTS"):
                    return SimpleNamespace(description=[("exists",)], fetchall=lambda: [(exists,)])
                if occupied:
                    raise ObjectInUse("private-provider-sentinel")
                exists = False
                return SimpleNamespace(description=None)

        @contextmanager
        def connect(address):
            self.assertEqual(address, "postgresql://fixture@localhost/postgres")
            yield Connection()

        with patch.object(backend, "_connect", connect):
            with self.assertRaises(RuntimeError) as error:
                backend.drop_database("mycel_check_busy")
            self.assertNotIn("private-provider-sentinel", str(error.exception))
            self.assertTrue(backend.owns_database("mycel_check_busy"))
            self.assertTrue(backend.database_exists("mycel_check_busy"))
            occupied = False
            backend.drop_database("mycel_check_busy")
            self.assertFalse(backend.owns_database("mycel_check_busy"))
            self.assertFalse(backend.database_exists("mycel_check_busy"))
            before = len(calls)
            with self.assertRaises(CoverageError):
                backend.drop_database("mycel_check_busy")
            self.assertEqual(len(calls), before)

    @proves("MYC-13.15")
    def test_native_cleanup_cancellation_after_removal_preserves_safe_retry_permission(self):
        backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
        backend._begin_creation("mycel_check_cancel")
        backend._acknowledge_creation("mycel_check_cancel")
        exists, interrupt = True, True
        calls = []

        class Connection:
            def execute(self, statement):
                nonlocal exists
                calls.append(statement)
                if statement.startswith("SELECT EXISTS"):
                    return SimpleNamespace(description=[("exists",)], fetchall=lambda: [(exists,)])
                exists = False
                return SimpleNamespace(description=None)

        @contextmanager
        def connect(address):
            self.assertEqual(address, "postgresql://fixture@localhost/postgres")
            yield Connection()
            if interrupt:
                raise KeyboardInterrupt()

        with patch.object(backend, "_connect", connect):
            with self.assertRaises(KeyboardInterrupt):
                backend.drop_database("mycel_check_cancel")
            self.assertFalse(exists)
            self.assertTrue(backend.owns_database("mycel_check_cancel"))
            interrupt = False
            backend.drop_database("mycel_check_cancel")
            self.assertFalse(backend.owns_database("mycel_check_cancel"))
            self.assertFalse(backend.database_exists("mycel_check_cancel"))
        self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 2)


if __name__ == "__main__":
    unittest.main()
