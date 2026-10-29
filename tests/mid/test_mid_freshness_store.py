"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_freshness_store as _support
from test_freshness_store import (Deadline ,DeadlineConnection ,DeadlineExceeded ,FreshnessScope ,StoreCandidates ,StoreFreshnessAdapter ,deadline_guard ,patch ,psycopg ,run_freshness ,time)


class FreshnessStoreTests(_support.FreshnessStoreTests):


# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source
    def test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            (self.folders['later'] / 'new.md').write_bytes(self.document('New', 'outside:@artifact/deep.md#Deep'))
            (self.folders['later'] / 'unrelated.md').write_bytes(self.document('Unrelated',
                'disabled:@artifact/absent.md#Disabled', 'shared:@artifact/selected.md#Selected'))
            (self.folders['outside'] / 'deep.md').write_bytes(b'# Deep\nA newly discovered governing definition.\n')
            self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary',
                                                   'later:@artifact/new.md#New'))
            adapter = StoreFreshnessAdapter(connection, self.settings)
            actual, order = adapter.refresh, []

            def record(name, *, deadline):
                outcome = actual(name, deadline=deadline)
                order.append((name, outcome.status))
                return outcome

            with patch.object(adapter, 'refresh', record):
                result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, (result, order))
            self.assertIn(('later', 'pending'), order)
            self.assertLess(order.index(('outside', 'done')), order.index(('later', 'done')))
            self.assertLess(order.index(('later', 'done')), order.index(('contract', 'done')))
            self.assertEqual({item.repository for item in result.repositories if item.scan_required},
                             {'fixture', 'contract', 'glossary', 'later', 'outside'})
            self.assertEqual(result.faults, ())
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                self.assertEqual({chunk.repository for chunk in snapshot.candidates('Deep', only='docs')[0].chunks}, {'fixture'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source


# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable
    def test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable(self):
        with self.base.connect() as connection:
            proxy = DeadlineConnection(connection)
            before = connection.execute('SHOW statement_timeout').fetchone()
            deadline, started = Deadline.after(0.35), time.monotonic()
            with deadline_guard(deadline):
                proxy.execute('SELECT pg_catalog.pg_sleep(0.18)').fetchone()
                with self.assertRaises((psycopg.errors.QueryCanceled, DeadlineExceeded)):
                    proxy.execute('SELECT pg_catalog.pg_sleep(0.4)').fetchone()
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(connection.execute('SHOW statement_timeout').fetchone(), before)
            self.assertEqual(connection.execute('SELECT 1').fetchone(), (1,))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable
