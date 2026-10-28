"""Pinned family membership survives current source selection-kind changes."""
import unittest
from unittest.mock import patch

from mycel._dependency_application import RetainedDependencyResolver
from mycel._evidence import CaptureLocation, EvidenceStore, capture_baseline
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._staleness import compare_dependency

try:
    from . import test_reconciliation as values
    from . import test_relation_staleness as fixtures
except ImportError:
    import test_reconciliation as values
    import test_relation_staleness as fixtures


class RelationMemberUnitTests(unittest.TestCase):
    def setUp(self):
        self.dependant = values.document('owner', 'answer.md', '# Answer\nClaim.\n')
        self.ref = 'source:@code/code.py#Worker'

    def baseline(self, source, ref=None):
        ref = self.ref if ref is None else ref
        selected = SourceResolver(values.settings(), (self.dependant, source)).resolve(ref)
        self.assertIsNone(selected.fault)
        return capture_baseline('owner', values.member(self.dependant), self.dependant,
            selected.selection, kind='related', declaration=ref,
            captured_at='2026-10-11T00:00:00Z', location=CaptureLocation('disk')).manifest.payload

    def compare(self, baseline, source, *, anchored=False, ref=None):
        ref = self.ref if ref is None else ref
        catalog = SourceResolver(values.settings(), (self.dependant, source))
        resolver = (RetainedDependencyResolver(catalog, {ref: baseline['members'][0]['id']})
                    if anchored else catalog)
        current = resolver.resolve(ref)
        self.assertIsNone(current.fault)
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            reasons = compare_dependency(baseline, current,
                SourceAddress('source', 'code', 'code.py', 'Worker'), 'related')
        return current.selection, reasons

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk
#     def test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk(self):
#         original = values.code('class Worker:\n    def first(self):\n        return 1\n')
#         baseline = self.baseline(original)
#         current, reasons = self.compare(baseline, values.code('def Worker():\n    return 2\n'))
#         self.assertEqual((baseline['selection'], current.kind), ('family', 'chunk'))
#         self.assertEqual(current.place.address, baseline['source']['address'])
#         self.assertEqual([(reason.kind, reason.source.address, reason.edge) for reason in reasons],
#             [('related_changed', self.ref, 'related'),
#              ('source_removed', 'source:@code/code.py#Worker.first', 'related')])
#         self.assertEqual(len(baseline['members']), 2)
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines
#     def test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines(self):
#         old_chunk = values.code('def Worker():\n    return 1\n')
#         new_family = values.code('class Worker:\n    def first(self):\n        return 2\n')
#         baseline = self.baseline(old_chunk)
#         current, reasons = self.compare(baseline, new_family)
#         self.assertEqual((baseline['selection'], current.kind), ('chunk', 'family'))
#         self.assertEqual([(reason.kind, reason.edge) for reason in reasons], [('related_changed', 'related')])
#         file_ref = 'source:@code/code.py'
#         baseline = self.baseline(new_family, file_ref)
#         current, reasons = self.compare(baseline, old_chunk, ref=file_ref)
#         self.assertEqual((baseline['selection'], current.kind), ('file', 'file'))
#         self.assertEqual([(reason.kind, reason.edge) for reason in reasons], [('related_changed', 'related')])
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal
#     def test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal(self):
#         original = values.code('class Worker:\n    def first(self):\n        return 1\n')
#         baseline = self.baseline(original)
#         renamed = values.code('class Renamed:\n    def first(self):\n        return 1\n')
#         renamed = replace(renamed, chunks=tuple(replace(chunk,
#             identifier=chunk.identifier.replace('Renamed', 'Worker')) for chunk in renamed.chunks))
#         moved_place = SourceAddress('source', 'code', 'moved.py')
#         moved = replace(original, primary=moved_place, aliases=(moved_place,),
#                         recognized_moves=(original.primary,))
#         for label, source in (('recognized family rename', renamed), ('recognized family file move', moved)):
#             with self.subTest(move=label):
#                 current, reasons = self.compare(baseline, source, anchored=True)
#                 self.assertEqual(current.kind, 'family')
#                 self.assertEqual({member.chunk.identifier for member in current.members},
#                                  {member['id'] for member in baseline['members']})
#                 self.assertEqual([reason.kind for reason in reasons], ['related_changed'])
#         method_moved = values.code('class Worker:\n    pass\n\nclass Other:\n'
#                                   '    def first(self):\n        return 1\n')
#         method_moved = replace(method_moved, chunks=tuple(replace(chunk,
#             identifier='code:Worker.first' if chunk.name == 'Other.first' else chunk.identifier)
#             for chunk in method_moved.chunks))
#         self.assertIn('code:Worker.first', {chunk.identifier for chunk in method_moved.chunks})
#         current, reasons = self.compare(baseline, method_moved)
#         self.assertNotIn('code:Worker.first', {member.chunk.identifier for member in current.members})
#         self.assertEqual([(reason.kind, reason.source.name) for reason in reasons],
#                          [('related_changed', 'Worker'), ('source_removed', 'Worker.first')])
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal


class RelationMemberStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.helper = fixtures.RelationStalenessStoreTests()
        self.helper.store_fixture = self.store_fixture
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.base, self.fixture = self.helper.base, self.helper.fixture
        self.code = self.base.code / 'worker.py'
        self.ref = 'fixture:@code/worker.py#Worker'
        self.helper.helper.ref = self.ref

    def seed(self, connection, source):
        self.code.write_bytes(source)
        identifier, baseline_id = self.helper.seed(connection)
        baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
        return identifier, baseline_id, baseline

    def baseline_unchanged(self, connection, identifier, baseline_id, baseline):
        row = self.helper.helper.relation(connection, identifier)
        self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.canonical_bytes,
                         baseline.manifest.canonical_bytes)
        return row

    def direct_only(self, connection, identifier, expected):
        reasons = self.helper.reasons(connection, 'downstream')
        self.assertEqual({(row[4]['kind'], row[4]['source']['address']) for row in reasons}, expected)
        self.assertTrue(all(row[3] is None and row[4]['edge'] == 'related'
                            and row[4]['relation'] == identifier and 'via' not in row[4] for row in reasons))
        self.assertEqual(self.helper.reasons(connection, 'tail'), [])
        self.assertEqual(self.fixture.role(connection), 'authored')
        self.assertEqual(self.fixture.edges(connection), [])
        return reasons

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method
#     def test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method(self):
#         original = b'class Worker:\n    def first(self):\n        return 1\n'
#         with self.base.connect() as connection:
#             identifier, baseline_id, baseline = self.seed(connection, original)
#             original_row = self.helper.helper.relation(connection, identifier)
#             self.assertEqual(baseline.manifest.payload['selection'], 'family')
#             self.code.write_bytes(b'def Worker():\n    return 2\n')
#             result = self.helper.publish(connection)
#             self.assertEqual(result.counts['dependencyRepositories']['downstream']['stale'], 1)
#             reasons = self.direct_only(connection, identifier,
#                 {('related_changed', self.ref), ('source_removed', self.ref + '.first')})
#             self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
#             self.helper.publish(connection)
#             self.assertEqual(self.helper.reasons(connection, 'downstream'), reasons)
#             self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
#             self.code.write_bytes(original)
#             self.helper.publish(connection)
#             self.assertEqual(self.helper.reasons(connection), [])
#             self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_retained_observation_reports_old_family_removal_without_repinning_or_propagation
#     def test_retained_observation_reports_old_family_removal_without_repinning_or_propagation(self):
#         with self.base.connect() as connection:
#             identifier, baseline_id, baseline = self.seed(connection,
#                 b'class Worker:\n    def first(self):\n        return 1\n')
#             owner = self.helper.helper.relation(connection, identifier)[5]
#             self.code.write_bytes(b'def Worker():\n    return 2\n')
#             self.helper.publish(connection)
#             reply = self.helper.helper.apply(connection, identifier)
#             self.assertEqual((reply.changed, reply.released, reply.state), (True, 0, 'present'))
#             row = self.baseline_unchanged(connection, identifier, baseline_id, baseline)
#             self.assertEqual(row[5], owner)
#             self.assertEqual(row[4]['selection']['kind'], 'chunk')
#             self.assertEqual(row[4]['reasons'], ['source_removed', 'related_changed'])
#             self.assertEqual(row[4]['baselineRef'], self.ref)
#             self.direct_only(connection, identifier,
#                 {('related_changed', self.ref), ('source_removed', self.ref + '.first')})
#             stable = self.helper.helper.relation(connection, identifier)
#             repeated = self.helper.helper.apply(connection, identifier)
#             self.assertFalse(repeated.changed)
#             self.assertEqual(self.helper.helper.relation(connection, identifier), stable)
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_retained_observation_reports_old_family_removal_without_repinning_or_propagation

# TEST-TIER-DISABLED-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal
#     def test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal(self):
#         with self.base.connect() as connection:
#             identifier, baseline_id, baseline = self.seed(connection, b'def Worker():\n    return 1\n')
#             original_row = self.helper.helper.relation(connection, identifier)
#             self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
#             self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 2\n')
#             self.helper.publish(connection)
#             self.direct_only(connection, identifier, {('related_changed', self.ref)})
#             self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
#             observed = self.helper.helper.apply(connection, identifier)
#             self.assertTrue(observed.changed)
#             row = self.baseline_unchanged(connection, identifier, baseline_id, baseline)
#             self.assertEqual(row[5], original_row[5])
#             self.assertEqual(row[4]['selection']['kind'], 'family')
#             self.assertEqual(row[4]['reasons'], ['related_changed'])
#             self.direct_only(connection, identifier, {('related_changed', self.ref)})
# TEST-TIER-DISABLED-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_member_regressions.py:2
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_relation_member_regressions.py:2
