"""Configured exact relation creation, ownership, guards and edit acceptance."""
import io
import json
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._capture import LocationId
from mycel._cli import Invocation, parse, run
from mycel._coverage import proves
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._locks import atomic_transaction
from mycel._relate import RelateStore, relate
from mycel._relations import RelationApplicationStore

try:
    from . import test_derive as fixtures
except ImportError:
    import test_derive as fixtures


class RelateCliTests(unittest.TestCase):
    @proves('MYC-0.6', 'MYC-0.7')
    def test_exact_two_chunk_grammar_and_closed_option_failures(self):
        dependant = 'fixture:@artifact/guide.md#Guide'
        source = 'fixture:@artifact/source.md#Source'
        self.assertEqual(parse(['relate', dependant, '--remove', source]),
                         Invocation('relate', arguments=('--remove', dependant, source)))
        self.assertEqual(parse(['relate', dependant, source]), Invocation('relate', arguments=(dependant, source)))
        for args in (['relate', '--repo', 'fixture'], ['relate', '--rem'], ['relate', '--all']):
            output = io.StringIO()
            self.assertEqual(run(args, stdout=output, stderr=io.StringIO()), 1)
            self.assertEqual(json.loads(output.getvalue())['error']['code'], 'invalid_input')
        for args in ((), ('x',), ('x', 'y', 'z'), (dependant, 'fixture:@artifact/source.md'),
                     ('fixture:@index/summary#one', source)):
            with self.assertRaises(MycelError):
                relate(Invocation('relate', arguments=args))


class RelateStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DeriveStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.dependant, self.ref = self.fixture.dependant, self.fixture.ref
        self.guide = self.base.artifact / 'guide.md'

    def rows(self, connection):
        return connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash,r.xmin::text FROM public.mycel_relations r LEFT JOIN public.mycel_evidence_references e
            ON e.owner=r.baseline_owner AND e.ordinal=0 ORDER BY r.id""").fetchall()

    def state(self, connection):
        return self.fixture.state(connection), connection.execute('SELECT to_jsonb(r),xmin::text '
            'FROM public.mycel_relations r ORDER BY r.id').fetchall(), connection.execute('SELECT to_jsonb(r),xmin::text '
            'FROM public.mycel_stale_reasons r ORDER BY r.id').fetchall()

    def relate(self, connection, source=None, dependant=None, **kwargs):
        return RelateStore(connection).apply(self.base.settings, dependant or self.dependant, source or self.ref,
            build=0xDA, settings_home=self.base.base, captured_at='2026-10-10T10:00:00Z', **kwargs)

    def confirm_hook(self, connection):
        location, version = connection.execute("""SELECT l.file_location,l.chunk_version FROM public.mycel_locations l
            WHERE l.kind='disk' AND l.metadata->>'name'='Guide'""").fetchone()
        inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            result = RelationApplicationStore(connection).apply_in_transaction(self.base.settings, str(location), version,
                mode='confirm', captured_at='2026-10-10T11:00:00Z',
                reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None))
            inputs.verify()
        return result

    @proves('MYC-7.17', 'MYC-7.26', kind='store')
    def test_one_way_exact_header_endpoint_cycles_roles_and_authority_exclusion(self):
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            authority_before = self.fixture.dependencies(connection)
            result = self.relate(connection, 'fixture:@code/policy.py#Policy')
            self.assertEqual(result['members'], 1)
            baseline = EvidenceStore(connection).read_baseline('fixture', result['baselineManifest'])
            self.assertEqual(baseline.manifest.payload['selection'], 'chunk')
            self.assertEqual(len(baseline.manifest.payload['members']), 1)
            self.assertEqual(baseline.manifest.payload['members'][0]['place']['name'], 'Policy')
            self.assertEqual(len(self.rows(connection)), 1)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.dependencies(connection), authority_before)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
            reverse = self.relate(connection, self.dependant, 'fixture:@code/policy.py#Policy')
            self.assertTrue(reverse['changed'])
            self.assertEqual(len(self.rows(connection)), 2)
            self.assertTrue(self.relate(connection, self.dependant)['changed'])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))

    @proves('MYC-7.15', 'MYC-7.26', kind='store')
    def test_declared_asserted_independence_alias_noops_and_exact_removed_selection(self):
        self.guide.write_bytes(self.guide.read_bytes().replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\nfixture:source.md#Source\n-->'))
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            declared = self.rows(connection)
            self.assertEqual(len(declared), 1)
            self.assertEqual(declared[0][3]['ownership'], 'declared')
            reply = self.relate(connection)
            self.assertTrue(reply['changed'])
            asserted = [row for row in self.rows(connection) if row[3]['ownership'] == 'asserted'][0]
            self.assertEqual(asserted[5], reply['baselineManifest'])
            before = self.state(connection)
            self.assertFalse(self.relate(connection, 'fixture:source.md#Source')['changed'])
            self.assertEqual(self.state(connection), before)
            self.assertTrue(self.relate(connection, remove=True)['changed'])
            self.assertEqual(self.rows(connection), declared)
            before = self.state(connection)
            self.assertFalse(self.relate(connection, remove=True)['changed'])
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.14', 'MYC-7.26', kind='store')
    def test_complete_file_family_declarations_atomic_snapshots_and_separate_header_assertion(self):
        self.guide.write_bytes(self.guide.read_bytes().replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\nfixture:@artifact/source.md\nfixture:@code/policy.py#Policy\n-->'))
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            rows = self.rows(connection)
            self.assertEqual(len(rows), 2)
            baselines = [EvidenceStore(connection).read_baseline('fixture', row[5]) for row in rows]
            self.assertEqual({baseline.manifest.payload['selection'] for baseline in baselines}, {'file', 'family'})
            family = next(baseline for baseline in baselines if baseline.manifest.payload['selection'] == 'family')
            self.assertEqual(len(family.manifest.payload['members']), 2)
            complete_file = next(baseline for baseline in baselines if baseline.manifest.payload['selection'] == 'file')
            self.assertIn(self.fixture.source_bytes, [blob.source for blob in complete_file.snapshots])
            self.relate(connection, 'fixture:@code/policy.py#Policy')
            current = self.rows(connection)
            self.assertEqual(len(current), 3)
            self.fixture.publish(connection)
            kept = {str(row[0]): row[5] for row in self.rows(connection)}
            self.assertTrue(all(kept[str(row[0])] == row[5] for row in rows))
            header = next(row for row in current if row[3]['ownership'] == 'asserted')
            self.assertEqual(len(EvidenceStore(connection).read_baseline('fixture', header[5]).manifest.payload['members']), 1)

    @proves('MYC-7.14', 'MYC-7.17', kind='store')
    def test_malformed_missing_unknown_disabled_ambiguous_related_faults_without_authority(self):
        self.guide.write_bytes(self.guide.read_bytes().replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\nnot a ref\nunknown:source.md#Source\nfixture:no.md#Absent\n'
            b'fixture:source.md#Source\nfixture:@artifact/source.md#Source\n-->'))
        (self.base.code / 'source.md').write_bytes(b'# Source\nColliding source.\n')
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            rows = self.rows(connection)
            faults = {row[3]['resolution']['fault'] for row in rows}
            self.assertTrue({'not_a_ref', 'unregistered_repository', 'missing_file', 'ambiguous_path'} <= faults)
            self.assertEqual(len(rows), 5)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_ref_faults').fetchone(), (4,))

    @proves('MYC-7.16', 'MYC-7.26', kind='store')
    def test_sibling_edit_preserves_pin_substantive_edit_and_confirmation_renew_direct_reasons(self):
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            reply = self.relate(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
            self.fixture.publish(connection)
            old = [row for row in self.rows(connection) if row[5] == reply['baselineManifest']][0]
            self.assertEqual(old[3]['reasons'], ['related_changed'])
            self.assertFalse(self.relate(connection)['changed'])
            self.guide.write_bytes(self.guide.read_bytes().replace(b'Other body.', b'Other edited body.'))
            self.fixture.publish(connection)
            self.assertEqual(next(row for row in self.rows(connection) if row[1] == old[1])[5], old[5])
            confirmed = self.confirm_hook(connection)
            self.assertEqual(confirmed.captured, 1)
            current = next(row for row in self.rows(connection) if row[1] == old[1])
            self.assertNotEqual(current[5], old[5])
            self.assertEqual(current[3]['reasons'], [])
            self.fixture.source.write_bytes(b'# Source\nChanged a second time.\n')
            self.fixture.publish(connection)
            self.guide.write_bytes(self.guide.read_bytes().replace(b'Original dependant.', b'Edited dependant.'))
            self.fixture.publish(connection)
            disk = connection.execute("SELECT chunk_version FROM public.mycel_locations WHERE kind='disk' "
                "AND metadata->>'name'='Guide'").fetchone()[0]
            edited = next(row for row in self.rows(connection) if row[1] == disk)
            self.assertEqual(edited[3]['reasons'], [])
            self.assertNotEqual(edited[5], current[5])

    @proves('MYC-7.15', 'MYC-7.26', kind='store')
    def test_retained_missing_removal_is_exact_and_absent_removal_does_not_collect(self):
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            reply = self.relate(connection)
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            self.assertEqual(self.rows(connection)[0][5], reply['baselineManifest'])
            self.assertTrue(self.relate(connection, remove=True)['changed'])
            self.assertEqual(self.rows(connection), [])
            before = self.state(connection)
            absent = self.relate(connection, remove=True)
            self.assertFalse(absent['changed'])
            self.assertEqual(absent['source'], reply['source'])
            self.assertNotIn('sourceRef', absent)
            self.assertEqual(self.state(connection), before)
            with self.assertRaises(MycelError) as error:
                self.relate(connection, source='fixture:source.md#Source', remove=True)
            self.assertIn('missing_file', error.exception.message)
            self.assertEqual(self.state(connection), before)
            absent_name = self.relate(connection, source='fixture:guide.md#Never existed', remove=True)
            self.assertEqual(absent_name['source']['address'],
                             'fixture:@artifact/guide.md#Never%20existed')
            self.assertFalse(absent_name['changed'])
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.26', kind='store')
    def test_exact_disk_source_and_dependant_guards_and_late_audit_rollback(self):
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            before = self.state(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged without ingest.\n')
            with self.assertRaises(MycelError) as error:
                self.relate(connection)
            self.assertIn('changed_since_ingest', error.exception.message)
            self.assertEqual(self.state(connection), before)
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            original = MutationActivity.record_in_transaction
            def late(activity, *args, **kwargs):
                result = original(activity, *args, **kwargs)
                self.fixture.source.write_bytes(b'# Source\nLate input.\n')
                return result
            with patch.object(MutationActivity, 'record_in_transaction', late):
                with self.assertRaises(MycelError):
                    self.relate(connection)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-7.26', kind='store')
    def test_public_dispatch_exact_committed_relation_reply_and_noop_activity(self):
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            with patch('mycel._cli.load_settings', return_value=self.base.settings), \
                    patch('mycel._cli.invocation_store') as store, patch('mycel._build_identity.current_build', return_value=0xDA):
                from contextlib import nullcontext
                store.return_value = nullcontext((connection, None))
                output = io.StringIO()
                self.assertEqual(run(['relate', self.dependant, self.ref], stdout=output, stderr=io.StringIO()), 0)
                reply = json.loads(output.getvalue())
            self.assertTrue(reply['changed'])
            entry = connection.execute("SELECT id FROM public.mycel_activity WHERE kind='relate'").fetchone()[0]
            self.assertEqual(activity_state(connection, entry)['counts'], reply)
            before = self.state(connection)
            self.assertFalse(self.relate(connection)['changed'])
            self.assertEqual(self.state(connection), before)
