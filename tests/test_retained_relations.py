"""Configured acceptance for deleted-source relation retention and withdrawal.

Initial links are seeded with the real guarded evidence writer. Future relate,
verification and declaration producers retain ownership of their public flows.
"""
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._activity import MutationActivity, activity_state
from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import (CaptureLocation, EvidenceError, EvidenceStore, PinInputs,
    capture_baseline, checked_transaction_input_guard)
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver
from mycel._retained_relations import RetainedRelationStore

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class RetainedRelationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.fixture.answer.write_bytes(b'---\nrole: authored\n---\n# Answer\nUnchanged dependant.\n')
        self.ref = 'fixture:@artifact/source.md#Source'

    def endpoint(self, connection):
        return connection.execute("""SELECT l.id,c.chunk_version
            FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk' AND c.metadata->>'name'='Answer'""").fetchone()

    def relation(self, connection, identifier):
        return connection.execute("""SELECT id,repository,left_version,right_place,state,baseline_owner
            FROM public.mycel_relations WHERE id=%s""", (identifier,)).fetchone()

    def state(self, connection):
        return (self.fixture.state(connection), connection.execute("""SELECT to_jsonb(r),xmin::text
            FROM public.mycel_relations r ORDER BY id""").fetchall())

    def seed(self, connection, *, ownership='declared'):
        self.fixture.prepare(connection)
        identifier = str(uuid4())
        location, version = self.endpoint(connection)
        catalog = SourceResolver.from_store(connection, self.base.settings)
        endpoint = catalog.resolve('downstream:@artifact/answer.md#Answer', purpose='endpoint').selection
        resolution = catalog.resolve(self.ref)
        selection = resolution.selection
        inputs = PinInputs(self.base.settings, endpoint.members[0], endpoint.file, selection,
            CaptureLocation('disk'), resolution, catalog)
        checks = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        reread = checks.rereader(LocationId('disk', None, 'disk'), 'downstream', None)
        # The production rereader expects the complete retained resolver shape.
        from mycel._dependency_application import RetainedDependencyResolver
        from dataclasses import replace
        inputs = replace(inputs, catalog=RetainedDependencyResolver(catalog, {}),
            guards={'dependencyApplication': {'sourcePlaces': {self.ref: selection.place.address}}})
        capture = capture_baseline('downstream', endpoint.members[0], endpoint.file, selection,
            kind='related', declaration=self.ref, captured_at='2026-10-09T11:00:00Z', location=CaptureLocation('disk'))
        state = {'rawRef': self.ref, 'baselineRef': self.ref, 'ownership': ownership,
            'everResolved': True, 'anchor': selection.file.identifier if selection.kind == 'file'
                else selection.members[0].chunk.identifier,
            'declarationLocation': {'file': str(location), 'kind': 'disk', 'location': 'disk'}}
        with self.fixture.guards(connection), atomic_transaction(connection):
            with checked_transaction_input_guard(connection, inputs, lambda: reread(inputs)) as token:
                owner = EvidenceStore(connection)._write(token, capture, f'{identifier}:{capture.manifest.identifier}')
                connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,%s,%s)',
                    (identifier, 'downstream', version, selection.place.address, Jsonb(state), owner))
            checks.verify()
        self.apply(connection, identifier)
        return identifier, capture.manifest.identifier

    def apply(self, connection, identifier, **kwargs):
        location, version = self.endpoint(connection)
        checks = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            reply = RetainedRelationStore(connection).apply_in_transaction(self.base.settings, str(location), version,
                identifier, captured_at='2026-10-09T12:00:00Z',
                reread=checks.rereader(LocationId('disk', None, 'disk'), 'downstream', None), **kwargs)
            checks.verify()
        return reply

    def test_source_publication_retains_relation_away_deleted_and_recreated_pin_without_authority(self):
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            original = self.relation(connection, identifier)
            baseline = EvidenceStore(connection).read_baseline('downstream', baseline_id)
            source_version = original[4]['selection']['members'][0]['version']
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            away = self.relation(connection, identifier)
            self.assertEqual(away[:4] + away[5:], original[:4] + original[5:])
            self.assertEqual((away[4]['sourceExistence'], away[4]['reasons']), ('away', ['source_removed']))
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.edges(connection), [])
            self.base.commit()
            with MutationActivity(connection, build=1).session() as activity:
                deleted_result = self.fixture.publish(connection, activity=activity)
                activity.finish('done', counts={('fixture', 'ingest'): deleted_result.counts,
                    ('downstream', 'ingest'): deleted_result.counts['dependencyRepositories']['downstream']})
            deleted = self.relation(connection, identifier)
            self.assertEqual((deleted[4]['sourceExistence'], deleted[4]['reasons']), ('deleted', ['source_removed']))
            self.assertEqual(deleted[4]['sourceAbsence']['place'], self.ref)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                (source_version,)).fetchone(), (0,))
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id), baseline)
            counts = deleted_result.counts['dependencyRepositories']['downstream']
            self.assertEqual(counts['relationsChanged'], 1)
            entries = connection.execute("SELECT id FROM public.mycel_activity WHERE repository='downstream'").fetchall()
            self.assertEqual(len(entries), 1)
            self.assertEqual(activity_state(connection, entries[0][0])['counts'], counts)
            stable = self.state(connection)
            self.assertFalse(self.fixture.publish(connection).changed)
            self.assertEqual(self.state(connection), stable)
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.fixture.publish(connection)
            recreated = self.relation(connection, identifier)
            self.assertEqual(recreated[:4] + recreated[5:], original[:4] + original[5:])
            self.assertEqual((recreated[4]['sourceExistence'], recreated[4]['reasons']), ('present', []))
            self.assertNotEqual(recreated[4]['selection']['members'][0]['version'], source_version)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.fixture.source.write_bytes(b'# Source\nChanged recreated source.\n')
            self.fixture.publish(connection)
            changed = self.relation(connection, identifier)
            self.assertEqual(changed[4]['reasons'], ['related_changed'])
            self.assertEqual(changed[5], original[5])

    def test_empty_relation_file_is_present_and_deleted_evidence_is_never_empty_substitution(self):
        self.fixture.source.write_bytes(b'')
        self.base.commit()
        self.ref = 'fixture:@artifact/source.md'
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            original = self.relation(connection, identifier)
            self.assertEqual(original[4]['sourceExistence'], 'present')
            self.assertEqual(original[4]['selection']['members'], [])
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            missing = self.relation(connection, identifier)
            self.assertEqual(missing[4]['sourceExistence'], 'deleted')
            self.assertEqual(missing[4]['sourceAbsence']['previousFileHash'], sha256(b'').hexdigest())
            self.assertEqual(missing[5], original[5])
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.payload['pinnedHash'],
                sha256(b'').hexdigest())
            self.fixture.source.write_bytes(b'')
            self.fixture.publish(connection)
            self.assertEqual(self.relation(connection, identifier)[4]['reasons'], [])
            self.assertEqual(self.relation(connection, identifier)[5], original[5])

    def test_confirmation_withdraws_missing_relation_baseline_and_keeps_declared_fault(self):
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            owner = self.relation(connection, identifier)[5]
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            reply = self.apply(connection, identifier, authorization='owner_confirmation')
            current = self.relation(connection, identifier)
            self.assertEqual(reply.released, 1)
            self.assertIsNone(current[5])
            self.assertEqual(current[4]['rawRef'], self.ref)
            self.assertEqual(current[4]['resolution']['fault'], 'missing_file')
            self.assertEqual(current[4]['reasons'], [])
            self.assertEqual(current[4]['sourceState'], 'unresolved')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
                (owner,)).fetchone(), (0,))
            self.assertEqual(self.fixture.role(connection), 'authored')

    def test_substantive_edit_withdraws_missing_current_relation_without_changing_historical_pin(self):
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            original = self.relation(connection, identifier)
            self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Edited dependant.'))
            result = self.fixture.publish(connection, 'downstream', collect=False)
            relations = connection.execute('SELECT id,left_version,state,baseline_owner FROM public.mycel_relations '
                'ORDER BY left_version').fetchall()
            self.assertEqual(len(relations), 2)
            self.assertEqual(self.relation(connection, identifier), original)
            current = next(row for row in relations if str(row[0]) != identifier)
            self.assertIsNone(current[3])
            self.assertEqual(current[2]['resolution']['fault'], 'missing_file')
            self.assertEqual(current[2]['reasons'], [])
            self.assertEqual(result.counts['relationsChanged'], 1)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.identifier, baseline_id)

    def test_same_capture_source_deletion_and_dependant_edit_withdraws_previously_present_relation(self):
        local = self.fixture.downstream / 'local.md'
        local.write_bytes(b'# Local\nSame-repository source.\n')
        self.ref = 'downstream:@artifact/local.md#Local'
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            previous = self.relation(connection, identifier)
            self.assertEqual(previous[4]['sourceExistence'], 'present')
            local.unlink()
            self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Edited dependant.'))
            result = self.fixture.publish(connection, 'downstream', collect=False)
            rows = connection.execute('SELECT id,left_version,state,baseline_owner FROM public.mycel_relations '
                'ORDER BY left_version').fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(self.relation(connection, identifier), previous)
            current = next(row for row in rows if str(row[0]) != identifier)
            self.assertIsNone(current[3])
            self.assertEqual(current[2]['resolution']['fault'], 'missing_file')
            self.assertEqual(current[2]['reasons'], [])
            self.assertFalse(current[2]['everResolved'])
            self.assertEqual(result.counts['relationsChanged'], 1)
            self.assertEqual(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.identifier, baseline_id)

    def test_removed_relation_family_member_preserves_complete_pin_and_direct_removed_reason(self):
        code = self.base.code / 'policy.py'
        code.write_bytes(b'class Policy:\n    def apply(self):\n        return 1\n')
        self.base.commit()
        self.ref = 'fixture:@code/policy.py#Policy'
        with self.base.connect() as connection:
            identifier, baseline_id = self.seed(connection)
            previous = self.relation(connection, identifier)
            self.assertEqual(len(previous[4]['selection']['members']), 2)
            code.write_bytes(b'class Policy:\n    pass\n')
            self.fixture.publish(connection)
            current = self.relation(connection, identifier)
            self.assertEqual(current[4]['reasons'], ['source_removed', 'related_changed'])
            self.assertEqual(current[5], previous[5])
            self.assertEqual(len(EvidenceStore(connection).read_baseline('downstream', baseline_id).manifest.payload['members']), 2)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(self.fixture.edges(connection), [])

    def test_selected_relation_removal_and_late_foreign_change_are_guarded_and_atomic(self):
        with self.base.connect() as connection:
            declared, _ = self.seed(connection)
            asserted, _ = self.seed(connection, ownership='asserted')
            original = self.relation(connection, declared)
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            missing = self.relation(connection, declared)
            self.apply(connection, asserted, remove=True)
            self.assertIsNone(self.relation(connection, asserted))
            self.assertEqual(self.relation(connection, declared), missing)
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            before = self.state(connection)
            with self.assertRaises(EvidenceError):
                self.apply(connection, declared, remove=True)
            self.assertEqual(self.state(connection), before)
            self.fixture.publish(connection)
            self.fixture.source.write_bytes(b'# Source\nNew source.\n')
            before = self.state(connection)
            def late_change(repository, counts):
                self.fixture.answer.write_bytes(b'# Answer\nChanged during reply callback.\n')
                return counts
            with self.assertRaises(EvidenceError):
                self.fixture.publish(connection, reply_counts=late_change)
            self.assertEqual(self.state(connection), before)
