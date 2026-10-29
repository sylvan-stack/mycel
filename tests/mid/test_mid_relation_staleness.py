"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_relation_staleness as _support
from test_relation_staleness import (
    CaptureLocation,
    EvidenceStore,
    LocatedCaptureStore,
    MycelError,
    RelateStore,
    RelationStalenessStoreTests,
    RelationStalenessUnitTests,
    SourceAddress,
    SourceResolver,
    StaleEdge,
    StaleNode,
    StaleReason,
    capture_baseline,
    capture_repository,
    checked_store,
    compare_dependency,
    fixtures,
    json,
    operation_guard,
    patch,
    plan_staleness,
    unittest,
    values,
)


class RelationStalenessUnitTests(_support.RelationStalenessUnitTests):
# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessUnitTests.test_complete_relation_comparisons_cover_family_membership_and_whole_file_bytes
    def test_complete_relation_comparisons_cover_family_membership_and_whole_file_bytes(self):
        dependant = values.document('owner', 'answer.md', '# Answer\nClaim.\n')
        source = values.code('class Worker:\n    def first(self):\n        return 1\n')
        ref = 'source:@code/code.py#Worker'
        original = SourceResolver(values.settings(), (dependant, source)).resolve(ref)
        baseline = capture_baseline('owner', values.member(dependant), dependant, original.selection,
            kind='related', declaration=ref, captured_at='2026-10-10T00:00:00Z',
            location=CaptureLocation('disk')).manifest.payload
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            self.assertEqual(compare_dependency(baseline, original, original.selection.place, 'related'), ())
            added = values.code('class Worker:\n    def first(self):\n        return 1\n'
                                '    def second(self):\n        return 2\n')
            selected = SourceResolver(values.settings(), (dependant, added)).resolve(ref)
            self.assertEqual([reason.kind for reason in compare_dependency(baseline, selected,
                             original.selection.place, 'related')], ['related_changed'])
            removed = values.code('class Worker:\n    pass\n')
            selected = SourceResolver(values.settings(), (dependant, removed)).resolve(ref)
            reasons = compare_dependency(baseline, selected, original.selection.place, 'related')
            self.assertEqual({reason.kind for reason in reasons}, {'related_changed', 'source_removed'})
            self.assertTrue(all(reason.edge == 'related' for reason in reasons))
            self.assertEqual(next(reason.source.name for reason in reasons if reason.kind == 'source_removed'),
                             'Worker.first')
            selected = SourceResolver(values.settings(), (dependant,)).resolve(ref)
            self.assertEqual(compare_dependency(baseline, selected, original.selection.place, 'related'),
                             (StaleReason('source_removed', original.selection.place, 'related'),))
            file = values.document('source', 'source.md', '---\nrole: authored\n---\n# Source\nSame body.\n')
            selected = SourceResolver(values.settings(), (dependant, file)).resolve('source:@artifact/source.md')
            baseline = capture_baseline('owner', values.member(dependant), dependant, selected.selection,
                kind='related', declaration=selected.declaration, captured_at='2026-10-10T00:00:00Z',
                location=CaptureLocation('disk')).manifest.payload
            changed = values.document('source', 'source.md', '---\nrole: derived\n---\n# Source\nSame body.\n')
            current = SourceResolver(values.settings(), (dependant, changed)).resolve(selected.declaration)
            self.assertEqual(compare_dependency(baseline, current, selected.selection.place, 'related'),
                             (StaleReason('related_changed', selected.selection.place, 'related'),))
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessUnitTests.test_complete_relation_comparisons_cover_family_membership_and_whole_file_bytes

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessUnitTests.test_changed_and_removed_relation_reasons_never_pass_through_authority_dependencies
    def test_changed_and_removed_relation_reasons_never_pass_through_authority_dependencies(self):
        nodes = tuple(StaleNode(str(number), number + 1,
            SourceAddress('fictional', 'artifact', str(number) + '.md', 'Heading')) for number in range(3))
        edges = (StaleEdge('0', '1', 'middle', 'declared'), StaleEdge('1', '2', 'tail', 'asserted'))
        direct = {'0': (('relation-a', StaleReason('related_changed', nodes[0].place, 'related')),
                        ('relation-b', StaleReason('source_removed', nodes[0].place, 'related')),
                        ('authority', StaleReason('source_changed', nodes[0].place, 'declared')))}
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            result = plan_staleness(nodes, edges, direct)
        self.assertEqual(len(result['0']), 3)
        self.assertEqual(len(result['1']), 1)
        self.assertEqual(len(result['2']), 1)
        self.assertEqual(result['2'][0][1].via, (nodes[0].place, nodes[1].place))
        self.assertEqual(result['2'][0][1].edge, 'asserted')
        self.assertEqual(plan_staleness(nodes, edges, {'0': direct['0'][:2]})['2'], ())
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessUnitTests.test_changed_and_removed_relation_reasons_never_pass_through_authority_dependencies



class RelationStalenessStoreTests(_support.RelationStalenessStoreTests):
# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_public_class_header_assertion_ignores_method_edits_and_detects_header_edits_without_repinning
    def test_public_class_header_assertion_ignores_method_edits_and_detects_header_edits_without_repinning(self):
        code = self.base.code / 'worker.py'
        code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.fixture.publish(connection, 'tail')
            reply = RelateStore(connection).apply(self.base.settings, 'downstream:@artifact/answer.md#Answer',
                'fixture:@code/worker.py#Worker', captured_at='2026-10-10T00:00:00Z', settings_home=self.base.base)
            self.assertEqual((reply['changed'], reply['members']), (True, 1))
            baseline = EvidenceStore(connection).read_baseline('downstream', reply['baselineManifest'])
            self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
            pins = self.pins(connection)
            code.write_bytes(b'class Worker:\n    def first(self):\n        return 2\n'
                             b'    def second(self):\n        return 3\n')
            self.fixture.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.edges(connection), [])
            code.write_bytes(b'class Worker(Base):\n    def first(self):\n        return 2\n'
                             b'    def second(self):\n        return 3\n')
            result = self.fixture.publish(connection)
            reasons = self.reasons(connection, 'downstream')
            self.assertEqual(len(reasons), 1)
            self.assertEqual((reasons[0][4]['kind'], reasons[0][4]['edge']), ('related_changed', 'related'))
            self.assertEqual(reasons[0][4]['source']['address'], 'fixture:@code/worker.py#Worker')
            self.assertEqual(self.reasons(connection, 'tail'), [])
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['stale'], 1)
            repeated = RelateStore(connection).apply(self.base.settings, 'downstream:@artifact/answer.md#Answer',
                'fixture:@code/worker.py#Worker', captured_at='2026-10-10T00:01:00Z', settings_home=self.base.base)
            self.assertFalse(repeated['changed'])
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(self.reasons(connection, 'downstream'), reasons)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', reply['baselineManifest']), baseline)
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_public_class_header_assertion_ignores_method_edits_and_detects_header_edits_without_repinning

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_declared_family_production_source_publication_detects_added_and_removed_members_directly
    def test_declared_family_production_source_publication_detects_added_and_removed_members_directly(self):
        code = self.base.code / 'worker.py'
        code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
        self.fixture.answer.write_bytes(b'---\nrole: authored\n---\n# Answer\nUnchanged dependant.\n'
            b'<!-- related:\nfixture:@code/worker.py#Worker\n-->\n')
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.fixture.publish(connection, 'tail')
            pins = self.pins(connection)
            self.assertEqual(len(pins), 1)
            baseline = EvidenceStore(connection).read_baseline('downstream', pins[0][3])
            self.assertEqual(baseline.manifest.payload['selection'], 'family')
            self.assertEqual(len(baseline.manifest.payload['members']), 2)
            code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n'
                             b'    def second(self):\n        return 2\n')
            self.fixture.publish(connection)
            self.assertEqual([row[4]['kind'] for row in self.reasons(connection)], ['related_changed'])
            self.assertEqual(self.pins(connection), pins)
            code.write_bytes(b'class Worker:\n    def second(self):\n        return 2\n')
            self.fixture.publish(connection)
            reasons = [row[4] for row in self.reasons(connection)]
            self.assertEqual({reason['kind'] for reason in reasons}, {'related_changed', 'source_removed'})
            self.assertEqual(next(reason['source']['name'] for reason in reasons if reason['kind'] == 'source_removed'),
                             'Worker.first')
            self.assertTrue(all(reason['edge'] == 'related' for reason in reasons))
            self.assertEqual(self.reasons(connection, 'tail'), [])
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.edges(connection), [])
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', pins[0][3]), baseline)
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_declared_family_production_source_publication_detects_added_and_removed_members_directly

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_source_only_change_removal_and_restoration_are_direct_and_preserve_exact_pin
    def test_source_only_change_removal_and_restoration_are_direct_and_preserve_exact_pin(self):
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            original = self.helper.relation(connection, identifier)
            baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
            self.fixture.source.write_bytes(b'# Source\nChanged related source.\n')
            result = self.publish(connection)
            downstream = self.reasons(connection, 'downstream')
            self.assertEqual(len(downstream), 1)
            self.assertIsNone(downstream[0][3])
            self.assertEqual(downstream[0][4], {'kind': 'related_changed', 'edge': 'related',
                'relation': identifier,
                'source': {'repository': 'fixture', 'root': 'artifact', 'path': 'source.md',
                           'name': 'Source', 'address': self.helper.ref}})
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['stale'], 1)
            self.assertEqual(self.reasons(connection, 'tail'), [])
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.edges(connection), [])
            stable = self.reasons(connection)
            self.publish(connection)
            self.assertEqual(self.reasons(connection), stable)
            self.fixture.source.unlink()
            self.publish(connection)
            self.assertEqual(self.reasons(connection, 'downstream')[0][4]['kind'], 'source_removed')
            self.assertEqual(self.reasons(connection, 'tail'), [])
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            self.assertEqual(self.helper.relation(connection, identifier), original)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), baseline)
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_source_only_change_removal_and_restoration_are_direct_and_preserve_exact_pin

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_family_member_changes_and_removal_compare_the_complete_pinned_selection
    def test_family_member_changes_and_removal_compare_the_complete_pinned_selection(self):
        code = self.base.code / 'worker.py'
        code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
        self.helper.ref = 'fixture:@code/worker.py#Worker'
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            original = self.helper.relation(connection, identifier)
            baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
            code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n'
                             b'    def second(self):\n        return 2\n')
            self.publish(connection)
            self.assertEqual([row[4]['kind'] for row in self.reasons(connection)], ['related_changed'])
            code.write_bytes(b'class Worker:\n    def second(self):\n        return 2\n')
            self.publish(connection)
            reasons = [row[4] for row in self.reasons(connection)]
            self.assertEqual({reason['kind'] for reason in reasons}, {'related_changed', 'source_removed'})
            self.assertEqual(next(reason['source']['name'] for reason in reasons if reason['kind'] == 'source_removed'),
                             'Worker.first')
            self.assertTrue(all(reason['edge'] == 'related' for reason in reasons))
            self.assertEqual(self.reasons(connection, 'tail'), [])
            self.assertEqual(self.helper.relation(connection, identifier), original)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), baseline)
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_family_member_changes_and_removal_compare_the_complete_pinned_selection

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_busy_relation_owner_and_corrupt_evidence_are_pending_only_at_the_direct_owner
    def test_busy_relation_owner_and_corrupt_evidence_are_pending_only_at_the_direct_owner(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            self.seed(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged with busy relation owner.\n')
            with checked_store(peer), operation_guard(peer, 'downstream', 'pass'):
                result = self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            self.assertEqual({item['chunk']['repository'] for item in result.counts['stalePending']}, {'downstream'})
            self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'busy'})
            result = self.publish(connection)
            self.assertEqual(result.counts['stalePending'], [])
            stable = self.reasons(connection)
            self.assertEqual(len(stable), 1)
            connection.execute("""UPDATE public.mycel_relations SET state=jsonb_set(state,'{baselineRef}',
                to_jsonb(%s::text)) WHERE repository='downstream'""", ('fixture:@artifact/guide.md#Guide',))
            result = self.publish(connection)
            self.assertEqual(self.reasons(connection), stable)
            self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'baseline_missing'})
            connection.execute("""UPDATE public.mycel_relations SET state=jsonb_set(state,'{baselineRef}',
                to_jsonb(%s::text)) WHERE repository='downstream'""", (self.helper.ref,))
            connection.execute("""UPDATE public.mycel_snapshots SET metadata=metadata || '{"bytes":0}'::jsonb
                WHERE repository='downstream'""")
            result = self.publish(connection)
            self.assertEqual(self.reasons(connection), stable)
            self.assertEqual({item['chunk']['repository'] for item in result.counts['stalePending']}, {'downstream'})
            self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'snapshot_corrupt'})
            self.assertEqual(self.reasons(connection, 'tail'), [])
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_busy_relation_owner_and_corrupt_evidence_are_pending_only_at_the_direct_owner

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication
    def test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            identifier, _ = self.seed(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged before late relation race.\n')
            def mutate(owner, counts):
                if owner == 'fixture':
                    peer.execute("""UPDATE public.mycel_relations SET state=state || '{"peerObservation":true}'::jsonb
                        WHERE id=%s""", (identifier,))
                return counts
            with checked_store(peer), operation_guard(peer, 'downstream', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, reply_counts=mutate)
            self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), [])
            original = self.fixture.answer.read_bytes()
            native = EvidenceStore._read_baseline
            def read(store, owner, baseline_id, **kwargs):
                value = native(store, owner, baseline_id, **kwargs)
                if owner == 'downstream':
                    self.fixture.answer.write_bytes(original + b'Late foreign mutation.\n')
                return value
            with patch.object(EvidenceStore, '_read_baseline', read):
                with self.assertRaises(MycelError):
                    self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_late_busy_relation_row_or_foreign_file_change_rolls_back_publication

# TEST-TIER-BEGIN tests/test_relation_staleness.py::RelationStalenessStoreTests.test_corrupt_pin_owner_and_reference_ordinals_remain_pending_and_late_owner_race_rolls_back
    def test_corrupt_pin_owner_and_reference_ordinals_remain_pending_and_late_owner_race_rolls_back(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            identifier, _ = self.seed(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged before ownership corruption.\n')
            self.publish(connection)
            stable = self.reasons(connection)
            owner = self.helper.relation(connection, identifier)[5]
            identity = connection.execute('SELECT identity FROM public.mycel_evidence_owners WHERE id=%s',
                                          (owner,)).fetchone()[0]
            connection.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s',
                               ('corrupt-related-owner', owner))
            result = self.publish(connection)
            self.assertEqual(self.reasons(connection), stable)
            self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'snapshot_corrupt'})
            connection.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s', (identity, owner))
            connection.execute('UPDATE public.mycel_evidence_references SET ordinal=101 WHERE owner=%s AND ordinal=1',
                               (owner,))
            result = self.publish(connection)
            self.assertEqual(self.reasons(connection), stable)
            self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'snapshot_corrupt'})
            connection.execute('UPDATE public.mycel_evidence_references SET ordinal=1 WHERE owner=%s AND ordinal=101',
                               (owner,))
            repaired = self.publish(connection)
            self.assertEqual(repaired.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection), stable)
            self.fixture.source.write_bytes(b'# Source\nChanged before late owning evidence race.\n')
            def mutate(publishing, counts):
                if publishing == 'fixture':
                    peer.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s',
                                 ('late-related-owner', owner))
                return counts
            with checked_store(peer), operation_guard(peer, 'downstream', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, reply_counts=mutate)
            self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), stable)
            self.assertEqual(self.reasons(connection, 'tail'), [])
# TEST-TIER-END tests/test_relation_staleness.py::RelationStalenessStoreTests.test_corrupt_pin_owner_and_reference_ordinals_remain_pending_and_late_owner_race_rolls_back
