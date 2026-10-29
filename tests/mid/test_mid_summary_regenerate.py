"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_regenerate as _support


class SummaryRegenerationStoreTests(_support.SummaryRegenerationStoreTests):


# TEST-TIER-BEGIN tests/test_summary_regenerate.py::SummaryRegenerationStoreTests.test_member_restored_during_memberless_deletion_preserves_stale_original
    def test_member_restored_during_memberless_deletion_preserves_stale_original(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summary = self.snapshot(connection)[0][0]
            sources = [(self.base.artifact / pin.place.path, (self.base.artifact / pin.place.path).read_bytes())
                       for pin in summary.state.members]
            for path, _ in sources:
                path.unlink()
            self.base.commit()
            self.base.apply(connection)
            old = self.current(connection)
            result = self.regenerate(connection, before_publish=lambda: sources[0][0].write_bytes(sources[0][1]))
            self.assertEqual((result.status, result.value["deleted"], result.value["written"]), (1, 0, 0))
            self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
            self.assertEqual(self.current(connection), old)
            self.no_leases(connection)
# TEST-TIER-END tests/test_summary_regenerate.py::SummaryRegenerationStoreTests.test_member_restored_during_memberless_deletion_preserves_stale_original

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_only_stale_nodes_retain_places_and_exact_membership_with_lower_response_feeding_parent
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Only stale nodes retain places and exact membership with lower response feeding parent.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_only_stale_nodes_retain_places_and_exact_membership_with_lower_response_feeding_parent(self):
#         with self.base.connect() as connection, self.base.connect() as reader:
#             self.prepare(connection, tree=True)
#             summaries, _, _ = self.snapshot(connection)
#             leaf, parent = summaries[0], summaries[-1]
#             self.change(connection, leaf)
#             (self.base.artifact / "new.md").write_text("# New\nA section added since the build.\n")
#             self.base.apply(connection)
#             old = self.current(connection)
#             observations = []
#
#             def during(number, requests):
#                 visible = self.current(reader)
#                 observations.append(visible)
#                 if number == 1:
#                     self.assertEqual(visible, old)
#                 else:
#                     self.assertIn(b"Whole regenerated response 1", requests[0])
#                     self.assertNotEqual(visible[leaf.member.chunk.identifier][1], old[leaf.member.chunk.identifier][1])
#                     self.assertEqual(visible[parent.member.chunk.identifier], old[parent.member.chunk.identifier])
#
#             writer = SequentialWriter(callback=during)
#             result = self.regenerate(connection, writer=writer)
#             self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 2, 0))
#             self.assertFalse(result.value["replaced"])
#             self.assertEqual((result.value["failed"], result.value["blocked"], result.value["cut"]), ([], [], []))
#             current = self.current(connection)
#             self.assertEqual(set(current), set(old))
#             for summary in summaries:
#                 identifier = summary.member.chunk.identifier
#                 self.assertEqual(current[identifier][3], old[identifier][3])
#                 self.assertEqual([item["chunkId"] for item in current[identifier][4]["members"]],
#                                  [pin.chunk_id for pin in summary.state.members])
#                 if summary not in (leaf, parent):
#                     self.assertEqual(current[identifier], old[identifier])
#             for summary in (leaf, parent):
#                 row = current[summary.member.chunk.identifier]
#                 self.assertNotEqual(row[1], summary.member.chunk.version)
#                 pins = self.generated(connection, row[1])
#                 self.assertEqual(len(pins), len(summary.state.members))
#                 for pin in pins:
#                     capture, member = generated_capture(connection, pin)
#                     self.assertEqual(capture.manifest.payload["response"]["hash"],
#                         connection.execute("SELECT snapshot_hash FROM public.mycel_chunk_versions WHERE id=%s", (row[1],)).fetchone()[0])
#                     self.assertEqual(connection.execute("SELECT source_version FROM public.mycel_edges WHERE dependency=%s", (pin[0],)).fetchone(), (member["version"],))
#                 self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p ON p.id=v.plan_id WHERE p.chunk_version=%s", (row[1],)).fetchone(), (1,))
#             self.assertTrue(all(level["stale"] == 0 for level in self.snapshot(connection)[1]["levels"]))
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_failed_leaf_remains_stale_parent_is_blocked_and_independent_successes_remain
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Failed leaf remains stale parent is blocked and independent successes remain.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_failed_leaf_remains_stale_parent_is_blocked_and_independent_successes_remain(self):
#         with self.base.connect() as connection:
#             self.prepare(connection, tree=True)
#             summaries, _, _ = self.snapshot(connection)
#             self.change(connection, summaries[0])
#             self.change(connection, summaries[1])
#             old = self.current(connection)
#             writer = SequentialWriter(fail_at=1)
#             result = self.regenerate(connection, writer=writer)
#             self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (1, 1, "failed"))
#             self.assertEqual(result.value["failed"], [{"summary": summaries[0].member.place.address, "reason": "nonzero_exit"}])
#             self.assertEqual(result.value["blocked"][0]["summary"]["address"], summaries[-1].member.place.address)
#             self.assertEqual(result.value["blocked"][0]["reason"], "stale_member")
#             self.assertEqual(len(writer.requests), 2)
#             now = self.current(connection)
#             self.assertEqual(now[summaries[0].member.chunk.identifier], old[summaries[0].member.chunk.identifier])
#             self.assertEqual(now[summaries[-1].member.chunk.identifier], old[summaries[-1].member.chunk.identifier])
#             self.assertNotEqual(now[summaries[1].member.chunk.identifier][1], old[summaries[1].member.chunk.identifier][1])
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_missing_members_are_dropped_and_memberless_nodes_deleted_with_owned_evidence_cleanup
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Missing members are dropped and memberless nodes deleted with owned evidence cleanup.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_members_are_dropped_and_memberless_nodes_deleted_with_owned_evidence_cleanup(self):
#         with self.base.connect() as connection:
#             self.prepare(connection, independent=True)
#             summaries, _, _ = self.snapshot(connection)
#             first, second = summaries[:2]
#             removed = first.state.members + second.state.members[:1]
#             for pin in removed:
#                 (self.base.artifact / pin.place.path).unlink()
#             self.base.commit()
#             self.base.apply(connection)
#             owners = [row[7] for row in self.generated(connection, first.member.chunk.version)]
#             original = self.current(connection)
#             writer = SequentialWriter()
#             result = self.regenerate(connection, writer=writer)
#             self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 1))
#             self.assertEqual(len(writer.requests), 1)
#             now = self.current(connection)
#             self.assertNotIn(first.member.chunk.identifier, now)
#             self.assertEqual([pin["chunkId"] for pin in now[second.member.chunk.identifier][4]["members"]],
#                              [pin.chunk_id for pin in second.state.members[1:]])
#             self.assertEqual(now[summaries[2].member.chunk.identifier], original[summaries[2].member.chunk.identifier])
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE id=ANY(%s::uuid[])", (owners,)).fetchone(), (0,))
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE dependant_version=%s", (first.member.chunk.version,)).fetchone(), (0,))
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_embedding_failure_and_exact_input_change_preserve_stale_original
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Embedding failure and exact input change preserve stale original.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_embedding_failure_and_exact_input_change_preserve_stale_original(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             summary = self.snapshot(connection)[0][0]
#             path = self.change(connection, summary)
#             old = self.current(connection)
#             result = self.regenerate(connection, client=builds.LocalEmbedding(fail=True))
#             self.assertEqual(result.value["failed"], [{"summary": summary.member.place.address, "reason": "embedding_failed"}])
#             self.assertEqual(self.current(connection), old)
#             original = path.read_bytes()
#             result = self.regenerate(connection, before_publish=lambda: path.write_bytes(b"# Changed\nLate edit.\n"))
#             self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
#             self.assertEqual(self.current(connection), old)
#             path.write_bytes(original)
#             self.assertEqual(self.snapshot(connection)[1]["levels"][0]["stale"], 1)
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_fixed_membership_that_grew_past_request_budget_is_blocked_without_calls_or_new_places
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Fixed membership that grew past request budget is blocked without calls or new places.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fixed_membership_that_grew_past_request_budget_is_blocked_without_calls_or_new_places(self):
#         with self.base.connect() as connection:
#             self.prepare(connection)
#             summary = self.snapshot(connection)[0][0]
#             self.change(connection, summary, text="x" * 49_000)
#             old = self.current(connection)
#             plan = self.snapshot(connection)[2]
#             detail = plan["work"][0]
#             self.assertEqual(detail["action"], "write")
#             self.assertGreater(detail["boundedRequestsForCurrentText"], 1)
#             self.assertEqual((detail["requestFits"], detail["requiresBuild"]), (False, True))
#             writer = SequentialWriter(callback=lambda *_: self.fail("oversized fixed group called writer"))
#             client = builds.LocalEmbedding(lambda _: self.fail("oversized fixed group called embedding"))
#             result = self.regenerate(connection, writer=writer, client=client)
#             self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (1, 0, "inputs_changed"))
#             self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
#             self.assertEqual(self.current(connection), old)
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_single_surviving_oversized_member_keeps_place_reports_cut_and_publishes_all_vector_parts
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Single surviving oversized member keeps place reports cut and publishes all vector parts.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_single_surviving_oversized_member_keeps_place_reports_cut_and_publishes_all_vector_parts(self):
#         with self.base.connect() as connection:
#             self.prepare(connection, independent=True)
#             summary = self.snapshot(connection)[0][0]
#             for pin in summary.state.members[1:]:
#                 (self.base.artifact / pin.place.path).unlink()
#             pin = summary.state.members[0]
#             path = self.base.artifact / pin.place.path
#             path.write_text(path.read_text().splitlines()[0] + "\n" + "雪🙂" * 26_000)
#             self.base.commit()
#             self.base.apply(connection)
#             tokenizer = replace(self.fixture.tokenizer,
#                                 catalog=replace(self.fixture.tokenizer.catalog, input_token_cap=60))
#             writer = builds.LocalWriter(response=("Whole response line.\n" * 80).encode())
#             result = self.regenerate(connection, writer=writer, tokenizer=tokenizer)
#             self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 0))
#             self.assertEqual(result.value["cut"][0]["address"], pin.place.address)
#             self.assertEqual(len(writer.requests[0].decode()), 48_000)
#             self.assertIn(b"[Mycel: source text cut at request limit]", writer.requests[0])
#             row = self.current(connection)[summary.member.chunk.identifier]
#             self.assertEqual(row[3], summary.member.place.address)
#             self.assertEqual([item["chunkId"] for item in row[4]["members"]], [pin.chunk_id])
#             capture, member = generated_capture(connection, self.generated(connection, row[1])[0])
#             self.assertTrue(member["cut"])
#             self.assertGreater(member["source"]["bytes"], member["sent"]["bytes"])
#             vectors = connection.execute("SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p "
#                 "ON p.id=v.plan_id WHERE p.chunk_version=%s", (row[1],)).fetchone()[0]
#             self.assertGreater(vectors, 1)
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_recreated_original_document_place_rejoins_new_identity_in_both_plan_and_actual_regeneration
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Recreated original document place rejoins new identity in both plan and actual regeneration.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recreated_original_document_place_rejoins_new_identity_in_both_plan_and_actual_regeneration(self):
#         with self.base.connect() as connection:
#             self.prepare(connection, independent=True)
#             summary = self.snapshot(connection)[0][0]
#             pin = summary.state.members[0]
#             path = self.base.artifact / pin.place.path
#             original = path.read_text()
#             path.unlink()
#             self.base.commit()
#             self.base.apply(connection)
#             path.write_text(original.splitlines()[0] + "\nRecreated current source at the retained place.\n")
#             self.base.commit()
#             self.base.apply(connection)
#             from mycel._resolver import SourceResolver
#             replacement = SourceResolver.from_store(connection, self.base.settings).resolve(pin.place.address,
#                 purpose="read").selection.members[0]
#             self.assertNotEqual(replacement.chunk.identifier, pin.chunk_id)
#             _, _, plan = self.snapshot(connection)
#             detail = next(item for item in plan["work"] if item["summary"]["address"] == summary.member.place.address)
#             self.assertEqual(detail["action"], "write")
#             self.assertEqual(detail["missingMembers"], [])
#             self.assertIn(replacement.chunk.identifier, [item["current"]["chunkId"] for item in detail["members"]])
#             result = self.regenerate(connection)
#             self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 0))
#             row = self.current(connection)[summary.member.chunk.identifier]
#             retained = row[4]["members"]
#             self.assertIn(replacement.chunk.identifier, [item["chunkId"] for item in retained])
#             self.assertNotIn(pin.chunk_id, [item["chunkId"] for item in retained])
#             self.assertEqual({item["place"] for item in retained}, {item.place.address for item in summary.state.members})
#             self.assertEqual(self.snapshot(connection)[1]["levels"][0]["stale"], 0)
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_interruption_retains_acknowledged_success_and_releases_unpublished_request_evidence
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Interruption retains acknowledged success and releases unpublished request evidence.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_interruption_retains_acknowledged_success_and_releases_unpublished_request_evidence(self):
#         with self.base.connect() as connection:
#             self.prepare(connection, independent=True)
#             summaries, _, _ = self.snapshot(connection)
#             self.change(connection, summaries[0])
#             self.change(connection, summaries[1])
#             old = self.current(connection)
#             result = self.regenerate(connection, writer=SequentialWriter(interrupt_at=2))
#             self.assertEqual((result.status, result.value["written"], result.value["deleted"], result.value["stopped"]), (2, 1, 0, "interrupted"))
#             current = self.current(connection)
#             self.assertNotEqual(current[summaries[0].member.chunk.identifier][1], old[summaries[0].member.chunk.identifier][1])
#             self.assertEqual(current[summaries[1].member.chunk.identifier], old[summaries[1].member.chunk.identifier])
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_final_audit_failure_returns_acknowledged_counts_and_truthful_activity
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Final audit failure returns acknowledged counts and truthful activity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_final_audit_failure_returns_acknowledged_counts_and_truthful_activity(self):
#         with self.base.connect() as connection, removal_guard(connection, "fixture"):
#             self.prepare(connection, independent=True)
#             summaries, _, _ = self.snapshot(connection)
#             self.change(connection, summaries[0])
#             self.change(connection, summaries[1])
#             with patch("mycel._summary_regenerate.current_build", return_value=1), \
#                     patch.object(MutationActivity, "finish", side_effect=MycelError("store_unavailable", "Final audit unavailable.")):
#                 result = self.regenerate(connection)
#             self.assertEqual((result.status, result.value["written"], result.value["countsState"]), (1, 2, "committed_prefix"))
#             self.assertEqual(result.value["error"]["code"], "store_unavailable")
#             counts = connection.execute("SELECT counts FROM public.mycel_activity WHERE kind='summaries_regenerate'").fetchone()[0]
#             self.assertEqual(counts["written"], 2)
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_signal_after_publication_acknowledgement_preserves_success_and_complete_interrupted_activity
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Signal after publication acknowledgement preserves success and complete interrupted activity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_signal_after_publication_acknowledgement_preserves_success_and_complete_interrupted_activity(self):
#         with self.base.connect() as connection, removal_guard(connection, "fixture"):
#             self.prepare(connection, independent=True)
#             summaries, _, _ = self.snapshot(connection)
#             self.change(connection, summaries[0])
#             self.change(connection, summaries[1])
#             old = self.current(connection)
#             record = MutationActivity.record_in_transaction
#
#             def signal_after_record(activity, repository, kind, result):
#                 record(activity, repository, kind, result)
#                 if kind == "summaries_regenerate":
#                     os.kill(os.getpid(), signal.SIGINT)
#
#             with patch("mycel._summary_regenerate.current_build", return_value=1), \
#                     patch.object(MutationActivity, "record_in_transaction", signal_after_record):
#                 result = self.regenerate(connection)
#             self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (2, 1, "interrupted"))
#             current = self.current(connection)
#             self.assertNotEqual(current[summaries[0].member.chunk.identifier][1], old[summaries[0].member.chunk.identifier][1])
#             self.assertEqual(current[summaries[1].member.chunk.identifier], old[summaries[1].member.chunk.identifier])
#             outcome, counts = connection.execute("SELECT outcome,counts FROM public.mycel_activity "
#                 "WHERE kind='summaries_regenerate'").fetchone()
#             self.assertEqual((outcome, counts), ("stopped", result.value))
#             self.no_leases(connection)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_regenerate.py::SummaryRegenerationStoreTests.test_no_stale_work_makes_no_service_calls_and_mutation_lock_is_nonblocking
# Reason: Narrower case removed from this family after retaining test_member_restored_during_memberless_deletion_preserves_stale_original. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: No stale work makes no service calls and mutation lock is nonblocking.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_regenerate.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_no_stale_work_makes_no_service_calls_and_mutation_lock_is_nonblocking(self):
#         with self.base.connect() as connection, self.base.connect() as competing:
#             self.prepare(connection)
#             old = self.current(connection)
#             writer = SequentialWriter(callback=lambda *_: self.fail("fresh summaries called writer"))
#             client = builds.LocalEmbedding(lambda _: self.fail("fresh summaries called embedding"))
#             result = self.regenerate(connection, writer=writer, client=client)
#             self.assertEqual(result.value, {"repository": "fixture", "written": 0, "deleted": 0, "replaced": False,
#                 "failed": [], "blocked": [], "cut": []})
#             with operation_guard(competing, "fixture", "summaries"):
#                 with self.assertRaises(MycelError) as error:
#                     self.regenerate(connection)
#                 self.assertEqual(error.exception.code, "busy")
#             self.assertEqual(self.current(connection), old)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
