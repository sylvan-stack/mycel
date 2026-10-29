# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
