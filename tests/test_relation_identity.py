"""Configured relation identity, located pins, exact faults and eligibility."""
import json
import unittest

from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import EvidenceStore
from mycel._locks import atomic_transaction
from mycel._relate import RelateStore
from mycel._relations import RelationApplicationStore
from mycel._settings import load_settings

try:
    from . import test_derive as fixtures
    from .test_refs import invoke, store_state
except ImportError:
    import test_derive as fixtures
    from test_refs import invoke, store_state


class RelationIdentityStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DeriveStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.guide = self.base.artifact / 'guide.md'

    def declared(self, refs):
        original = self.guide.read_bytes()
        self.guide.write_bytes(original.replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\n' + refs + b'\n-->'))
        self.base.commit()
        return self.guide.read_bytes()

    def current(self, connection):
        rows = connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash,fl.kind,fl.location,r.xmin::text
            FROM public.mycel_relations r
            JOIN public.mycel_file_locations fl ON fl.id::text=r.state->'declarationLocation'->>'file'
            JOIN public.mycel_locations l ON l.file_location=fl.id AND l.chunk_version=r.left_version
            JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
            WHERE r.repository='fixture' ORDER BY fl.kind,fl.location,r.id""").fetchall()
        return {(row[6], row[7], row[3]['ownership'], row[2]): row for row in rows}

    def disk(self, connection):
        return {key[2:]: row for key, row in self.current(connection).items() if key[0] == 'disk'}

    def baselines(self, connection, rows):
        return {key: EvidenceStore(connection).read_baseline('fixture', row[5]) for key, row in rows.items()}

    def foreign(self, *, enabled):
        path = self.base.base / 'foreign'
        path.mkdir(exist_ok=True)
        (path / 'source.md').write_bytes(b'# Source\nForeign source.\n')
        text = self.base.config.read_text()
        text += '\n[repos.foreign]\nenabled=' + str(enabled).lower() + '\nartifact_root=' + json.dumps(str(path)) + '\n'
        self.base.config.write_text(text)
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        return path

    def test_normalized_body_heading_rename_substantive_edit_and_known_restore_keep_version_pins(self):
        original_bytes = self.declared(b'fixture:@artifact/source.md\nfixture:@code/policy.py#Policy')
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            RelateStore(connection).apply(self.base.settings, 'fixture:@artifact/guide.md#Guide',
                'fixture:@code/policy.py#Policy', captured_at='2026-10-10T12:00:00Z', settings_home=self.base.base)
            original = self.disk(connection)
            original_baselines = self.baselines(connection, original)
            branch = {key: row for key, row in self.current(connection).items() if key[0] == 'branch'}
            self.assertEqual(len(original), 3)
            self.fixture.source.write_bytes(b'# Source\nChanged source.\n')
            self.fixture.code.write_bytes(self.fixture.code.read_bytes().replace(b'return 1', b'return 2'))
            self.guide.write_bytes(original_bytes.replace(b'Original dependant.', b'Original   dependant.'))
            normalized = self.fixture.publish(connection)
            inherited = self.disk(connection)
            self.assertEqual(normalized.counts['relationPinsInherited'], 3)
            self.assertNotEqual(next(iter(inherited.values()))[1], next(iter(original.values()))[1])
            for key, baseline in self.baselines(connection, inherited).items():
                self.assertEqual(baseline.manifest.payload['pinnedHash'], original_baselines[key].manifest.payload['pinnedHash'])
            self.assertEqual(inherited[('asserted', 'fixture:@code/policy.py#Policy')][3]['reasons'], [])
            self.assertEqual(inherited[('declared', 'fixture:@code/policy.py#Policy')][3]['reasons'], ['related_changed'])
            self.guide.write_bytes(self.guide.read_bytes().replace(b'# Guide\n', b'# Renamed\n'))
            renamed = self.fixture.publish(connection)
            renamed_rows = self.disk(connection)
            self.assertEqual(renamed.counts['relationPinsInherited'], 3)
            for key, baseline in self.baselines(connection, renamed_rows).items():
                self.assertEqual(baseline.manifest.payload['pinnedHash'], original_baselines[key].manifest.payload['pinnedHash'])
                self.assertEqual(baseline.manifest.payload['dependant']['place']['name'], 'Renamed')
                self.assertEqual(baseline.manifest.payload['dependantId'], original_baselines[key].manifest.payload['dependantId'])
            self.guide.write_bytes(self.guide.read_bytes().replace(b'Original   dependant.', b'Substantive changed dependant.'))
            edited = self.fixture.publish(connection)
            edited_rows = self.disk(connection)
            self.assertEqual(edited.counts['relationPinsCaptured'], 3)
            for key, baseline in self.baselines(connection, edited_rows).items():
                self.assertEqual(edited_rows[key][3]['reasons'], [])
                if key[0] == 'declared':
                    self.assertNotEqual(baseline.manifest.payload['pinnedHash'], original_baselines[key].manifest.payload['pinnedHash'])
            self.guide.write_bytes(original_bytes)
            restored_result = self.fixture.publish(connection)
            restored = self.disk(connection)
            self.assertEqual((restored_result.counts['relationPinsCaptured'], restored_result.counts['relationPinsInherited']), (0, 0))
            self.assertEqual({key: (row[0], row[1], row[4], row[5]) for key, row in restored.items()},
                             {key: (row[0], row[1], row[4], row[5]) for key, row in original.items()})
            self.assertEqual({key: row for key, row in self.current(connection).items() if key[0] == 'branch'}, branch)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))

    def test_shared_exact_dependant_version_pins_separate_disk_and_branch_source_bytes(self):
        self.declared(b'fixture:@artifact/source.md')
        disk_source = b'# Source\nDifferent disk source.\n'
        self.fixture.source.write_bytes(disk_source)
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            rows = self.current(connection)
            self.assertEqual(len(rows), 2)
            disk = next(row for key, row in rows.items() if key[0] == 'disk')
            branch = next(row for key, row in rows.items() if key[0] == 'branch')
            self.assertEqual(disk[1], branch[1])
            self.assertNotEqual(disk[4:6], branch[4:6])
            disk_baseline = EvidenceStore(connection).read_baseline('fixture', disk[5])
            branch_baseline = EvidenceStore(connection).read_baseline('fixture', branch[5])
            self.assertNotEqual(disk_baseline.manifest.payload['pinnedHash'], branch_baseline.manifest.payload['pinnedHash'])
            self.assertIn(disk_source, [blob.source for blob in disk_baseline.snapshots])
            self.assertIn(self.fixture.source_bytes, [blob.source for blob in branch_baseline.snapshots])
            self.fixture.source.write_bytes(b'# Source\nChanged disk a second time.\n')
            self.fixture.publish(connection)
            changed = self.current(connection)
            self.assertEqual(next(row for key, row in changed.items() if key[0] == 'branch'), branch)
            now = next(row for key, row in changed.items() if key[0] == 'disk')
            self.assertEqual(now[4:6], disk[4:6])
            self.assertEqual(now[3]['reasons'], ['related_changed'])

    def test_exact_nul_and_all_declared_faults_report_readonly_without_dependency_authority(self):
        self.foreign(enabled=False)
        self.declared(b'bad\0ref\nforeign:source.md#Source\nunknown:source.md#Source\n'
            b'fixture:missing.md#Absent\nfixture:source.md#Source\n'
            b'fixture:@artifact/source.md#Source\n  fixture:@artifact/source.md#Source  ')
        (self.base.code / 'source.md').write_bytes(b'# Source\nColliding source.\n')
        with self.base.connect() as connection:
            self.fixture.publish(connection)
            before = store_state(connection)
            status, reply, diagnostics = invoke(self.base.config, ('refs', '--repo', 'fixture'))
            self.assertEqual((status, diagnostics), (0, ''))
            refs = reply['repositories'][0]['result']['refs']
            self.assertEqual(len(refs), 14)
            self.assertTrue(all(ref['kind'] == 'related' for ref in refs))
            self.assertEqual(sum(ref['parsedRef'] == 'bad\0ref' and ref['fault'] == 'not_a_ref' for ref in refs), 2)
            self.assertEqual({ref['fault'] for ref in refs},
                {None, 'not_a_ref', 'disabled_repository', 'unknown_repository', 'not_found', 'ambiguous_path'})
            resolved = [ref for ref in refs if ref['fault'] is None]
            self.assertEqual(len(resolved), 5)
            self.assertEqual(len({ref['id'] for ref in resolved}), 2)
            self.assertIn('  fixture:@artifact/source.md#Source  ', {ref['ref'] for ref in resolved})
            filtered_status, filtered, filtered_diagnostics = invoke(self.base.config,
                ('refs', '--repo', 'fixture', '--unresolved'))
            self.assertEqual((filtered_status, filtered_diagnostics), (0, ''))
            self.assertEqual(filtered['repositories'][0]['result']['count'], 9)
            self.assertEqual(store_state(connection), before)
            self.assertEqual(self.fixture.role(connection), 'authored')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))

    def test_disabled_repository_keeps_exact_relation_baseline_and_reenable_reuses_it(self):
        self.foreign(enabled=True)
        self.declared(b'foreign:@artifact/source.md#Source')
        with self.base.connect() as connection:
            self.fixture.publish(connection, repository='foreign')
            self.fixture.publish(connection)
            original = next(iter(self.disk(connection).values()))
            self.base.config.write_text(self.base.config.read_text().replace(
                '[repos.foreign]\nenabled=true', '[repos.foreign]\nenabled=false'))
            self.base.settings = load_settings(path=self.base.config, home=self.base.base)
            self.fixture.publish(connection)
            disabled = next(iter(self.disk(connection).values()))
            self.assertEqual((disabled[0], disabled[1], disabled[4], disabled[5]),
                             (original[0], original[1], original[4], original[5]))
            self.assertEqual((disabled[3]['resolution']['fault'], disabled[3]['sourceState'], disabled[3]['reasons']),
                             ('disabled_repository', 'ineligible', []))
            before = store_state(connection)
            status, reply, diagnostics = invoke(self.base.config, ('refs', '--repo', 'fixture', '--unresolved'))
            self.assertEqual((status, diagnostics), (0, ''))
            self.assertTrue(all(ref['fault'] == 'disabled_repository' for ref in reply['repositories'][0]['result']['refs']))
            self.assertEqual(store_state(connection), before)
            self.base.config.write_text(self.base.config.read_text().replace(
                '[repos.foreign]\nenabled=false', '[repos.foreign]\nenabled=true'))
            self.base.settings = load_settings(path=self.base.config, home=self.base.base)
            reenabled = self.fixture.publish(connection)
            current = next(iter(self.disk(connection).values()))
            self.assertEqual((current[0], current[1], current[4], current[5]),
                             (original[0], original[1], original[4], original[5]))
            self.assertEqual((current[3]['resolution']['fault'], current[3]['reasons']), (None, []))
            self.assertEqual(reenabled.counts['relationPinsCaptured'], 0)
            self.assertEqual(self.fixture.role(connection), 'authored')

    def test_missing_asserted_source_withdraws_on_edit_and_confirmation_preserving_history_and_sibling(self):
        original_bytes = self.declared(b'fixture:@artifact/source.md#Source')
        self.base.git('branch', 'history-first')
        with self.base.connect() as connection:
            def scope(name):
                return connection.execute("SELECT file_location,chunk_version FROM public.mycel_locations "
                    "WHERE kind='disk' AND metadata->>'name'=%s", (name,)).fetchone()

            def rows(version):
                return connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
                    e.manifest_hash,r.xmin::text FROM public.mycel_relations r
                    LEFT JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
                    WHERE r.repository='fixture' AND r.left_version=%s
                    AND r.state->'declarationLocation'->>'file'=%s ORDER BY r.id""",
                    (version, str(location))).fetchall()

            def missing_declared(version):
                current = rows(version)
                self.assertEqual(len(current), 1)
                self.assertEqual((current[0][3]['ownership'], current[0][3]['resolution']['fault'],
                                  current[0][4], current[0][5]), ('declared', 'missing_file', None, None))
                before = store_state(connection)
                status, reply, diagnostics = invoke(self.base.config,
                    ('refs', '--repo', 'fixture', '--unresolved'))
                self.assertEqual((status, diagnostics), (0, ''))
                visible = [ref for ref in reply['repositories'][0]['result']['refs']
                           if ref['chunk']['version'] == version and ref['location']['kind'] == 'disk']
                self.assertEqual(len(visible), 1)
                self.assertEqual((visible[0]['kind'], visible[0]['parsedRef'], visible[0]['fault'],
                    visible[0]['baselineStatus']), ('related', self.fixture.ref, 'not_found', 'baseline_missing'))
                self.assertEqual(store_state(connection), before)

            self.fixture.publish(connection)
            location, first_version = scope('Guide')
            RelateStore(connection).apply(self.base.settings, self.fixture.dependant, self.fixture.ref,
                settings_home=self.base.base, captured_at='2026-10-10T13:00:00Z')
            RelateStore(connection).apply(self.base.settings, 'fixture:@artifact/guide.md#Other',
                'fixture:@code/policy.py#Policy', settings_home=self.base.base,
                captured_at='2026-10-10T13:00:00Z')
            sibling_version = scope('Guide > Other')[1]
            sibling = rows(sibling_version)
            self.assertEqual(len(rows(first_version)), 2)
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            historical_first = rows(first_version)
            self.assertTrue(all(row[3]['reasons'] == ['source_removed'] for row in historical_first))
            self.guide.write_bytes(original_bytes.replace(b'Original dependant.', b'Edited dependant.'))
            self.fixture.publish(connection)
            edited_version = scope('Guide')[1]
            self.assertNotEqual(edited_version, first_version)
            missing_declared(edited_version)
            self.assertEqual(rows(first_version), historical_first)
            self.assertEqual(rows(sibling_version), sibling)

            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.base.commit()
            self.fixture.publish(connection)
            RelateStore(connection).apply(self.base.settings, self.fixture.dependant, self.fixture.ref,
                settings_home=self.base.base, captured_at='2026-10-10T13:10:00Z')
            self.assertEqual(len(rows(edited_version)), 2)
            self.guide.write_bytes(self.guide.read_bytes().replace(b'Edited dependant.', b'Edited   dependant.'))
            inherited = self.fixture.publish(connection)
            confirming_version = scope('Guide')[1]
            self.assertNotEqual(confirming_version, edited_version)
            self.assertEqual(inherited.counts['relationPinsInherited'], 2)
            self.fixture.source.unlink()
            self.fixture.publish(connection)
            historical_edited = rows(edited_version)
            current = rows(confirming_version)
            self.assertEqual(len(current), 2)
            self.assertTrue(all(row[4] is not None and row[3]['reasons'] == ['source_removed'] for row in current))
            inputs = DependencyCaptureInputs(connection, self.base.settings, settings_home=self.base.base)
            with self.fixture.guards(connection), atomic_transaction(connection):
                confirmed = RelationApplicationStore(connection).apply_in_transaction(self.base.settings,
                    str(location), confirming_version, mode='confirm', captured_at='2026-10-10T13:20:00Z',
                    reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None))
                inputs.verify()
            self.assertEqual((confirmed.captured, confirmed.released), (0, 2))
            missing_declared(confirming_version)
            self.assertEqual(rows(first_version), historical_first)
            self.assertEqual(rows(edited_version), historical_edited)
            self.assertEqual(rows(sibling_version), sibling)
            for historical in (historical_first, historical_edited):
                for row in historical:
                    baseline = EvidenceStore(connection).read_baseline('fixture', row[5])
                    self.assertIn(self.fixture.source_bytes, [snapshot.source for snapshot in baseline.snapshots])
            self.fixture.source.write_bytes(self.fixture.source_bytes)
            self.fixture.publish(connection)
            self.assertEqual([row[3]['ownership'] for row in rows(confirming_version)], ['declared'])
            self.assertEqual(rows(first_version), historical_first)
            self.assertEqual(rows(edited_version), historical_edited)
            self.assertEqual(rows(sibling_version), sibling)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
