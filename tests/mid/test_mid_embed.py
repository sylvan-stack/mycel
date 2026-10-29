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

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedCliTests.test_all_initial_capture_or_prepare_failures_have_one_closed_error
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: All initial capture or prepare failures have one closed error.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_all_initial_capture_or_prepare_failures_have_one_closed_error(self):
#         with self.dry_run_boundary() as (config, writer):
#             for phase in ("capture", "prepare"):
#                 with self.subTest(phase=phase):
#                     writer.prepare.reset_mock(side_effect=True)
#                     failure = MycelError("invalid_input", "Fictional initial retained-input failure.")
#                     writer.prepare.side_effect = failure if phase == "prepare" else None
#                     with patch("mycel._embed.retained_contexts", return_value=({}, frozenset()),
#                                side_effect=failure if phase == "capture" else None):
#                         status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--repo", "b", "--dry-run"))
#                     self.assertEqual((status, set(reply), diagnostic), (1, {"repositories"}, ""))
#                     self.assertEqual([row["repository"] for row in reply["repositories"]], ["a", "b"])
#                     for row in reply["repositories"]:
#                         self.assertEqual(set(row["error"]), {"code", "message"})
#                         self.assertEqual(row["error"]["code"], "invalid_input")
#                         self.assertIn("Fictional", row["error"]["message"])
#                     if phase == "capture":
#                         writer.prepare.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedCliTests.test_initial_capture_or_prepare_interruption_has_common_closed_reply_without_later_work
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Initial capture or prepare interruption has common closed reply without later work.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_initial_capture_or_prepare_interruption_has_common_closed_reply_without_later_work(self):
#         with self.dry_run_boundary() as (config, writer):
#             for phase in ("capture", "prepare"):
#                 with self.subTest(phase=phase):
#                     writer.prepare.reset_mock(side_effect=True)
#                     writer.prepare.side_effect = KeyboardInterrupt if phase == "prepare" else None
#                     with patch("mycel._embed.retained_contexts", return_value=({}, frozenset()),
#                                side_effect=KeyboardInterrupt if phase == "capture" else None) as capture:
#                         status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--repo", "b", "--dry-run"))
#                     self.assertEqual((status, reply, diagnostic),
#                         (2, {"error": {"code": "refused", "message": "Stopped by the caller."}}, "Stopped by the caller.\n"))
#                     self.assertEqual(capture.call_count, 1)
#                     self.assertEqual(writer.prepare.call_count, int(phase == "prepare"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedCliTests.test_completed_empty_or_failed_planning_preserves_started_and_mixed_replies
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Completed empty or failed planning preserves started and mixed replies.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_completed_empty_or_failed_planning_preserves_started_and_mixed_replies(self):
#         empty = PreparedRepository("b", True, (), EmbeddingCounts(), ())
#         version = RetainedVersion("b", "public-fixture-chunk", "document", {}, "1", "f" * 64,
#                                   "complete retained public fixture", {})
#         planning = PreparedRepository("b", True,
#             (VersionEmbedding(version, None, None, (), {"kind": "planning", "message": "Public local planning failure."}),),
#             EmbeddingCounts(failed_versions=1), ())
#         with self.dry_run_boundary() as (config, writer):
#             for prepared in (empty, planning):
#                 with self.subTest(failed=prepared.counts.failed_versions):
#                     writer.prepare.side_effect = [MycelError("invalid_input", "Fictional local capture fault."), prepared]
#                     with patch("mycel._embed.retained_contexts", return_value=({}, frozenset())):
#                         status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--repo", "b", "--dry-run"))
#                     self.assertEqual((status, diagnostic, set(reply["repositories"])), (1, "", {"a", "b"}))
#                     self.assertNotIn("error", reply)
#                     self.assertEqual(reply["repositories"]["a"]["error"]["code"], "invalid_input")
#                     self.assertEqual(reply["repositories"]["b"]["failed"], prepared.counts.failed_versions)
#                     writer.prepare.side_effect = None
#                     writer.prepare.return_value = prepared
#                     with patch("mycel._embed.retained_contexts", return_value=({}, frozenset())):
#                         status, reply, diagnostic = invoke(config, ("embed", "--repo", "b", "--dry-run"))
#                     self.assertEqual((status, diagnostic, set(reply["repositories"])),
#                                      (int(bool(prepared.counts.failed_versions)), "", {"b"}))
#                     self.assertEqual(reply["estimate"]["planningFailed"], prepared.counts.failed_versions)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedCliTests.test_help_options_and_invalid_or_ineligible_scope_precede_store_and_credentials
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Help options and invalid or ineligible scope precede store and credentials.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_help_options_and_invalid_or_ineligible_scope_precede_store_and_credentials(self):
#         with tempfile.TemporaryDirectory() as directory:
#             config = Path(directory) / "config.toml"
#             config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
#                               '[repos.disabled]\nenabled=false\n')
#             with patch("mycel._database.store_connection") as connected, \
#                     patch("mycel._credentials.Credentials.embedding_key") as key, \
#                     patch("mycel._voyage._https_request") as provider:
#                 for args in (("embed", "extra"), ("embed", "--repo", "a", "--all"),
#                              ("embed", "--dry"), ("embed", "--repo", "")):
#                     status, reply, diagnostic = invoke(config, args)
#                     self.assertEqual((status, reply["error"]["code"], diagnostic), (1, "invalid_input", ""))
#                 for name, code in (("unknown", "unknown_repository"), ("disabled", "refused")):
#                     status, reply, diagnostic = invoke(config, ("embed", "--repo", name))
#                     self.assertEqual((status, reply["repositories"][0]["error"]["code"], diagnostic), (1, code, ""))
#                 status, reply, diagnostic = invoke(config, ("embed", "--help"))
#                 self.assertEqual((status, diagnostic), (0, ""))
#                 self.assertTrue(reply["commands"][0]["available"])
#                 self.assertIn("--dry-run", reply["commands"][0]["options"])
#                 self.assertEqual(parse(("embed", "--retry-failed", "--repo", "a", "--dry-run")).arguments,
#                                  ("--dry-run", "--retry-failed"))
#                 connected.assert_not_called()
#                 key.assert_not_called()
#                 provider.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_public_named_repeated_cwd_organization_and_all_scopes_exclude_other_repositories
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Public named repeated cwd organization and all scopes exclude other repositories.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_named_repeated_cwd_organization_and_all_scopes_exclude_other_repositories(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             root = Path(directory)
#             config = self.configured(root, organization=True)
#             for name in ("a", "b", "disabled", "unknown", "removed"):
#                 seed_document(connection, name, name + ".md", "# " + name + "\n" + name + " private text\n")
#             with self.product(connection) as service:
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a", "--repo", "a", "--repo", "unknown", "--repo", "disabled"))
#                 self.assertEqual(status, 1)
#                 self.assertEqual(set(reply["repositories"]), {"a", "unknown", "disabled"})
#                 self.assertEqual(reply["repositories"]["a"]["sent"], 1)
#                 self.assertEqual(len(service.attempts), 1)
#                 self.assertTrue(all(text.startswith("a.md › a\n") for attempt in service.attempts for text in attempt.inputs))
#                 with patch("pathlib.Path.cwd", return_value=root / "org" / "b"):
#                     status, reply, _ = invoke(config, ("embed",))
#                 self.assertEqual((status, set(reply["repositories"])), (0, {"b"}))
#                 with patch("pathlib.Path.cwd", return_value=root / "org"):
#                     status, reply, _ = invoke(config, ("embed", "--dry-run"))
#                 self.assertEqual((status, set(reply["repositories"])), (0, {"a", "b"}))
#                 status, reply, _ = invoke(config, ("embed", "--all"))
#                 self.assertEqual((status, set(reply["repositories"]), len(service.attempts)), (0, {"a", "b"}, 2))
#                 with patch("pathlib.Path.cwd", return_value=root / "outside"):
#                     status, reply, _ = invoke(config, ("embed",))
#                 self.assertEqual((status, reply["error"]["code"]), (1, "unknown_repository"))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (2,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_dry_run_has_provisional_exact_selection_tokens_and_local_faults_with_no_mutation
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Dry run has provisional exact selection tokens and local faults with no mutation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_dry_run_has_provisional_exact_selection_tokens_and_local_faults_with_no_mutation(self):
#         local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=40,
#                     batch_token_cap=40, batch_input_cap=1))
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             _, _, _, versions = seed_document(connection, "a", "unicode.md", "# Parent\n## Child\n" + "雪 é 😀 complete tail\n" * 16)
#             seed_document(connection, "a", "bad\nplace.md", "# Invalid\nkeep every byte\n")
#             before = store_state(connection)
#             with self.product(connection, tokenizer=local, build=123), \
#                     patch("mycel._credentials.Credentials.require_embedding_key", side_effect=AssertionError("dry run key")), \
#                     patch("mycel._voyage._https_request", side_effect=AssertionError("dry run provider")), \
#                     patch("mycel._activity.MutationActivity.session", side_effect=AssertionError("dry run activity")):
#                 status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--dry-run"))
#                 repeated_status, repeated, _ = invoke(config, ("embed", "--repo", "a", "--dry-run"))
#             self.assertEqual((status, repeated_status, diagnostic), (1, 1, ""))
#             self.assertEqual(repeated, reply)
#             self.assertEqual(before, store_state(connection))
#             report = reply["repositories"]["a"]
#             self.assertEqual((report["pending"], report["failed"], report["embedded"]), (2, 1, 0))
#             self.assertEqual(reply["estimate"]["planningFailed"], 1)
#             selection = report["estimate"]["selection"]
#             self.assertEqual({entry["version"] for entry in selection}, {str(version) for version in versions})
#             child = next(entry for entry in selection if entry["placeLine"] == "unicode.md › Parent › Child")
#             self.assertGreater(len(child["parts"]), 1)
#             self.assertEqual(child["parts"][0]["startByte"], 0)
#             self.assertEqual(child["parts"][-1]["endByte"], len(("## Child\n" + "雪 é 😀 complete tail\n" * 16).encode()))
#             self.assertEqual(sum(part["tokens"] for entry in selection for part in entry["parts"]), reply["estimate"]["tokens"])
#             self.assertTrue(all(part["tokens"] > part["submittedTokens"] for entry in selection for part in entry["parts"]))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_interrupted_batches_retain_commits_and_resume_only_missing_parts_with_finite_inventory
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Interrupted batches retain commits and resume only missing parts with finite inventory.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_interrupted_batches_retain_commits_and_resume_only_missing_parts_with_finite_inventory(self):
#         local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=1))
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "first.md", "# First\ncomplete first\n", kind="branch", location="main")
#             seed_document(connection, "a", "second.md", "# Second\ncomplete second\n", kind="stash", location="stash-id")
#             sent = []
#             def transport(body, key, **kwargs):
#                 request = json.loads(body)
#                 if sent:
#                     raise KeyboardInterrupt
#                 sent.extend(request["input"])
#                 with self.store_fixture.backend.connection(self.store_fixture.database) as other:
#                     with operation_guard(other, "a", "pass"), atomic_transaction(other):
#                         seed_document(other, "a", "added.md", "# Added\nconcurrent exact version\n")
#                 return HTTPResult(200, json.dumps({"data": [{"index": 0, "embedding": [0.1] * 1024}],
#                                                     "model": "voyage-code-4", "usage": {"total_tokens": 1}}).encode(), {})
#             with self.product(connection, tokenizer=local, transport=transport, build=123):
#                 status, reply, diagnostic = invoke(config, ("embed", "--repo", "a"))
#             self.assertEqual((status, reply["stopped"], diagnostic), (2, "interrupted", ""))
#             report = reply["repositories"]["a"]
#             self.assertEqual((report["sent"], report["parts"]["sent"], report["pending"]), (1, 1, 2))
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(), (report, "stopped"))
#             with self.product(connection, tokenizer=local, build=123) as service:
#                 status, resumed, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, resumed["repositories"]["a"]["sent"]), (0, 2))
#                 self.assertEqual(len(service.attempts), 2)
#                 self.assertFalse(set(sent).intersection(text for attempt in service.attempts for text in attempt.inputs))
#                 status, empty, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, empty["repositories"]["a"]["parts"]["sent"]), (0, 0))
#                 self.assertEqual(len(service.attempts), 2)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity").fetchone(), (2,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_content_failures_keep_successful_parts_and_only_explicit_retry_selects_failures
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Content failures keep successful parts and only explicit retry selects failures.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_content_failures_keep_successful_parts_and_only_explicit_retry_selects_failures(self):
#         local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=32,
#                     batch_token_cap=32, batch_input_cap=1))
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "mixed.md", "# Mixed\n" + "good complete text\n" * 6 + "BAD particular part\n" + "good tail\n" * 4)
#             service = EmbeddingStandIn(local.counts, input_cap=32, batch_cap=32, inputs_cap=1)
#             service.reject_input = lambda text: "BAD" in text
#             with self.product(connection, tokenizer=local, service=service, build=123):
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a"))
#                 report = reply["repositories"]["a"]
#                 self.assertEqual((status, report["embedded"], report["pending"], report["failed"]), (1, 0, 0, 1))
#                 self.assertEqual(report["parts"]["failed"], 1)
#                 self.assertGreater(report["parts"]["embedded"], 1)
#                 vectors = connection.execute("SELECT plan_id,part_order,embedding::text FROM public.mycel_vectors ORDER BY part_order").fetchall()
#                 attempts = len(service.attempts)
#                 status, ordinary, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, len(service.attempts), ordinary["repositories"]["a"]["parts"]["sent"]), (1, attempts, 0))
#                 status, retry_plan, _ = invoke(config, ("embed", "--repo", "a", "--dry-run", "--retry-failed"))
#                 self.assertEqual(retry_plan["estimate"]["parts"], 1)
#                 service.reject_input = None
#                 status, retry, _ = invoke(config, ("embed", "--repo", "a", "--retry-failed"))
#                 self.assertEqual((status, retry["repositories"]["a"]["sent"], retry["repositories"]["a"]["parts"]["sent"]), (0, 1, 1))
#                 self.assertEqual(len(service.attempts), attempts + 1)
#                 self.assertTrue(set(vectors).issubset(connection.execute("SELECT plan_id,part_order,embedding::text FROM public.mycel_vectors").fetchall()))
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity ORDER BY id DESC LIMIT 1").fetchone(),
#                              (retry["repositories"]["a"], "done"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_changed_settings_stage_paid_response_block_publication_and_dry_run_never_drains
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Changed settings stage paid response block publication and dry run never drains.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_settings_stage_paid_response_block_publication_and_dry_run_never_drains(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "paid.md", "# Paid\ncomplete paid response\n")
#             enabled = config.read_text()
#             def transport(body, key, **kwargs):
#                 config.write_text(enabled.replace("[repos.a]\nenabled=true", "[repos.a]\nenabled=false"))
#                 return HTTPResult(200, json.dumps({"data": [{"index": 0, "embedding": [0.1] * 1024}],
#                                                     "model": "voyage-code-4", "usage": {"total_tokens": 1}}).encode(), {})
#             with self.product(connection, transport=transport, build=123):
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a"))
#             self.assertEqual((status, reply["stopped"]), (1, "gave_up"))
#             report = reply["repositories"]["a"]
#             self.assertEqual((report["parts"]["sent"], report["parts"]["deferred"], report["embedded"]), (0, 1, 0))
#             self.assertEqual((report["pending"], report["parts"]["pending"]), (0, 0))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone(), (1,))
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(), (report, "failed"))
#             config.write_text(enabled)
#             before = store_state(connection)
#             with self.product(connection, build=123) as service, \
#                     patch("mycel._credentials.Credentials.require_embedding_key", side_effect=AssertionError("no new paid request")):
#                 status, dry, _ = invoke(config, ("embed", "--repo", "a", "--dry-run"))
#                 self.assertEqual((status, dry["estimate"]["parts"]), (0, 0))
#                 self.assertEqual(before, store_state(connection))
#                 status, resumed, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, resumed["repositories"]["a"]["sent"], resumed["repositories"]["a"]["parts"]["sent"]), (0, 1, 1))
#                 self.assertFalse(service.attempts)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_retry_dry_run_reports_saved_planning_failure_as_failed_and_retry_selection_separately
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Retry dry run reports saved planning failure as failed and retry selection separately.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_retry_dry_run_reports_saved_planning_failure_as_failed_and_retry_selection_separately(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "bad\nplace.md", "# Retained\ncomplete exact text\n")
#             with self.product(connection) as service:
#                 status, failed, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, failed["repositories"]["a"]["failed"]), (1, 1))
#                 self.assertFalse(service.attempts)
#                 connection.execute("UPDATE public.mycel_files SET path='fixed.md' WHERE repository='a'")
#                 before = store_state(connection)
#                 status, dry, _ = invoke(config, ("embed", "--repo", "a", "--dry-run", "--retry-failed"))
#                 report = dry["repositories"]["a"]
#                 self.assertEqual((status, report["failed"], report["pending"], report["parts"]["pending"]), (1, 1, 0, 0))
#                 self.assertEqual((dry["estimate"]["versions"], dry["estimate"]["parts"]), (1, 1))
#                 self.assertEqual(before, store_state(connection))
#                 status, ordinary, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, ordinary["repositories"]["a"]["parts"]["sent"]), (1, 0))
#                 self.assertFalse(service.attempts)
#                 status, retried, _ = invoke(config, ("embed", "--repo", "a", "--retry-failed"))
#                 self.assertEqual((status, retried["repositories"]["a"]["sent"], len(service.attempts)), (0, 1, 1))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_unavailable_final_recount_and_later_local_fault_preserve_committed_prefix_and_other_results
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unavailable final recount and later local fault preserve committed prefix and other results.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unavailable_final_recount_and_later_local_fault_preserve_committed_prefix_and_other_results(self):
#         from mycel import _embed
#         local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=1))
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "first.md", "# First\ncomplete first\n")
#             seed_document(connection, "a", "second.md", "# Second\ncomplete second\n")
#             seed_document(connection, "b", "other.md", "# Other\ncomplete other\n")
#             service = EmbeddingStandIn(local.counts, inputs_cap=1)
#             service.fail_attempt(2, "authentication")
#             original = _embed.retained_contexts
#             reads = {}
#             def broken_recount(current, repository):
#                 reads[repository] = reads.get(repository, 0) + 1
#                 if repository == "a" and reads[repository] > 1:
#                     raise MycelError("store_unavailable", "Fictional later store-read failure.")
#                 if repository == "b":
#                     raise MycelError("invalid_input", "Fictional repository-local retained receipt fault.")
#                 return original(current, repository)
#             with self.product(connection, tokenizer=local, service=service, build=123), \
#                     patch.object(_embed, "retained_contexts", broken_recount):
#                 status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--repo", "b"))
#             self.assertEqual((status, diagnostic, set(reply["repositories"])), (1, "", {"a", "b"}))
#             report = reply["repositories"]["a"]
#             self.assertEqual((report["sent"], report["parts"]["sent"], report["embedded"], report["pending"]), (1, 1, 1, 1))
#             self.assertEqual(report["countsState"], "committed_prefix")
#             self.assertEqual(report["error"]["code"], "store_unavailable")
#             self.assertEqual(reply["repositories"]["b"]["error"]["code"], "invalid_input")
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(), (report, "failed"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_interruption_during_later_repository_capture_keeps_first_reply_and_exact_stopped_activity
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Interruption during later repository capture keeps first reply and exact stopped activity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_interruption_during_later_repository_capture_keeps_first_reply_and_exact_stopped_activity(self):
#         from mycel import _embed
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "first.md", "# First\ncomplete first\n")
#             seed_document(connection, "b", "second.md", "# Second\ncomplete second\n")
#             original = _embed.retained_contexts
#             def interrupt_capture(current, repository):
#                 if repository == "b":
#                     raise KeyboardInterrupt
#                 return original(current, repository)
#             with self.product(connection, build=123) as service, patch.object(_embed, "retained_contexts", interrupt_capture):
#                 status, reply, diagnostic = invoke(config, ("embed", "--repo", "a", "--repo", "b"))
#             self.assertEqual((status, reply["stopped"], diagnostic, set(reply["repositories"])), (2, "interrupted", "", {"a", "b"}))
#             self.assertEqual((reply["repositories"]["a"]["sent"], reply["repositories"]["a"]["parts"]["sent"]), (1, 1))
#             self.assertEqual(reply["repositories"]["b"]["error"]["code"], "refused")
#             self.assertEqual(len(service.attempts), 1)
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(),
#                              (reply["repositories"]["a"], "stopped"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_disable_during_credential_acquisition_prevents_the_first_provider_send
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Disable during credential acquisition prevents the first provider send.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disable_during_credential_acquisition_prevents_the_first_provider_send(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "guard.md", "# Guard\ncomplete retained text\n")
#             def key():
#                 config.write_text(config.read_text().replace("[repos.a]\nenabled=true", "[repos.a]\nenabled=false"))
#                 return Secret("public-fixture-key")
#             with self.product(connection, build=123) as service, \
#                     patch("mycel._credentials.Credentials.require_embedding_key", side_effect=key):
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a"))
#             report = reply["repositories"]["a"]
#             self.assertEqual((status, report["parts"]["sent"], report["parts"]["pending"]), (1, 0, 0))
#             self.assertFalse(service.attempts)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone(), (0,))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_settings_change_after_audit_rolls_back_vectors_and_preserves_original_receipt
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Settings change after audit rolls back vectors and preserves original receipt.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_settings_change_after_audit_rolls_back_vectors_and_preserves_original_receipt(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "audit.md", "# Audit\nexact guarded result\n")
#             original = MutationActivity.record_in_transaction
#             def change_settings(audit, repository, kind, result):
#                 original(audit, repository, kind, result)
#                 if result.counts.get("sent", 0):
#                     config.write_text(config.read_text().replace("[repos.a]\nenabled=true", "[repos.a]\nenabled=false"))
#             with self.product(connection, build=123), patch.object(MutationActivity, "record_in_transaction", change_settings):
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a"))
#             report = reply["repositories"]["a"]
#             self.assertEqual((status, report["parts"]["sent"], report["parts"]["deferred"]), (1, 0, 1))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone(), (1,))
#             self.assertEqual(connection.execute("SELECT counts,outcome FROM public.mycel_activity").fetchone(), (report, "failed"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_embed.py::EmbedStoreTests.test_busy_pass_keeps_receipt_and_embed_lock_refuses_duplicate_sends
# Reason: Narrower case removed from this family after retaining test_lost_connection_after_first_batch_keeps_progress_reply_and_committed_vector, test_publication_audit_failure_rolls_back_vectors_preserving_paid_receipt_and_safe_progress. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Busy pass keeps receipt and embed lock refuses duplicate sends.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_embed.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_busy_pass_keeps_receipt_and_embed_lock_refuses_duplicate_sends(self):
#         with tempfile.TemporaryDirectory() as directory, self.store_fixture.backend.connection(self.store_fixture.database) as connection, \
#                 self.store_fixture.backend.connection(self.store_fixture.database) as blocker:
#             config = self.configured(Path(directory))
#             seed_document(connection, "a", "busy.md", "# Busy\nexact paid text\n")
#             def transport(body, key, **kwargs):
#                 lock = operation_guard(blocker, "a", "pass")
#                 lock.__enter__()
#                 self.addCleanup(lock.__exit__, None, None, None)
#                 return HTTPResult(200, json.dumps({"data": [{"index": 0, "embedding": [0.1] * 1024}],
#                                                     "model": "voyage-code-4", "usage": {"total_tokens": 1}}).encode(), {})
#             with self.product(connection, transport=transport):
#                 status, reply, _ = invoke(config, ("embed", "--repo", "a"))
#             self.assertEqual((status, reply["repositories"]["a"]["parts"]["deferred"]), (1, 1))
#             # Release the pass before the product connection is closed.
#             self.doCleanups()
#             with operation_guard(blocker, "a", "embed"), self.product(connection) as service:
#                 status, refused, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, refused["repositories"]["a"]["error"]["code"]), (1, "busy"))
#                 self.assertFalse(service.attempts)
#             with self.product(connection) as service:
#                 status, resumed, _ = invoke(config, ("embed", "--repo", "a"))
#                 self.assertEqual((status, resumed["repositories"]["a"]["parts"]["sent"]), (0, 1))
#                 self.assertFalse(service.attempts)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
