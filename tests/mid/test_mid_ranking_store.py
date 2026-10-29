"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_ranking_store as _support
from test_ranking_store import (StoreCandidates ,graph_for ,ingest_fixtures)


class RankingStoreTests(_support.RankingStoreTests):


# TEST-TIER-BEGIN tests/test_ranking_store.py::RankingStoreTests.test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source
    def test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source(self):
        base = ingest_fixtures.IngestStoreTests()
        base.store_fixture = self.store_fixture
        base.setUp()
        self.addCleanup(base.doCleanups)
        code = base.base.code / 'work.py'
        code.write_text('def work():\n    return 1\n')
        (base.base.artifact / 'guide.md').write_text('---\nrole: authored\n---\n# Guide\nHow work happens.\n'
            '<!-- sources:\nfixture:@code/work.py#work\n-->\n')
        base.base.commit()
        self.assertEqual(base.invoke('--repo', 'fixture')[0], 0)
        code.unlink()
        status, reply = base.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 0, reply)
        with base.base.connect() as connection:
            rows = connection.execute("SELECT dependant_version,state FROM public.mycel_dependencies WHERE kind='declared'").fetchall()
            self.assertEqual(len({version for version,state in rows}), 1)
            self.assertEqual({state['declarationLocation']['kind'] for version,state in rows}, {'disk','branch'})
            with StoreCandidates(connection, base.base.settings).snapshot(('fixture',)) as snapshot:
                self.assertEqual(graph_for(snapshot, 'fixture').citations, ())
                self.assertEqual(snapshot.ranked('how does work happen', self.query, only='code')[0].results, ())
# TEST-TIER-END tests/test_ranking_store.py::RankingStoreTests.test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source
