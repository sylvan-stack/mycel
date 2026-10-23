"""Evidence-only dependency refreshes remain scoped applied mutations."""
from hashlib import sha256
import unittest

from psycopg.types.json import Jsonb

from mycel._activity import MutationActivity, activity_state

try:
    from . import test_located_dependency_application as fixtures
except ImportError:
    import test_located_dependency_application as fixtures


class DependencyRefreshCollectionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedDependencyApplicationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def test_orphan_snapshot_refresh_is_scoped_audited_and_a_genuine_repeat_is_quiet(self):
        raw = b'An unowned evidence snapshot left by an earlier operation.'
        digest = sha256(raw).hexdigest()
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            current = self.fixture.current(connection)
            connection.execute('INSERT INTO public.mycel_repository_state(repository,read_locations) '
                               'VALUES (%s,%s)', ('untouched', Jsonb([])))
            for repository in ('fixture', 'untouched'):
                connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s)',
                                   (repository, digest, raw, Jsonb({})))

            with MutationActivity(connection, build=1).session() as activity:
                result = self.fixture.publish(connection, activity=activity)
                activity.finish('done', counts={('fixture', 'ingest'): result.counts})
            self.assertTrue(result.changed)
            self.assertTrue(all(not file.changed for file in result.files))
            self.assertEqual(result.counts['files']['changed'], 0)
            self.assertEqual(result.counts['refsChanged'], 0)
            self.assertEqual(result.counts['pinsCaptured'], 0)
            self.assertEqual(result.counts['pinsInherited'], 0)
            self.assertEqual(result.counts['evidenceSnapshotsCollected'], 1)
            self.assertEqual(result.counts['evidenceManifestsCollected'], 0)
            self.assertEqual(self.fixture.current(connection), current)
            self.assertEqual(connection.execute('SELECT repository,bytes FROM public.mycel_snapshots '
                'WHERE hash=%s ORDER BY repository', (digest,)).fetchall(), [('untouched', raw)])
            rows = connection.execute('SELECT id,repository,kind,counts FROM public.mycel_activity ORDER BY id').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1:3], ('fixture', 'ingest'))
            self.assertEqual(rows[0][3], result.counts)
            entry = activity_state(connection, rows[0][0])
            self.assertEqual(entry['files'], [])
            self.assertEqual(entry['decisions'], [])

            before = self.base.state(connection)
            with MutationActivity(connection, build=1).session() as activity:
                repeated = self.fixture.publish(connection, activity=activity)
                activity.finish('done', counts={('fixture', 'ingest'): repeated.counts})
            self.assertFalse(repeated.changed)
            self.assertEqual(repeated.counts['evidenceSnapshotsCollected'], 0)
            self.assertEqual(repeated.counts['evidenceManifestsCollected'], 0)
            self.assertEqual(self.base.state(connection), before)
            self.assertEqual(connection.execute('SELECT id,repository,kind,counts FROM public.mycel_activity '
                'ORDER BY id').fetchall(), rows)
