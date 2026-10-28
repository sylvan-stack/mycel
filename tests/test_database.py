"""The native store boundary with only private, injected connections."""

import unittest

from mycel._credentials import Secret, StoreTarget
from mycel._errors import MycelError

SENTINEL = "private-password-not-for-output"
ADDRESS = "postgresql://fixture@127.0.0.1:6543/fixture"


class FakePGconn:
    def __init__(self, needs_password=False):
        self.needs_password = needs_password
        self.finished = False

    def finish(self):
        self.finished = True


class FakeConnection:
    def __init__(self):
        self.closed = False
        self.pgconn = FakePGconn()

    def close(self):
        self.closed = True


class FakeCredentials:
    def __init__(self, address=ADDRESS, password=SENTINEL):
        self.address = address
        self.password = password
        self.requests = []
        self.budgets = []

    def store_target(self, *, password_requested=False, timeout_seconds=None, cancelled=None):
        self.requests.append(password_requested)
        self.budgets.append(timeout_seconds)
        password = Secret(self.password) if password_requested and self.password is not None else None
        return StoreTarget(self.address, password)


class DatabaseTests(unittest.TestCase):
    def assert_unavailable(self, function):
        with self.assertRaises(MycelError) as raised:
            function()
        self.assertEqual(raised.exception.code, "store_unavailable")
        self.assertNotIn(SENTINEL, str(raised.exception))
        self.assertNotIn(ADDRESS, str(raised.exception))
        return raised.exception

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_address_parameters_are_explicit_and_no_ambient_auth_or_service_is_available
#     def test_address_parameters_are_explicit_and_no_ambient_auth_or_service_is_available(self):
#         credentials = FakeCredentials()
#         connection, calls = FakeConnection(), []
#         environment = {"PGHOST": "wrong-host", "PGHOSTADDR": "192.0.2.1", "PGPORT": "1",
#                        "PGDATABASE": "wrong-db", "PGUSER": "wrong-user", "PGPASSWORD": SENTINEL,
#                        "PGPASSFILE": "/wrong/private", "PGSERVICE": "wrong-service", "PGSERVICEFILE": "/wrong/service",
#                        "PGOPTIONS": "-c secret=" + SENTINEL, "PGSSLCERT": "/wrong/cert", "PGSSLKEY": "/wrong/key",
#                        "PGSSLKEYLOGFILE": "/wrong/log", "SSLKEYLOGFILE": "/wrong/log", "HOME": "/private/home",
#                        "UNRELATED": "preserved"}
#
#         def connect(**kwargs):
#             self.assertFalse(any(name.startswith("PG") or name == "SSLKEYLOGFILE" for name in os.environ))
#             self.assertEqual(os.environ["HOME"], "/private/home")
#             calls.append(kwargs)
#             return connection
#
#         with patch.dict(os.environ, environment, clear=True), \
#                 patch("subprocess.run", side_effect=AssertionError("child program")), \
#                 patch.object(Path, "write_text", side_effect=AssertionError("file write")):
#             with store_connection(credentials, _connector=connect) as selected:
#                 self.assertIs(selected, connection)
#                 self.assertFalse(selected.closed)
#             self.assertEqual(dict(os.environ), environment)
#         self.assertTrue(connection.closed)
#         self.assertEqual(credentials.requests, [False])
#         self.assertEqual(len(calls), 1)
#         parameters = calls[0]
#         self.assertEqual((parameters["host"], parameters["hostaddr"], parameters["port"], parameters["user"], parameters["dbname"]),
#                          ("127.0.0.1", "127.0.0.1", "6543", "fixture", "fixture"))
#         self.assertEqual(parameters["password"], "")
#         self.assertEqual(parameters["passfile"], os.devnull + "/mycel-passfile")
#         self.assertNotIn("service", parameters)
#         self.assertEqual(parameters["options"], "")
#         self.assertEqual(parameters["sslcertmode"], "disable")
#         self.assertEqual(parameters["gssencmode"], "disable")
#         self.assertEqual(parameters["require_auth"], "password,md5,scram-sha-256,none")
#         self.assertLessEqual(int(parameters["connect_timeout"]), 5)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_address_parameters_are_explicit_and_no_ambient_auth_or_service_is_available

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_password_is_acquired_only_after_a_native_challenge_and_passed_only_in_memory
#     def test_password_is_acquired_only_after_a_native_challenge_and_passed_only_in_memory(self):
#         credentials, calls = FakeCredentials(), []
#         failed, connection = FakePGconn(needs_password=True), FakeConnection()
#
#         def connect(**parameters):
#             calls.append(parameters)
#             if len(calls) == 1:
#                 self.assertEqual(credentials.requests, [False])
#                 raise psycopg.OperationalError(SENTINEL + ADDRESS, pgconn=failed)
#             self.assertTrue(failed.finished)
#             self.assertEqual(credentials.requests, [False, True])
#             return connection
#
#         stdout, stderr = StringIO(), StringIO()
#         with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
#             with store_connection(credentials, _connector=connect):
#                 pass
#         self.assertEqual([call["password"] for call in calls], ["", SENTINEL])
#         self.assertTrue(failed.finished)
#         self.assertTrue(connection.closed)
#         self.assertEqual(stdout.getvalue(), "")
#         self.assertEqual(stderr.getvalue(), "")
#         self.assertNotIn(SENTINEL, str(credentials))
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_password_is_acquired_only_after_a_native_challenge_and_passed_only_in_memory

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_refusal_without_password_challenge_never_acquires_keychain_password
#     def test_refusal_without_password_challenge_never_acquires_keychain_password(self):
#         credentials, failed = FakeCredentials(), FakePGconn()
#
#         def refused(**kwargs):
#             raise psycopg.OperationalError(SENTINEL + ADDRESS, pgconn=failed)
#
#         def operation():
#             with store_connection(credentials, _connector=refused):
#                 self.fail("connection unexpectedly succeeded")
#
#         self.assert_unavailable(operation)
#         self.assertEqual(credentials.requests, [False])
#         self.assertTrue(failed.finished)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_refusal_without_password_challenge_never_acquires_keychain_password

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_missing_password_sends_none_and_rejected_password_is_not_reacquired
#     def test_missing_password_sends_none_and_rejected_password_is_not_reacquired(self):
#         for password, attempts in ((None, 1), (SENTINEL, 2)):
#             with self.subTest(password_present=password is not None):
#                 credentials, calls, failures = FakeCredentials(password=password), [], []
#
#                 def refused(**kwargs):
#                     calls.append(kwargs)
#                     failure = FakePGconn(needs_password=True)
#                     failures.append(failure)
#                     raise psycopg.OperationalError(SENTINEL + ADDRESS, pgconn=failure)
#
#                 def operation():
#                     with store_connection(credentials, _connector=refused):
#                         self.fail("connection unexpectedly succeeded")
#
#                 self.assert_unavailable(operation)
#                 self.assertEqual(credentials.requests, [False, True])
#                 self.assertEqual(len(calls), attempts)
#                 self.assertTrue(all(failure.finished for failure in failures))
#                 self.assertEqual(calls[0]["password"], "")
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_missing_password_sends_none_and_rejected_password_is_not_reacquired

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_uri_credentials_and_unsupported_options_are_refused_before_resolution_or_connect
#     def test_uri_credentials_and_unsupported_options_are_refused_before_resolution_or_connect(self):
#         for address in ("postgresql://fixture:password@localhost/fixture", "postgresql://fixture@localhost/fixture?service=other",
#                         "postgresql://fixture@localhost/fixture?passfile=/private", "postgresql://fixture@localhost/fixture?options=secret",
#                         "postgresql://fixture@localhost/fixture?sslmode=unknown", "postgresql://fixture@localhost/fixture?connect_timeout=nan",
#                         "postgresql://fixture@localhost/fixture?connect_timeout=0", "postgresql://fixture@localhost/fixture%00other",
#                         "postgresql://fixture@one%2Ctwo/fixture", "postgresql://fixture@one,two/fixture"):
#             with self.subTest(address=address), self.assertRaises(MycelError) as raised:
#                 with store_connection(FakeCredentials(address), _connector=lambda **kwargs: self.fail("connected"),
#                                       _resolver=lambda *args: self.fail("resolved")):
#                     self.fail("accepted")
#             self.assertEqual(raised.exception.code, "settings")
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_uri_credentials_and_unsupported_options_are_refused_before_resolution_or_connect

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_literal_ipv6_skips_dns_and_encoded_target_names_remain_separate_parameters
#     def test_literal_ipv6_skips_dns_and_encoded_target_names_remain_separate_parameters(self):
#         calls = []
#
#         def connect(**kwargs):
#             calls.append(kwargs)
#             return FakeConnection()
#
#         address = "postgresql://user%20name@[::1]:6544/database%20name?sslmode=verify-full&connect_timeout=0.4"
#         with store_connection(FakeCredentials(address), _connector=connect,
#                               _resolver=lambda *args: self.fail("literal IP required DNS")):
#             pass
#         self.assertEqual((calls[0]["host"], calls[0]["hostaddr"], calls[0]["port"], calls[0]["user"], calls[0]["dbname"]),
#                          ("::1", "::1", "6544", "user name", "database name"))
#         self.assertEqual(calls[0]["sslmode"], "verify-full")
#         self.assertLessEqual(calls[0]["timeout_seconds"], 0.4)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_literal_ipv6_skips_dns_and_encoded_target_names_remain_separate_parameters

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_hostname_resolution_preserves_all_explicit_ips_under_one_deadline
#     def test_hostname_resolution_preserves_all_explicit_ips_under_one_deadline(self):
#         calls, resolutions = [], []
#
#         def resolve(host, port):
#             resolutions.append((host, port, threading.current_thread().daemon))
#             return ["::1", "127.0.0.2", "127.0.0.1"]
#
#         def connect(**kwargs):
#             calls.append(kwargs)
#             return FakeConnection()
#
#         with store_connection(FakeCredentials("postgresql://fixture@store.invalid/fixture"), _resolver=resolve, _connector=connect):
#             pass
#         self.assertEqual(resolutions, [("store.invalid", 5432, True)])
#         self.assertEqual(calls[0]["hostaddr"], "127.0.0.1,127.0.0.2,::1")
#         self.assertEqual(calls[0]["host"], "store.invalid,store.invalid,store.invalid")
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_hostname_resolution_preserves_all_explicit_ips_under_one_deadline

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_dns_timeout_or_failure_never_reaches_connector_or_password_acquisition
#     def test_dns_timeout_or_failure_never_reaches_connector_or_password_acquisition(self):
#         release = threading.Event()
#         self.addCleanup(release.set)
#
#         def hung(*args):
#             release.wait(1)
#             return ["127.0.0.1"]
#
#         for resolver in (hung, lambda *args: [], lambda *args: ["not-an-ip"]):
#             credentials = FakeCredentials("postgresql://fixture@store.invalid/fixture")
#             started = time.monotonic()
#
#             def operation():
#                 with store_connection(credentials, timeout_seconds=0.03, _resolver=resolver,
#                                       _connector=lambda **kwargs: self.fail("connected")):
#                     self.fail("accepted")
#
#             self.assert_unavailable(operation)
#             self.assertLess(time.monotonic() - started, 0.4)
#             self.assertEqual(credentials.requests, [False])
#         release.set()
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_dns_timeout_or_failure_never_reaches_connector_or_password_acquisition

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_cancellation_during_dns_returns_before_any_connection_or_password_acquisition
#     def test_cancellation_during_dns_returns_before_any_connection_or_password_acquisition(self):
#         cancel, entered, release = threading.Event(), threading.Event(), threading.Event()
#         self.addCleanup(release.set)
#         credentials = FakeCredentials("postgresql://fixture@store.invalid/fixture")
#
#         def resolve(*args):
#             entered.set()
#             cancel.set()
#             release.wait(1)
#             return ["127.0.0.1"]
#
#         with self.assertRaises(KeyboardInterrupt):
#             with store_connection(credentials, _resolver=resolve, cancel_event=cancel,
#                                   _connector=lambda **kwargs: self.fail("connected")):
#                 self.fail("accepted")
#         self.assertTrue(entered.is_set())
#         self.assertEqual(credentials.requests, [False])
#         release.set()
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_cancellation_during_dns_returns_before_any_connection_or_password_acquisition

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_context_failure_interrupt_and_normal_exit_all_close_connection
#     def test_context_failure_interrupt_and_normal_exit_all_close_connection(self):
#         for error in (None, RuntimeError("operation failed"), KeyboardInterrupt()):
#             connection = FakeConnection()
#             try:
#                 with store_connection(FakeCredentials(), _connector=lambda **kwargs: connection):
#                     if error is not None:
#                         raise error
#             except BaseException as raised:
#                 self.assertIs(raised, error)
#             self.assertTrue(connection.closed)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_context_failure_interrupt_and_normal_exit_all_close_connection

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_environment_is_restored_after_native_error_and_interruption
#     def test_environment_is_restored_after_native_error_and_interruption(self):
#         for error in (psycopg.OperationalError(SENTINEL), KeyboardInterrupt()):
#             environment = {"PGPASSWORD": SENTINEL, "PGOPTIONS": "private", "HOME": "/home"}
#
#             def fail(**kwargs):
#                 self.assertNotIn("PGPASSWORD", os.environ)
#                 os.environ["PGNEW"] = "new"
#                 raise error
#
#             with patch.dict(os.environ, environment, clear=True):
#                 try:
#                     with store_connection(FakeCredentials(), _connector=fail):
#                         self.fail("accepted")
#                 except BaseException as raised:
#                     self.assertIsInstance(raised, KeyboardInterrupt if isinstance(error, KeyboardInterrupt) else MycelError)
#                 self.assertEqual(dict(os.environ), environment)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_environment_is_restored_after_native_error_and_interruption

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_late_connector_success_is_closed_and_not_published_after_total_deadline
#     def test_late_connector_success_is_closed_and_not_published_after_total_deadline(self):
#         connection = FakeConnection()
#
#         def slow(**kwargs):
#             time.sleep(0.03)
#             return connection
#
#         def operation():
#             with store_connection(FakeCredentials(), timeout_seconds=0.01, _connector=slow):
#                 self.fail("late connection was published")
#
#         self.assert_unavailable(operation)
#         self.assertTrue(connection.closed)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_late_connector_success_is_closed_and_not_published_after_total_deadline

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_cancellation_immediately_after_environment_lock_preserves_original_parameters
#     def test_cancellation_immediately_after_environment_lock_preserves_original_parameters(self):
#         cancel, environment = threading.Event(), {"PGPASSWORD": SENTINEL, "PGUSER": "fixture", "HOME": "/home"}
#
#         class Guard:
#             released = False
#
#             def acquire(self, *, timeout):
#                 cancel.set()
#                 return True
#
#             def release(self):
#                 self.released = True
#
#         guard = Guard()
#         with patch.dict(os.environ, environment, clear=True), patch("mycel._database._ENVIRONMENT_GUARD", guard):
#             with self.assertRaises(KeyboardInterrupt):
#                 with _without_libpq_environment(time.monotonic() + 1, cancel):
#                     self.fail("cancelled guard yielded")
#             self.assertEqual(dict(os.environ), environment)
#         self.assertTrue(guard.released)
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_cancellation_immediately_after_environment_lock_preserves_original_parameters

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_native_polling_handshake_is_password_free_until_challenged_and_closes_both_native_handles
#     def test_native_polling_handshake_is_password_free_until_challenged_and_closes_both_native_handles(self):
#         calls, natives = [], []
#
#         class Native(FakePGconn):
#             nonblocking = 0
#
#             def connect_poll(self):
#                 return pq.PollingStatus.FAILED if self.needs_password else pq.PollingStatus.OK
#
#         class Factory:
#             @staticmethod
#             def connect_start(private_conninfo):
#                 calls.append(conninfo.conninfo_to_dict(private_conninfo.decode()))
#                 native = Native(needs_password=len(calls) == 1)
#                 natives.append(native)
#                 if len(calls) == 2:
#                     self.assertTrue(natives[0].finished)
#                 self.assertFalse(any(name.startswith("PG") for name in os.environ))
#                 return native
#
#         class Connection(FakeConnection):
#             def __init__(self, native):
#                 super().__init__()
#                 self.pgconn = native
#                 self.autocommit = False
#
#             def close(self):
#                 super().close()
#                 self.pgconn.finish()
#
#         credentials = FakeCredentials()
#         connector = partial(_native_connect, _pgconn_factory=Factory.connect_start, _connection_factory=Connection)
#         with patch.dict(os.environ, {"PGPASSWORD": "wrong"}):
#             with store_connection(credentials, _connector=connector) as connection:
#                 self.assertTrue(connection.autocommit)
#                 self.assertFalse(connection.closed)
#         self.assertEqual(credentials.requests, [False, True])
#         self.assertEqual(calls[0].get("password", ""), "")
#         self.assertEqual(calls[1]["password"], SENTINEL)
#         self.assertTrue(all(native.finished for native in natives))
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_native_polling_handshake_is_password_free_until_challenged_and_closes_both_native_handles

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_native_polling_cancellation_and_deadline_finish_handles_without_network_or_password_reads
#     def test_native_polling_cancellation_and_deadline_finish_handles_without_network_or_password_reads(self):
#         for cancelled in (False, True):
#             cancel, native = threading.Event(), FakePGconn()
#             native.socket = 42
#             native.connect_poll = lambda: pq.PollingStatus.READING
#
#             class Factory:
#                 @staticmethod
#                 def connect_start(*args):
#                     return native
#
#             class Selector:
#                 def __enter__(self):
#                     return self
#
#                 def __exit__(self, *args):
#                     pass
#
#                 def register(self, descriptor, event):
#                     self.asserted = (descriptor, event)
#
#                 def select(self, *, timeout):
#                     if cancelled:
#                         cancel.set()
#                     else:
#                         time.sleep(timeout)
#                     return []
#
#             credentials = FakeCredentials()
#             with patch("mycel._database.selectors.DefaultSelector", Selector):
#                 with self.assertRaises(KeyboardInterrupt if cancelled else MycelError):
#                     with store_connection(credentials, timeout_seconds=0.01, cancel_event=cancel,
#                                           _connector=partial(_native_connect, _pgconn_factory=Factory.connect_start)):
#                         self.fail("native polling did not stop")
#             self.assertTrue(native.finished)
#             self.assertEqual(credentials.requests, [False])
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_native_polling_cancellation_and_deadline_finish_handles_without_network_or_password_reads

# TEST-TIER-DISABLED-BEGIN tests/test_database.py::DatabaseTests.test_password_acquisition_shares_remaining_total_deadline_and_cancellation_prevents_retry
#     def test_password_acquisition_shares_remaining_total_deadline_and_cancellation_prevents_retry(self):
#         for should_cancel in (False, True):
#             cancel, calls = threading.Event(), []
#
#             class BudgetedCredentials(FakeCredentials):
#                 def store_target(self, *, password_requested=False, timeout_seconds=None, cancelled=None):
#                     result = super().store_target(password_requested=password_requested, timeout_seconds=timeout_seconds,
#                                                   cancelled=cancelled)
#                     if password_requested:
#                         self.cancel_callback = cancelled
#                         if should_cancel:
#                             cancel.set()
#                         else:
#                             time.sleep(0.003)
#                     return result
#
#             credentials = BudgetedCredentials()
#
#             def connect(**kwargs):
#                 calls.append(kwargs)
#                 if len(calls) == 1:
#                     time.sleep(0.003)
#                     raise psycopg.OperationalError(SENTINEL, pgconn=FakePGconn(needs_password=True))
#                 return FakeConnection()
#
#             try:
#                 with store_connection(credentials, timeout_seconds=0.1, cancel_event=cancel, _connector=connect):
#                     self.assertFalse(should_cancel)
#             except KeyboardInterrupt:
#                 self.assertTrue(should_cancel)
#             self.assertIsNone(credentials.budgets[0])
#             self.assertGreater(credentials.budgets[1], 0)
#             self.assertLess(credentials.budgets[1], 0.1)
#             self.assertIsNotNone(credentials.cancel_callback)
#             self.assertEqual(len(calls), 1 if should_cancel else 2)
#             if not should_cancel:
#                 self.assertLess(calls[1]["timeout_seconds"], credentials.budgets[1])
# TEST-TIER-DISABLED-END tests/test_database.py::DatabaseTests.test_password_acquisition_shares_remaining_total_deadline_and_cancellation_prevents_retry


if __name__ == "__main__":
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:3
# from io import StringIO
# TEST-TIER-IMPORTS-END tests/test_database.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:4
# from functools import partial
# TEST-TIER-IMPORTS-END tests/test_database.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:5
# import os
# TEST-TIER-IMPORTS-END tests/test_database.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:6
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_database.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:7
# import threading
# TEST-TIER-IMPORTS-END tests/test_database.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:8
# import time
# TEST-TIER-IMPORTS-END tests/test_database.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:10
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_database.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:12
# import psycopg
# TEST-TIER-IMPORTS-END tests/test_database.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:13
# from psycopg import conninfo, pq
# TEST-TIER-IMPORTS-END tests/test_database.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_database.py:16
# from mycel._database import _native_connect, _without_libpq_environment, store_connection
# TEST-TIER-IMPORTS-END tests/test_database.py:16
