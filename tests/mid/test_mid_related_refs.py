"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_related_refs as _support
# from test_related_refs import (
#     RelatedRefTests,
#     _ReadOnlyRows,
#     _raw,
#     _refs,
#     _stored,
#     row,
#     unittest,
# )


# class RelatedRefTests(_support.RelatedRefTests):
# TEST-TIER-DISABLED-BEGIN tests/test_related_refs.py::RelatedRefTests.test_malformed_nul_missing_disabled_unknown_and_ambiguous_faults_remain_visible
#     def test_malformed_nul_missing_disabled_unknown_and_ambiguous_faults_remain_visible(self):
#         for raw, internal, public in (
#                 ('bad\0ref', 'not_a_ref', 'not_a_ref'),
#                 ('not a ref', 'invalid_ref', 'not_a_ref'),
#                 ('fixture:missing.md', 'missing_file', 'not_found'),
#                 ('fixture:guide.md#Missing', 'missing_name', 'not_found'),
#                 ('disabled:guide.md', 'disabled_repository', 'disabled_repository'),
#                 ('unknown:guide.md', 'unregistered_repository', 'unknown_repository'),
#                 ('fixture:collision.md', 'ambiguous_path', 'ambiguous_path'),
#                 ('fixture:guide.md#Repeat', 'ambiguous_name', 'ambiguous_title')):
#             with self.subTest(fault=internal):
#                 retained = row(raw=raw, fault=internal)
#                 if internal.startswith('ambiguous'):
#                     retained[3]['resolution'].update(candidates=['fixture:@artifact/other.md#Repeat'], candidateCount=2)
#                 before = deepcopy(retained)
#                 reports = _refs._related_reports(retained)
#                 self.assertEqual(retained, before)
#                 self.assertEqual(len(reports), 1)
#                 report = reports[0]
#                 self.assertEqual((report['kind'], report['parsedRef'], report['fault'], report['resolutionFault']),
#                                  ('related', raw, public, internal))
#                 self.assertEqual((report['ref'], report['rawLine'], report['origin'], report['line']),
#                                  ('  ' + raw + '  ', '  ' + raw + '  \r\n', 'comment', 3))
#                 self.assertEqual(report['chunk']['address'], 'fixture:@artifact/guide.md#Guide')
#                 if internal.startswith('ambiguous'):
#                     self.assertEqual(report['candidateCount'], 2)
#                     self.assertEqual(report['candidates'][0]['address'], 'fixture:@artifact/other.md#Repeat')
# TEST-TIER-DISABLED-END tests/test_related_refs.py::RelatedRefTests.test_malformed_nul_missing_disabled_unknown_and_ambiguous_faults_remain_visible

# TEST-TIER-DISABLED-BEGIN tests/test_related_refs.py::RelatedRefTests.test_equivalent_relation_occurrences_keep_each_spelling_physical_line_and_location
#     def test_equivalent_relation_occurrences_keep_each_spelling_physical_line_and_location(self):
#         spellings = ('  fixture:source.md#Source  ', 'fixture:@artifact/source.md#Source')
#         occurrences = [{'rawDeclared': _raw(raw), 'rawLine': _raw('> ' + raw + '\n'),
#                         'origin': 'comment', 'line': index + 4, 'syntaxFault': None}
#                        for index, raw in enumerate(spellings)]
#         retained = row(raw=spellings[0].strip(), fault=None, state='resolved',
#                        kind='branch', location='branches/earlier', occurrences=occurrences)
#         retained[3]['resolution']['place'] = 'fixture:@artifact/source.md#Source'
#         retained[3]['sourceState'] = 'present'
#         retained = (*retained[:10], {'root': 'code', 'path': 'old.md'}, *retained[11:])
#         reports = _refs._related_reports(retained)
#         self.assertEqual([report['ref'] for report in reports], list(spellings))
#         self.assertEqual([report['parsedRef'] for report in reports], [raw.strip() for raw in spellings])
#         self.assertEqual([report['line'] for report in reports], [4, 5])
#         self.assertEqual([report['occurrence'] for report in reports], [0, 1])
#         self.assertTrue(all(report['chunk']['address'] == 'fixture:@code/old.md#Guide' for report in reports))
#         self.assertTrue(all(report['kind'] == 'related' and report['fault'] is None for report in reports))
#         self.assertTrue(all(report['location']['kind'] == 'branch' for report in reports))
# TEST-TIER-DISABLED-END tests/test_related_refs.py::RelatedRefTests.test_equivalent_relation_occurrences_keep_each_spelling_physical_line_and_location

# TEST-TIER-DISABLED-BEGIN tests/test_related_refs.py::RelatedRefTests.test_asserted_unmanaged_and_corrupt_relation_metadata_is_never_reported_as_declaration
#     def test_asserted_unmanaged_and_corrupt_relation_metadata_is_never_reported_as_declaration(self):
#         for change in ({'ownership': 'asserted'}, {'managedDeclaration': False},
#                        {'rawRefHex': 'not hex'}, {'occurrences': []}):
#             with self.subTest(change=change):
#                 retained = row()
#                 retained[3].update(change)
#                 with self.assertRaises(MycelError) as failure:
#                     _refs._related_reports(retained)
#                 self.assertEqual(failure.exception.code, 'store_format')
# TEST-TIER-DISABLED-END tests/test_related_refs.py::RelatedRefTests.test_asserted_unmanaged_and_corrupt_relation_metadata_is_never_reported_as_declaration

# TEST-TIER-DISABLED-BEGIN tests/test_related_refs.py::RelatedRefTests.test_missing_owner_preserves_fault_and_does_not_guess_a_live_address
#     def test_missing_owner_preserves_fault_and_does_not_guess_a_live_address(self):
#         retained = row(fault='owner_location_missing')
#         retained = (*retained[:7], None, *retained[8:13], None)
#         report = _refs._related_reports(retained)[0]
#         self.assertEqual(report['fault'], 'not_found')
#         self.assertFalse(report['ownerLocationAvailable'])
#         self.assertIsNone(report['chunk']['address'])
#         self.assertEqual(report['location'], {'id': 'file-location', 'kind': 'disk', 'name': 'disk'})
# TEST-TIER-DISABLED-END tests/test_related_refs.py::RelatedRefTests.test_missing_owner_preserves_fault_and_does_not_guess_a_live_address

# TEST-TIER-DISABLED-BEGIN tests/test_related_refs.py::RelatedRefTests.test_public_refs_merges_relations_under_one_readonly_snapshot_without_refresh
#     def test_public_refs_merges_relations_under_one_readonly_snapshot_without_refresh(self):
#         related = row('a-related', raw='bad\0ref', fault='not_a_ref')
#         resolved = row('c-related', raw='fixture:source.md#Source', fault=None, state='resolved')
#         dependency = row('b-dependency')
#         dependency[3].update(rawRef=_raw('fixture:dependency.md'),
#                              rawDeclared=_raw('fixture:dependency.md'), rawLine=_raw('fixture:dependency.md\n'),
#                              origin='comment', line=2)
#         dependency[3].pop('occurrences')
#         expected_dependency = _refs._reports(dependency)[0]
#         connection = _ReadOnlyRows([dependency], [resolved, related])
#         @contextmanager
#         def store(invocation):
#             yield connection, None
#         @contextmanager
#         def snapshot(selected):
#             self.assertIs(selected, connection)
#             self.assertFalse(connection.in_snapshot)
#             connection.in_snapshot = True
#             try:
#                 yield
#             finally:
#                 connection.in_snapshot = False
#         settings = resolver_fixtures.settings()
#         settings = replace(settings, values=_freeze({**settings.values, 'organizations': {},
#             'repos': {name: {**value, 'code_subdirs': ()} for name, value in settings.values['repos'].items()}}))
#         invocation = Invocation('refs', ('fixture',), settings=settings)
#         with patch.object(_refs, 'invocation_store', store), patch.object(_refs, 'snapshot_transaction', snapshot), \
#                 patch('mycel._resolver.SourceResolver.resolve', side_effect=AssertionError('Never retry resolution')), \
#                 patch('mycel._capture.capture_repository', side_effect=AssertionError('Never ingest or refresh')):
#             result = _refs.refs(invocation)
#             filtered = _refs.refs(Invocation('refs', ('fixture',), arguments=('--unresolved',),
#                                              settings=invocation.settings))
#         self.assertEqual(result.status, 0)
#         reports = result.value['repositories'][0]['result']['refs']
#         self.assertEqual([report['id'] for report in reports], ['a-related', 'b-dependency', 'c-related'])
#         self.assertEqual(reports[1], expected_dependency)
#         self.assertNotIn('kind', reports[1])
#         self.assertEqual([report['id'] for report in filtered.value['repositories'][0]['result']['refs']],
#                          ['a-related', 'b-dependency'])
#         self.assertEqual(len(connection.queries), 6)
#         self.assertFalse(connection.in_snapshot)
# TEST-TIER-DISABLED-END tests/test_related_refs.py::RelatedRefTests.test_public_refs_merges_relations_under_one_readonly_snapshot_without_refresh


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:2
# from contextlib import contextmanager
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:3
# from copy import deepcopy
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:4
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:6
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:6

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:8
# from mycel._cli import Invocation
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:10
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:11
# from mycel._settings import _freeze
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_related_refs.py:13
# import test_resolver as resolver_fixtures
# TEST-TIER-IMPORTS-END tests/test_related_refs.py:13

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
