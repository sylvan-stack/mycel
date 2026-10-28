"""Configured regressions for independently valid and malformed occurrences."""
import unittest

from mycel._evidence import EvidenceStore

try:
    from . import test_derive as fixtures
    from .test_refs import invoke, store_state
except ImportError:
    import test_derive as fixtures
    from test_refs import invoke, store_state


SOURCE = 'fixture:@artifact/source.md#Source'
DEPENDANT = 'fixture:@artifact/guide.md#Guide'


class RelationOccurrenceRegressionStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DeriveStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.guide = self.base.artifact / 'guide.md'

    def mixed(self, body='Original dependant.'):
        return ('---\nrole: authored\n---\n# Guide\n' + body + '\n'
                '<!-- related: ' + SOURCE + ' -->\n'
                '<!-- related:\n  ' + SOURCE + '  \n').encode()

    def publish_guide(self, connection, raw):
        self.guide.write_bytes(raw)
        return self.fixture.publish(connection)

    def current_rows(self, connection):
        return connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash FROM public.mycel_relations r
            JOIN public.mycel_locations l ON l.chunk_version=r.left_version
                AND l.file_location::text=r.state->'declarationLocation'->>'file'
            LEFT JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
            WHERE r.repository='fixture' AND l.kind='disk' AND l.metadata->>'name'='Guide'
            ORDER BY r.id""").fetchall()

    def current_pins(self, connection):
        rows = [row for row in self.current_rows(connection)
                if row[4] is not None and row[3]['resolution']['fault'] is None]
        result = {row[3]['ownership']: row for row in rows}
        self.assertEqual(len(result), len(rows), 'One authoritative pin per independently owned selection')
        return result

    def baseline(self, connection, row):
        return EvidenceStore(connection).read_baseline('fixture', row[5])

    def pin_identities(self, rows):
        return {kind: (row[0], row[1], row[4], row[5]) for kind, row in rows.items()}

    def reports(self, *, unresolved=False):
        arguments = ('refs', '--repo', 'fixture') + (('--unresolved',) if unresolved else ())
        status, reply, diagnostics = invoke(self.base.config, arguments)
        self.assertEqual((status, diagnostics), (0, ''))
        return [ref for ref in reply['repositories'][0]['result']['refs']
                if ref['location']['kind'] == 'disk' and ref['ownerLocationAvailable']]

    def assert_mixed_reports(self):
        refs = sorted(self.reports(), key=lambda ref: ref['line'])
        self.assertEqual(len(refs), 2)
        self.assertEqual([(ref['parsedRef'], ref['line'], ref['fault']) for ref in refs],
                         [(SOURCE, 6, None), (SOURCE, 8, 'not_a_ref')])
        self.assertEqual(refs[0]['resolvedAddress'], SOURCE)
        self.assertEqual(refs[0]['baselineStatus'], 'retained')
        self.assertEqual((refs[1]['state'], refs[1]['resolutionFault'], refs[1]['resolvedAddress']),
                         ('invalid', 'not_a_ref', None))
        self.assertEqual((refs[1]['candidates'], refs[1]['candidateCount']), ([], 0))
        self.assertEqual(refs[1]['ref'], '  ' + SOURCE + '  ')
        self.assertEqual(refs[1]['rawLine'], '  ' + SOURCE + '  \n')
        unresolved = self.reports(unresolved=True)
        self.assertEqual([(ref['parsedRef'], ref['line'], ref['fault']) for ref in unresolved],
                         [(SOURCE, 8, 'not_a_ref')])

    def test_mixed_closed_and_unclosed_same_ref_pins_valid_occurrence_and_reports_only_invalid_fault(self):
        self.guide.write_bytes(self.mixed())
        self.base.commit()
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            pins = self.current_pins(connection)
            self.assertEqual(set(pins), {'declared'})
            baseline = self.baseline(connection, pins['declared'])
            self.assertEqual((baseline.manifest.payload['selection'], baseline.manifest.payload['source']['address']),
                             ('chunk', SOURCE))
            self.assertEqual(len(baseline.manifest.payload['members']), 1)
            self.assertIn(self.fixture.source_bytes, [blob.source for blob in baseline.snapshots])
            before = store_state(connection)
            self.assert_mixed_reports()
            self.assertEqual(store_state(connection), before)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))

# TEST-TIER-DISABLED-BEGIN tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_confirmation_refuses_malformed_occurrence_without_renewing_valid_pin
#     def test_confirmation_refuses_malformed_occurrence_without_renewing_valid_pin(self):
#         self.guide.write_bytes(self.mixed())
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             original = self.current_pins(connection)
#             self.assertEqual(set(original), {'declared'})
#             self.fixture.source.write_bytes(b'# Source\nChanged source requires a new comparison.\n')
#             self.fixture.publish(connection)
#             current = self.current_pins(connection)
#             self.assertEqual(self.pin_identities(current), self.pin_identities(original))
#             self.assertEqual(current['declared'][3]['reasons'], ['related_changed'])
#             location, version = connection.execute("""SELECT file_location,chunk_version FROM public.mycel_locations
#                 WHERE kind='disk' AND metadata->>'name'='Guide'""").fetchone()
#             inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
#             before = store_state(connection)
#             with self.assertRaises(MycelError) as error:
#                 with self.fixture.guards(connection), atomic_transaction(connection):
#                     RelationApplicationStore(connection).apply_in_transaction(self.base.settings,
#                         str(location), version, mode='confirm', captured_at='2026-10-11T10:00:00Z',
#                         reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None))
#                     inputs.verify()
#             self.assertEqual(error.exception.code, 'invalid_input')
#             self.assertEqual(store_state(connection), before)
#             self.assert_mixed_reports()
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(original))
# TEST-TIER-DISABLED-END tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_confirmation_refuses_malformed_occurrence_without_renewing_valid_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_valid_duplicates_share_one_pin_and_invalid_only_duplicates_have_no_pin
#     def test_valid_duplicates_share_one_pin_and_invalid_only_duplicates_have_no_pin(self):
#         valid = ('---\nrole: authored\n---\n# Guide\nBody.\n<!-- related:\n' + SOURCE + '\n  ' +
#                  SOURCE + '  \n-->\n').encode()
#         self.guide.write_bytes(valid)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             first = self.current_pins(connection)
#             self.assertEqual(set(first), {'declared'})
#             refs = self.reports()
#             self.assertEqual(len(refs), 2)
#             self.assertTrue(all(ref['fault'] is None and ref['baselineStatus'] == 'retained' for ref in refs))
#             self.assertEqual(len({ref['id'] for ref in refs}), 1)
#             self.assertEqual(self.reports(unresolved=True), [])
#             repeated = self.fixture.publish(connection)
#             self.assertEqual(repeated.counts['relationPinsCaptured'], 0)
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(first))
#             invalid = ('---\nrole: authored\n---\n# Guide\nBody.\n<!-- related:\n' + SOURCE + '\n  ' +
#                        SOURCE + '  \n').encode()
#             self.publish_guide(connection, invalid)
#             self.assertEqual(self.current_pins(connection), {})
#             refs = self.reports()
#             self.assertEqual(len(refs), 2)
#             self.assertTrue(all(ref['fault'] == 'not_a_ref' for ref in refs))
#             self.assertEqual(self.reports(unresolved=True), refs)
#             self.assertTrue(all(row[4] is None for row in self.current_rows(connection)))
#             retained = connection.execute("""SELECT r.id,r.left_version,r.baseline_owner,e.manifest_hash
#                 FROM public.mycel_relations r JOIN public.mycel_evidence_references e
#                 ON e.owner=r.baseline_owner AND e.ordinal=0 WHERE r.id=%s""", (first['declared'][0],)).fetchone()
#             self.assertEqual(retained, (first['declared'][0], first['declared'][1],
#                                        first['declared'][4], first['declared'][5]))
#             self.assertIn(self.fixture.source_bytes,
#                           [blob.source for blob in self.baseline(connection, first['declared']).snapshots])
# TEST-TIER-DISABLED-END tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_valid_duplicates_share_one_pin_and_invalid_only_duplicates_have_no_pin

# TEST-TIER-DISABLED-BEGIN tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_mixed_occurrences_preserve_independent_pins_through_edit_inheritance_and_known_restore
#     def test_mixed_occurrences_preserve_independent_pins_through_edit_inheritance_and_known_restore(self):
#         original = self.mixed()
#         self.guide.write_bytes(original)
#         self.base.commit()
#         with self.base.connect() as connection:
#             self.fixture.publish(connection)
#             RelateStore(connection).apply(self.base.settings, DEPENDANT, SOURCE,
#                 captured_at='2026-10-11T10:00:00Z', settings_home=self.base.base)
#             first = self.current_pins(connection)
#             self.assertEqual(set(first), {'declared', 'asserted'})
#             first_hashes = {kind: self.baseline(connection, row).manifest.payload['pinnedHash']
#                             for kind, row in first.items()}
#             self.assertNotEqual(first['declared'][4], first['asserted'][4])
#             self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
#             inherited = self.publish_guide(connection, self.mixed('Original   dependant.'))
#             equivalent = self.current_pins(connection)
#             self.assertEqual(set(equivalent), {'declared', 'asserted'})
#             self.assertEqual(inherited.counts['relationPinsInherited'], 2)
#             self.assertNotEqual(equivalent['declared'][1], first['declared'][1])
#             for kind, row in equivalent.items():
#                 self.assertEqual(self.baseline(connection, row).manifest.payload['pinnedHash'], first_hashes[kind])
#                 self.assertEqual(row[3]['reasons'], ['related_changed'])
#             self.assert_mixed_reports()
#             edited = self.publish_guide(connection, self.mixed('Edited dependant.'))
#             repinned = self.current_pins(connection)
#             self.assertEqual(edited.counts['relationPinsCaptured'], 2)
#             for kind, row in repinned.items():
#                 self.assertNotEqual(self.baseline(connection, row).manifest.payload['pinnedHash'], first_hashes[kind])
#                 self.assertEqual(row[3]['reasons'], [])
#             self.assert_mixed_reports()
#             restored = self.publish_guide(connection, original)
#             current = self.current_pins(connection)
#             self.assertEqual((restored.counts['relationPinsCaptured'], restored.counts['relationPinsInherited']), (0, 0))
#             self.assertEqual(self.pin_identities(current), self.pin_identities(first))
#             self.assertTrue(all(row[3]['reasons'] == ['related_changed'] for row in current.values()))
#             self.assert_mixed_reports()
#             before = store_state(connection)
#             assertion = RelateStore(connection).apply(self.base.settings, DEPENDANT, SOURCE,
#                 captured_at='2026-10-11T10:10:00Z', settings_home=self.base.base)
#             self.assertFalse(assertion['changed'])
#             self.assertEqual(store_state(connection), before)
#             self.assertEqual(self.pin_identities(self.current_pins(connection)), self.pin_identities(first))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_relation_occurrence_regressions.py::RelationOccurrenceRegressionStoreTests.test_mixed_occurrences_preserve_independent_pins_through_edit_inheritance_and_known_restore


if __name__ == '__main__':
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:4
# from mycel._capture import LocationId
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:5
# from mycel._dependency_inputs import DependencyCaptureInputs
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:6
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:8
# from mycel._locks import atomic_transaction
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:9
# from mycel._relate import RelateStore
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:9
# TEST-TIER-IMPORTS-BEGIN tests/test_relation_occurrence_regressions.py:10
# from mycel._relations import RelationApplicationStore
# TEST-TIER-IMPORTS-END tests/test_relation_occurrence_regressions.py:10
