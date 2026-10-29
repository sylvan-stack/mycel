"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_relation_occurrence_aliases as _support
from test_relation_occurrence_aliases import (
    CaptureLocation,
    DeclaredSource,
    RelationOccurrenceAliasTests,
    RetainedDependencyResolver,
    SourceAddress,
    SourceResolver,
    _RelationRecord,
    _anchor,
    _match_declarations,
    _raw,
    _relation_syntax_faults,
    capture_baseline,
    fixtures,
    parse_source_address,
    permutations,
    replace,
    unittest,
)


class RelationOccurrenceAliasTests(_support.RelationOccurrenceAliasTests):
# TEST-TIER-BEGIN tests/test_relation_occurrence_aliases.py::RelationOccurrenceAliasTests.test_malformed_alias_keeps_its_fault_and_valid_selection_keeps_prior_pin_in_either_order
    def test_malformed_alias_keeps_its_fault_and_valid_selection_keeps_prior_pin_in_either_order(self):
        legacy = 'source:source.md#Source'
        qualified = 'source:@artifact/source.md#Source'
        dependant = fixtures.document('owner', 'answer.md', '# Answer\nBody.\n', identifier='answer')
        source = fixtures.document('source', 'source.md', '# Source\nSource body.\n', identifier='source-chunk')
        catalog = SourceResolver(fixtures.settings(), (dependant, source))
        selection = catalog.resolve(qualified).selection
        baseline = capture_baseline('owner', fixtures.member(dependant), dependant, selection,
            kind='related', declaration=qualified, captured_at='2026-10-11T00:00:00Z',
            location=CaptureLocation('disk')).manifest
        previous_bytes = baseline.canonical_bytes
        row = ('prior-pin', 'owner', dependant.chunks[0].version, qualified,
               selection.place.address, 'declared', {'rawRef': _raw(qualified)}, 'prior-owner')
        records = {'prior-pin': _RelationRecord(baseline, selection.place, _anchor(selection))}
        valid = DeclaredSource(qualified, qualified, qualified + '\n', 'comment',
                               'Answer', 7, parse_source_address(qualified))
        malformed = DeclaredSource(legacy, '  ' + legacy + '  ', '  ' + legacy + '  \n',
                                   'comment', 'Answer', 9, parse_source_address(legacy), 'not_a_ref')

        for refs in permutations((valid, malformed)):
            with self.subTest(order=tuple(ref.ref for ref in refs)):
                syntax_faults = _relation_syntax_faults(refs, RetainedDependencyResolver(catalog, {}))
                self.assertEqual(syntax_faults, {})
                resolver = RetainedDependencyResolver(catalog, {}, syntax_faults)
                requests, occurrences = _match_declarations(refs, (row,), resolver, records)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].identifier, 'prior-pin')
                self.assertEqual(resolver.resolve(requests[0].declaration).selection.place, selection.place)
                self.assertEqual([item['syntaxFault'] for item in occurrences['prior-pin']],
                                 [ref.fault for ref in refs])
                self.assertEqual([bytes.fromhex(item['rawDeclared']).decode()
                                  for item in occurrences['prior-pin']], [ref.declared for ref in refs])
                self.assertEqual(baseline.canonical_bytes, previous_bytes)

        # A syntactically valid but unresolved declaration is no authority to
        # reinterpret another malformed occurrence as a resolved selection.
        missing_ref = 'source:@artifact/absent.md#Source'
        missing = replace(valid, ref=missing_ref, declared=missing_ref, raw_line=missing_ref + '\n',
                          address=parse_source_address(missing_ref))
        for refs in ((malformed,), (malformed, missing), (missing, malformed)):
            syntax_faults = _relation_syntax_faults(refs, RetainedDependencyResolver(catalog, {}))
            self.assertEqual(syntax_faults, {legacy: 'not_a_ref'})
            self.assertEqual(RetainedDependencyResolver(catalog, {}, syntax_faults).resolve(legacy).fault,
                             'not_a_ref')

        # For an exact repeated spelling, the valid occurrence still governs
        # lookup. It preserves the ordinary unknown-repository fault rather
        # than turning that independently valid declaration into bad syntax.
        unknown_ref = 'unregistered:@artifact/source.md#Source'
        unknown = replace(valid, ref=unknown_ref, declared=unknown_ref, raw_line=unknown_ref + '\n',
                          address=parse_source_address(unknown_ref))
        malformed_unknown = replace(unknown, line=9, fault='not_a_ref')
        for refs in permutations((unknown, malformed_unknown)):
            syntax_faults = _relation_syntax_faults(refs, RetainedDependencyResolver(catalog, {}))
            self.assertEqual(syntax_faults, {})
            self.assertEqual(RetainedDependencyResolver(catalog, {}, syntax_faults).resolve(unknown_ref).fault,
                             'unregistered_repository')

        # A legacy path that now reaches two physical files cannot borrow the
        # qualified occurrence's identity; the resolver must keep its fault.
        collision = fixtures.document('source', 'source.md', '# Source\nOther body.\n',
                                      identifier='other-chunk')
        code_place = SourceAddress('source', 'code', 'source.md')
        collision = replace(collision, identifier='other-file', primary=code_place, aliases=(code_place,))
        ambiguous = SourceResolver(fixtures.settings(), (dependant, source, collision))
        self.assertEqual(ambiguous.resolve(legacy).fault, 'ambiguous_path')
        self.assertEqual(ambiguous.resolve(qualified).selection.place, selection.place)
        for refs in permutations((valid, malformed)):
            syntax_faults = _relation_syntax_faults(refs, RetainedDependencyResolver(ambiguous, {}))
            self.assertEqual(syntax_faults, {legacy: 'not_a_ref'})
            resolver = RetainedDependencyResolver(ambiguous, {}, syntax_faults)
            self.assertEqual(resolver.resolve(legacy).fault, 'not_a_ref')
            requests, occurrences = _match_declarations(
                sorted(refs, key=lambda ref: ref.fault is not None), (row,), resolver, records)
            self.assertEqual(len(requests), 2)
            resolved = [request for request in requests if resolver.resolve(request.declaration).selection]
            self.assertEqual([(request.identifier, request.declaration) for request in resolved],
                             [('prior-pin', qualified)])
            invalid = [request for request in requests if resolver.resolve(request.declaration).selection is None]
            self.assertEqual(len(invalid), 1)
            self.assertNotEqual(invalid[0].identifier, 'prior-pin')
            self.assertEqual(occurrences[invalid[0].identifier][0]['syntaxFault'], 'not_a_ref')
# TEST-TIER-END tests/test_relation_occurrence_aliases.py::RelationOccurrenceAliasTests.test_malformed_alias_keeps_its_fault_and_valid_selection_keeps_prior_pin_in_either_order
