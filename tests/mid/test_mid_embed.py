"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_embed as _support
from test_embed import (EmbeddingStandIn ,HTTPResult ,MutationActivity ,MycelError ,Path ,ProviderFailure ,invoke ,json ,patch ,replace ,seed_document ,tempfile)


class EmbedStoreTests(_support.EmbedStoreTests):


# TEST-TIER-BEGIN tests/test_embed.py::EmbedStoreTests.test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector
    def test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector(self):
        local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=1))
        with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            config = self.configured(Path(directory))
            seed_document(connection, "a", "first.md", "# First\ncomplete first\n")
            seed_document(connection, "a", "second.md", "# Second\ncomplete second\n")
            service = EmbeddingStandIn(local.counts, inputs_cap=1)
            def transport(body, key, **kwargs):
                if service.attempts:
                    connection.close()
                    raise ProviderFailure("connection")
                return HTTPResult(200, json.dumps(service.request(json.loads(body))).encode(), {})
            with self.product(connection, tokenizer=local, transport=transport, build=123):
                status, reply, diagnostic = invoke(config, ("embed", "--repo", "a"))
            self.assertEqual((status, diagnostic), (1, ""))
            self.assertEqual((reply["repositories"]["a"]["sent"], reply["repositories"]["a"]["parts"]["sent"]), (1, 1))
            self.assertEqual(reply["repositories"]["a"]["countsState"], "committed_prefix")
            with self.store_fixture.backend.connection(self.store_fixture.database) as reopened:
                self.assertEqual(reopened.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (1,))
# TEST-TIER-END tests/test_embed.py::EmbedStoreTests.test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector


# TEST-TIER-BEGIN tests/test_embed.py::EmbedStoreTests.test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress
    def test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress(self):
        with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            config = self.configured(Path(directory))
            seed_document(connection, "a", "audit-fail.md", "# Audit\ncomplete retained text\n")
            original = MutationActivity.record_in_transaction
            def fail_publish(audit, repository, kind, result):
                if result.counts.get("sent", 0):
                    raise MycelError("internal", "Fictional publication audit failure.")
                return original(audit, repository, kind, result)
            with self.product(connection, build=123), patch.object(MutationActivity, "record_in_transaction", fail_publish):
                status, reply, _ = invoke(config, ("embed", "--repo", "a"))
            report = reply["repositories"]["a"]
            self.assertEqual((status, report["parts"]["sent"], report["parts"]["deferred"], report["error"]["code"]), (1, 0, 1, "internal"))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone(), (1,))
            self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(), (report, "failed"))
# TEST-TIER-END tests/test_embed.py::EmbedStoreTests.test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress
