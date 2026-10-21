"""Read-only projections of declared relation occurrences and their faults."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from mycel._cli import Invocation
from mycel._coverage import proves
from mycel._declared_refs import _raw, _stored
from mycel._errors import MycelError
from mycel._settings import _freeze
from mycel import _refs
import test_resolver as resolver_fixtures


def row(identifier='related', *, raw='fixture:missing.md', fault='missing_file',
        state='unresolved', kind='disk', location='disk', occurrences=None):
    declared = '  ' + raw + '  '
    occurrence = {'rawDeclared': _raw(declared), 'rawLine': _raw(declared + '\r\n'),
                  'origin': 'comment', 'line': 3, 'syntaxFault': None}
    relation = {'rawRef': _stored(raw), 'rawRefHex': _raw(raw), 'ownership': 'declared',
        'managedDeclaration': True, 'occurrences': occurrences or [occurrence],
        'declarationLocation': {'file': 'file-location', 'kind': kind, 'location': location},
        'resolution': {'state': state, 'fault': fault, 'place': None, 'candidates': [], 'candidateCount': 0},
        'sourceState': 'unresolved'}
    return (identifier, 'fixture', 1, relation, None, 'chunk-id', {'name': 'Guide'},
            'fixture', 'artifact', 'guide.md', {}, kind, location, [{'name': 'Guide'}])


class _ReadOnlyRows:
    def __init__(self, dependencies, related):
        self.dependencies, self.related = dependencies, related
        self.queries = []
        self.in_snapshot = False

    def execute(self, sql, parameters):
        if not self.in_snapshot or not sql.startswith('SELECT '):
            raise AssertionError('Reporting must use the established read-only snapshot')
        self.queries.append((sql, parameters))
        if sql == _refs._REFS_SQL:
            values = self.dependencies
        elif sql == _refs._RELATED_REFS_SQL:
            values = self.related
        elif sql == _refs._JUSTIFIED_REFS_SQL:
            values = []
        else:
            raise AssertionError('Reporting may only select retained rows')
        class Cursor:
            def fetchall(self):
                return values
        return Cursor()


class RelatedRefTests(unittest.TestCase):
    @proves('MYC-16.1')
    def test_malformed_nul_missing_disabled_unknown_and_ambiguous_faults_remain_visible(self):
        for raw, internal, public in (
                ('bad\0ref', 'not_a_ref', 'not_a_ref'),
                ('not a ref', 'invalid_ref', 'not_a_ref'),
                ('fixture:missing.md', 'missing_file', 'not_found'),
                ('fixture:guide.md#Missing', 'missing_name', 'not_found'),
                ('disabled:guide.md', 'disabled_repository', 'disabled_repository'),
                ('unknown:guide.md', 'unregistered_repository', 'unknown_repository'),
                ('fixture:collision.md', 'ambiguous_path', 'ambiguous_path'),
                ('fixture:guide.md#Repeat', 'ambiguous_name', 'ambiguous_title')):
            with self.subTest(fault=internal):
                retained = row(raw=raw, fault=internal)
                if internal.startswith('ambiguous'):
                    retained[3]['resolution'].update(candidates=['fixture:@artifact/other.md#Repeat'], candidateCount=2)
                before = deepcopy(retained)
                reports = _refs._related_reports(retained)
                self.assertEqual(retained, before)
                self.assertEqual(len(reports), 1)
                report = reports[0]
                self.assertEqual((report['kind'], report['parsedRef'], report['fault'], report['resolutionFault']),
                                 ('related', raw, public, internal))
                self.assertEqual((report['ref'], report['rawLine'], report['origin'], report['line']),
                                 ('  ' + raw + '  ', '  ' + raw + '  \r\n', 'comment', 3))
                self.assertEqual(report['chunk']['address'], 'fixture:@artifact/guide.md#Guide')
                if internal.startswith('ambiguous'):
                    self.assertEqual(report['candidateCount'], 2)
                    self.assertEqual(report['candidates'][0]['address'], 'fixture:@artifact/other.md#Repeat')

    @proves('MYC-0.6', 'MYC-16.1')
    def test_equivalent_relation_occurrences_keep_each_spelling_physical_line_and_location(self):
        spellings = ('  fixture:source.md#Source  ', 'fixture:@artifact/source.md#Source')
        occurrences = [{'rawDeclared': _raw(raw), 'rawLine': _raw('> ' + raw + '\n'),
                        'origin': 'comment', 'line': index + 4, 'syntaxFault': None}
                       for index, raw in enumerate(spellings)]
        retained = row(raw=spellings[0].strip(), fault=None, state='resolved',
                       kind='branch', location='branches/earlier', occurrences=occurrences)
        retained[3]['resolution']['place'] = 'fixture:@artifact/source.md#Source'
        retained[3]['sourceState'] = 'present'
        retained = (*retained[:10], {'root': 'code', 'path': 'old.md'}, *retained[11:])
        reports = _refs._related_reports(retained)
        self.assertEqual([report['ref'] for report in reports], list(spellings))
        self.assertEqual([report['parsedRef'] for report in reports], [raw.strip() for raw in spellings])
        self.assertEqual([report['line'] for report in reports], [4, 5])
        self.assertEqual([report['occurrence'] for report in reports], [0, 1])
        self.assertTrue(all(report['chunk']['address'] == 'fixture:@code/old.md#Guide' for report in reports))
        self.assertTrue(all(report['kind'] == 'related' and report['fault'] is None for report in reports))
        self.assertTrue(all(report['location']['kind'] == 'branch' for report in reports))

    @proves('MYC-0.7')
    def test_asserted_unmanaged_and_corrupt_relation_metadata_is_never_reported_as_declaration(self):
        for change in ({'ownership': 'asserted'}, {'managedDeclaration': False},
                       {'rawRefHex': 'not hex'}, {'occurrences': []}):
            with self.subTest(change=change):
                retained = row()
                retained[3].update(change)
                with self.assertRaises(MycelError) as failure:
                    _refs._related_reports(retained)
                self.assertEqual(failure.exception.code, 'store_format')

    @proves('MYC-0.6')
    def test_missing_owner_preserves_fault_and_does_not_guess_a_live_address(self):
        retained = row(fault='owner_location_missing')
        retained = (*retained[:7], None, *retained[8:13], None)
        report = _refs._related_reports(retained)[0]
        self.assertEqual(report['fault'], 'not_found')
        self.assertFalse(report['ownerLocationAvailable'])
        self.assertIsNone(report['chunk']['address'])
        self.assertEqual(report['location'], {'id': 'file-location', 'kind': 'disk', 'name': 'disk'})

    @proves('MYC-0.6', 'MYC-0.10')
    def test_public_refs_merges_relations_under_one_readonly_snapshot_without_refresh(self):
        related = row('a-related', raw='bad\0ref', fault='not_a_ref')
        resolved = row('c-related', raw='fixture:source.md#Source', fault=None, state='resolved')
        dependency = row('b-dependency')
        dependency[3].update(rawRef=_raw('fixture:dependency.md'),
                             rawDeclared=_raw('fixture:dependency.md'), rawLine=_raw('fixture:dependency.md\n'),
                             origin='comment', line=2)
        dependency[3].pop('occurrences')
        expected_dependency = _refs._reports(dependency)[0]
        connection = _ReadOnlyRows([dependency], [resolved, related])
        @contextmanager
        def store(invocation):
            yield connection, None
        @contextmanager
        def snapshot(selected):
            self.assertIs(selected, connection)
            self.assertFalse(connection.in_snapshot)
            connection.in_snapshot = True
            try:
                yield
            finally:
                connection.in_snapshot = False
        settings = resolver_fixtures.settings()
        settings = replace(settings, values=_freeze({**settings.values, 'organizations': {},
            'repos': {name: {**value, 'code_subdirs': ()} for name, value in settings.values['repos'].items()}}))
        invocation = Invocation('refs', ('fixture',), settings=settings)
        with patch.object(_refs, 'invocation_store', store), patch.object(_refs, 'snapshot_transaction', snapshot), \
                patch('mycel._resolver.SourceResolver.resolve', side_effect=AssertionError('Never retry resolution')), \
                patch('mycel._capture.capture_repository', side_effect=AssertionError('Never ingest or refresh')):
            result = _refs.refs(invocation)
            filtered = _refs.refs(Invocation('refs', ('fixture',), arguments=('--unresolved',),
                                             settings=invocation.settings))
        self.assertEqual(result.status, 0)
        reports = result.value['repositories'][0]['result']['refs']
        self.assertEqual([report['id'] for report in reports], ['a-related', 'b-dependency', 'c-related'])
        self.assertEqual(reports[1], expected_dependency)
        self.assertNotIn('kind', reports[1])
        self.assertEqual([report['id'] for report in filtered.value['repositories'][0]['result']['refs']],
                         ['a-related', 'b-dependency'])
        self.assertEqual(len(connection.queries), 6)
        self.assertFalse(connection.in_snapshot)


if __name__ == '__main__':
    unittest.main()
