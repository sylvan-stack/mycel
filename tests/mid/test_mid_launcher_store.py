"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_launcher_store as _support
# from test_launcher_store import (
#     LauncherRollbackStoreTests,
#     Path,
#     _frozen_fixture,
#     _wheel_fixture,
#     bundle_fixture,
#     create_stage,
#     digest,
#     io,
#     json,
#     json_bytes,
#     patch,
#     sql,
#     stage_fixture_build,
#     store_state,
#     tarfile,
#     unittest,
# )


# class LauncherRollbackStoreTests(_support.LauncherRollbackStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_launcher_store.py::LauncherRollbackStoreTests.test_build_install_select_withdraw_prune_and_version_rollback_preserve_settings_all_rows_schema_and_sequences
#     def test_build_install_select_withdraw_prune_and_version_rollback_preserve_settings_all_rows_schema_and_sequences(self):
#         history = _History(self.store_fixture)
#         with tempfile.TemporaryDirectory() as directory, history.connect() as connection:
#             fixture = LauncherFixture(directory)
#             fixture.registry = fixture.home / '.mycel/builds'
#             credential_home = os.environ['HOME']
#             private_environment = fixture.environment
#
#             def store_environment(**changes):
#                 # The generated DB uses the normal read-only login Keychain.
#                 # Registry/install paths and MYCEL_CONFIG remain private.
#                 return private_environment(**{**changes, 'HOME': credential_home})
#
#             fixture.environment = store_environment
#             fixture.config.write_bytes(self.store_fixture.settings_file.read_bytes())
#             artifacts = fixture.base / 'documents'
#             artifacts.mkdir()
#             with fixture.config.open('a') as output:
#                 output.write('\n[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(fixture.cwd))
#                     + '\nartifact_root=' + json.dumps(str(artifacts)) + '\n')
#             (fixture.cwd / 'sample.txt').write_text('needle\nordinary\n')
#             history.repositories(connection, 'fixture')
#             identifier, = history.seed(connection, 'fixture', 1)
#             history.details(connection, identifier)
#             expected_ids = [row[0] for row in connection.execute(
#                 'SELECT id FROM public.mycel_activity ORDER BY started_at DESC,id DESC').fetchall()]
#             private_settings = self.store_fixture.settings_file.read_bytes()
#             selected_settings = fixture.config.read_bytes()
#             before = store_state(connection)
#
#             def unchanged(expected=before):
#                 self.assertEqual(store_state(connection), expected)
#                 self.assertEqual(self.store_fixture.settings_file.read_bytes(), private_settings)
#                 self.assertEqual(fixture.config.read_bytes(), selected_settings)
#
#             # Actual release staging is filesystem work. Runtime/provider gate
#             # execution is explicitly finite; this is not Build qualification.
#             staged = stage_fixture_build(fixture.base / 'staged build operation')
#             self.assertEqual(staged['build'], '1')
#             unchanged()
#             fixture.build(product=True, store_format=STORE_FORMAT)
#             fixture.build(product=True, store_format=STORE_FORMAT - 1)
#             unchanged()
#             bundle = bundle_fixture(fixture.base, 'independent bootstrap')
#             installed = install_launcher(bundle, home=fixture.home)
#             self.assertTrue(installed['installed'])
#             unchanged()
#
#             current = fixture.run('-v', '1', 'activity', '--all')
#             self.assertEqual(current.returncode, 0, (current.stdout, current.stderr))
#             self.assertEqual([int(row['id']) for row in json.loads(current.stdout)['entries']], expected_ids)
#             unchanged()
#             # Switching to an older executable never tries a reverse migration.
#             old = fixture.run('activity', '--all')
#             self.assertEqual(old.returncode, 1)
#             self.assertEqual(json.loads(old.stdout)['error']['code'], 'store_format')
#             diagnostic = fixture.run('info')
#             self.assertEqual(diagnostic.returncode, 0)
#             self.assertEqual(json.loads(diagnostic.stdout)['build'], '2')
#             unchanged()
#             withdraw(fixture.registry, '2', 'older supported format')
#             compatible_default = fixture.run('activity', '--all')
#             self.assertEqual(compatible_default.returncode, 0)
#             old_explicit = fixture.run('-v', '2', 'activity', '--all')
#             self.assertEqual(json.loads(old_explicit.stdout)['error']['code'], 'store_format')
#             self.assertIn(b'older supported format', old_explicit.stderr)
#             unchanged()
#             self.assertTrue(prune(fixture.registry, '2')['pruneComplete'])
#             unchanged()
#
#             # A simulated owner migration/new-state write is explicit fixture
#             # preparation. The second snapshot must survive every rollback read.
#             connection.execute('UPDATE public.mycel_store SET format=%s', (STORE_FORMAT + 1,))
#             connection.execute('CREATE TABLE public.mycel_future_state '
#                 '(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, value text NOT NULL)')
#             connection.execute("INSERT INTO public.mycel_future_state(value) VALUES ('retain newer state')")
#             migrated = store_state(connection)
#             for arguments in (('activity', '--all'), ('init',)):
#                 result = fixture.run('-v', '1', *arguments)
#                 self.assertEqual(result.returncode, 1)
#                 self.assertEqual(json.loads(result.stdout)['error']['code'], 'store_format')
#                 unchanged(migrated)
#             diagnostic = fixture.run('-v', '1', 'info')
#             self.assertEqual(diagnostic.returncode, 0)
#             self.assertEqual(json.loads(diagnostic.stdout)['store']['format'], STORE_FORMAT + 1)
#             fallback = fixture.run('-v', '1', 'grep', '-n', 'needle', 'sample.txt')
#             self.assertEqual((fallback.returncode, fallback.stdout), (0, b'1:needle\n'))
#             self.assertTrue(fallback.stderr)
#             unchanged(migrated)
# TEST-TIER-DISABLED-END tests/test_launcher_store.py::LauncherRollbackStoreTests.test_build_install_select_withdraw_prune_and_version_rollback_preserve_settings_all_rows_schema_and_sequences


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:5
# import os
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:8
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:14
# from mycel._store import STORE_FORMAT
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:14

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:16
# from mycel_build._launcher import install_launcher
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:17
# from mycel_build._maintenance import prune, withdraw
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:21
#     from .test_activity_retention import _History
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:21

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:24
#     from .test_launcher_selection import LauncherFixture
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:24

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:26
#     from test_activity_retention import _History
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:26

# TEST-TIER-IMPORTS-BEGIN tests/test_launcher_store.py:29
#     from test_launcher_selection import LauncherFixture
# TEST-TIER-IMPORTS-END tests/test_launcher_store.py:29

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
