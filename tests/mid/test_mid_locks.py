"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_locks as _support
from test_locks import (
    Counter,
    Jsonb,
    LockProtocolTests,
    LockStoreTests,
    MycelError,
    Path,
    Rows,
    ScriptedConnection,
    SimpleNamespace,
    UUID,
    contextmanager,
    datetime,
    deepcopy,
    json,
    locks,
    pq,
    psycopg,
    require_check_database,
    require_store,
    selectors,
    sha256,
    subprocess,
    sys,
    time,
    timezone,
    unittest,
    uuid4,
)


class LockProtocolTests(_support.LockProtocolTests):
# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_nonblocking_structure_protocol_and_balanced_cleanup
    def test_nonblocking_structure_protocol_and_balanced_cleanup(self):
        connection = ScriptedConnection()
        for exclusive in (False, True):
            with locks.structure_guard(connection, exclusive=exclusive):
                self.assertEqual(sum(connection.held.values()), 1)
            self.assertEqual(sum(connection.held.values()), 0)
        self.assertTrue(all("pg_try_advisory_lock" in sql or "pg_advisory_unlock" in sql
                            for sql, _ in connection.statements))
        self.assertTrue(all(params == locks.STRUCTURE_LOCK for _, params in connection.statements))
        connection.busy.add(locks.STRUCTURE_LOCK)
        with self.assertRaises(MycelError) as raised:
            with locks.structure_guard(connection):
                self.fail("busy lock was entered")
        self.assertEqual(raised.exception.code, "busy")
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_nonblocking_structure_protocol_and_balanced_cleanup

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_registry_allocates_distinct_exact_identities_and_reuses_committed_key
    def test_registry_allocates_distinct_exact_identities_and_reuses_committed_key(self):
        connection = ScriptedConnection()
        identities = ["fixture", "Fixture", "é", "e\u0301", "fixture\nother"]
        keys = [locks.allocate_key(connection, namespace, identity)
                for namespace in locks.LockNamespace for identity in identities]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(locks.allocate_key(connection, "repository.pass", "fixture"), keys[0])
        insertions = [params for sql, params in connection.statements if sql.startswith("INSERT")]
        self.assertEqual(len(insertions), len(keys))
        self.assertTrue(all("hash" not in sql for sql, _ in connection.statements))
        self.assertNotEqual(locks.ALLOCATOR_LOCK, locks.STRUCTURE_LOCK)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_registry_allocates_distinct_exact_identities_and_reuses_committed_key

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_allocator_busy_and_failed_allocation_are_bounded_and_release_guard
    def test_allocator_busy_and_failed_allocation_are_bounded_and_release_guard(self):
        connection = ScriptedConnection()
        connection.busy.add(locks.ALLOCATOR_LOCK)
        with self.assertRaises(MycelError) as raised:
            locks.allocate_key(connection, locks.LockNamespace.PASS, "fixture")
        self.assertEqual(raised.exception.code, "busy")
        self.assertFalse(connection.registry)
        connection.busy.clear()
        connection.failure = lambda sql, _: sql.startswith("INSERT")
        with self.assertRaises(MycelError) as raised:
            locks.allocate_key(connection, locks.LockNamespace.PASS, "fixture")
        self.assertEqual(raised.exception.code, "busy")
        self.assertFalse(connection.registry)
        self.assertEqual(sum(connection.held.values()), 0)
        self.assertIn(("SET LOCAL lock_timeout = '1ms'", None), connection.statements)
        self.assertEqual(connection.transactions[-1], "rollback")
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_allocator_busy_and_failed_allocation_are_bounded_and_release_guard

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_operations_share_removal_protection_but_use_separate_exclusive_keys
    def test_operations_share_removal_protection_but_use_separate_exclusive_keys(self):
        connection = ScriptedConnection()
        for operation in ("pass", "embed", "classify", "summaries"):
            with locks.operation_guard(connection, "fixture", operation) as key:
                self.assertEqual(connection.held[((key,), "exclusive")], 1)
                removal = connection.registry[("repository.mutation", "fixture")]
                self.assertEqual(connection.held[((removal,), "shared")], 1)
                self.assertEqual(sum(connection.held.values()), 3)
            self.assertEqual(sum(connection.held.values()), 0)
        operation_keys = {key for (namespace, _), key in connection.registry.items()
                          if namespace != "repository.mutation"}
        self.assertEqual(len(operation_keys), 4)
        with locks.removal_guard(connection, "fixture"):
            self.assertEqual(connection.held[((removal,), "exclusive")], 1)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_operations_share_removal_protection_but_use_separate_exclusive_keys

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_failed_last_acquisition_releases_prior_guards_and_interrupt_releases_all
    def test_failed_last_acquisition_releases_prior_guards_and_interrupt_releases_all(self):
        connection = ScriptedConnection()
        key = locks.allocate_key(connection, locks.LockNamespace.CLASSIFY, "fixture")
        connection.busy.add((key,))
        with self.assertRaises(MycelError) as raised:
            with locks.operation_guard(connection, "fixture", "classify"):
                self.fail("busy classifier guard entered")
        self.assertEqual(raised.exception.code, "busy")
        self.assertEqual(sum(connection.held.values()), 0)
        connection.busy.clear()
        with self.assertRaises(KeyboardInterrupt):
            with locks.invocation_guard(connection), locks.operation_guard(connection, "fixture", "classify"):
                raise KeyboardInterrupt()
        self.assertEqual(sum(connection.held.values()), 0)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_failed_last_acquisition_releases_prior_guards_and_interrupt_releases_all

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_store_failures_name_the_postgres_error_class_and_state_without_native_text
    def test_store_failures_name_the_postgres_error_class_and_state_without_native_text(self):
        error = psycopg.errors.QueryCanceled("canceling statement: public private-looking fixture URI/password")
        message = locks._database_failure(error).message
        self.assertIn("QueryCanceled", message)
        self.assertIn("SQLSTATE 57014", message)
        self.assertNotIn("URI/password", message)
        self.assertEqual(locks._database_failure().message,
                         "The index store could not complete the lock or transaction operation.")
        self.assertEqual(locks.postgres_detail(RuntimeError("not a database fault")), "")
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_store_failures_name_the_postgres_error_class_and_state_without_native_text

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_unlock_failure_closes_session_without_masking_primary_failure_or_native_text
    def test_unlock_failure_closes_session_without_masking_primary_failure_or_native_text(self):
        connection = ScriptedConnection()
        original_execute = connection.execute

        def execute(statement, parameters=None):
            if "pg_advisory_unlock" in statement:
                raise psycopg.OperationalError("public private-looking fixture URI/password")
            return original_execute(statement, parameters)

        connection.execute = execute
        with self.assertRaises(RuntimeError) as raised:
            with locks.structure_guard(connection):
                raise RuntimeError("original public failure")
        self.assertEqual(str(raised.exception), "original public failure")
        self.assertTrue(connection.closed)
        connection = ScriptedConnection()
        original_execute = connection.execute
        connection.execute = execute
        with self.assertRaises(MycelError) as raised:
            with locks.structure_guard(connection):
                pass
        self.assertEqual(raised.exception.code, "store_unavailable")
        self.assertNotIn("URI/password", str(raised.exception))
        self.assertTrue(connection.closed)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_unlock_failure_closes_session_without_masking_primary_failure_or_native_text

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_invocation_guard_records_exact_session_and_balances_failure_cleanup
    def test_invocation_guard_records_exact_session_and_balances_failure_cleanup(self):
        connection = ScriptedConnection()
        identifier = uuid4()
        with locks.invocation_guard(connection, invocation_id=identifier) as invocation:
            self.assertEqual((invocation.backend_pid, invocation.backend_start, invocation.index_generation), connection.session)
            self.assertEqual(connection.invocations[identifier],
                             (identifier, invocation.liveness_key, *connection.session))
            self.assertEqual(connection.held[((invocation.liveness_key,), "exclusive")], 1)
            self.assertTrue(locks.invocation_is_live(connection, invocation))
        self.assertEqual(sum(connection.held.values()), 0)
        with self.assertRaises(MycelError) as raised:
            with locks.invocation_guard(connection, invocation_id=identifier):
                self.fail("reused invocation UUID")
        self.assertEqual(raised.exception.code, "invalid_input")
        self.assertEqual(sum(connection.held.values()), 0)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_invocation_guard_records_exact_session_and_balances_failure_cleanup

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_snapshot_and_atomic_helpers_require_idle_autocommit_and_rollback_interrupts
    def test_snapshot_and_atomic_helpers_require_idle_autocommit_and_rollback_interrupts(self):
        connection = ScriptedConnection()
        with locks.read_snapshot(connection):
            self.assertEqual(connection.info.transaction_status, pq.TransactionStatus.INTRANS)
        begin = next(index for index, (sql, _) in enumerate(connection.statements)
                     if sql.startswith("SET TRANSACTION"))
        self.assertIn("REPEATABLE READ, READ ONLY", connection.statements[begin][0])
        for error in (RuntimeError("public injected failure"), KeyboardInterrupt()):
            with self.assertRaises(type(error)):
                with locks.atomic_transaction(connection):
                    connection.registry[("test", "partial")] = 42
                    raise error
            self.assertNotIn(("test", "partial"), connection.registry)
            self.assertEqual(connection.transactions[-1], "rollback")
        connection.autocommit = False
        with self.assertRaises(MycelError):
            with locks.atomic_transaction(connection):
                self.fail("implicit transaction accepted")
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_snapshot_and_atomic_helpers_require_idle_autocommit_and_rollback_interrupts

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_invalid_identifiers_and_operation_fail_before_sql_or_store_writes
    def test_invalid_identifiers_and_operation_fail_before_sql_or_store_writes(self):
        connection = ScriptedConnection()
        for namespace, identity in (("unknown", "fixture"), (locks.LockNamespace.PASS, ""),
                                    (locks.LockNamespace.PASS, "bad\0name")):
            with self.assertRaises(MycelError):
                locks.allocate_key(connection, namespace, identity)
        with self.assertRaises(MycelError):
            with locks.operation_guard(connection, "fixture", "unknown"):
                pass
        with self.assertRaises(MycelError):
            with locks.invocation_guard(connection, invocation_id="not-a-uuid"):
                pass
        self.assertFalse(connection.statements)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_invalid_identifiers_and_operation_fail_before_sql_or_store_writes

# TEST-TIER-BEGIN tests/test_locks.py::LockProtocolTests.test_real_store_declarations_cannot_be_replaced_by_protocol_proofs
    def test_real_store_declarations_cannot_be_replaced_by_protocol_proofs(self):
        self.assertTrue(unittest.defaultTestLoader.getTestCaseNames(LockStoreTests))
        self.assertEqual(LockStoreTests.check_kind, "store")
        connection = ScriptedConnection()
        self.assertTrue(locks.invocation_is_live(connection, uuid4()))
        sql = connection.statements[-1][0]
        for predicate in ("a.backend_start = i.backend_start", "l.pid = a.pid", "l.granted",
                          "l.objsubid = 1", "k.namespace = 'invocation.liveness'",
                          "s.index_generation = i.index_generation"):
            self.assertIn(predicate, sql)
# TEST-TIER-END tests/test_locks.py::LockProtocolTests.test_real_store_declarations_cannot_be_replaced_by_protocol_proofs



class LockStoreTests(_support.LockStoreTests):
# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_pass_embed_and_distinct_repositories_follow_conflict_matrix
    def test_pass_embed_and_distinct_repositories_follow_conflict_matrix(self):
        with self.connect() as first, self.connect() as second:
            with locks.operation_guard(first, "fixture", "pass"):
                self.busy(locks.operation_guard(second, "fixture", "pass"))
                with locks.operation_guard(second, "fixture", "embed"):
                    pass
                with locks.operation_guard(second, "other", "pass"):
                    pass
                with locks.read_snapshot(second):
                    self.assertEqual(second.execute("SELECT count(*) FROM public.mycel_lock_keys").fetchone()[0], 5)
            for operation in ("embed", "classify", "summaries"):
                with locks.operation_guard(first, "fixture", operation):
                    self.busy(locks.operation_guard(second, "fixture", operation))
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_pass_embed_and_distinct_repositories_follow_conflict_matrix

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_structure_removal_and_every_mutation_guard_refuse_conflicts
    def test_structure_removal_and_every_mutation_guard_refuse_conflicts(self):
        with self.connect() as first, self.connect() as second:
            for operation in ("pass", "embed", "classify", "summaries"):
                with locks.operation_guard(first, "fixture", operation):
                    self.busy(locks.removal_guard(second, "fixture"))
                    self.busy(locks.structure_guard(second, exclusive=True))
            with locks.mutation_guard(first, "fixture"):
                self.busy(locks.removal_guard(second, "fixture"))
            with locks.removal_guard(first, "fixture"):
                for operation in ("pass", "embed", "classify", "summaries"):
                    self.busy(locks.operation_guard(second, "fixture", operation))
                self.busy(locks.mutation_guard(second, "fixture"))
            with locks.structure_guard(first, exclusive=True):
                self.busy(locks.operation_guard(second, "fixture", "pass"))
                self.busy(locks.read_snapshot(second))
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_structure_removal_and_every_mutation_guard_refuse_conflicts

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_paid_model_interval_retains_operation_liveness_and_releases_pass_lock
    def test_paid_model_interval_retains_operation_liveness_and_releases_pass_lock(self):
        with self.connect() as owner, self.connect() as other:
            for operation in ("classify", "summaries"):
                with locks.invocation_guard(owner) as invocation, locks.operation_guard(owner, "fixture", operation):
                    with locks.operation_guard(owner, "fixture", "pass"), locks.atomic_transaction(owner):
                        owner.execute("SELECT 1")  # Immutable capture transaction.
                    self.assertTrue(locks.invocation_is_live(other, invocation))
                    self.busy(locks.operation_guard(other, "fixture", operation))
                    self.busy(locks.removal_guard(other, "fixture"))
                    with locks.operation_guard(other, "fixture", "pass"):
                        self.busy(locks.operation_guard(owner, "fixture", "pass"))
                    with locks.operation_guard(owner, "fixture", "pass"), locks.atomic_transaction(owner):
                        owner.execute("SELECT 1")  # Guarded publication transaction.
                self.assertFalse(locks.invocation_is_live(other, invocation))
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_paid_model_interval_retains_operation_liveness_and_releases_pass_lock

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_atomic_change_rolls_back_all_rows_and_commits_complete_changes
    def test_atomic_change_rolls_back_all_rows_and_commits_complete_changes(self):
        with self.connect() as connection:
            with self.assertRaises(RuntimeError):
                with locks.operation_guard(connection, "fixture", "pass"), locks.atomic_transaction(connection):
                    for repository in ("fixture", "other"):
                        connection.execute("INSERT INTO public.mycel_repository_state (repository, read_locations) VALUES (%s,%s)",
                                           (repository, Jsonb({"value": 0})))
                    raise RuntimeError("public injected failure")
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_repository_state").fetchone()[0], 0)
            with locks.operation_guard(connection, "fixture", "pass"), locks.atomic_transaction(connection):
                for repository in ("fixture", "other"):
                    connection.execute("INSERT INTO public.mycel_repository_state (repository, read_locations) VALUES (%s,%s)",
                                       (repository, Jsonb({"value": 0})))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_repository_state").fetchone()[0], 2)
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_atomic_change_rolls_back_all_rows_and_commits_complete_changes

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_snapshot_keeps_first_committed_state_and_rejects_writes
    def test_snapshot_keeps_first_committed_state_and_rejects_writes(self):
        with self.connect() as reader, self.connect() as writer:
            with locks.atomic_transaction(writer):
                writer.execute("INSERT INTO public.mycel_repository_state (repository, read_locations) VALUES ('fixture', %s)",
                               (Jsonb({"value": 0}),))
            query = "SELECT read_locations FROM public.mycel_repository_state WHERE repository='fixture'"
            with locks.read_snapshot(reader):
                self.assertEqual(reader.execute(query).fetchone()[0], {"value": 0})
                with locks.atomic_transaction(writer):
                    writer.execute("UPDATE public.mycel_repository_state SET read_locations=%s WHERE repository='fixture'",
                                   (Jsonb({"value": 1}),))
                self.assertEqual(reader.execute(query).fetchone()[0], {"value": 0})
            self.assertEqual(reader.execute(query).fetchone()[0], {"value": 1})
            with self.assertRaises(MycelError):
                with locks.read_snapshot(reader):
                    reader.execute("DELETE FROM public.mycel_repository_state")
            self.assertEqual(reader.execute("SELECT count(*) FROM public.mycel_repository_state").fetchone()[0], 1)
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_snapshot_keeps_first_committed_state_and_rejects_writes

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_allocator_guard_and_uncommitted_unique_conflict_refuse_without_waiting
    def test_allocator_guard_and_uncommitted_unique_conflict_refuse_without_waiting(self):
        with self.connect() as first, self.connect() as second:
            existing = locks.allocate_key(first, locks.LockNamespace.PASS, "existing")
            with locks._session_guard(first, locks.ALLOCATOR_LOCK, shared=False, message="fixture"):
                self.assertEqual(locks.allocate_key(second, locks.LockNamespace.PASS, "existing"), existing)
                started = time.monotonic()
                with self.assertRaises(MycelError) as raised:
                    locks.allocate_key(second, locks.LockNamespace.PASS, "new")
                self.assertEqual(raised.exception.code, "busy")
                self.assertLess(time.monotonic() - started, 0.5)
            with locks.atomic_transaction(first):
                first.execute("INSERT INTO public.mycel_lock_keys (namespace,identity) VALUES ('repository.pass','raced')")
                started = time.monotonic()
                with self.assertRaises(MycelError) as raised:
                    locks.allocate_key(second, locks.LockNamespace.PASS, "raced")
                self.assertEqual(raised.exception.code, "busy")
                # This exercises an actual uncommitted unique-key conflict,
                # which has no INSERT ... NOWAIT syntax. A 100 ms fallback
                # would fail this bound even on an otherwise idle server.
                self.assertLess(time.monotonic() - started, 0.1)
                self.assertEqual(second.info.transaction_status, pq.TransactionStatus.IDLE)
                self.assertEqual(second.execute(
                    "SELECT count(*) FROM public.mycel_lock_keys "
                    "WHERE namespace='repository.pass' AND identity='raced'").fetchone(), (0,))
                # Refusal must roll back the allocation and release its
                # session guard, while the original writer still holds its row.
                with locks._session_guard(first, locks.ALLOCATOR_LOCK, shared=False, message="fixture"):
                    pass
            self.assertEqual(locks.allocate_key(second, locks.LockNamespace.PASS, "raced"),
                             locks.allocate_key(first, locks.LockNamespace.PASS, "raced"))
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_allocator_guard_and_uncommitted_unique_conflict_refuse_without_waiting

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_exact_liveness_uses_full_bigint_session_start_and_not_other_lock_holders
    def test_exact_liveness_uses_full_bigint_session_start_and_not_other_lock_holders(self):
        with self.connect() as owner, self.connect() as other:
            owner.execute("SELECT pg_catalog.setval('public.mycel_lock_keys_key_seq', 4294967311, false)")
            with locks.invocation_guard(owner) as invocation:
                self.assertGreater(invocation.liveness_key, 2**32)
                self.assertTrue(locks.invocation_is_live(other, invocation))
                with locks.atomic_transaction(owner):
                    owner.execute("UPDATE public.mycel_invocations SET backend_start=backend_start-interval '1 second' WHERE id=%s",
                                  (invocation.id,))
                self.assertFalse(locks.invocation_is_live(other, invocation))
                with locks.atomic_transaction(owner):
                    owner.execute("UPDATE public.mycel_invocations SET backend_start=%s WHERE id=%s",
                                  (invocation.backend_start, invocation.id))
                self.assertTrue(locks.invocation_is_live(other, invocation))
            with locks._session_guard(other, invocation.liveness_key, shared=False, message="fixture"):
                self.assertFalse(locks.invocation_is_live(other, invocation))
            with locks.operation_guard(other, "fixture", "pass"):
                self.assertFalse(locks.invocation_is_live(other, invocation))
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_exact_liveness_uses_full_bigint_session_start_and_not_other_lock_holders

# TEST-TIER-BEGIN tests/test_locks.py::LockStoreTests.test_killed_owning_process_releases_every_lock_without_cleanup_files
    def test_killed_owning_process_releases_every_lock_without_cleanup_files(self):
        fixture = self.store_fixture
        def files():
            return {str(path.relative_to(fixture.root)): sha256(path.read_bytes()).hexdigest()
                    for path in fixture.root.rglob("*") if path.is_file()}
        before = files()
        # Only the disposable settings filename is passed. The child reads it
        # itself; argv/environment contain no store URI or credential value.
        program = """
import json, time
from urllib.parse import unquote, urlsplit
from mycel._coverage import require_check_database
from mycel._settings import load_settings
from mycel._credentials import Credentials
from mycel._database import store_connection
from mycel._locks import invocation_guard, operation_guard
from mycel._safeguards import InvocationPolicy
settings = load_settings()
settings.require_valid()
database = require_check_database(unquote(urlsplit(settings.values['store']['address']).path[1:]))
with store_connection(Credentials(settings, InvocationPolicy('init'))) as connection:
    assert connection.execute('SELECT pg_catalog.current_database()').fetchone()[0] == database
    with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'pass'):
        print(json.dumps({'invocation': str(invocation.id)}), flush=True)
        time.sleep(60)
"""
        process = subprocess.Popen((sys.executable, "-c", program), cwd=fixture.root,
                                   env={"HOME": str(Path.home()), "MYCEL_CONFIG": str(fixture.settings_file),
                                        "PATH": "/usr/bin:/bin", "LC_ALL": "C",
                                        "PYTHONDONTWRITEBYTECODE": "1",
                                        "PYTHONPATH": str(Path(locks._support.__file__).parent.parent)},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(5), "Fictional lock holder did not become ready.")
            payload = json.loads(process.stdout.readline())
            identifier = UUID(payload["invocation"])
            with self.connect() as other:
                self.assertTrue(locks.invocation_is_live(other, identifier))
                self.busy(locks.operation_guard(other, "fixture", "pass"))
                process.kill()
                process.wait(timeout=5)
                until = time.monotonic() + 2
                while locks.invocation_is_live(other, identifier) and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertFalse(locks.invocation_is_live(other, identifier))
                with locks.operation_guard(other, "fixture", "pass"):
                    pass
                with locks.removal_guard(other, "fixture"):
                    pass
                with locks.structure_guard(other, exclusive=True):
                    pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        self.assertEqual(files(), before)
# TEST-TIER-END tests/test_locks.py::LockStoreTests.test_killed_owning_process_releases_every_lock_without_cleanup_files
