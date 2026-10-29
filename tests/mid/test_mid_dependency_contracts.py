"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_dependency_contracts as _support
from test_dependency_contracts import (EvidenceStore)


class DependencyContractStoreTests(_support.DependencyContractStoreTests):


# TEST-TIER-BEGIN tests/test_dependency_contracts.py::DependencyContractStoreTests.test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline
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
# TEST-TIER-END tests/test_dependency_contracts.py::DependencyContractStoreTests.test_actual_branch_switch_restores_disk_pin_and_stash_keeps_own_exact_baseline
