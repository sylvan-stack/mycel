"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_relation_member_regressions as _support
from test_relation_member_regressions import (
    CaptureLocation,
    EvidenceStore,
    RelationMemberStoreTests,
    RelationMemberUnitTests,
    RetainedDependencyResolver,
    SourceAddress,
    SourceResolver,
    capture_baseline,
    compare_dependency,
    fixtures,
    patch,
    replace,
    unittest,
    values,
)


class RelationMemberUnitTests(_support.RelationMemberUnitTests):
# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk
    def test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk(self):
        original = values.code('class Worker:\n    def first(self):\n        return 1\n')
        baseline = self.baseline(original)
        current, reasons = self.compare(baseline, values.code('def Worker():\n    return 2\n'))
        self.assertEqual((baseline['selection'], current.kind), ('family', 'chunk'))
        self.assertEqual(current.place.address, baseline['source']['address'])
        self.assertEqual([(reason.kind, reason.source.address, reason.edge) for reason in reasons],
            [('related_changed', self.ref, 'related'),
             ('source_removed', 'source:@code/code.py#Worker.first', 'related')])
        self.assertEqual(len(baseline['members']), 2)
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_family_baseline_reports_removed_method_when_current_selection_is_one_chunk

# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines
    def test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines(self):
        old_chunk = values.code('def Worker():\n    return 1\n')
        new_family = values.code('class Worker:\n    def first(self):\n        return 2\n')
        baseline = self.baseline(old_chunk)
        current, reasons = self.compare(baseline, new_family)
        self.assertEqual((baseline['selection'], current.kind), ('chunk', 'family'))
        self.assertEqual([(reason.kind, reason.edge) for reason in reasons], [('related_changed', 'related')])
        file_ref = 'source:@code/code.py'
        baseline = self.baseline(new_family, file_ref)
        current, reasons = self.compare(baseline, old_chunk, ref=file_ref)
        self.assertEqual((baseline['selection'], current.kind), ('file', 'file'))
        self.assertEqual([(reason.kind, reason.edge) for reason in reasons], [('related_changed', 'related')])
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_current_family_does_not_invent_removed_members_for_chunk_or_file_baselines

# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal
    def test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal(self):
        original = values.code('class Worker:\n    def first(self):\n        return 1\n')
        baseline = self.baseline(original)
        renamed = values.code('class Renamed:\n    def first(self):\n        return 1\n')
        renamed = replace(renamed, chunks=tuple(replace(chunk,
            identifier=chunk.identifier.replace('Renamed', 'Worker')) for chunk in renamed.chunks))
        moved_place = SourceAddress('source', 'code', 'moved.py')
        moved = replace(original, primary=moved_place, aliases=(moved_place,),
                        recognized_moves=(original.primary,))
        for label, source in (('recognized family rename', renamed), ('recognized family file move', moved)):
            with self.subTest(move=label):
                current, reasons = self.compare(baseline, source, anchored=True)
                self.assertEqual(current.kind, 'family')
                self.assertEqual({member.chunk.identifier for member in current.members},
                                 {member['id'] for member in baseline['members']})
                self.assertEqual([reason.kind for reason in reasons], ['related_changed'])
        method_moved = values.code('class Worker:\n    pass\n\nclass Other:\n'
                                  '    def first(self):\n        return 1\n')
        method_moved = replace(method_moved, chunks=tuple(replace(chunk,
            identifier='code:Worker.first' if chunk.name == 'Other.first' else chunk.identifier)
            for chunk in method_moved.chunks))
        self.assertIn('code:Worker.first', {chunk.identifier for chunk in method_moved.chunks})
        current, reasons = self.compare(baseline, method_moved)
        self.assertNotIn('code:Worker.first', {member.chunk.identifier for member in current.members})
        self.assertEqual([(reason.kind, reason.source.name) for reason in reasons],
                         [('related_changed', 'Worker'), ('source_removed', 'Worker.first')])
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberUnitTests.test_recognized_family_moves_keep_members_but_moving_method_out_reports_removal



class RelationMemberStoreTests(_support.RelationMemberStoreTests):
# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method
    def test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method(self):
        original = b'class Worker:\n    def first(self):\n        return 1\n'
        with self.base.connect() as connection:
            identifier, baseline_id, baseline = self.seed(connection, original)
            original_row = self.helper.helper.relation(connection, identifier)
            self.assertEqual(baseline.manifest.payload['selection'], 'family')
            self.code.write_bytes(b'def Worker():\n    return 2\n')
            result = self.helper.publish(connection)
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['stale'], 1)
            reasons = self.direct_only(connection, identifier,
                {('related_changed', self.ref), ('source_removed', self.ref + '.first')})
            self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
            self.helper.publish(connection)
            self.assertEqual(self.helper.reasons(connection, 'downstream'), reasons)
            self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
            self.code.write_bytes(original)
            self.helper.publish(connection)
            self.assertEqual(self.helper.reasons(connection), [])
            self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_family_to_chunk_publication_preserves_pin_and_direct_removed_method

# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_retained_observation_reports_old_family_removal_without_repinning_or_propagation
    def test_retained_observation_reports_old_family_removal_without_repinning_or_propagation(self):
        with self.base.connect() as connection:
            identifier, baseline_id, baseline = self.seed(connection,
                b'class Worker:\n    def first(self):\n        return 1\n')
            owner = self.helper.helper.relation(connection, identifier)[5]
            self.code.write_bytes(b'def Worker():\n    return 2\n')
            self.helper.publish(connection)
            reply = self.helper.helper.apply(connection, identifier)
            self.assertEqual((reply.changed, reply.released, reply.state), (True, 0, 'present'))
            row = self.baseline_unchanged(connection, identifier, baseline_id, baseline)
            self.assertEqual(row[5], owner)
            self.assertEqual(row[4]['selection']['kind'], 'chunk')
            self.assertEqual(row[4]['reasons'], ['source_removed', 'related_changed'])
            self.assertEqual(row[4]['baselineRef'], self.ref)
            self.direct_only(connection, identifier,
                {('related_changed', self.ref), ('source_removed', self.ref + '.first')})
            stable = self.helper.helper.relation(connection, identifier)
            repeated = self.helper.helper.apply(connection, identifier)
            self.assertFalse(repeated.changed)
            self.assertEqual(self.helper.helper.relation(connection, identifier), stable)
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_retained_observation_reports_old_family_removal_without_repinning_or_propagation

# TEST-TIER-BEGIN tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal
    def test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal(self):
        with self.base.connect() as connection:
            identifier, baseline_id, baseline = self.seed(connection, b'def Worker():\n    return 1\n')
            original_row = self.helper.helper.relation(connection, identifier)
            self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
            self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 2\n')
            self.helper.publish(connection)
            self.direct_only(connection, identifier, {('related_changed', self.ref)})
            self.assertEqual(self.baseline_unchanged(connection, identifier, baseline_id, baseline), original_row)
            observed = self.helper.helper.apply(connection, identifier)
            self.assertTrue(observed.changed)
            row = self.baseline_unchanged(connection, identifier, baseline_id, baseline)
            self.assertEqual(row[5], original_row[5])
            self.assertEqual(row[4]['selection']['kind'], 'family')
            self.assertEqual(row[4]['reasons'], ['related_changed'])
            self.direct_only(connection, identifier, {('related_changed', self.ref)})
# TEST-TIER-END tests/test_relation_member_regressions.py::RelationMemberStoreTests.test_source_only_chunk_to_family_and_retained_observation_do_not_invent_removal
