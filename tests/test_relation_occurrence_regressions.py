# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured regressions for independently valid and malformed occurrences."""

from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._errors import MycelError
from mycel._locks import atomic_transaction
from mycel._relate import RelateStore
from mycel._relations import RelationApplicationStore

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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
