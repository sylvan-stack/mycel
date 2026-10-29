# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured regressions for valid changes to a declared source selection.

Every publication passes through the complete located producer. The checks
keep immutable observation pins distinct from accepted edits and confirmations.
"""


import unittest

from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._resolver import SourceResolver

try:
    from . import test_relate as fixtures
except ImportError:
    import test_relate as fixtures


FAMILY = b'class Policy:\n    """Governing policy."""\n    def apply(self):\n        return 1\n'
CHUNK = b'def Policy():\n    return 2\n'
SOURCE = 'fixture:@code/policy.py#Policy'


class RelationSelectionRegressionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.harness = fixtures.RelateStoreTests()
        self.harness.store_fixture = self.store_fixture
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.fixture, self.base = self.harness.fixture, self.harness.base
        self.guide = self.harness.guide

    def declare(self, *, source=SOURCE, original=FAMILY):
        self.fixture.code.write_bytes(original)
        self.guide.write_bytes(self.guide.read_bytes().replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\n' + source.encode() + b'\n-->'))
        # Retain the original dependant and source in a real branch so an exact
        # disk restoration can recover their already owned versions and pins.
        self.base.commit()
        return self.guide.read_bytes()

    def current(self, connection):
        rows = connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash,r.xmin::text FROM public.mycel_relations r
            JOIN public.mycel_locations c ON c.chunk_version=r.left_version AND c.kind='disk'
            JOIN public.mycel_file_locations f ON f.id=c.file_location AND f.kind='disk'
              AND f.id::text=r.state->'declarationLocation'->>'file'
            LEFT JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
            WHERE r.repository='fixture' AND c.metadata->>'name'='Guide' ORDER BY r.id""").fetchall()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def pin(self, row):
        return row[0], row[1], row[4], row[5]

    def reasons(self, connection, row):
        return tuple(value[0] for value in connection.execute("""SELECT reason FROM public.mycel_stale_reasons
            WHERE repository='fixture' AND reason->>'relation'=%s ORDER BY reason::text""",
            (str(row[0]),)).fetchall())

    def assert_observed(self, connection, original, baseline, *, current_kind, raw, removed=False):
        row = self.current(connection)
        expected = {'related_changed', 'source_removed'} if removed else {'related_changed'}
        self.assertEqual(self.pin(row), self.pin(original))
        self.assertEqual(row[2], SOURCE)
        self.assertEqual(row[3]['selection']['kind'], current_kind)
        self.assertEqual(row[3]['resolution']['place'], SOURCE)
        self.assertEqual(row[3]['sourceExistence'], 'present')
        self.assertEqual(set(row[3]['reasons']), expected)
        kept = EvidenceStore(connection).read_baseline('fixture', row[5])
        self.assertEqual(kept.manifest.canonical_bytes, baseline.manifest.canonical_bytes)
        self.assertEqual([snapshot.source for snapshot in kept.snapshots],
                         [snapshot.source for snapshot in baseline.snapshots])
        resolution = SourceResolver.from_store(connection, self.base.settings).resolve(SOURCE, purpose='source')
        self.assertIsNotNone(resolution.selection)
        self.assertEqual(resolution.selection.kind, current_kind)
        self.assertEqual(resolution.selection.file.source, raw)
        reasons = self.reasons(connection, row)
        self.assertEqual({reason['kind'] for reason in reasons}, expected)
        self.assertTrue(all(reason['edge'] == 'related' and 'via' not in reason for reason in reasons))
        if removed:
            self.assertEqual([reason['source']['address'] for reason in reasons if reason['kind'] == 'source_removed'],
                             ['fixture:@code/policy.py#Policy.apply'])
        self.assertEqual(self.fixture.role(connection), 'authored')
        self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone(), (0,))
        self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
        return row

    def assert_restored(self, connection, original, baseline):
        restored = self.current(connection)
        self.assertEqual(self.pin(restored), self.pin(original))
        self.assertEqual(restored[3]['reasons'], [])
        self.assertEqual(self.reasons(connection, restored), ())
        self.assertEqual(EvidenceStore(connection).read_baseline('fixture', restored[5]).manifest.canonical_bytes,
                         baseline.manifest.canonical_bytes)


    def accepted_edit_and_restoration(self, *, original_source, changed_source, changed_kind, removed):
        original_guide = self.declare(original=original_source)
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            original = self.current(connection)
            baseline = EvidenceStore(connection).read_baseline('fixture', original[5])
            self.fixture.code.write_bytes(changed_source)
            self.fixture.publish(connection)
            self.assert_observed(connection, original, baseline,
                current_kind=changed_kind, raw=changed_source, removed=removed)
            self.guide.write_bytes(original_guide.replace(b'Original dependant.', b'Substantively revised dependant.'))
            self.fixture.publish(connection)
            accepted = self.current(connection)
            self.assertNotEqual(accepted[1], original[1])
            self.assertNotEqual(accepted[5], original[5])
            self.assertEqual(accepted[3]['reasons'], [])
            self.assertEqual(self.reasons(connection, accepted), ())
            accepted_baseline = EvidenceStore(connection).read_baseline('fixture', accepted[5])
            self.assertEqual(accepted_baseline.manifest.payload['selection'], changed_kind)
            selected = SourceResolver.from_store(connection, self.base.settings).resolve(SOURCE, purpose='source').selection
            self.assertIsNotNone(selected)
            self.assertTrue(all(member.chunk.source in [snapshot.source for snapshot in accepted_baseline.snapshots]
                                for member in selected.members))
            # Restoring the dependant selects its old version and old pin, even
            # while the source still has the changed valid selection kind.
            self.guide.write_bytes(original_guide)
            self.fixture.publish(connection)
            self.assert_observed(connection, original, baseline,
                current_kind=changed_kind, raw=changed_source, removed=removed)
            self.fixture.code.write_bytes(original_source)
            self.fixture.publish(connection)
            self.assert_restored(connection, original, baseline)
