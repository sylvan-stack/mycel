"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_staleness as _support
from test_staleness import (MycelError ,checked_store ,operation_guard)


class MechanicalStalenessStoreTests(_support.MechanicalStalenessStoreTests):


# TEST-TIER-BEGIN tests/test_staleness.py::MechanicalStalenessStoreTests.test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries
    def test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries(self):
        from psycopg.types.json import Jsonb
        from mycel._derive import DeriveStore
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            DeriveStore(connection).apply(self.settings, 'unrelated:@artifact/answer.md#Other',
                'fixture:@artifact/source.md#Source', captured_at='2026-10-09T21:00:00Z')
            row = connection.execute("SELECT * FROM public.mycel_dependencies WHERE repository='unrelated'").fetchone()
            connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (row[0],))
            self.source.unlink()
            inserted = False
            def publish_new_pin(owner, counts):
                nonlocal inserted
                if owner == 'fixture' and not inserted:
                    peer.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                                 (*row[:6], Jsonb(row[6]), row[7]))
                    inserted = True
                return counts
            with checked_store(peer), operation_guard(peer, 'unrelated', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, producer=False, reply_counts=publish_new_pin)
                self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), [])
            retry = self.publish(connection, producer=False)
            self.assertEqual(retry.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection, 'unrelated')[0][4]['kind'], 'source_removed')
# TEST-TIER-END tests/test_staleness.py::MechanicalStalenessStoreTests.test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::StalenessUnitTests.test_hash_and_membership_decisions_are_pure_and_use_complete_selection
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Hash and membership decisions are pure and use complete selection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_hash_and_membership_decisions_are_pure_and_use_complete_selection(self):
#         import test_reconciliation as values
#         from mycel._evidence import CaptureLocation, capture_baseline
#         from mycel._resolver import SourceResolver
#         dep = values.document('owner', 'answer.md', '# Answer\nClaim.\n')
#         old = values.code('class Worker:\n    def first(self):\n        return 1\n')
#         ref = 'source:@code/code.py#Worker'
#         resolver = SourceResolver(values.settings(), (dep, old))
#         selected = resolver.resolve(ref)
#         baseline = capture_baseline('owner', values.member(dep), dep, selected.selection,
#             kind='declared', declaration=ref, captured_at='2026-10-09T00:00:00Z', location=CaptureLocation('disk')).manifest.payload
#         with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
#             self.assertEqual(compare_dependency(baseline, selected, selected.selection.place, 'declared'), ())
#             added = values.code('class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
#             changed = SourceResolver(values.settings(), (dep, added)).resolve(ref)
#             self.assertEqual([reason.kind for reason in compare_dependency(baseline, changed,
#                 selected.selection.place, 'asserted')], ['source_changed'])
#             removed = values.code('class Worker:\n    pass\n')
#             changed = SourceResolver(values.settings(), (dep, removed)).resolve(ref)
#             self.assertEqual({reason.kind for reason in compare_dependency(baseline, changed,
#                 selected.selection.place, 'declared')}, {'source_changed', 'source_removed'})
#             missing = SourceResolver(values.settings(), (dep,)).resolve(ref)
#             self.assertEqual(compare_dependency(baseline, missing, selected.selection.place,
#                 'declared')[0].kind, 'source_removed')
#             whole = values.document('source', 'source.md', '---\nrole: authored\n---\n# Source\nSame body.\n')
#             selected = SourceResolver(values.settings(), (dep, whole)).resolve('source:@artifact/source.md')
#             baseline = capture_baseline('owner', values.member(dep), dep, selected.selection,
#                 kind='declared', declaration=selected.declaration, captured_at='2026-10-09T00:00:00Z',
#                 location=CaptureLocation('disk')).manifest.payload
#             changed_file = values.document('source', 'source.md', '---\nrole: derived\n---\n# Source\nSame body.\n')
#             changed = SourceResolver(values.settings(), (dep, changed_file)).resolve(selected.declaration)
#             self.assertEqual(compare_dependency(baseline, changed, selected.selection.place, 'declared')[0].kind,
#                              'source_changed')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::StalenessUnitTests.test_offline_iterative_all_path_planning_and_cycle_refusal
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Offline iterative all path planning and cycle refusal.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_offline_iterative_all_path_planning_and_cycle_refusal(self):
#         def node(number, exempt=False):
#             return StaleNode(str(number), number + 1,
#                 SourceAddress('fictional', 'artifact', str(number) + '.md', 'Heading'), exempt)
#         nodes = tuple(node(number) for number in range(1100))
#         edges = tuple(StaleEdge(str(number), str(number + 1), str(number), 'declared') for number in range(1099))
#         direct = {'0': (('origin', StaleReason('source_changed', nodes[0].place, 'asserted')),)}
#         with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
#             result = plan_staleness(nodes, edges, direct)
#         self.assertEqual(len(result['1099'][0][1].via), 1099)
#         self.assertEqual(result['1099'][0][1].source, nodes[0].place)
#         with self.assertRaises(MycelError):
#             plan_staleness(nodes[:2], (StaleEdge('0', '1', 'x', 'declared'),
#                 StaleEdge('1', '0', 'y', 'declared')), direct)
#         blocked = plan_staleness((node(0), node(1, True), node(2)),
#             (StaleEdge('0', '1', 'x', 'declared'), StaleEdge('1', '2', 'y', 'declared')), direct)
#         self.assertEqual(blocked['1'], ())
#         self.assertEqual(blocked['2'], ())
#         mixed = plan_staleness(nodes[:2], edges[:1],
#             {'0': direct['0'], '1': (('local', StaleReason('source_removed', nodes[1].place, 'declared')),)})
#         self.assertEqual([reason.kind for _, reason in mixed['1']], ['source_removed', 'upstream_stale'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_complete_same_pass_hash_reasons_diamond_paths_and_unrelated_rows
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Complete same pass hash reasons diamond paths and unrelated rows.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_complete_same_pass_hash_reasons_diamond_paths_and_unrelated_rows(self):
#         self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'right:@artifact/answer.md#Right',
#                                    'fixture:@code/worker.py#work'))
#         unrelated_source = self.roots['unrelated'] / 'anchor.md'
#         unrelated_source.write_text('# Anchor\nIndependent original source.\n')
#         self.write('unrelated', 'Other', ('unrelated:@artifact/anchor.md#Anchor',))
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             pins, unrelated = self.pins(connection), self.unrelated_state(connection)
#             unrelated_source.write_text('# Anchor\nUnindexed edit in an independent component.\n')
#             self.source.write_bytes(b'# Source\nChanged governing document.\n')
#             self.code.write_bytes(b'def work():\n    return 2\n')
#             result = self.publish(connection)
#             self.assertEqual(self.pins(connection), pins)
#             tail = self.reasons(connection, 'tail')
#             self.assertEqual(len(tail), 3)
#             self.assertEqual(tail[0][4]['kind'], 'source_changed')
#             self.assertEqual(tail[0][4]['source']['address'], 'fixture:@code/worker.py#work')
#             indirect = [row[4] for row in tail if row[4]['kind'] == 'upstream_stale']
#             self.assertEqual({tuple(place['repository'] for place in reason['via']) for reason in indirect},
#                              {('left',), ('right',)})
#             self.assertTrue(all(reason['source']['address'] == 'fixture:@artifact/source.md#Source' for reason in indirect))
#             self.assertEqual(self.unrelated_state(connection), unrelated)
#             self.assertEqual(result.counts['dependencyRepositories']['tail']['stale'], 1)
#             self.assertEqual(result.counts['stalePending'], [])
#             connection.execute("UPDATE public.mycel_stale_reasons SET reason=reason || "
#                 "'{\"classification\":{\"bundle\":\"fictional-retained-link\"}}'::jsonb WHERE repository='tail'")
#             stable = self.reasons(connection)
#             self.assertFalse(self.publish(connection).changed)
#             self.assertEqual(self.reasons(connection), stable)
#             self.code.write_bytes(b'def work():\n    return 1\n')
#             self.publish(connection)
#             self.assertEqual(len(self.reasons(connection, 'tail')), 2)
#             self.assertTrue(all(row[4]['kind'] == 'upstream_stale' for row in self.reasons(connection, 'tail')))
#             self.source.write_bytes(b'# Source\nOriginal source body.\n')
#             self.publish(connection)
#             self.assertEqual(self.reasons(connection), [])
#             self.assertEqual(self.pins(connection), pins)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_disk_absence_and_restoration_clear_direct_and_every_indirect_reason
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disk absence and restoration clear direct and every indirect reason.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disk_absence_and_restoration_clear_direct_and_every_indirect_reason(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             pins = self.pins(connection)
#             self.source.unlink()  # Its committed local branch still retains the source.
#             self.publish(connection)
#             reasons = self.reasons(connection)
#             self.assertEqual(len(reasons), 4)
#             self.assertEqual({row[4]['kind'] for row in self.reasons(connection, 'left')}, {'source_removed'})
#             self.assertTrue(all(row[4]['source']['address'] == 'fixture:@artifact/source.md#Source' for row in reasons))
#             self.source.write_bytes(b'# Source\nOriginal source body.\n')
#             self.publish(connection)
#             self.assertEqual(self.reasons(connection), [])
#             self.assertEqual(self.pins(connection), pins)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_heartwood_and_external_generated_stop_propagation_but_their_bytes_still_compare
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Heartwood and external generated stop propagation but their bytes still compare.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_heartwood_and_external_generated_stop_propagation_but_their_bytes_still_compare(self):
#         self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
#         self.write('right', 'Right', ('fixture:@artifact/source.md#Source',), metadata='generated: true\n')
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged blocked source.\n')
#             self.publish(connection)
#             self.assertEqual(self.reasons(connection), [])
#             path = self.roots['left'] / 'answer.md'
#             path.write_text(path.read_text().replace('Unchanged claim.', 'Changed Heartwood record.'))
#             self.publish(connection, 'left')
#             reasons = self.reasons(connection, 'tail')
#             self.assertEqual(len(reasons), 1)
#             self.assertEqual(reasons[0][4]['kind'], 'source_changed')
#             self.assertEqual(reasons[0][4]['source']['repository'], 'left')
#             self.assertEqual(self.reasons(connection, 'left'), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_generic_frontmatter_exemption_changes_clear_and_restore_only_applicable_paths
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Generic frontmatter exemption changes clear and restore only applicable paths.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_generic_frontmatter_exemption_changes_clear_and_restore_only_applicable_paths(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             pins = self.pins(connection)
#             self.source.write_bytes(b'# Source\nChanged before exemptions.\n')
#             self.publish(connection)
#             self.assertEqual(len(self.reasons(connection)), 4)
#             self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
#             self.publish(connection, 'left', producer=False)
#             self.assertEqual(self.reasons(connection, 'left'), [])
#             tail = self.reasons(connection, 'tail')
#             self.assertEqual(len(tail), 1)
#             self.assertEqual(tail[0][4]['via'][0]['repository'], 'right')
#             self.write('right', 'Right', ('fixture:@artifact/source.md#Source',), metadata='generated: true\n')
#             self.publish(connection, 'right', producer=False)
#             self.assertEqual(self.reasons(connection), [])
#             self.write('left', 'Left', ('fixture:@artifact/source.md#Source',))
#             self.publish(connection, 'left', producer=False)
#             self.assertEqual(len(self.reasons(connection, 'left')), 1)
#             self.assertEqual(len(self.reasons(connection, 'tail')), 1)
#             self.assertEqual(self.reasons(connection, 'tail')[0][4]['via'][0]['repository'], 'left')
#             self.assertEqual(self.pins(connection), pins)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_document_to_code_move_cannot_carry_its_old_document_exemption
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Document to code move cannot carry its old document exemption.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_document_to_code_move_cannot_carry_its_old_document_exemption(self):
#         from mycel._derive import DeriveStore
#         from mycel._resolver import SourceResolver
#         document = self.base.artifact / 'generated.md'
#         document.write_bytes(b'---\ngenerated: true\n---\n# Historical\nOriginal generated text.\n')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             previous = next(file for file in SourceResolver.from_store(connection, self.settings).files
#                             if file.primary.path == 'generated.md')
#             document.rename(self.base.artifact / 'generated.py')
#             self.base.commit()
#             self.publish(connection, producer=False)
#             current = next(file for file in SourceResolver.from_store(connection, self.settings).files
#                            if file.primary.path == 'generated.py')
#             self.assertEqual(current.identifier, previous.identifier)
#             self.assertTrue(all(chunk.kind != 'document' for chunk in current.chunks))
#             metadata = connection.execute("""SELECT l.metadata FROM public.mycel_file_locations l
#                 JOIN public.mycel_file_versions v ON v.id=l.file_version
#                 WHERE v.file_id=%s AND l.kind='disk'""", (current.identifier,)).fetchone()[0]
#             self.assertIs(metadata['documentDeclarations']['metadata']['generated'], True)
#             dependant = SourceResolver._members(current, current.chunks)[0].place.address
#             DeriveStore(connection).apply(self.settings, dependant, 'fixture:@artifact/source.md#Source',
#                 captured_at='2026-10-09T21:00:00Z')
#             self.source.write_bytes(b'# Source\nChanged source of current code.\n')
#             self.publish(connection)
#             reasons = self.reasons(connection, 'fixture')
#             self.assertEqual(len(reasons), 1)
#             self.assertEqual(reasons[0][4]['kind'], 'source_changed')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_busy_owner_stays_pending_while_guarded_descendants_apply_and_retry
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Busy owner stays pending while guarded descendants apply and retry.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_busy_owner_stays_pending_while_guarded_descendants_apply_and_retry(self):
#         with self.base.connect() as connection, self.base.connect() as busy:
#             self.prepare(connection)
#             pins = self.pins(connection)
#             self.source.write_bytes(b'# Source\nChanged with a busy intermediate.\n')
#             with checked_store(busy), operation_guard(busy, 'left', 'pass'):
#                 result = self.publish(connection, producer=False)
#                 self.assertEqual(self.reasons(connection, 'left'), [])
#                 self.assertEqual(len(self.reasons(connection, 'tail')), 2)
#                 self.assertEqual({item['chunk']['repository'] for item in result.counts['stalePending']}, {'left'})
#                 self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'busy'})
#             retried = self.publish(connection, producer=False)
#             self.assertEqual(retried.counts['stalePending'], [])
#             self.assertEqual(len(self.reasons(connection, 'left')), 1)
#             self.assertEqual(self.pins(connection), pins)
#             unrelated = self.unrelated_state(connection)
#             with checked_store(busy), operation_guard(busy, 'unrelated', 'pass'):
#                 repeated = self.publish(connection, producer=False)
#             self.assertEqual(repeated.counts['stalePending'], [])
#             self.assertNotIn('unrelated', repeated.counts.get('dependencyRepositories', {}))
#             self.assertEqual(self.unrelated_state(connection), unrelated)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_final_busy_peer_dependency_change_refuses_all_prospective_marks
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Final busy peer dependency change refuses all prospective marks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_final_busy_peer_dependency_change_refuses_all_prospective_marks(self):
#         with self.base.connect() as connection, self.base.connect() as peer:
#             self.prepare(connection)
#             before = self.reasons(connection)
#             old_source = connection.execute("SELECT v.snapshot_hash FROM public.mycel_file_versions v "
#                 "JOIN public.mycel_file_locations l ON l.file_version=v.id JOIN public.mycel_files f ON f.id=v.file_id "
#                 "WHERE f.repository='fixture' AND l.kind='disk' AND l.metadata->>'path'='source.md'").fetchone()
#             self.source.write_bytes(b'# Source\nChanged before peer guard.\n')
#             def mutate(owner, counts):
#                 if owner == 'fixture':
#                     peer.execute("UPDATE public.mycel_dependencies SET state=state || '{\"peerObservation\":true}'::jsonb "
#                                  "WHERE repository='left'")
#                 return counts
#             with checked_store(peer), operation_guard(peer, 'left', 'pass'):
#                 with self.assertRaises(MycelError) as caught:
#                     self.publish(connection, producer=False, reply_counts=mutate)
#                 self.assertEqual(caught.exception.code, 'invalid_input')
#             self.assertEqual(self.reasons(connection), before)
#             self.assertEqual(connection.execute("SELECT v.snapshot_hash FROM public.mycel_file_versions v "
#                 "JOIN public.mycel_file_locations l ON l.file_version=v.id JOIN public.mycel_files f ON f.id=v.file_id "
#                 "WHERE f.repository='fixture' AND l.kind='disk' AND l.metadata->>'path'='source.md'").fetchone(), old_source)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_disjoint_busy_owner_can_commit_metadata_during_source_publication
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disjoint busy owner can commit metadata during source publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disjoint_busy_owner_can_commit_metadata_during_source_publication(self):
#         with self.base.connect() as connection, self.base.connect() as peer:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged with disjoint concurrent work.\n')
#             def mutate(owner, counts):
#                 if owner == 'fixture':
#                     peer.execute("""UPDATE public.mycel_locations SET metadata=metadata || '{"peerObservation":true}'::jsonb
#                         WHERE chunk_version IN (SELECT v.id FROM public.mycel_chunk_versions v
#                             JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository='unrelated')""")
#                 return counts
#             with checked_store(peer), operation_guard(peer, 'unrelated', 'pass'):
#                 result = self.publish(connection, producer=False, reply_counts=mutate)
#             self.assertEqual(result.counts['stalePending'], [])
#             self.assertEqual(len(self.reasons(connection)), 4)
#             self.assertEqual(connection.execute("""SELECT count(*) FROM public.mycel_locations
#                 WHERE metadata->>'peerObservation'='true'""").fetchone(), (1,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_native_activity_contains_exact_downstream_detection_and_audit_failure_rolls_back
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native activity contains exact downstream detection and audit failure rolls back.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_activity_contains_exact_downstream_detection_and_audit_failure_rolls_back(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged with activity.\n')
#             with MutationActivity(connection, build=1).session() as audit:
#                 result = self.publish(connection, activity=audit)
#                 final = {('fixture', 'ingest'): result.counts,
#                          **{(owner, 'ingest'): counts for owner, counts in result.counts['dependencyRepositories'].items()}}
#                 audit.finish('done', counts=final)
#             entries = connection.execute('SELECT id,repository FROM public.mycel_activity ORDER BY repository').fetchall()
#             self.assertEqual({owner for _, owner in entries}, {'fixture', 'left', 'right', 'tail'})
#             for identifier, owner in entries:
#                 state = activity_state(connection, identifier)
#                 self.assertEqual(state['counts'], final[(owner, 'ingest')])
#                 if owner != 'fixture':
#                     self.assertEqual(state['files'], [])
#                     self.assertEqual(state['decisions'], [])
#             stable = self.reasons(connection)
#             self.source.write_bytes(b'# Source\nOriginal source body.\n')
#             with MutationActivity(connection, build=1).session() as audit:
#                 with patch.object(audit, 'record_in_transaction', side_effect=MycelError('internal', 'Fictional audit failure')):
#                     with self.assertRaises(MycelError):
#                         self.publish(connection, activity=audit)
#             self.assertEqual(self.reasons(connection), stable)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_final_root_audit_and_baseline_reader_file_mutations_refuse_publication
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Final root audit and baseline reader file mutations refuse publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_final_root_audit_and_baseline_reader_file_mutations_refuse_publication(self):
#         from mycel._evidence import EvidenceStore
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged with late foreign mutation.\n')
#             left = self.roots['left'] / 'answer.md'
#             original = left.read_bytes()
#             with MutationActivity(connection, build=1).session() as audit:
#                 native = audit.record_in_transaction
#                 def record(owner, kind, mutation):
#                     value = native(owner, kind, mutation)
#                     if owner == 'fixture':
#                         left.write_bytes(original + b'Late root-audit mutation.\n')
#                     return value
#                 with patch.object(audit, 'record_in_transaction', side_effect=record):
#                     with self.assertRaises(MycelError):
#                         self.publish(connection, producer=False, activity=audit)
#             self.assertEqual(self.reasons(connection), [])
#             left.write_bytes(original)
#             native = EvidenceStore._read_baseline
#             def read(store, owner, identifier, **kwargs):
#                 value = native(store, owner, identifier, **kwargs)
#                 if owner == 'left':
#                     left.write_bytes(original + b'Late baseline-reader mutation.\n')
#                 return value
#             with patch.object(EvidenceStore, '_read_baseline', read):
#                 with self.assertRaises(MycelError):
#                     self.publish(connection, producer=False)
#             self.assertEqual(self.reasons(connection), [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_corrupt_baseline_and_foreign_uningested_bytes_keep_marks_pending_with_exact_counts
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Corrupt baseline and foreign uningested bytes keep marks pending with exact counts.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_corrupt_baseline_and_foreign_uningested_bytes_keep_marks_pending_with_exact_counts(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged before missing evidence.\n')
#             self.publish(connection)
#             before = self.reasons(connection)
#             connection.execute("""UPDATE public.mycel_snapshots SET metadata=metadata || '{"bytes":0}'::jsonb
#                 WHERE repository='left'""")
#             result = self.publish(connection, producer=False)
#             self.assertEqual(self.reasons(connection), before)
#             self.assertEqual(result.counts['dependencyRepositories']['left']['staleReasons'], 1)
#             self.assertEqual(result.counts['dependencyRepositories']['tail']['staleReasons'], 2)
#             self.assertEqual({item['reason'] for item in result.counts['stalePending']},
#                              {'snapshot_corrupt', 'upstream_unchecked'})
#             right = self.roots['right'] / 'answer.md'
#             right.write_bytes(right.read_bytes() + b'Unindexed foreign edit.\n')
#             result = self.publish(connection, producer=False)
#             self.assertIn('changed_since_ingest', {item['reason'] for item in result.counts['stalePending']})
#             self.assertEqual(self.reasons(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_fault_on_exempt_intermediate_does_not_block_an_independent_downstream_reason
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Fault on exempt intermediate does not block an independent downstream reason.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fault_on_exempt_intermediate_does_not_block_an_independent_downstream_reason(self):
#         self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
#         self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'fixture:@code/worker.py#work'))
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             connection.execute("""UPDATE public.mycel_snapshots SET metadata=metadata || '{"bytes":0}'::jsonb
#                 WHERE repository='left'""")
#             self.code.write_bytes(b'def work():\n    return 2\n')
#             result = self.publish(connection, producer=False)
#             self.assertEqual(result.counts['stalePending'], [])
#             self.assertEqual(self.reasons(connection, 'left'), [])
#             self.assertEqual(len(self.reasons(connection, 'tail')), 1)
#             self.assertEqual(self.reasons(connection, 'tail')[0][4]['source']['address'], 'fixture:@code/worker.py#work')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_current_class_members_expand_prelocks_and_retries_after_generic_publication
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Current class members expand prelocks and retries after generic publication.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_current_class_members_expand_prelocks_and_retries_after_generic_publication(self):
#         self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
#         self.write('left', 'Left', ('fixture:@code/worker.py#Worker',))
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
#             result = self.publish(connection, producer=False)
#             self.assertEqual(result.counts['stalePending'], [])
#             self.assertEqual(self.reasons(connection, 'left')[0][4]['kind'], 'source_changed')
#             self.code.write_bytes(b'class Worker:\n    def second(self):\n        return 2\n')
#             result = self.publish(connection, producer=False)
#             self.assertEqual(result.counts['stalePending'], [])
#             self.assertEqual({row[4]['kind'] for row in self.reasons(connection, 'left')},
#                              {'source_changed', 'source_removed'})
#             self.assertEqual(next(row[4]['source']['name'] for row in self.reasons(connection, 'left')
#                 if row[4]['kind'] == 'source_removed'), 'Worker.first')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_disabled_source_deactivates_stale_authority_without_a_removed_or_missing_baseline_claim
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disabled source deactivates stale authority without a removed or missing baseline claim.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disabled_source_deactivates_stale_authority_without_a_removed_or_missing_baseline_claim(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             self.source.write_bytes(b'# Source\nChanged before disabling.\n')
#             self.publish(connection)
#             self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=true',
#                                                                           '[repos.fixture]\nenabled=false'))
#             self.reload()
#             result = self.publish(connection, 'left')
#             self.assertEqual(self.reasons(connection, 'left'), [])
#             tail = self.reasons(connection, 'tail')
#             self.assertEqual(tail, [])
#             self.assertEqual(result.counts['stalePending'], [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_shared_disk_branch_version_selects_only_its_disk_owned_pin
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Shared disk branch version selects only its disk owned pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_shared_disk_branch_version_selects_only_its_disk_owned_pin(self):
#         guide = self.base.artifact / 'guide.md'
#         guide.write_bytes(b'---\nsources: ["fixture:@artifact/source.md#Source"]\n---\n# Guide\nRepository guide.\n')
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             deps = connection.execute("""SELECT id,dependant_version,baseline_owner,state->'declarationLocation'->>'kind'
#                 FROM public.mycel_dependencies WHERE repository='fixture' ORDER BY id""").fetchall()
#             self.assertEqual({row[3] for row in deps}, {'disk', 'branch'})
#             self.assertEqual(len({row[1] for row in deps}), 1)
#             self.assertEqual(len({row[2] for row in deps}), 2)
#             self.source.write_bytes(b'# Source\nDisk-only source change.\n')
#             self.publish(connection)
#             current = self.reasons(connection, 'fixture')
#             self.assertEqual(len(current), 1)
#             self.assertEqual(current[0][3], next(row[0] for row in deps if row[3] == 'disk'))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_staleness.py::MechanicalStalenessStoreTests.test_declared_asserted_reasons_keep_both_kinds_and_new_family_members_supply_prelocks
# Reason: Narrower case removed from this family after retaining test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Declared asserted reasons keep both kinds and new family members supply prelocks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_staleness.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_declared_asserted_reasons_keep_both_kinds_and_new_family_members_supply_prelocks(self):
#         from mycel._derive import DeriveStore
#         self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
#         self.write('left', 'Left', ('fixture:@code/worker.py#Worker',))
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             DeriveStore(connection).apply(self.settings, 'right:@artifact/answer.md#Right',
#                 'fixture:@artifact/source.md#Source', captured_at='2026-10-09T21:00:00Z')
#             self.source.write_bytes(b'# Source\nBoth independent edge kinds change.\n')
#             self.publish(connection)
#             self.assertEqual({row[4]['edge'] for row in self.reasons(connection, 'right')}, {'declared', 'asserted'})
#             self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
#             self.publish(connection, producer=False)
#             DeriveStore(connection).apply(self.settings, 'fixture:@code/worker.py#Worker.second',
#                 'right:@artifact/answer.md#Right', captured_at='2026-10-09T21:00:00Z')
#             right = self.roots['right'] / 'answer.md'
#             right.write_text(right.read_text().replace('Unchanged claim.', 'Changed source for the new member.'))
#             result = self.publish(connection, 'right', producer=False)
#             self.assertEqual(result.counts['stalePending'], [])
#             reasons = self.reasons(connection, 'left')
#             self.assertTrue(any(row[4]['kind'] == 'upstream_stale' and row[4]['source']['repository'] == 'right'
#                 and row[4]['via'][0]['name'] == 'Worker.second' for row in reasons))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
