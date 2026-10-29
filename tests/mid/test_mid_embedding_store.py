"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_embedding_store as _support
from test_embedding_store import (MycelError ,operation_guard ,patch ,psycopg ,store)


class EmbeddingStoreAcceptanceTests(_support.EmbeddingStoreAcceptanceTests):


# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume
    def test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume(self):
        class FaultingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.calls = 0
                self.inject = True

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, params=None):
                if sql.startswith("INSERT INTO public.mycel_vectors"):
                    self.calls += 1
                    if self.inject and self.calls == 2:
                        raise psycopg.ProgrammingError("fictional secret native failure")
                return self.connection.execute(sql, params)

        with self.connect() as connection:
            self.seed(connection, "first"); self.seed(connection, "second")
            proxy = FaultingConnection(connection)
            writer = store.EmbeddingStore(proxy, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                writes = self.writes(self.prepare(writer, persist=True))
                with self.assertRaises(MycelError) as failure:
                    writer.commit(writes)
                self.assertEqual(failure.exception.code, "store_unavailable")
                self.assertNotIn("secret", str(failure.exception))
                # The first INSERT executed against PostgreSQL, then the
                # product transaction rolled it back when the second failed.
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 1)
                proxy.inject = False
                resumed = writer.drain("fixture")
                self.assertEqual(set(resumed.retained), {w.part for w in writes})
                self.assertEqual(self.prepare(writer).counts.embedded_versions, 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume


# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture
    def test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture(self):
        with self.connect() as connection, self.connect() as passer:
            _, first = self.seed(connection, "first captured input")
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            original_save = writer._save
            def interleave(repository, replacements):
                original_save(repository, replacements)
                with operation_guard(passer, "fixture", "pass"):
                    self.seed(passer, "introduced after capture was saved")
            with writer.session("fixture"):
                with patch.object(writer, "_save", side_effect=interleave):
                    captured = self.prepare(writer, persist=True)
                self.assertEqual({v.version.version for v in captured.versions}, {str(first)})
                self.assertTrue(all(v.id is not None for v in captured.versions))
                receipt = writer.commit(self.writes(captured))
                self.assertEqual(len(receipt.retained), 1)
                provisional = self.prepare(writer)
                self.assertEqual((provisional.counts.embedded_versions, provisional.counts.pending_versions), (1, 1))
                self.assertTrue(any(v.id is None for v in provisional.versions))
                next_pass = self.prepare(writer, persist=True)
                self.assertTrue(all(v.id is not None for v in next_pass.versions))
                writer.commit(self.writes(next_pass))
                self.assertEqual(self.prepare(writer).counts.embedded_versions, 2)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture
