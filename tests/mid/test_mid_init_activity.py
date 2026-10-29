"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_init_activity as _support
from test_init_activity import (
    BuildIdentityTests,
    InitActivityStoreTests,
    MycelError,
    Path,
    activity,
    bootstrap_invocation_guard,
    contextmanager,
    current_build,
    invocation_is_live,
    io,
    json,
    load_settings,
    patch,
    run,
    store,
    tempfile,
    unittest,
)


class BuildIdentityTests(_support.BuildIdentityTests):
# TEST-TIER-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_development_has_no_number_and_exact_package_identity_ignores_environment
    def test_development_has_no_number_and_exact_package_identity_ignores_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/development-identity.json').write_bytes(b'{"schemaVersion":1,"development":true}\n')
            with patch('mycel._build_identity.files', return_value=root):
                from types import SimpleNamespace
                with patch('mycel._build_identity.sys.flags', SimpleNamespace(isolated=0)):
                    self.assertIsNone(current_build())
                (root / 'data/build-identity.json').write_text('{"schemaVersion":1,"build":26}')
                with patch.dict('os.environ', {'MYCEL_BUILD': '99', 'BUILD_NUMBER': '99'}):
                    self.assertEqual(current_build(), 26)
# TEST-TIER-END tests/test_init_activity.py::BuildIdentityTests.test_development_has_no_number_and_exact_package_identity_ignores_environment

# TEST-TIER-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_damaged_identity_never_falls_back_to_a_number
    def test_damaged_identity_never_falls_back_to_a_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            path = root / 'data/build-identity.json'
            invalid = (b'{}', b'{"schemaVersion":true,"build":1}',
                       b'{"schemaVersion":1,"build":true}', b'{"schemaVersion":1,"build":0}',
                       b'{"schemaVersion":1,"build":1,"build":2}',
                       b'{"schemaVersion":1,"build":1.5}', b'\xff',
                       b'{"schemaVersion":1,"build":1,"secret":"private-sentinel"}')
            for raw in invalid:
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    with patch('mycel._build_identity.files', return_value=root):
                        with self.assertRaises(MycelError) as error:
                            current_build()
                    self.assertEqual(error.exception.code, 'internal')
                    self.assertNotIn('private-sentinel', str(error.exception))
# TEST-TIER-END tests/test_init_activity.py::BuildIdentityTests.test_damaged_identity_never_falls_back_to_a_number

# TEST-TIER-BEGIN tests/test_init_activity.py::BuildIdentityTests.test_missing_installed_identity_and_isolated_development_marker_fail_closed
    def test_missing_installed_identity_and_isolated_development_marker_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            with patch('mycel._build_identity.files', return_value=root):
                with self.assertRaises(MycelError):
                    current_build()
                (root / 'data/development-identity.json').write_bytes(b'{"schemaVersion":1,"development":true}\n')
                from types import SimpleNamespace
                with patch('mycel._build_identity.sys.flags', SimpleNamespace(isolated=1)):
                    with self.assertRaises(MycelError):
                        current_build()
# TEST-TIER-END tests/test_init_activity.py::BuildIdentityTests.test_missing_installed_identity_and_isolated_development_marker_fail_closed



class InitActivityStoreTests(_support.InitActivityStoreTests):
# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit
    def test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit(self):
        original = activity._execute
        witnessed = []
        def observe(connection, sql, parameters=None):
            if sql == activity._OPEN_SQL:
                self.assertTrue(invocation_is_live(connection, parameters[1]))
                with self.connect() as observer:
                    self.assertEqual(store.inspect_store(observer).state, 'empty')
                witnessed.append(parameters[1])
            return original(connection, sql, parameters)
        with self.package(), patch('mycel._activity._execute', side_effect=observe):
            status, reply = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(len(witnessed), 1)
        with self.connect() as connection:
            identifier, = self.entries(connection)
            detail = activity.activity_state(connection, identifier[0])
            self.assertEqual((detail['repository'], detail['kind'], detail['build'], detail['outcome']),
                             (None, 'init', 26, 'done'))
            self.assertEqual(detail['counts'], reply)
            self.assertEqual(detail['indexGeneration'].hex, reply['indexGeneration'].replace('-', ''))
            self.assertEqual(detail['startedBy'], 'command')
            self.assertLessEqual(detail['startedAt'], detail['endedAt'])
            self.assertEqual((detail['files'], detail['decisions']), ([], []))
            self.assertFalse(invocation_is_live(connection, detail['invocation']))
        out = io.StringIO()
        with self.package():
            self.assertEqual(run(['info'], stdout=out, stderr=io.StringIO()), 0)
        self.assertEqual(json.loads(out.getvalue())['build'], '1a')
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_actual_empty_init_commits_global_exact_reply_audit_with_liveness_until_commit

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply
    def test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply(self):
        with self.package():
            self.assertEqual(self.invoke()[0], 0)
            with self.connect() as connection:
                before = self.entries(connection)
                invocations = connection.execute('SELECT count(*) FROM public.mycel_invocations').fetchone()[0]
            status, unchanged = self.invoke()
            self.assertEqual(status, 0)
            self.assertFalse(unchanged['changed'])
            with self.connect() as connection:
                self.assertEqual(self.entries(connection), before)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_invocations').fetchone()[0], invocations)
            status, reply = self.invoke(dimensions=2048)
        self.assertEqual(status, 0)
        self.assertEqual(reply['dimensions'], {'before': 1024, 'after': 2048})
        with self.connect() as connection:
            rows = self.entries(connection)
            self.assertEqual(len(rows), 2)
            self.assertEqual(activity.activity_state(connection, rows[-1][0])['counts'], reply)
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_actual_compatible_init_is_noop_and_dimensions_audit_uses_its_reply

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks
    def test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks(self):
        original = activity._execute
        def fail(connection, sql, parameters=None):
            if sql == activity._OPEN_SQL:
                sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
            return original(connection, sql, parameters)
        with self.package(), patch('mycel._activity._execute', side_effect=fail):
            status, reply = self.invoke()
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.inspect_store(connection).state, 'empty')
            self.assertEqual(connection.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
                "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())").fetchone()[0], 0)
        with self.package():
            self.assertEqual(self.invoke()[0], 0)
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_failure_rolls_back_entire_empty_bootstrap_and_releases_locks

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry
    def test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry(self):
        with self.package():
            self.assertEqual(self.invoke()[0], 0)
            original = activity._execute
            def fail(connection, sql, parameters=None):
                if sql == activity._CLOSE_SQL:
                    sql = sql.replace('public.mycel_activity', 'public.mycel_missing_activity')
                return original(connection, sql, parameters)
            with patch('mycel._activity._execute', side_effect=fail):
                status, reply = self.invoke(dimensions=2048)
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.require_store(connection).dimensions, 1024)
            self.assertEqual(len(self.entries(connection)), 1)
            self.assertEqual(activity.activity_state(connection, self.entries(connection)[0][0])['outcome'], 'done')
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_native_audit_close_failure_rolls_back_dimension_and_keeps_prior_entry

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard
    def test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard(self):
        with self.package('{"schemaVersion":1,"build":true}'):
            status, reply = self.invoke()
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.inspect_store(connection).state, 'empty')
            store.initialize_store(connection, dimensions=1024)
            with connection.transaction():
                with self.assertRaises(MycelError) as error:
                    with bootstrap_invocation_guard(connection):
                        self.fail('No exclusive guard was held')
                self.assertEqual(error.exception.code, 'internal')
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_bad_packaged_identity_refuses_before_schema_change_and_bootstrap_requires_guard

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store
    def test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store(self):
        def fail(connection, identifier, key):
            connection.execute('INSERT INTO public.mycel_missing_invocations VALUES (%s)', (identifier,))
        with self.package(), patch('mycel._locks._record_invocation', side_effect=fail):
            status, reply = self.invoke()
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.inspect_store(connection).state, 'empty')
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_native_invocation_bootstrap_failure_is_internal_and_leaves_empty_store

# TEST-TIER-BEGIN tests/test_init_activity.py::InitActivityStoreTests.test_missing_installed_identity_cannot_silently_initialize_without_audit
    def test_missing_installed_identity_cannot_silently_initialize_without_audit(self):
        with self.package():
            (self.store_fixture.root / 'fictional-package/data/build-identity.json').unlink()
            status, reply = self.invoke()
        self.assertEqual((status, reply['error']['code']), (1, 'internal'))
        with self.connect() as connection:
            self.assertEqual(store.inspect_store(connection).state, 'empty')
# TEST-TIER-END tests/test_init_activity.py::InitActivityStoreTests.test_missing_installed_identity_cannot_silently_initialize_without_audit
