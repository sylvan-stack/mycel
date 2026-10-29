"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_check_real as _support
from test_check_real import (
    Path,
    RealActivityCheckStoreTests,
    RealProviderIsolationTests,
    deepcopy,
    fixtures,
    pstats,
    runpy,
    unittest,
)


class RealActivityCheckStoreTests(_support.RealActivityCheckStoreTests):
# TEST-TIER-BEGIN tests/test_check_real.py::RealActivityCheckStoreTests.test_real_check_rejects_missing_duplicate_or_mismatched_public_activity
    def test_real_check_rejects_missing_duplicate_or_mismatched_public_activity(self):
        fixture = fixtures.PublicIngestActivityStoreTests()
        fixture.store_fixture = self.store_fixture
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        script = runpy.run_path(str(Path(_support.__file__).resolve().parents[1] / 'scripts/check_real.py'))
        fixture.package_root = script['_numbered_package'](fixture.base.base)
        verify = script['_activity_problems']
        before = {'entries': fixture.history()}
        result = fixture.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
        after = {'entries': fixture.history()}
        entry, = after['entries']
        detail = fixture.invoke('activity', '--entry', entry['id'])
        self.assertEqual(verify('fixture', result, before, after, detail), [])
        self.assertTrue(detail['entries'][0]['files'])
        self.assertTrue(detail['entries'][0]['decisions'])

        for key, value in [('counts', {}), ('build', 'ff'), ('outcome', 'running'),
                           ('repository', 'other'), ('kind', 'embed'), ('startedBy', 'freshness_check')]:
            with self.subTest(field=key):
                broken = deepcopy(after)
                broken['entries'][0][key] = value
                self.assertTrue(verify('fixture', result, before, broken, detail))
        for broken in (None, {}, {'entries': 'invalid'}, {'entries': [{}]}, before,
                       {'entries': [entry, entry]},
                       {'entries': [entry, {**entry, 'id': '999999999'}]}):
            with self.subTest(history=broken):
                self.assertTrue(verify('fixture', result, before, broken, detail))
        for broken in (None, before, {'entries': [entry]},
                       {'entries': [{**detail['entries'][0], 'files': []}]},
                       {'entries': [{**detail['entries'][0], 'decisions': []}]},
                       {'entries': [{**detail['entries'][0], 'counts': {}}]}):
            with self.subTest(detail=broken):
                self.assertTrue(verify('fixture', result, before, after, broken))
        # Existing valid history cannot masquerade as this changed invocation.
        self.assertTrue(verify('fixture', result, after, after, detail))
        quiet = fixture.invoke('ingest', '--repo', 'fixture')['repositories']['fixture']
        unchanged = {'entries': fixture.history()}
        self.assertEqual(verify('fixture', quiet, after, unchanged, None), [])
        self.assertTrue(verify('fixture', quiet, before, after, detail))
# TEST-TIER-END tests/test_check_real.py::RealActivityCheckStoreTests.test_real_check_rejects_missing_duplicate_or_mismatched_public_activity

# TEST-TIER-BEGIN tests/test_check_real.py::RealActivityCheckStoreTests.test_profile_measures_the_real_numbered_subprocess_without_changing_its_reply
    def test_profile_measures_the_real_numbered_subprocess_without_changing_its_reply(self):
        fixture = fixtures.PublicIngestActivityStoreTests()
        fixture.store_fixture = self.store_fixture
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        script = runpy.run_path(str(Path(_support.__file__).resolve().parents[1] / 'scripts/check_real.py'))
        package = script['_numbered_package'](fixture.base.base)
        fixture.package_root = package
        for number in (1, 2):
            profile = fixture.base.base / f'ingest-{number}.prof'
            status, reply, seconds = script['_mycel'](fixture.base.config, 'ingest', '--repo',
                'fixture', package=package, profile=profile)
            self.assertEqual(status, 0, reply)
            result = reply['repositories']['fixture']
            self.assertEqual(result['changed'], number == 1)
            self.assertGreater(seconds, 0)
            stats = pstats.Stats(str(profile))
            self.assertTrue(any(path.endswith('/mycel/_ingest.py') and name == 'ingest'
                                for path, line, name in stats.stats))
            self.assertEqual(len(fixture.history()), 1)
        # The ordinary command keeps the same quiet reply without a profiler.
        status, quiet, _ = script['_mycel'](fixture.base.config, 'ingest', '--repo',
                                           'fixture', package=package)
        self.assertEqual(status, 0, quiet)
        self.assertEqual(quiet['repositories']['fixture'], result)
# TEST-TIER-END tests/test_check_real.py::RealActivityCheckStoreTests.test_profile_measures_the_real_numbered_subprocess_without_changing_its_reply



class RealProviderIsolationTests(_support.RealProviderIsolationTests):
# TEST-TIER-BEGIN tests/test_check_real.py::RealProviderIsolationTests.test_disposable_check_cannot_read_owner_provider_key_or_send_a_query
    def test_disposable_check_cannot_read_owner_provider_key_or_send_a_query(self):
        import tempfile
        from unittest.mock import patch
        from mycel._settings import load_settings
        from mycel._credentials import Credentials
        from mycel._search import prepare_query
        from mycel._voyage import VoyageClient
        script=runpy.run_path(str(Path(_support.__file__).resolve().parents[1]/'scripts/check_real.py'))
        def transport(*args,**kwargs):
            raise AssertionError('The real-repository check must never send a provider request')
        def factory(credentials,policy,**options):
            return VoyageClient(credentials,policy,**options,_transport=transport)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'settings.toml'
            config.write_text(script['_settings']('postgresql://fixture@unreachable.invalid/store',
                {'fixture':(root/'code',root/'docs')}))
            settings=load_settings(path=config,home=root)
            with patch.object(Credentials,'_keychain',side_effect=AssertionError('Owner key was accessed')):
                result=prepare_query(settings,'the pass publishes its capture',_client_factory=factory)
            self.assertIsNone(result.vector)
            self.assertTrue(result.reason)
# TEST-TIER-END tests/test_check_real.py::RealProviderIsolationTests.test_disposable_check_cannot_read_owner_provider_key_or_send_a_query
