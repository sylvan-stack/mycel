"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_activity_history as _support
from test_activity_history import (locks ,patch)


class ActivityHistoryStoreTests(_support.ActivityHistoryStoreTests):


# TEST-TIER-BEGIN tests/test_activity_history.py::ActivityHistoryStoreTests.test_running_unfinished_and_over_limit_reads_never_prune_or_write_tables_or_sequences
    def test_running_unfinished_and_over_limit_reads_never_prune_or_write_tables_or_sequences(self):
        with self.history.connect() as connection, self.history.connect() as observer:
            self.history.repositories(connection, 'fixture')
            self.history.seed(connection, 'fixture', 1001)
            dead, = self.history.seed(connection, 'fixture', 1, open_entry=True,
                                      at='2002-01-01T00:00:00Z')
            with locks.invocation_guard(connection) as invocation:
                live, = self.history.seed(connection, 'fixture', 1, open_entry=True, invocation=invocation,
                                          at='2003-01-01T00:00:00Z')
                before = self.history.state(observer, sequences=True)
                with patch('mycel._activity_retention.ActivityRetentionStore.prune_in_transaction',
                           side_effect=AssertionError('pruning')), \
                        patch('mycel._activity.MutationActivity.session', side_effect=AssertionError('activity')), \
                        patch('mycel._capture._Capture.capture', side_effect=AssertionError('freshness')), \
                        patch('mycel._embed.embed', side_effect=AssertionError('embedding')), \
                        patch('mycel._credentials.Credentials.embedding_key', side_effect=AssertionError('model credentials')):
                    listed = self.read(observer)
                    self.assertEqual([(row['id'], row['outcome']) for row in listed['entries'][:2]],
                                     [(str(live), 'running'), (str(dead), 'unfinished')])
                    live_detail, = self.read(observer, names=(), identifier=live)['entries']
                    self.assertEqual(live_detail['outcome'], 'running')
                    self.assertNotIn('endedAt', live_detail)
                    self.assertEqual(self.history.state(observer, sequences=True), before)
            # The lock's disappearance changes the computed reply only.
            before = self.history.state(observer, sequences=True)
            live_detail, = self.read(observer, names=(), identifier=live)['entries']
            self.assertEqual(live_detail['outcome'], 'unfinished')
            self.assertNotIn('endedAt', live_detail)
            self.assertEqual(len(self.history.ids(observer, 'fixture')), 1003)
            self.assertEqual(self.history.state(observer, sequences=True), before)
# TEST-TIER-END tests/test_activity_history.py::ActivityHistoryStoreTests.test_running_unfinished_and_over_limit_reads_never_prune_or_write_tables_or_sequences
