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

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores
#     def test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores(self):
#         self.declare()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current(connection)
#             baseline = EvidenceStore(connection).read_baseline('fixture', original[5])
#             self.assertEqual(baseline.manifest.payload['selection'], 'family')
#             self.assertEqual([member['place']['name'] for member in baseline.manifest.payload['members']],
#                              ['Policy', 'Policy.apply'])
#             self.fixture.code.write_bytes(CHUNK)
#             self.fixture.publish(connection)
#             self.assert_observed(connection, original, baseline, current_kind='chunk', raw=CHUNK, removed=True)
#             self.fixture.code.write_bytes(FAMILY)
#             self.fixture.publish(connection)
#             self.assert_restored(connection, original, baseline)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_family_to_chunk_publication_keeps_pin_reports_removed_member_and_restores

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member
#     def test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member(self):
#         self.declare(original=CHUNK)
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current(connection)
#             baseline = EvidenceStore(connection).read_baseline('fixture', original[5])
#             self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
#             self.assertEqual(len(baseline.manifest.payload['members']), 1)
#             self.fixture.code.write_bytes(FAMILY)
#             self.fixture.publish(connection)
#             self.assert_observed(connection, original, baseline, current_kind='family', raw=FAMILY)
#             self.fixture.code.write_bytes(CHUNK)
#             self.fixture.publish(connection)
#             self.assert_restored(connection, original, baseline)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_chunk_to_family_publication_keeps_pin_and_restores_without_removed_member

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

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin
#     def test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin(self):
#         self.accepted_edit_and_restoration(original_source=FAMILY, changed_source=CHUNK,
#             changed_kind='chunk', removed=True)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_family_to_chunk_and_dependant_restoration_recovers_original_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin
#     def test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin(self):
#         self.accepted_edit_and_restoration(original_source=CHUNK, changed_source=FAMILY,
#             changed_kind='family', removed=False)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_substantive_edit_repins_chunk_to_family_and_dependant_restoration_recovers_original_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant
#     def test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant(self):
#         original_guide = self.declare()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             previous = self.current(connection)
#             for raw, kind, removed in ((CHUNK, 'chunk', True), (FAMILY, 'family', False)):
#                 baseline = EvidenceStore(connection).read_baseline('fixture', previous[5])
#                 self.fixture.code.write_bytes(raw)
#                 self.fixture.publish(connection)
#                 self.assert_observed(connection, previous, baseline, current_kind=kind, raw=raw, removed=removed)
#                 reply = self.harness.confirm_hook(connection)
#                 self.assertEqual(reply.captured, 1)
#                 confirmed = self.current(connection)
#                 self.assertEqual(confirmed[:2], previous[:2])
#                 self.assertNotEqual(confirmed[5], previous[5])
#                 self.assertEqual(confirmed[3]['reasons'], [])
#                 self.assertEqual(EvidenceStore(connection).read_baseline('fixture', confirmed[5]).manifest.payload['selection'], kind)
#                 self.assertEqual(self.guide.read_bytes(), original_guide)
#                 self.fixture.publish(connection)
#                 self.assertEqual(self.reasons(connection, self.current(connection)), ())
#                 previous = self.current(connection)
# TEST-TIER-DISABLED-END tests/test_relation_selection_regressions.py::RelationSelectionRegressionStoreTests.test_confirmation_accepts_both_new_selection_kinds_without_changing_dependant

    def test_same_literal_short_method_ref_cannot_redirect_existing_pin_to_unrelated_place(self):
        self.declare(source='fixture:@code/policy.py#apply')
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            original = self.current(connection)
            self.assertEqual(original[2], 'fixture:@code/policy.py#Policy.apply')
            before = self.harness.state(connection)
            self.fixture.code.write_bytes(b'class Other:\n    """Unrelated replacement."""\n'
                b'    def apply(self):\n        return "entirely different behaviour"\n')
            with self.assertRaises(MycelError) as error:
                self.fixture.publish(connection)
            self.assertEqual(error.exception.code, 'invalid_input')
            self.assertEqual(error.exception.message, 'An existing relation cannot bind another source selection.')
            self.assertEqual(self.harness.state(connection), before)
            self.assertEqual(self.current(connection), original)
