"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_check_store as _support
from test_check_store import (NativePostgresBackend ,Path ,json ,os ,patch ,tempfile)


class NativeCheckRunnerTests(_support.NativeCheckRunnerTests):


# TEST-TIER-BEGIN tests/test_check_store.py::NativeCheckRunnerTests.test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission
    def test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory)
            address = "postgresql://fixture@localhost/owner"
            worker = NativePostgresBackend(address, _ownership_journal=journal)
            name = "mycel_check_atomic"
            original_replace = os.replace
            def replace(source, destination):
                self.assertEqual(json.loads(Path(source).read_text())["database"], name)
                self.assertEqual(Path(source).stat().st_mode & 0o777, 0o600)
                self.assertFalse(Path(destination).exists())
                original_replace(source, destination)
            worker._begin_creation(name)
            with patch("mycel._check_store.os.replace", side_effect=replace) as publish:
                worker._acknowledge_creation(name)
                publish.assert_called_once()
            with patch.object(worker, "_execute", return_value=""):
                worker.drop_database(name)
            worker._begin_creation(name)
            with patch("mycel._check_store.json.dump", side_effect=OSError("private-file-sentinel")):
                with self.assertRaisesRegex(RuntimeError, "ownership record failed"):
                    worker._acknowledge_creation(name)
            self.assertEqual(list(journal.iterdir()), [])
            parent = NativePostgresBackend(address, _ownership_journal=journal)
            with patch.object(parent, "_execute") as boundary:
                self.assertEqual(parent.recover_owned_databases(), ())
                boundary.assert_not_called()
# TEST-TIER-END tests/test_check_store.py::NativeCheckRunnerTests.test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_owner_database_never_reaches_native_boundary_and_unsafe_names_refuse_first
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Owner database never reaches native boundary and unsafe names refuse first.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_owner_database_never_reaches_native_boundary_and_unsafe_names_refuse_first(self):
#         for owner, admin in (("owner", "postgres"), ("postgres", "template1"), ("%70ostgres", "template1")):
#             backend = NativePostgresBackend("postgresql://fixture@localhost/" + owner)
#             calls = []
#             class Cursor:
#                 def __init__(self, presence=False):
#                     self.description = [("exists",)] if presence else None
#                 def fetchall(self):
#                     return [(False,)]
#             class Connection:
#                 def execute(self, statement):
#                     calls.append(statement)
#                     return Cursor(statement.startswith("SELECT EXISTS"))
#             @contextmanager
#             def connect(credentials):
#                 calls.append(credentials.store_target().address)
#                 yield Connection()
#             with patch("mycel._check_store.store_connection", connect), patch("subprocess.Popen") as child:
#                 backend.create_database("mycel_check_safe")
#                 with backend.connection("mycel_check_safe"):
#                     pass
#                 backend.drop_database("mycel_check_safe")
#                 child.assert_not_called()
#             addresses = [member for member in calls if member.startswith("postgresql:")]
#             self.assertEqual(addresses, ["postgresql://fixture@localhost/" + admin]*2
#                              + ["postgresql://fixture@localhost/mycel_check_safe"]
#                              + ["postgresql://fixture@localhost/" + admin])
#             with patch("mycel._check_store.store_connection") as connection:
#                 for unsafe in ("owner", "mycel_check_", "mycel_check_a;DROP"):
#                     with self.assertRaises(CoverageError):
#                         backend.query(unsafe, "SELECT 1")
#                     with self.assertRaises(CoverageError):
#                         with backend.connection(unsafe):
#                             pass
#                 connection.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_native_failure_bodies_and_credentials_never_enter_check_reports
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native failure bodies and credentials never enter check reports.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_failure_bodies_and_credentials_never_enter_check_reports(self):
#         backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
#         with patch.object(backend, "_execute", side_effect=["f", ""]):
#             backend.create_database("mycel_check_safe")
#         with patch("mycel._check_store.store_connection", side_effect=RuntimeError("private-provider-sentinel")):
#             with self.assertRaises(RuntimeError) as error:
#                 backend.query("mycel_check_safe", "SELECT 1")
#         self.assertNotIn("private-provider-sentinel", str(error.exception))
#         for address in ("postgresql://fixture:private@localhost/owner", "postgresql://localhost/owner",
#                         "postgresql://fixture@localhost/owner?service=x", "postgresql://fixture@localhost/owner#x"):
#             with self.assertRaises(CoverageError):
#                 NativePostgresBackend(address)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_prefix_valid_and_percent_encoded_owner_targets_refuse_before_every_boundary
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Prefix valid and percent encoded owner targets refuse before every boundary.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_prefix_valid_and_percent_encoded_owner_targets_refuse_before_every_boundary(self):
#         for spelling in ("mycel_check_owner", "mycel_check_%6fwner"):
#             for backend in self.backends(spelling):
#                 name = "mycel_check_owner"
#                 with tempfile.TemporaryDirectory() as directory:
#                     config = Path(directory) / "config.toml"
#                     address = "postgresql://fixture@localhost/" + name
#                     config.write_text('[store]\naddress=' + json.dumps(address) + '\n')
#                     operations = (
#                         lambda: backend.address(name),
#                         lambda: backend.create_database(name),
#                         lambda: backend.drop_database(name),
#                         lambda: backend.query(name, "SELECT 1"),
#                         lambda: backend.database_exists(name),
#                         lambda: backend._execute(name, "SELECT 1"),
#                         lambda: backend.initialize(config),
#                     )
#                     with patch("mycel._check_store.store_connection") as native, \
#                             patch("subprocess.run") as child, \
#                             patch.dict("os.environ", {"MYCEL_CONFIG": str(config)}):
#                         for operation in operations:
#                             with self.assertRaises(CoverageError):
#                                 operation()
#                         if isinstance(backend, NativePostgresBackend):
#                             with self.assertRaises(CoverageError):
#                                 with backend.connection(name):
#                                     pass
#                             with self.assertRaises(CoverageError):
#                                 with backend._connect(address):
#                                     pass
#                             with self.assertRaises(CoverageError):
#                                 backend._credentials(address)
#                         native.assert_not_called()
#                         child.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_unowned_prefix_valid_databases_cannot_be_queried_connected_or_dropped
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unowned prefix valid databases cannot be queried connected or dropped.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unowned_prefix_valid_databases_cannot_be_queried_connected_or_dropped(self):
#         for backend in self.backends():
#             with patch("mycel._check_store.store_connection") as native, patch("subprocess.run") as child:
#                 for operation in (lambda: backend.query("mycel_check_existing", "SELECT 1"),
#                                   lambda: backend.drop_database("mycel_check_existing")):
#                     with self.assertRaises(CoverageError):
#                         operation()
#                 if isinstance(backend, NativePostgresBackend):
#                     with self.assertRaises(CoverageError):
#                         with backend.connection("mycel_check_existing"):
#                             pass
#                 native.assert_not_called()
#                 child.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_preexisting_or_previously_owned_collision_is_never_removed_by_failed_creation
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Preexisting or previously owned collision is never removed by failed creation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_preexisting_or_previously_owned_collision_is_never_removed_by_failed_creation(self):
#         for already_owned in (False, True):
#             for backend in self.backends():
#                 calls = []
#                 exists = already_owned
#                 def execute(database, statement, **kwargs):
#                     nonlocal exists
#                     calls.append(statement)
#                     if statement.startswith("SELECT EXISTS"):
#                         return "t" if exists else "f"
#                     if statement.startswith("CREATE"):
#                         exists = True
#                         return ""
#                     if statement.startswith("DROP"):
#                         self.fail("dropped a preexisting/colliding database")
#                 with patch.object(backend, "_execute", side_effect=execute):
#                     if already_owned:
#                         exists = False
#                         backend.create_database("mycel_check_collision")
#                     else:
#                         exists = True
#                     calls.clear()
#                     with patch("mycel._coverage.uuid4", return_value=SimpleNamespace(hex="collision")):
#                         with self.assertRaisesRegex(CoverageError, "already exists"):
#                             with disposable_store(backend, initialize=lambda *_: None):
#                                 self.fail("ran against preexisting database")
#                     self.assertTrue(exists)
#                     self.assertTrue(all(statement.startswith("SELECT EXISTS") for statement in calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_failed_unacknowledged_create_never_deletes_a_database_that_appears_afterward
# Reason: Uses a simulated database-existence flag and mocked SQL calls to restate the ownership branch; it does not verify actual create/drop acknowledgement or PostgreSQL ownership. Retain the real ownership-journal publication invariant and isolated release lifecycle instead.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_failed_unacknowledged_create_never_deletes_a_database_that_appears_afterward(self):
#         for server_created in (False, True):
#             for backend in self.backends():
#                 calls, exists = [], False
#                 def execute(database, statement, **kwargs):
#                     nonlocal exists
#                     calls.append(statement)
#                     if statement.startswith("SELECT EXISTS"):
#                         return "t" if exists else "f"
#                     if statement.startswith("CREATE"):
#                         exists = server_created
#                         raise RuntimeError("temporary PostgreSQL database operation failed")
#                     self.fail("unacknowledged CREATE permitted DROP or query")
#                 with patch.object(backend, "_execute", side_effect=execute):
#                     with self.assertRaises(CoverageError if server_created else RuntimeError) as error:
#                         with disposable_store(backend, initialize=lambda *_: None):
#                             self.fail("failed create initialized")
#                 self.assertFalse(any(statement.startswith("DROP") for statement in calls))
#                 if server_created:
#                     self.assertIn("ownership is unconfirmed", str(error.exception))
#                     self.assertTrue(exists)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_acknowledged_creation_is_cleaned_after_body_init_and_immediate_cancellation
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Acknowledged creation is cleaned after body init and immediate cancellation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_acknowledged_creation_is_cleaned_after_body_init_and_immediate_cancellation(self):
#         for failure in (RuntimeError("body failed"), KeyboardInterrupt()):
#             for backend in self.backends():
#                 databases, calls = set(), []
#                 def execute(database, statement, **kwargs):
#                     calls.append(statement)
#                     if statement.startswith("SELECT EXISTS"):
#                         return "t" if database in databases else "f"
#                     if statement.startswith("CREATE"):
#                         databases.add(database)
#                     elif statement.startswith("DROP"):
#                         databases.remove(database)
#                     return ""
#                 original = backend.create_database
#                 def interrupted(database):
#                     original(database)
#                     raise failure
#                 with patch.object(backend, "_execute", side_effect=execute), \
#                         patch.object(backend, "create_database", side_effect=interrupted):
#                     with self.assertRaises(type(failure)):
#                         with disposable_store(backend, initialize=lambda *_: None):
#                             self.fail("interrupted create continued")
#                 self.assertFalse(databases)
#                 self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_cancellation_before_create_acknowledgement_retains_no_cleanup_permission
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Cancellation before create acknowledgement retains no cleanup permission.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cancellation_before_create_acknowledgement_retains_no_cleanup_permission(self):
#         for backend in self.backends():
#             calls = []
#             def execute(database, statement, **kwargs):
#                 calls.append(statement)
#                 if statement.startswith("SELECT EXISTS"):
#                     return "f"
#                 raise KeyboardInterrupt()
#             with patch.object(backend, "_execute", side_effect=execute):
#                 with self.assertRaises(KeyboardInterrupt) as error:
#                     with disposable_store(backend, initialize=lambda *_: None):
#                         pass
#             self.assertTrue(any("no unowned database was removed" in note for note in error.exception.__notes__))
#             self.assertFalse(any(statement.startswith("DROP") for statement in calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_native_acknowledgement_survives_interrupt_while_closing_admin_session
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native acknowledgement survives interrupt while closing admin session.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_acknowledgement_survives_interrupt_while_closing_admin_session(self):
#         backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
#         databases, calls = set(), []
#         class Cursor:
#             description = None
#             def fetchall(self):
#                 return [(False,)]
#         class Connection:
#             created = False
#             def execute(self, statement):
#                 calls.append(statement)
#                 cursor = Cursor()
#                 if statement.startswith("SELECT EXISTS"):
#                     cursor.description = [("exists",)]
#                 elif statement.startswith("CREATE"):
#                     databases.add("mycel_check_native_ack")
#                     self.created = True
#                 elif statement.startswith("DROP"):
#                     databases.remove("mycel_check_native_ack")
#                 return cursor
#         @contextmanager
#         def connect(address):
#             connection = Connection()
#             yield connection
#             if connection.created:
#                 raise KeyboardInterrupt()
#         with patch.object(backend, "_connect", connect), \
#                 patch("mycel._coverage.uuid4", return_value=SimpleNamespace(hex="native_ack")):
#             with self.assertRaises(KeyboardInterrupt):
#                 with disposable_store(backend, initialize=lambda *_: None):
#                     self.fail("interrupted admin close continued")
#         self.assertFalse(databases)
#         self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_native_cleanup_refusal_keeps_owned_fixture_and_failure_bodies_private
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native cleanup refusal keeps owned fixture and failure bodies private.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_cleanup_refusal_keeps_owned_fixture_and_failure_bodies_private(self):
#         backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
#         exists, occupied = True, True
#         calls = []
#         backend._begin_creation("mycel_check_busy")
#         backend._acknowledge_creation("mycel_check_busy")
#
#         class Connection:
#             def execute(self, statement):
#                 nonlocal exists
#                 calls.append(statement)
#                 if statement.startswith("SELECT EXISTS"):
#                     return SimpleNamespace(description=[("exists",)], fetchall=lambda: [(exists,)])
#                 if occupied:
#                     raise ObjectInUse("private-provider-sentinel")
#                 exists = False
#                 return SimpleNamespace(description=None)
#
#         @contextmanager
#         def connect(address):
#             self.assertEqual(address, "postgresql://fixture@localhost/postgres")
#             yield Connection()
#
#         with patch.object(backend, "_connect", connect):
#             with self.assertRaises(RuntimeError) as error:
#                 backend.drop_database("mycel_check_busy")
#             self.assertNotIn("private-provider-sentinel", str(error.exception))
#             self.assertTrue(backend.owns_database("mycel_check_busy"))
#             self.assertTrue(backend.database_exists("mycel_check_busy"))
#             occupied = False
#             backend.drop_database("mycel_check_busy")
#             self.assertFalse(backend.owns_database("mycel_check_busy"))
#             self.assertFalse(backend.database_exists("mycel_check_busy"))
#             before = len(calls)
#             with self.assertRaises(CoverageError):
#                 backend.drop_database("mycel_check_busy")
#             self.assertEqual(len(calls), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_native_cleanup_cancellation_after_removal_preserves_safe_retry_permission
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native cleanup cancellation after removal preserves safe retry permission.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_cleanup_cancellation_after_removal_preserves_safe_retry_permission(self):
#         backend = NativePostgresBackend("postgresql://fixture@localhost/owner")
#         backend._begin_creation("mycel_check_cancel")
#         backend._acknowledge_creation("mycel_check_cancel")
#         exists, interrupt = True, True
#         calls = []
#
#         class Connection:
#             def execute(self, statement):
#                 nonlocal exists
#                 calls.append(statement)
#                 if statement.startswith("SELECT EXISTS"):
#                     return SimpleNamespace(description=[("exists",)], fetchall=lambda: [(exists,)])
#                 exists = False
#                 return SimpleNamespace(description=None)
#
#         @contextmanager
#         def connect(address):
#             self.assertEqual(address, "postgresql://fixture@localhost/postgres")
#             yield Connection()
#             if interrupt:
#                 raise KeyboardInterrupt()
#
#         with patch.object(backend, "_connect", connect):
#             with self.assertRaises(KeyboardInterrupt):
#                 backend.drop_database("mycel_check_cancel")
#             self.assertFalse(exists)
#             self.assertTrue(backend.owns_database("mycel_check_cancel"))
#             interrupt = False
#             backend.drop_database("mycel_check_cancel")
#             self.assertFalse(backend.owns_database("mycel_check_cancel"))
#             self.assertFalse(backend.database_exists("mycel_check_cancel"))
#         self.assertEqual(sum(statement.startswith("DROP") for statement in calls), 2)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_parent_recovers_exact_acknowledged_worker_database_after_admin_close_interrupt
# Reason: Mocked create/drop protocol repeats the journal-recovery flow without observing database ownership. Atomic private journal publication remains covered; actual PostgreSQL destruction is not claimed by this mock.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_parent_recovers_exact_acknowledged_worker_database_after_admin_close_interrupt(self):
#         with tempfile.TemporaryDirectory() as directory:
#             journal = Path(directory)
#             address = "postgresql://fixture@localhost/owner"
#             worker = NativePostgresBackend(address, _ownership_journal=journal)
#             name = "mycel_check_interrupted_worker"
#             databases = {"owner", "mycel_check_unrelated"}
#
#             class Connection:
#                 created = False
#                 def execute(self, statement):
#                     if statement.startswith("SELECT EXISTS"):
#                         return SimpleNamespace(description=[("exists",)], fetchall=lambda: [(False,)])
#                     databases.add(name)
#                     self.created = True
#                     return SimpleNamespace(description=None)
#
#             @contextmanager
#             def connect(address):
#                 connection = Connection()
#                 yield connection
#                 if connection.created:
#                     # The acknowledgement must already be durable here, before
#                     # the child can resume or report anything to its parent.
#                     self.assertTrue((journal / (name + ".json")).is_file())
#                     raise KeyboardInterrupt()
#
#             with patch.object(worker, "_connect", connect):
#                 with self.assertRaises(KeyboardInterrupt):
#                     worker.create_database(name)
#
#             parent = NativePostgresBackend(address, _ownership_journal=journal)
#             def drop(database, statement, **kwargs):
#                 self.assertEqual(statement, f'DROP DATABASE IF EXISTS "{name}"')
#                 databases.remove(database)
#                 return ""
#             with patch.object(parent, "_execute", side_effect=drop) as execute:
#                 self.assertEqual(parent.recover_owned_databases(), (name,))
#                 execute.assert_called_once()
#             self.assertEqual(databases, {"owner", "mycel_check_unrelated"})
#             self.assertEqual(list(journal.iterdir()), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_failed_collision_and_unacknowledged_create_grant_parent_no_cleanup_permission
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Failed collision and unacknowledged create grant parent no cleanup permission.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_failed_collision_and_unacknowledged_create_grant_parent_no_cleanup_permission(self):
#         for collision in (False, True):
#             with self.subTest(collision=collision), tempfile.TemporaryDirectory() as directory:
#                 address = "postgresql://fixture@localhost/owner"
#                 journal = Path(directory)
#                 worker = NativePostgresBackend(address, _ownership_journal=journal)
#                 exists = collision
#                 def execute(database, statement, **kwargs):
#                     nonlocal exists
#                     if statement.startswith("SELECT EXISTS"):
#                         return "t" if exists else "f"
#                     if statement.startswith("CREATE"):
#                         exists = True
#                         raise RuntimeError("private-provider-sentinel")
#                     self.fail("failed unacknowledged creation authorized cleanup")
#                 with patch.object(worker, "_execute", side_effect=execute):
#                     with self.assertRaises(CoverageError):
#                         worker.create_database("mycel_check_unconfirmed")
#                 self.assertTrue(exists)
#                 self.assertEqual(list(journal.iterdir()), [])
#                 parent = NativePostgresBackend(address, _ownership_journal=journal)
#                 with patch.object(parent, "_execute") as boundary:
#                     self.assertEqual(parent.recover_owned_databases(), ())
#                     boundary.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_cleanup_failure_retains_record_and_parent_continues_other_exact_drops
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Cleanup failure retains record and parent continues other exact drops.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cleanup_failure_retains_record_and_parent_continues_other_exact_drops(self):
#         with tempfile.TemporaryDirectory() as directory:
#             address = "postgresql://fixture@localhost/owner"
#             journal = Path(directory)
#             worker = NativePostgresBackend(address, _ownership_journal=journal)
#             names = ("mycel_check_a_busy", "mycel_check_b_closed")
#             for name in names:
#                 worker._begin_creation(name)
#                 worker._acknowledge_creation(name)
#             parent = NativePostgresBackend(address, _ownership_journal=journal)
#             calls = []
#             def drop(database, statement, **kwargs):
#                 calls.append(database)
#                 if database == names[0]:
#                     raise RuntimeError("private-provider-sentinel")
#                 return ""
#             with patch.object(parent, "_execute", side_effect=drop):
#                 with self.assertRaisesRegex(RuntimeError, "failed for 1 ownership records") as error:
#                     parent.recover_owned_databases()
#             self.assertNotIn("private-provider-sentinel", str(error.exception))
#             self.assertEqual(calls, list(names))
#             self.assertEqual([path.stem for path in journal.iterdir()], [names[0]])
#             with patch.object(parent, "_execute", return_value=""):
#                 self.assertEqual(parent.recover_owned_databases(), (names[0],))
#             self.assertEqual(list(journal.iterdir()), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_recovery_rejects_owner_foreign_server_invalid_and_nonprivate_records
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Recovery rejects owner foreign server invalid and nonprivate records.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recovery_rejects_owner_foreign_server_invalid_and_nonprivate_records(self):
#         for fault in ("owner", "server", "filename", "invalid", "public", "symlink"):
#             with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
#                 journal = Path(directory)
#                 address = "postgresql://fixture@localhost/mycel_check_owner"
#                 worker = NativePostgresBackend(address, _ownership_journal=journal)
#                 name = "mycel_check_worker"
#                 worker._begin_creation(name)
#                 worker._acknowledge_creation(name)
#                 record = journal / (name + ".json")
#                 data = json.loads(record.read_text())
#                 if fault == "owner":
#                     data["database"] = "mycel_check_owner"
#                     record.rename(journal / "mycel_check_owner.json")
#                     record = journal / "mycel_check_owner.json"
#                 elif fault == "server":
#                     data["server"] = "foreign-server"
#                 elif fault == "filename":
#                     record.rename(journal / "mycel_check_another.json")
#                     record = journal / "mycel_check_another.json"
#                 elif fault == "invalid":
#                     data["database"] = "mycel_check_worker;DROP"
#                 record.write_text(json.dumps(data))
#                 if fault == "public":
#                     record.chmod(0o644)
#                 elif fault == "symlink":
#                     record.rename(journal / "not-a-record")
#                     record.symlink_to(journal / "not-a-record")
#                 parent = NativePostgresBackend(address, _ownership_journal=journal)
#                 with patch.object(parent, "_execute") as boundary:
#                     with self.assertRaises(RuntimeError):
#                         parent.recover_owned_databases()
#                     boundary.assert_not_called()
#                 self.assertTrue(record.exists())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_ownership_journal_requires_existing_private_directory
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Ownership journal requires existing private directory.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ownership_journal_requires_existing_private_directory(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             insecure = root / "public"
#             insecure.mkdir(mode=0o755)
#             link = root / "link"
#             link.symlink_to(root, target_is_directory=True)
#             for journal in (root / "missing", insecure, link):
#                 with self.subTest(journal=journal), patch("mycel._check_store.store_connection") as boundary:
#                     with self.assertRaises(CoverageError):
#                         NativePostgresBackend("postgresql://fixture@localhost/owner", _ownership_journal=journal)
#                     boundary.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_preflight_really_creates_journals_and_drops_probe_before_returning_safe_label
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Preflight really creates journals and drops probe before returning safe label.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_preflight_really_creates_journals_and_drops_probe_before_returning_safe_label(self):
#         with tempfile.TemporaryDirectory() as directory:
#             journal = Path(directory)
#             backend = NativePostgresBackend("postgresql://private-user@[::1]:6543/private-owner?sslmode=require",
#                                             _ownership_journal=journal)
#             statements = []
#             name = "mycel_check_preflight"
#             def execute(database, statement, **kwargs):
#                 self.assertEqual(database, name)
#                 statements.append(statement)
#                 if statement.startswith("SELECT EXISTS"):
#                     return "f"
#                 if statement.startswith("DROP"):
#                     self.assertTrue((journal / (name + ".json")).exists())
#                 return ""
#             with patch("mycel._check_store.uuid4", return_value=SimpleNamespace(hex="preflight")), \
#                     patch.object(backend, "_execute", side_effect=execute):
#                 self.assertEqual(backend.preflight(), "[::1]:6543")
#             self.assertEqual(sum(statement.startswith("CREATE") for statement in statements), 1)
#             self.assertEqual(sum(statement.startswith("DROP") for statement in statements), 1)
#             self.assertEqual(list(journal.iterdir()), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_check_store.py::NativeCheckRunnerTests.test_preflight_connect_and_create_failures_report_only_safe_one_line_server_label
# Reason: Narrower case removed from this family after retaining test_ownership_records_publish_atomically_and_failed_writes_grant_parent_no_permission. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Preflight connect and create failures report only safe one line server label.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_check_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_preflight_connect_and_create_failures_report_only_safe_one_line_server_label(self):
#         for connected in (False, True):
#             backend = NativePostgresBackend("postgresql://private-user@host%0aheader:6543/private-owner?sslmode=require")
#             def execute(database, statement, **kwargs):
#                 if connected and statement.startswith("SELECT EXISTS"):
#                     return "f"
#                 raise RuntimeError("private-provider-sentinel\nprivate-auth-body")
#             with patch.object(backend, "_execute", side_effect=execute):
#                 with self.assertRaisesRegex(RuntimeError, "cannot create" if connected else "cannot connect") as error:
#                     backend.preflight()
#             message = str(error.exception)
#             self.assertIn("host?0aheader:6543", message)
#             self.assertNotIn("private", message)
#             self.assertNotIn("\n", message)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
