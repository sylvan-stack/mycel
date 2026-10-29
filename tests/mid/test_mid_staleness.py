"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_staleness as _support
from test_staleness import (MycelError ,checked_store ,operation_guard)


class MechanicalStalenessStoreTests(_support.MechanicalStalenessStoreTests):


# TEST-TIER-BEGIN tests/test_staleness.py::MechanicalStalenessStoreTests.test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries
    def test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries(self):
        from psycopg.types.json import Jsonb
        from mycel._derive import DeriveStore
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            DeriveStore(connection).apply(self.settings, 'unrelated:@artifact/answer.md#Other',
                'fixture:@artifact/source.md#Source', captured_at='2026-10-09T21:00:00Z')
            row = connection.execute("SELECT * FROM public.mycel_dependencies WHERE repository='unrelated'").fetchone()
            connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (row[0],))
            self.source.unlink()
            inserted = False
            def publish_new_pin(owner, counts):
                nonlocal inserted
                if owner == 'fixture' and not inserted:
                    peer.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                                 (*row[:6], Jsonb(row[6]), row[7]))
                    inserted = True
                return counts
            with checked_store(peer), operation_guard(peer, 'unrelated', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, producer=False, reply_counts=publish_new_pin)
                self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), [])
            retry = self.publish(connection, producer=False)
            self.assertEqual(retry.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection, 'unrelated')[0][4]['kind'], 'source_removed')
# TEST-TIER-END tests/test_staleness.py::MechanicalStalenessStoreTests.test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries
