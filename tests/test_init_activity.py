"""Actual init producer with an immutable fixture Build and native transactions."""

import io
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings


class BuildIdentityTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_development_has_no_number_and_exact_package_identity_ignores_environment
#     def test_development_has_no_number_and_exact_package_identity_ignores_environment(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             (root / 'data').mkdir()
#             (root / 'data/development-identity.json').write_bytes(b'{"schemaVersion":1,"development":true}\n')
#             with patch('mycel._build_identity.files', return_value=root):
#                 from types import SimpleNamespace
#                 with patch('mycel._build_identity.sys.flags', SimpleNamespace(isolated=0)):
#                     self.assertIsNone(current_build())
#                 (root / 'data/build-identity.json').write_text('{"schemaVersion":1,"build":26}')
#                 with patch.dict('os.environ', {'MYCEL_BUILD': '99', 'BUILD_NUMBER': '99'}):
#                     self.assertEqual(current_build(), 26)
# TEST-TIER-DISABLED-END tests/test_init_activity.py::BuildIdentityTests.test_development_has_no_number_and_exact_package_identity_ignores_environment

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_damaged_identity_never_falls_back_to_a_number
#     def test_damaged_identity_never_falls_back_to_a_number(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             (root / 'data').mkdir()
#             path = root / 'data/build-identity.json'
#             invalid = (b'{}', b'{"schemaVersion":true,"build":1}',
#                        b'{"schemaVersion":1,"build":true}', b'{"schemaVersion":1,"build":0}',
#                        b'{"schemaVersion":1,"build":1,"build":2}',
#                        b'{"schemaVersion":1,"build":1.5}', b'\xff',
#                        b'{"schemaVersion":1,"build":1,"secret":"private-sentinel"}')
#             for raw in invalid:
#                 with self.subTest(raw=raw):
#                     path.write_bytes(raw)
#                     with patch('mycel._build_identity.files', return_value=root):
#                         with self.assertRaises(MycelError) as error:
#                             current_build()
#                     self.assertEqual(error.exception.code, 'internal')
#                     self.assertNotIn('private-sentinel', str(error.exception))
# TEST-TIER-DISABLED-END tests/test_init_activity.py::BuildIdentityTests.test_damaged_identity_never_falls_back_to_a_number

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_missing_installed_identity_and_isolated_development_marker_fail_closed
#     def test_missing_installed_identity_and_isolated_development_marker_fail_closed(self):
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             (root / 'data').mkdir()
#             with patch('mycel._build_identity.files', return_value=root):
#                 with self.assertRaises(MycelError):
#                     current_build()
#                 (root / 'data/development-identity.json').write_bytes(b'{"schemaVersion":1,"development":true}\n')
#                 from types import SimpleNamespace
#                 with patch('mycel._build_identity.sys.flags', SimpleNamespace(isolated=1)):
#                     with self.assertRaises(MycelError):
#                         current_build()
# TEST-TIER-DISABLED-END tests/test_init_activity.py::BuildIdentityTests.test_missing_installed_identity_and_isolated_development_marker_fail_closed


class InitActivityStoreTests(unittest.TestCase):
    check_kind = "store"

    initialize_store = staticmethod(lambda backend, settings_file: None)

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    @contextmanager
    def package(self, raw='{"schemaVersion":1,"build":26}'):
        root = self.store_fixture.root / 'fictional-package'
        (root / 'data').mkdir(parents=True, exist_ok=True)
        (root / 'data/build-identity.json').write_text(raw)
        with patch('mycel._build_identity.files', return_value=root):
            yield

    def invoke(self, dimensions=None):
        snapshot = load_settings(path=self.store_fixture.settings_file)
        if dimensions is not None:
            from mycel._settings import SettingsSnapshot, _freeze
            values = {
                **snapshot.values, 'embedding': {**snapshot.values['embedding'], 'dimensions': dimensions}}
            snapshot = SettingsSnapshot(snapshot.file, _freeze(values), snapshot.exists, snapshot.readable)
        out = io.StringIO()
        with patch('mycel._cli.load_settings', return_value=snapshot):
            status = run(['init'], stdout=out, stderr=io.StringIO())
        return status, json.loads(out.getvalue())

    def entries(self, connection):
        return connection.execute('SELECT id FROM public.mycel_activity ORDER BY id').fetchall()

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit
#     def test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit(self):
#         original = activity._execute
#         witnessed = []
#         def observe(connection, sql, parameters=None):
#             if sql == activity._OPEN_SQL:
#                 self.assertTrue(invocation_is_live(connection, parameters[1]))
#                 with self.connect() as observer:
#                     self.assertEqual(store.inspect_store(observer).state, 'empty')
#                 witnessed.append(parameters[1])
#             return original(connection, sql, parameters)
#         with self.package(), patch('mycel._activity._execute', side_effect=observe):
#             status, reply = self.invoke()
#         self.assertEqual(status, 0)
#         self.assertEqual(len(witnessed), 1)
#         with self.connect() as connection:
#             identifier, = self.entries(connection)
#             detail = activity.activity_state(connection, identifier[0])
#             self.assertEqual((detail['repository'], detail['kind'], detail['build'], detail['outcome']),
#                              (None, 'init', 26, 'done'))
#             self.assertEqual(detail['counts'], reply)
#             self.assertEqual(detail['indexGeneration'].hex, reply['indexGeneration'].replace('-', ''))
#             self.assertEqual(detail['startedBy'], 'command')
#             self.assertLessEqual(detail['startedAt'], detail['endedAt'])
#             self.assertEqual((detail['files'], detail['decisions']), ([], []))
#             self.assertFalse(invocation_is_live(connection, detail['invocation']))
#         out = io.StringIO()
#         with self.package():
#             self.assertEqual(run(['info'], stdout=out, stderr=io.StringIO()), 0)
#         self.assertEqual(json.loads(out.getvalue())['build'], '1a')
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply
#     def test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply(self):
#         with self.package():
#             self.assertEqual(self.invoke()[0], 0)
#             with self.connect() as connection:
#                 before = self.entries(connection)
#                 invocations = connection.execute('SELECT count(*) FROM public.mycel_invocations').fetchone()[0]
#             status, unchanged = self.invoke()
#             self.assertEqual(status, 0)
#             self.assertFalse(unchanged['changed'])
#             with self.connect() as connection:
#                 self.assertEqual(self.entries(connection), before)
#                 self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_invocations').fetchone()[0], invocations)
#             status, reply = self.invoke(dimensions=2048)
#         self.assertEqual(status, 0)
#         self.assertEqual(reply['dimensions'], {'before': 1024, 'after': 2048})
#         with self.connect() as connection:
#             rows = self.entries(connection)
#             self.assertEqual(len(rows), 2)
#             self.assertEqual(activity.activity_state(connection, rows[-1][0])['counts'], reply)
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks
#     def test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks(self):
#         original = activity._execute
#         def fail(connection, sql, parameters=None):
#             if sql == activity._OPEN_SQL:
#                 sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
#             return original(connection, sql, parameters)
#         with self.package(), patch('mycel._activity._execute', side_effect=fail):
#             status, reply = self.invoke()
#         self.assertEqual((status, reply['error']['code']), (1, 'internal'))
#         with self.connect() as connection:
#             self.assertEqual(store.inspect_store(connection).state, 'empty')
#             self.assertEqual(connection.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
#                 "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())").fetchone()[0], 0)
#         with self.package():
#             self.assertEqual(self.invoke()[0], 0)
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry
#     def test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry(self):
#         with self.package():
#             self.assertEqual(self.invoke()[0], 0)
#             original = activity._execute
#             def fail(connection, sql, parameters=None):
#                 if sql == activity._CLOSE_SQL:
#                     sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
#                 return original(connection, sql, parameters)
#             with patch('mycel._activity._execute', side_effect=fail):
#                 status, reply = self.invoke(dimensions=2048)
#         self.assertEqual((status, reply['error']['code']), (1, 'internal'))
#         with self.connect() as connection:
#             self.assertEqual(store.require_store(connection).dimensions, 1024)
#             self.assertEqual(len(self.entries(connection)), 1)
#             self.assertEqual(activity.activity_state(connection, self.entries(connection)[0][0])['outcome'], 'done')
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard
#     def test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard(self):
#         with self.package('{"schemaVersion":1,"build":true}'):
#             status, reply = self.invoke()
#         self.assertEqual((status, reply['error']['code']), (1, 'internal'))
#         with self.connect() as connection:
#             self.assertEqual(store.inspect_store(connection).state, 'empty')
#             store.initialize_store(connection, dimensions=1024)
#             with connection.transaction():
#                 with self.assertRaises(MycelError) as error:
#                     with bootstrap_invocation_guard(connection):
#                         self.fail('No exclusive guard was held')
#                 self.assertEqual(error.exception.code, 'internal')
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store
#     def test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store(self):
#         def fail(connection, identifier, key):
#             connection.execute('INSERT INTO public.mycel_missing_invocations VALUES (%s)', (identifier,))
#         with self.package(), patch('mycel._locks._record_invocation', side_effect=fail):
#             status, reply = self.invoke()
#         self.assertEqual((status, reply['error']['code']), (1, 'internal'))
#         with self.connect() as connection:
#             self.assertEqual(store.inspect_store(connection).state, 'empty')
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store

# TEST-TIER-DISABLED-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_missing_installed_identity_cannot_silently_initialize_without_audit
#     def test_missing_installed_identity_cannot_silently_initialize_without_audit(self):
#         with self.package():
#             (self.store_fixture.root / 'fictional-package/data/build-identity.json').unlink()
#             status, reply = self.invoke()
#         self.assertEqual((status, reply['error']['code']), (1, 'internal'))
#         with self.connect() as connection:
#             self.assertEqual(store.inspect_store(connection).state, 'empty')
# TEST-TIER-DISABLED-END tests/test_init_activity.py::InitActivityStoreTests.test_missing_installed_identity_cannot_silently_initialize_without_audit


if __name__ == '__main__':
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:6
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:7
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:11
# from mycel import _activity as activity, _store as store
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:12
# from mycel._build_identity import current_build
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:14
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_init_activity.py:15
# from mycel._locks import bootstrap_invocation_guard, invocation_is_live
# TEST-TIER-IMPORTS-END tests/test_init_activity.py:15
