"""The real-repository checker must reject misleading public activity evidence."""

from copy import deepcopy
from pathlib import Path
import runpy
import unittest

from mycel._coverage import proves

try:
    from . import test_ingest_activity as fixtures
except ImportError:
    import test_ingest_activity as fixtures


class RealActivityCheckStoreTests(unittest.TestCase):
    @proves('MYC-12.1', 'MYC-12.2', 'MYC-12.4', 'MYC-12.12', kind='store')
    def test_real_check_rejects_missing_duplicate_or_mismatched_public_activity(self):
        fixture = fixtures.PublicIngestActivityStoreTests()
        fixture.store_fixture = self.store_fixture
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        script = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_real.py'))
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


if __name__ == '__main__':
    unittest.main()
