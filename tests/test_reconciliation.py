"""Dependency decisions only; all SYL-111 store acceptance remains unclaimed."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from itertools import permutations
from pathlib import Path
import unittest

from mycel._code import chunk_code
from mycel._coverage import proves
from mycel._evidence import (CaptureLocation, capture_baseline, document_comparisons,
                             exact_comparison)
from mycel._markdown import split_markdown
from mycel._reconciliation import (AssertedRemoval, BaselineFault, DependencyRecord,
    DependencyRequest, GraphEdge, ReconciliationError, plan_dependencies)
from mycel._resolver import ResolvedChunk, ResolvedFile, SelectionMember, SourceResolver
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress


def settings(*, enabled=True, registered=True):
    repos = {'owner': {'enabled': True}}
    if registered:
        repos['source'] = {'enabled': enabled}
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({'repos': repos, 'store': {}}), True, True)


def document(repo, path, text, *, version=1, identifier=None):
    parsed = split_markdown(text)
    place = SourceAddress(repo, 'artifact', path)
    chunks = tuple(ResolvedChunk(identifier or f'{repo}:{path}:{index}', version + index,
        chunk.name, 'document', chunk.text.encode(), chunk.snapshot_hash,
        (chunk.span.byte_start, chunk.span.byte_end), chunk.title, None,
        document_comparisons(chunk.body, chunk.title or ''), chunk.body.encode(),
        (len(chunk.text.encode()) - len(chunk.body.encode()), len(chunk.text.encode())))
        for index, chunk in enumerate(parsed.chunks))
    return ResolvedFile(f'file:{repo}:{path}', repo, place, (place,), parsed.source, parsed.file_hash, chunks)


def code(text):
    raw = text.encode()
    place = SourceAddress('source', 'code', 'code.py')
    chunks = []
    for index, item in enumerate(chunk_code('code.py', text)):
        start = raw.find(item.text.encode())
        chunks.append(ResolvedChunk('code:' + item.symbol, index + 1, item.symbol, item.kind, item.text.encode(),
            sha256(item.text.encode()).hexdigest(), (start, start + len(item.text.encode())), None, item.symbol.rsplit('.', 1)[0] if '.' in item.symbol else item.symbol,
            exact_comparison(item.text.encode(), 'code_text').as_dict()))
    return ResolvedFile('code-file', 'source', place, (place,), raw, sha256(raw).hexdigest(), tuple(chunks))


def member(file, index=0):
    chunk = file.chunks[index]
    return SelectionMember(SourceAddress(file.repository, file.primary.root, file.primary.path, chunk.name), chunk)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.dep = document('owner', 'answer.md', '# Answer\nAnswer body.\n', identifier='answer')
        self.src = document('source', 'source.md', '# Source\nOld source.\n', identifier='source-chunk')
        self.declaration = 'source:source.md#Source'

    def resolver(self, source=None, *, enabled=True, registered=True):
        files = (self.dep,) + (() if source is None else (source,))
        return SourceResolver(settings(enabled=enabled, registered=registered), files)

    def record(self, identifier='declared-link', kind='declared', *, source=None, declaration=None):
        source = self.src if source is None else source
        declaration = self.declaration if declaration is None else declaration
        selected = self.resolver(source).resolve(declaration).selection
        manifest = capture_baseline('owner', member(self.dep), self.dep, selected, kind=kind,
            declaration=declaration, captured_at='2026-10-09T00:00:00Z', location=CaptureLocation('disk')).manifest
        return DependencyRecord(identifier, manifest)

    def plan(self, requests=(), existing=(), *, source=None, **kwargs):
        return plan_dependencies(member(self.dep), self.resolver(source), tuple(requests), tuple(existing),
            pin_version=kwargs.pop('pin_version', self.dep.chunks[0].version), **kwargs)

    @proves('MYC-13.15')
    def test_initial_resolution_schedules_capture_without_claiming_captured_evidence(self):
        plan = self.plan((DependencyRequest('new', 'declared', self.declaration),), source=self.src)
        decision = plan.decisions[0]
        self.assertEqual((decision.action, decision.baseline, decision.source_state), ('capture', None, 'present'))
        self.assertEqual(plan.role, 'derived')
        self.assertEqual(plan.graph, (GraphEdge('source-chunk', 'answer', 'new'),))

    @proves('MYC-13.15')
    def test_unresolved_first_reference_remains_visible_without_removed_baseline(self):
        for absent in (None, 'away', 'deleted'):
            plan = self.plan((DependencyRequest('new', 'declared', self.declaration, absent),))
            decision = plan.decisions[0]
            self.assertEqual((decision.action, decision.baseline, decision.source_state, decision.reasons),
                             ('unresolved', None, 'unresolved', ()))
            self.assertEqual(decision.fault, 'missing_file')
            self.assertEqual(plan.role, 'unclassified')

    @proves('MYC-13.15')
    def test_missing_previously_resolved_source_retains_every_baseline_and_governs_role(self):
        old = self.record()
        for state in ('away', 'deleted'):
            decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration, state),), (old,)).decisions[0]
            self.assertIs(decision.baseline, old.baseline)
            self.assertEqual((decision.action, decision.source_state, decision.reasons), ('keep', state, ('source_removed',)))
            self.assertEqual(decision.natural_place, old.natural_place)
            self.assertEqual(decision.active_sources, ())
            self.assertEqual(self.plan((DependencyRequest(old.identifier, 'declared', self.declaration, state),), (old,)).role, 'derived')
        with self.assertRaises(ReconciliationError):
            self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,))

    @proves('MYC-13.15')
    def test_recreation_joins_new_identifier_without_renewing_the_old_pin(self):
        old = self.record()
        recreated = document('source', 'source.md', '# Source\nNew source.\n', identifier='recreated', version=22)
        decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=recreated).decisions[0]
        self.assertEqual((decision.action, decision.active_sources, decision.reasons), ('keep', ('recreated',), ('source_changed',)))
        self.assertIs(decision.baseline, old.baseline)
        self.assertEqual(decision.baseline.identifier, old.baseline.identifier)

    @proves('MYC-13.15')
    def test_source_changes_and_sibling_file_changes_do_not_authorize_repinning(self):
        old = self.record()
        changed = document('source', 'source.md', '# Source\nChanged.\n', identifier='source-chunk', version=8)
        decision = self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=changed).decisions[0]
        self.assertEqual(decision.action, 'keep')
        self.assertIs(decision.baseline, old.baseline)
        self.assertEqual(decision.reasons, ('source_changed',))
        self.dep = replace(self.dep, source=self.dep.source + b'# Sibling\nNew text.\n',
                           snapshot_hash=sha256(self.dep.source + b'# Sibling\nNew text.\n').hexdigest())
        self.assertEqual(self.plan((DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), source=changed).decisions[0].action, 'keep')

    @proves('MYC-13.15')
    def test_disabled_and_unregistered_targets_keep_baseline_but_are_not_governing(self):
        old = self.record()
        for enabled, registered, fault in ((False, True, 'disabled_repository'), (True, False, 'unregistered_repository')):
            plan = plan_dependencies(member(self.dep), self.resolver(self.src, enabled=enabled, registered=registered),
                (DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), pin_version=1)
            decision = plan.decisions[0]
            self.assertEqual((decision.action, decision.source_state, decision.reasons, decision.fault),
                             ('keep', 'ineligible', (), fault))
            self.assertIs(decision.baseline, old.baseline)
            self.assertEqual(plan.role, 'unclassified')
            self.assertEqual(plan.graph, ())

    @proves('MYC-13.15')
    def test_empty_file_and_empty_chunk_are_present_and_govern_role(self):
        empty = document('source', 'empty.md', '')
        self.assertEqual(empty.chunks, ())
        plan = self.plan((DependencyRequest('empty', 'declared', 'source:empty.md'),), source=empty)
        self.assertEqual((plan.role, plan.graph, plan.decisions[0].source_state), ('derived', (), 'present'))
        heading = document('source', 'source.md', '# Source\n')
        self.assertEqual(self.plan((DependencyRequest('heading', 'declared', self.declaration),), source=heading).role, 'derived')

    @proves('MYC-13.15')
    def test_declared_removal_never_removes_an_assertion_between_the_same_ends(self):
        declared, asserted = self.record(), self.record('asserted-link', 'asserted')
        plan = self.plan((), (declared, asserted), source=self.src)
        by_id = {decision.identifier: decision for decision in plan.decisions}
        self.assertEqual(by_id[declared.identifier].action, 'release')
        self.assertEqual(by_id[asserted.identifier].action, 'keep')
        self.assertEqual(plan.graph, (GraphEdge('source-chunk', 'answer', 'asserted-link'),))
        self.assertEqual(plan.role, 'derived')

    @proves('MYC-13.15')
    def test_asserted_removal_is_selection_exact_and_leaves_declared_record(self):
        declared, asserted = self.record(), self.record('asserted-link', 'asserted')
        requests = (DependencyRequest(declared.identifier, 'declared', self.declaration),)
        plan = self.plan(requests, (declared, asserted), source=self.src,
                         remove_assertions=(AssertedRemoval(asserted.natural_place, 'chunk'),))
        self.assertEqual({decision.identifier: decision.action for decision in plan.decisions},
                         {'declared-link': 'keep', 'asserted-link': 'release'})
        absent = AssertedRemoval(SourceAddress('source', 'artifact', 'other.md', 'Other'), 'chunk')
        self.assertEqual(self.plan(requests, (declared, asserted), source=self.src, remove_assertions=(absent,)).decisions[-1].action, 'keep')

    @proves('MYC-13.15')
    def test_asserted_removal_of_absent_source_requires_no_new_capture(self):
        old = self.record('asserted-link', 'asserted')
        request = DependencyRequest(old.identifier, 'asserted', self.declaration, 'deleted')
        decision = self.plan((request,), (old,), remove_assertions=(AssertedRemoval(old.natural_place, 'chunk'),)).decisions[0]
        self.assertEqual(decision.action, 'release')
        self.assertIs(decision.baseline, old.baseline)

    @proves('MYC-13.15')
    def test_confirmation_withdraws_old_missing_source_but_refuses_new_fault_atomically(self):
        old = self.record()
        request = DependencyRequest(old.identifier, 'declared', self.declaration, 'deleted')
        plan = self.plan((request,), (old,), mode='confirm')
        self.assertEqual((plan.decisions[0].action, plan.decisions[0].fault, plan.role), ('withdraw', 'missing_file', 'unclassified'))
        for bad in ('source:unknown.md', 'bad ref', 'disabled:thing'):
            with self.subTest(bad=bad), self.assertRaises(ReconciliationError) as caught:
                self.plan((request, DependencyRequest('bad', 'declared', bad)), (old,), mode='confirm')
            self.assertEqual((caught.exception.status, caught.exception.dependencies), ('invalid_input', ('bad',)))

    @proves('MYC-13.15')
    def test_authorized_confirmation_schedules_capture_and_identical_assertion_scan_is_noop(self):
        old = self.record('asserted-link', 'asserted')
        observed = self.plan((), (old,), source=self.src)
        confirmed = self.plan((), (old,), source=self.src, mode='confirm')
        self.assertEqual((observed.decisions[0].action, confirmed.decisions[0].action), ('keep', 'capture'))
        self.assertIs(confirmed.decisions[0].baseline, old.baseline)
        with self.assertRaises(ReconciliationError):
            self.plan((DependencyRequest('different-id', 'asserted', self.declaration),), (old,), source=self.src)

    @proves('MYC-13.15')
    def test_exact_restoration_uses_that_versions_pin_and_rejects_the_later_pin(self):
        old = self.record()
        self.dep = document('owner', 'answer.md', '# Answer\nChanged answer.\n', identifier='answer', version=2)
        later = self.record()
        self.dep = document('owner', 'answer.md', '# Answer\nAnswer body.\n', identifier='answer', version=1)
        request = DependencyRequest(old.identifier, 'declared', self.declaration)
        decision = self.plan((request,), (old,), source=self.src, mode='restore').decisions[0]
        self.assertIs(decision.baseline, old.baseline)
        self.assertEqual(decision.action, 'keep')
        with self.assertRaises(ReconciliationError):
            self.plan((request,), (later,), source=self.src, mode='restore')

    @proves('MYC-13.15')
    def test_normalized_edit_and_heading_rename_inherit_instead_of_recapturing(self):
        old = self.record()
        self.dep = document('owner', 'answer.md', '# Renamed\nAnswer\t body.\n', identifier='answer', version=2)
        request = DependencyRequest(old.identifier, 'declared', self.declaration)
        decision = self.plan((request,), (old,), source=self.src, mode='inherit', pin_version=1).decisions[0]
        self.assertEqual(decision.action, 'inherit')
        self.assertIs(decision.baseline, old.baseline)
        with self.assertRaises(ReconciliationError):
            self.plan((request,), (old,), source=self.src, mode='edit', pin_version=1)

    @proves('MYC-13.15')
    def test_substantive_edit_schedules_capture_or_withdraws_missing_and_never_confirms_a_normalized_edit(self):
        old = self.record()
        self.dep = document('owner', 'answer.md', '# Answer\nSubstantive change.\n', identifier='answer', version=2)
        request = DependencyRequest(old.identifier, 'declared', self.declaration)
        self.assertEqual(self.plan((request,), (old,), source=self.src, mode='edit', pin_version=1).decisions[0].action, 'capture')
        missing = replace(request, absent_state='away')
        self.assertEqual(self.plan((missing,), (old,), mode='edit', pin_version=1).decisions[0].action, 'withdraw')
        with self.assertRaises(ReconciliationError):
            self.plan((request,), (old,), source=self.src, mode='inherit', pin_version=1)

    @proves('MYC-13.15')
    def test_missing_or_corrupt_baseline_can_never_be_treated_as_initial_resolution(self):
        request = DependencyRequest('previously-resolved', 'declared', self.declaration)
        for status in ('baseline_missing', 'snapshot_corrupt', 'unsupported_comparison'):
            with self.subTest(status=status), self.assertRaises(ReconciliationError) as caught:
                self.plan((request,), source=self.src, baseline_faults=(BaselineFault(request.identifier, status),))
            self.assertEqual((caught.exception.status, caught.exception.dependencies), (status, (request.identifier,)))

    @proves('MYC-13.15')
    def test_roles_recomputed_from_file_or_code_default_without_governing_dependencies(self):
        self.assertEqual(self.plan(file_role='authored').role, 'authored')
        self.assertEqual(self.plan(file_role='derived').role, 'derived')
        self.assertEqual(self.plan().role, 'unclassified')
        self.dep = replace(self.dep, chunks=(replace(self.dep.chunks[0], kind='code', body=None, body_span=None,
            comparison=exact_comparison(self.dep.chunks[0].source, 'code_text').as_dict()),))
        self.assertEqual(self.plan().role, 'authored')

    @proves('MYC-13.15')
    def test_whole_operation_refuses_self_cycle_and_cross_repository_cycle(self):
        self_ref = DependencyRequest('self', 'declared', 'owner:answer.md#Answer')
        with self.assertRaises(ReconciliationError) as caught:
            self.plan((self_ref,), source=self.src)
        self.assertEqual(caught.exception.cycle, ('answer', 'answer'))
        request = DependencyRequest('new', 'declared', self.declaration)
        graph = (GraphEdge('answer', 'intermediate', 'other'), GraphEdge('intermediate', 'source-chunk', 'other-2'))
        with self.assertRaises(ReconciliationError) as caught:
            self.plan((request,), source=self.src, graph=graph)
        self.assertEqual(set(caught.exception.cycle[:-1]), {'answer', 'intermediate', 'source-chunk'})
        self.assertEqual(caught.exception.cycle[0], caught.exception.cycle[-1])

    @proves('MYC-13.15')
    def test_cycle_result_is_independent_of_insert_order_and_large_graph_is_iterative(self):
        request = DependencyRequest('new', 'declared', self.declaration)
        edges = (GraphEdge('answer', 'middle', 'a'), GraphEdge('middle', 'source-chunk', 'b'), GraphEdge('other', 'end', 'c'))
        cycles = set()
        for order in permutations(edges):
            with self.assertRaises(ReconciliationError) as caught:
                self.plan((request,), source=self.src, graph=order)
            cycles.add(caught.exception.cycle)
        self.assertEqual(len(cycles), 1)
        large = tuple(GraphEdge(str(index), str(index + 1), 'chain:' + str(index)) for index in range(2000))
        self.assertEqual(len(self.plan(graph=large).graph), 2000)

    @proves('MYC-13.15')
    def test_owned_graph_edges_are_replaced_and_other_kinds_are_preserved(self):
        old = self.record()
        graph = (GraphEdge('source-chunk', 'answer', old.identifier), GraphEdge('answer', 'source-chunk', 'elsewhere'))
        plan = self.plan((), (old,), graph=graph)
        self.assertEqual(plan.graph, (graph[1],))
        self.assertEqual(plan.decisions[0].action, 'release')

    @proves('MYC-13.15')
    def test_file_selection_expands_every_current_chunk_for_cycle_check(self):
        source = document('source', 'source.md', '# First\nFirst.\n# Second\nSecond.\n')
        requests = (DependencyRequest('file', 'declared', 'source:source.md'),)
        plan = self.plan(requests, source=source)
        self.assertEqual(len(plan.graph), 2)
        graph = (GraphEdge('answer', source.chunks[-1].identifier, 'back'),)
        with self.assertRaises(ReconciliationError):
            self.plan(requests, source=source, graph=graph)

    @proves('MYC-13.15')
    def test_family_added_and_removed_members_keep_complete_old_baseline(self):
        initial = code('class C:\n    def first(self):\n        return 1\n\n    def second(self):\n        return 2\n')
        old = self.record(source=initial, declaration='source:code.py#C')
        before = old.baseline.canonical_bytes
        changed = code('class C:\n    def first(self):\n        return 1\n\n    def third(self):\n        return 3\n')
        request = DependencyRequest(old.identifier, 'declared', 'source:code.py#C')
        decision = self.plan((request,), (old,), source=changed).decisions[0]
        self.assertEqual(decision.action, 'keep')
        self.assertEqual(decision.reasons, ('source_removed', 'source_changed'))
        self.assertEqual(old.baseline.canonical_bytes, before)
        self.assertIn('code:C.third', decision.active_sources)
        self.assertNotIn('code:C.second', decision.active_sources)

    @proves('MYC-13.15')
    def test_alias_spelling_keeps_identity_pin_original_declaration_and_natural_place(self):
        old = self.record()
        request = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source')
        decision = self.plan((request,), (old,), source=self.src).decisions[0]
        self.assertEqual(decision.action, 'keep')
        self.assertEqual(decision.declaration, request.declaration)
        self.assertEqual(decision.baseline.payload['ref'], self.declaration)
        self.assertEqual(decision.natural_place, old.natural_place)

    @proves('MYC-13.15')
    def test_frozen_decisions_and_invalid_request_observations(self):
        plan = self.plan((DependencyRequest('new', 'declared', self.declaration),), source=self.src)
        with self.assertRaises(FrozenInstanceError):
            plan.role = 'authored'
        with self.assertRaises(ReconciliationError):
            self.plan((DependencyRequest('new', 'declared', self.declaration, 'deleted'),), source=self.src)
        with self.assertRaises(ReconciliationError):
            self.plan((DependencyRequest('same', 'declared', self.declaration), DependencyRequest('same', 'asserted', self.declaration)), source=self.src)
        with self.assertRaises(ReconciliationError):
            self.plan((DependencyRequest('bad', 'declared', 'bad ref', 'deleted'),))

    @proves('MYC-13.15')
    def test_reusing_a_record_id_cannot_rebind_an_unrelated_selection(self):
        old = self.record()
        unrelated = document('source', 'other.md', '# Other\nOther bytes.\n', identifier='unrelated')
        resolver = SourceResolver(settings(), (self.dep, self.src, unrelated))
        with self.assertRaises(ReconciliationError):
            plan_dependencies(member(self.dep), resolver,
                (DependencyRequest(old.identifier, 'declared', 'source:other.md#Other'),), (old,), pin_version=1)

    @proves('MYC-13.15')
    def test_recognized_move_retains_natural_place_when_current_identity_is_the_same(self):
        old = self.record()
        moved = document('source', 'moved.md', '# Source\nOld source.\n', identifier='source-chunk')
        request = DependencyRequest(old.identifier, 'declared', 'source:moved.md#Source')
        decision = self.plan((request,), (old,), source=moved).decisions[0]
        self.assertEqual(decision.action, 'keep')
        self.assertEqual(decision.natural_place, old.natural_place)
        self.assertEqual(decision.current_selection.place.path, 'moved.md')
        self.assertIs(decision.baseline, old.baseline)

    @proves('MYC-13.15')
    def test_unaffected_incoming_authoritative_graph_edge_governs_role(self):
        incoming = GraphEdge('unaffected-source', 'answer', 'unaffected-generated')
        self.assertEqual(self.plan(graph=(incoming,)).role, 'derived')
        outgoing = GraphEdge('answer', 'other', 'outgoing')
        self.assertEqual(self.plan(graph=(outgoing,)).role, 'unclassified')

    @proves('MYC-13.15')
    def test_current_dependant_must_be_exactly_the_enabled_catalog_endpoint(self):
        fake = document('owner', 'not-in-catalog.md', '# Fake\nFake.\n', identifier='fake')
        resolver = self.resolver(self.src)
        with self.assertRaises(ReconciliationError):
            plan_dependencies(member(fake), resolver,
                (DependencyRequest('new', 'declared', self.declaration),), (), pin_version=1)
        altered = replace(member(self.dep), chunk=replace(self.dep.chunks[0], version=99))
        with self.assertRaises(ReconciliationError):
            plan_dependencies(altered, resolver, (), (), pin_version=99)

    @proves('MYC-13.15')
    def test_missing_disabled_and_malformed_rebinding_cannot_reuse_old_dependency_id(self):
        old = self.record()
        for declaration, state in (('source:other.md#Other', 'deleted'), ('unknown:source.md#Source', None), ('bad ref', None)):
            with self.subTest(declaration=declaration), self.assertRaises(ReconciliationError):
                self.plan((DependencyRequest(old.identifier, 'declared', declaration, state),), (old,))
        disabled = self.resolver(enabled=False)
        with self.assertRaises(ReconciliationError):
            plan_dependencies(member(self.dep), disabled,
                (DependencyRequest(old.identifier, 'declared', 'source:other.md#Other'),), (old,), pin_version=1)
        equivalent = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source', 'deleted')
        self.assertEqual(self.plan((equivalent,), (old,)).decisions[0].action, 'keep')
        new = DependencyRequest('new-target', 'declared', 'source:other.md#Other', 'deleted')
        plan = self.plan((new,), (old,))
        self.assertEqual({decision.identifier: decision.action for decision in plan.decisions},
                         {old.identifier: 'release', 'new-target': 'unresolved'})

    @proves('MYC-13.15')
    def test_recreated_anchor_can_move_again_without_replacing_audit_baseline(self):
        old = self.record()
        recreated = document('source', 'source.md', '# Source\nRecreated.\n', identifier='recreated')
        request = DependencyRequest(old.identifier, 'declared', self.declaration)
        reconnected = self.plan((request,), (old,), source=recreated).decisions[0]
        retained = replace(old, retained_place=reconnected.current_selection.place, current_anchor='recreated',
                           current_declaration=request.declaration)
        moved = document('source', 'moved.md', '# Source\nRecreated.\n', identifier='recreated')
        moved_request = replace(request, declaration='source:moved.md#Source')
        decision = self.plan((moved_request,), (retained,), source=moved).decisions[0]
        self.assertEqual(decision.action, 'keep')
        self.assertEqual(decision.active_sources, ('recreated',))
        self.assertIs(decision.baseline, old.baseline)
        after_move = replace(retained, retained_place=decision.current_selection.place,
                             current_declaration=moved_request.declaration)
        gone = replace(moved_request, absent_state='deleted')
        missing = self.plan((gone,), (after_move,)).decisions[0]
        self.assertEqual(missing.natural_place.path, 'moved.md')
        self.assertEqual(missing.baseline.payload['source']['path'], 'source.md')
        self.assertEqual(missing.reasons, ('source_removed',))

    @proves('MYC-13.15')
    def test_new_matching_id_cannot_displace_an_unaffected_graph_dependency(self):
        existing_generated = GraphEdge('generated-source', 'answer', 'collision')
        request = DependencyRequest('collision', 'declared', self.declaration)
        with self.assertRaises(ReconciliationError):
            self.plan((request,), source=self.src, graph=(existing_generated,))
        different_dependant = GraphEdge('elsewhere', 'other-answer', 'collision')
        with self.assertRaises(ReconciliationError):
            self.plan((request,), source=self.src, graph=(different_dependant,))

    @proves('MYC-13.15')
    def test_ambiguity_report_retains_typed_candidates_without_replacing_baseline(self):
        old = self.record()
        secondary_place = SourceAddress('source', 'code', 'source.md')
        secondary = replace(self.src, identifier='secondary-file', primary=secondary_place, aliases=(secondary_place,))
        resolver = SourceResolver(settings(), (self.dep, self.src, secondary))
        decision = plan_dependencies(member(self.dep), resolver,
            (DependencyRequest(old.identifier, 'declared', self.declaration),), (old,), pin_version=1).decisions[0]
        self.assertEqual((decision.action, decision.source_state, decision.fault), ('keep', 'unresolved', 'ambiguous_path'))
        self.assertEqual(decision.resolution.candidate_count, 2)
        self.assertEqual(decision.resolution.candidates,
                         ('source:@artifact/source.md', 'source:@code/source.md'))
        self.assertIs(decision.baseline, old.baseline)

    @proves('MYC-13.15')
    def test_binding_output_updates_current_anchor_without_mutating_audit(self):
        old = self.record()
        recreated = document('source', 'source.md', '# Source\nRecreated.\n', identifier='recreated')
        request = DependencyRequest(old.identifier, 'declared', 'source:@artifact/source.md#Source')
        decision = self.plan((request,), (old,), source=recreated).decisions[0]
        self.assertEqual((decision.binding.place, decision.binding.anchor, decision.binding.declaration),
                         (decision.current_selection.place, 'recreated', request.declaration))
        self.assertEqual(old.baseline.payload['members'][0]['id'], 'source-chunk')
        self.assertEqual(old.baseline.payload['ref'], self.declaration)

    @proves('MYC-13.15')
    def test_real_parser_code_kinds_without_governing_dependencies_are_authored(self):
        parsed = code('import os\n\nclass C:\n    def method(self):\n        return 1\n\ndef function():\n    return 2\n')
        owner_place = SourceAddress('owner', 'code', 'code.py')
        owner_file = replace(parsed, identifier='owner-code-file', repository='owner',
                             primary=owner_place, aliases=(owner_place,))
        resolver = SourceResolver(settings(), (owner_file,))
        kinds = set()
        for index, chunk in enumerate(owner_file.chunks):
            with self.subTest(kind=chunk.kind, name=chunk.name):
                kinds.add(chunk.kind)
                plan = plan_dependencies(member(owner_file, index), resolver, (), (), pin_version=chunk.version)
                self.assertEqual(plan.role, 'authored')
                self.assertEqual(plan.graph, ())
        self.assertTrue({'class', 'method', 'function'} <= kinds)
        self.assertEqual(self.plan().role, 'unclassified')
