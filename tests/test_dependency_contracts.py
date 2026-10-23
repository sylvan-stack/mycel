"""Complete local dependency contracts through guarded configured-store callers.

These acceptance callers use the reusable publication/confirmation boundary;
they do not dispatch future ingest, confirmation, relation or detection commands.
"""
from hashlib import sha256
import unittest

from mycel._capture import LocationId
from mycel._coverage import proves
from mycel._dependency_application import DependencyApplicationStore
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import EvidenceStore
from mycel._locks import atomic_transaction
from mycel._reconciliation import ReconciliationError

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class DependencyContractStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def baseline(self, connection, row):
        return EvidenceStore(connection).read_baseline('downstream', row[7]).manifest.payload

    def confirm(self, connection):
        location, version = connection.execute("""SELECT l.id,c.chunk_version
            FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations c ON c.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk'
            AND l.metadata->>'path'='answer.md' AND c.metadata->>'name'='Answer'""").fetchone()
        inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
        with self.fixture.guards(connection), atomic_transaction(connection):
            reply = DependencyApplicationStore(connection).apply_in_transaction(self.base.settings,
                str(location), version, mode='confirm', captured_at='2026-10-09T12:00:00Z',
                reread=inputs.rereader(LocationId('disk', None, 'disk'), 'downstream', None))
            inputs.verify()
        return reply

    @proves('MYC-2.9', 'MYC-2.19', 'MYC-16.5', 'MYC-16.13', kind='store')
    def test_family_membership_and_complete_file_changes_keep_pin_until_declaration_removal(self):
        code = self.base.code / 'policy.py'
        original = b'class Policy:\n    def apply(self):\n        return 1\n'
        code.write_bytes(original)
        self.base.commit()
        self.fixture.answer.write_bytes(b'---\nsources: ["fixture:@code/policy.py#Policy", '
            b'"fixture:@artifact/source.md"]\n---\n# Answer\nUnchanged dependant.\n')
        with self.base.connect() as connection:
            before = self.fixture.prepare(connection)
            self.assertEqual(len(before), 2)
            family = next(row for row in before if row[4].endswith('#Policy'))
            whole = next(row for row in before if row[4].endswith('/source.md'))
            family_manifest, file_manifest = self.baseline(connection, family), self.baseline(connection, whole)
            self.assertEqual(len(family_manifest['members']), 2)
            self.assertEqual(file_manifest['pinnedHash'], sha256(self.fixture.source_bytes).hexdigest())
            self.assertEqual(len(self.fixture.edges(connection)), 3)
            code.write_bytes(original + b'    def added(self):\n        return 2\n')
            self.fixture.source.write_bytes(b'---\nrole: authored\n---\n' + self.fixture.source_bytes)
            observed = self.fixture.publish(connection)
            current = self.fixture.dependencies(connection)
            self.assertEqual(self.fixture.pins(current), self.fixture.pins(before))
            self.assertEqual(len(self.fixture.edges(connection)), 4)
            self.assertTrue(all(row[5]['reasons'] == ['source_changed'] for row in current))
            self.assertEqual(observed.counts['dependencyRepositories']['downstream']['pinsCaptured'], 0)
            code.write_bytes(b'class Policy:\n    def added(self):\n        return 2\n')
            self.fixture.publish(connection)
            current_family = next(row for row in self.fixture.dependencies(connection) if row[4].endswith('#Policy'))
            self.assertEqual(current_family[5]['reasons'], ['source_removed', 'source_changed'])
            self.assertEqual(self.baseline(connection, current_family), family_manifest)
            self.fixture.answer.write_bytes(b'# Answer\nUnchanged dependant.\n')
            removed = self.fixture.publish(connection, 'downstream')
            self.assertEqual(removed.counts['dependenciesReleased'], 2)
            self.assertEqual(self.fixture.dependencies(connection), [])
            self.assertEqual(self.fixture.edges(connection), [])
            self.assertEqual(self.fixture.role(connection), 'unclassified')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners '
                'WHERE id=ANY(%s)', ([family[6], whole[6]],)).fetchone(), (0,))

    @proves('MYC-2.12', kind='store')
    def test_each_publication_recomputes_file_role_and_document_code_defaults(self):
        self.fixture.answer.write_bytes(b'# Answer\nUnchanged dependant.\n')
        (self.base.code / 'plain.py').write_bytes(b'def plain():\n    return 1\n')
        self.base.commit()
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.assertEqual(self.fixture.role(connection), 'unclassified')
            self.assertEqual(connection.execute("""SELECT DISTINCT l.metadata->>'role'
                FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
                JOIN public.mycel_chunks c ON c.id=v.chunk_id
                WHERE c.repository='fixture' AND l.kind='disk' AND c.kind<>'document'""").fetchall(), [('authored',)])
            old_version = connection.execute("""SELECT c.chunk_version FROM public.mycel_locations c
                JOIN public.mycel_file_locations l ON l.id=c.file_location
                JOIN public.mycel_file_versions v ON v.id=l.file_version
                JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository='downstream'""").fetchone()[0]
            for role in ('authored', 'derived', 'authored'):
                self.fixture.answer.write_bytes(('---\nrole: ' + role + '\n---\n# Answer\nUnchanged dependant.\n').encode())
                self.fixture.publish(connection, 'downstream')
                self.assertEqual(self.fixture.role(connection), role)
                self.assertEqual(connection.execute("""SELECT c.chunk_version FROM public.mycel_locations c
                    JOIN public.mycel_file_locations l ON l.id=c.file_location
                    JOIN public.mycel_file_versions v ON v.id=l.file_version
                    JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository='downstream'""").fetchone()[0], old_version)

    @proves('MYC-2.19', 'MYC-16.13', kind='store')
    def test_source_sibling_frontmatter_observations_keep_pin_and_authorized_confirmation_answers_change(self):
        self.fixture.answer.write_bytes(self.fixture.answer.read_bytes() + b'\n## Other\nOriginal sibling.\n')
        with self.base.connect() as connection:
            before = self.fixture.prepare(connection)
            answer = next(row for row in before if row[6] is not None)
            baseline = self.baseline(connection, answer)
            self.fixture.source.write_bytes(b'# Source\nCurrent changed source.\n')
            self.fixture.publish(connection)
            self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Original sibling.', b'Edited sibling.')
                .replace(b'role: authored', b'role: derived'))
            observed = self.fixture.publish(connection, 'downstream')
            current = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
            self.assertEqual(self.fixture.pins([current]), self.fixture.pins([answer]))
            self.assertEqual(current[5]['reasons'], ['source_changed'])
            self.assertEqual(observed.counts['pinsCaptured'], 0)
            confirmed = self.confirm(connection)
            self.assertEqual(confirmed.captured, 1)
            renewed = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
            self.assertEqual(renewed[1], answer[1])
            self.assertNotEqual(renewed[7], answer[7])
            self.assertNotEqual(self.baseline(connection, renewed)['pinnedHash'], baseline['pinnedHash'])
            self.assertEqual(renewed[5]['reasons'], [])
            self.assertEqual(confirmed.plan.decisions[0].reasons, ())

    @proves('MYC-2.19', 'MYC-16.13', kind='store')
    def test_substantive_dependant_edit_pins_current_source_and_answers_direct_change_in_same_commit(self):
        with self.base.connect() as connection:
            before = self.fixture.prepare(connection)
            old_hash = self.baseline(connection, before[0])['pinnedHash']
            self.fixture.source.write_bytes(b'# Source\nCurrent changed source.\n')
            self.fixture.publish(connection)
            self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(b'Unchanged dependant.', b'Revised dependant.'))
            edited = self.fixture.publish(connection, 'downstream')
            current = self.fixture.dependencies(connection)
            self.assertEqual(edited.counts['pinsCaptured'], 1)
            self.assertNotEqual(self.baseline(connection, current[0])['pinnedHash'], old_hash)
            self.assertEqual(current[0][5]['reasons'], [])

    @proves('MYC-7.24', 'MYC-2.24', 'MYC-16.7', 'MYC-16.13', kind='store')
    def test_guarded_confirmation_withdraws_deleted_baseline_but_retains_declared_fault(self):
        with self.base.connect() as connection:
            before = self.fixture.prepare(connection)
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            retained = self.fixture.dependencies(connection)
            self.assertEqual(self.fixture.pins(retained), self.fixture.pins(before))
            self.assertEqual(retained[0][5]['reasons'], ['source_removed'])
            confirmed = self.confirm(connection)
            current = self.fixture.dependencies(connection)
            self.assertEqual(confirmed.released, 1)
            self.assertIsNone(current[0][6])
            self.assertEqual(current[0][5]['resolution']['fault'], 'missing_file')
            self.assertEqual(current[0][5]['reasons'], [])
            self.assertFalse(current[0][5]['everResolved'])
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners WHERE id=%s',
                (before[0][6],)).fetchone(), (0,))

    @proves('MYC-2.19', 'MYC-16.13', kind='store')
    def test_unresolved_declared_selection_refuses_confirmation_before_any_repin_or_withdrawal(self):
        with self.base.connect() as connection:
            original = self.fixture.prepare(connection)
            self.fixture.source.write_bytes(b'# Source\nChanged before confirmation.\n')
            self.fixture.publish(connection)
            self.fixture.answer.write_bytes(self.fixture.answer.read_bytes().replace(
                b'source.md#Source"]', b'source.md#Source", "fixture:@artifact/missing.md#Absent"]'))
            self.fixture.publish(connection, 'downstream')
            before = self.fixture.state(connection)
            with self.assertRaises(ReconciliationError) as error:
                self.confirm(connection)
            self.assertEqual(error.exception.status, 'invalid_input')
            self.assertEqual(self.fixture.state(connection), before)
            pinned = next(row for row in self.fixture.dependencies(connection) if row[6] is not None)
            self.assertEqual(self.fixture.pins([pinned]), self.fixture.pins(original))
            self.fixture.source.unlink()
            self.base.commit()
            self.fixture.publish(connection)
            before = self.fixture.state(connection)
            with self.assertRaises(ReconciliationError):
                self.confirm(connection)
            self.assertEqual(self.fixture.state(connection), before)
            self.assertIsNotNone(next(row for row in self.fixture.dependencies(connection) if row[6] is not None)[6])

    @proves('MYC-2.22', 'MYC-2.19', 'MYC-16.5', 'MYC-16.7', kind='store')
    def test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'---\nsources: ["fixture:@artifact/source.md#Source"]\n---\n# Guide\nMain dependant.\n')
        self.base.commit()
        self.base.git('checkout', '-b', 'feature')
        guide.write_bytes(guide.read_bytes().replace(b'Main dependant.', b'Feature dependant.'))
        self.fixture.source.write_bytes(b'# Source\nFeature governing source.\n')
        self.base.commit()
        self.base.git('checkout', 'fixture-main')
        guide.write_bytes(guide.read_bytes().replace(b'Main dependant.', b'Stashed dependant.'))
        self.fixture.source.write_bytes(b'# Source\nStashed governing source.\n')
        self.base.git('stash', 'push', '--message', 'Dependency baseline fixture')

        def rows(connection):
            return connection.execute("""SELECT l.kind,l.location,d.dependant_version,d.id,d.baseline_owner,
                r.manifest_hash,d.state FROM public.mycel_dependencies d
                JOIN public.mycel_file_locations l ON l.id::text=d.state->'declarationLocation'->>'file'
                JOIN public.mycel_locations c ON c.file_location=l.id AND c.chunk_version=d.dependant_version
                JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
                WHERE d.repository='fixture' AND l.metadata->>'path'='guide.md'
                ORDER BY l.kind,l.location,d.dependant_version""").fetchall()

        with self.base.connect() as connection:
            self.fixture.publish(connection)
            first = rows(connection)
            self.assertEqual({row[0] for row in first}, {'disk', 'branch', 'stash'})
            disk = next(row for row in first if row[0] == 'disk')
            retained = [row for row in first if row[0] != 'disk']
            stash = next(row for row in first if row[0] == 'stash')
            stash_baseline = EvidenceStore(connection).read_baseline('fixture', stash[5]).manifest.payload
            self.assertEqual(stash_baseline['location']['kind'], 'stash')
            self.assertNotEqual(stash[2], disk[2])
            self.assertIn(b'# Source\nStashed governing source.\n',
                [item.source for item in EvidenceStore(connection).read_baseline('fixture', stash[5]).snapshots])
            self.base.git('checkout', 'feature')
            self.fixture.publish(connection)
            later = next(row for row in rows(connection) if row[0] == 'disk')
            self.assertNotEqual(later[2], disk[2])
            self.assertNotEqual(later[5], disk[5])
            self.assertEqual([row for row in rows(connection) if row[0] != 'disk'], retained)
            self.base.git('checkout', 'fixture-main')
            restored = self.fixture.publish(connection)
            self.assertEqual(next(row for row in rows(connection) if row[0] == 'disk'), disk)
            self.assertEqual(restored.counts['pinsCaptured'], 0)
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            missing = next(row for row in rows(connection) if row[0] == 'disk')
            self.assertEqual(missing[:6], disk[:6])
            self.assertEqual((missing[6]['sourceExistence'], missing[6]['reasons']), ('away', ['source_removed']))
            self.assertEqual([row for row in rows(connection) if row[0] != 'disk'], retained)
