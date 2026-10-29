
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_eligibility_uses_exact_current_disk_sections_and_complete_current_vectors
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Eligibility uses exact current disk sections and complete current vectors.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_eligibility_uses_exact_current_disk_sections_and_complete_current_vectors(self):
#         with self.connection() as connection:
#             full = self.document(connection, path="full.md")
#             multipart_text = "first\nsecond\n"
#             multipart = self.document(connection, path="multipart.md", text=multipart_text, embedded=False)
#             self.fixture.plan(connection, multipart[1], multipart[2], multipart_text, split_lines=True,
#                               vectors=((1.0, 0.0), (0.0, 1.0)))
#             self.document(connection, path="missing.md", embedded=False)
#             self.document(connection, path="historic.md", model="old-model")
#             partial = self.document(connection, path="partial.md", text=multipart_text, embedded=False)
#             self.fixture.plan(connection, partial[1], partial[2], multipart_text, split_lines=True,
#                               vectors=((1.0, 0.0), None))
#             failed = self.document(connection, path="failed.md", embedded=False)
#             self.fixture.plan(connection, failed[1], failed[2], part_failure={"kind": "content"})
#             self.document(connection, path="heartwood.md", text="---\nstatus: heartwood\n---\nfixed\n")
#             self.document(connection, path="generated.md", text="---\ngenerated: true\n---\nexternal\n")
#             self.document(connection, path="branch.md", location_kind="branch")
#             self.document(connection, path="stash.md", location_kind="stash")
#             self.fixture.seed(connection, path="code.py")
#             self.document(connection, path="other.md", repository="other")
#             self.document(connection, path="disabled.md", repository="disabled")
#             self.summary(connection, (), kind="overview")
#             self.summary(connection, (self.pin(connection, *full[1:], path="full.md"),))
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 self.assertEqual({section.member.chunk.identifier for section in snapshot.sections},
#                                  {str(full[1]), str(multipart[1])})
#                 self.assertEqual(snapshot.status()["sections"], {"inSummary": 1, "inNone": 1, "notEmbedded": 4})
#                 self.assertEqual(snapshot.status()["levels"], [{"level": 1, "summaries": 1, "stale": 0}])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_status_reports_disjoint_membership_order_stale_and_historical_build_metadata
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Status reports disjoint membership order stale and historical build metadata.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_status_reports_disjoint_membership_order_stale_and_historical_build_metadata(self):
#         with self.connection() as connection:
#             member = self.document(connection, path="member.md")
#             unembedded = self.document(connection, path="unembedded.md", embedded=False)
#             self.document(connection, path="new.md")
#             lower = self.summary(connection, (self.pin(connection, *member[1:], path="member.md"),
#                                                self.pin(connection, *unembedded[1:], path="unembedded.md")),
#                                  number=12, stale=True)
#             self.summary(connection, (self.pin(connection, *member[1:], path="member.md"),), number=2)
#             self.summary(connection, (self.pin(connection, *lower[:2], path="summaries", root="index", name="1/12"),),
#                          level=2)
#             values = {**self.settings().values, "summaries": {"at_once": 4, "command": ["fictional-writer"]}}
#             settings = replace(self.settings(), values=_freeze(values))
#             before = self.fixture.contents(connection)
#             with StoreSummaries(connection, settings).snapshot(("fixture",)) as snapshot:
#                 report = snapshot.status()
#                 self.assertEqual(report["levels"], [{"level": 1, "summaries": 2, "stale": 1},
#                                                    {"level": 2, "summaries": 1, "stale": 1}])
#                 self.assertEqual(report["sections"], {"inSummary": 1, "inNone": 1, "notEmbedded": 1})
#                 self.assertEqual((report["commandSet"], report["build"], report["groupingProfile"]),
#                                  (True, "1a", "mycel-summary-v1"))
#                 self.assertEqual(report["numericalVersions"]["numpy"], "historical-numpy")
#                 self.assertEqual(report["builtAt"], "2026-10-08T12:00:00Z")
#                 self.assertEqual(self.fixture.contents(connection), before)
#             connection.execute("UPDATE public.mycel_generated_state SET state=jsonb_set(state,'{set,build}','null') "
#                                "WHERE repository='fixture' AND kind='summary'")
#             with StoreSummaries(connection, settings).snapshot(("fixture",)) as development:
#                 report = development.status()
#                 self.assertNotIn("build", report)
#                 self.assertEqual(report["builtAt"], "2026-10-08T12:00:00Z")
#                 self.assertEqual(report["groupingProfile"], "mycel-summary-v1")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_build_dry_run_fits_exact_leaf_requests_and_keeps_current_store_unchanged
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Build dry run fits exact leaf requests and keeps current store unchanged.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_build_dry_run_fits_exact_leaf_requests_and_keeps_current_store_unchanged(self):
#         with self.connection() as connection, ExitStack() as stack:
#             self.no_effects(stack)
#             for index in range(11):
#                 self.document(connection, path=f"section-{index:02}.md", text="whole section\n" * 480)
#             self.document(connection, path="not-embedded.md", embedded=False)
#             before = self.fixture.contents(connection)
#             recorded = fixtures._RecordingConnection(connection)
#             with StoreSummaries(recorded, self.settings()).snapshot(("fixture",)) as snapshot:
#                 self.assertEqual(connection.execute("SELECT current_setting('transaction_read_only'), "
#                     "current_setting('transaction_isolation')").fetchone(), ("on", "repeatable read"))
#                 report = snapshot.build_plan()
#                 self.assertTrue(report["estimated"])
#                 self.assertEqual((report["sections"], report["notEmbedded"]), (11, 1))
#                 self.assertEqual(report["groupingProfile"], "mycel-summary-v1")
#                 number = current_build()
#                 self.assertEqual(report["build"], "development" if number is None else format(number, "x"))
#                 self.assertEqual(set(report["numericalVersions"]), {"numpy", "scipy", "scikit-learn"})
#                 self.assertGreater(report["requests"], 1)
#                 leaf = report["levels"][0]
#                 self.assertEqual((leaf["level"], leaf["nodesIn"], leaf["movedUp"]), (1, 11, 0))
#                 self.assertEqual(leaf["summaries"], report["requests"])
#                 places = [member for group in leaf["groups"] for member in group["members"]]
#                 self.assertEqual(len(places), 11)
#                 self.assertEqual(len(set(places)), 11)
#                 self.assertEqual(snapshot.build_plan(), report)
#                 self.assertEqual(self.fixture.contents(connection), before)
#             self.assertFalse(any(statement.lstrip().upper().startswith(
#                 ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")) for statement in recorded.statements))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_regeneration_keeps_exact_logical_members_plans_lower_first_and_blocks_remaining_stale_generated_members
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Regeneration keeps exact logical members plans lower first and blocks remaining stale generated members.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_regeneration_keeps_exact_logical_members_plans_lower_first_and_blocks_remaining_stale_generated_members(self):
#         with self.connection() as connection, ExitStack() as stack:
#             self.no_effects(stack)
#             old = self.document(connection, path="member.md", text="old\n")
#             pin = self.pin(connection, *old[1:], path="member.md")
#             lower = self.summary(connection, (pin,), number=2)
#             # The logical member survives at another exact current version and
#             # changed declarations do not regroup the existing summary.
#             connection.execute("UPDATE public.mycel_locations SET kind='branch',location='old' WHERE chunk_version=%s", (old[2],))
#             connection.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old'")
#             new = self.document(connection, path="member.md", text="---\ngenerated: true\n---\nnew\n",
#                                 file_id=old[0], chunk_id=old[1])
#             self.document(connection, path="new-unassigned.md")
#             deleted = self.document(connection, path="deleted.md")
#             orphan = self.summary(connection, (self.pin(connection, *deleted[1:], path="deleted.md"),), number=10)
#             connection.execute("DELETE FROM public.mycel_locations WHERE chunk_version=%s", (deleted[2],))
#             overview = self.summary(connection, (), kind="overview", stale=True)
#             blocked_lower = self.summary(connection, (self.pin(connection, *overview[:2], path="overview",
#                                                                root="index", name="Overview1"),), number=20)
#             parent = self.summary(connection, (self.pin(connection, *lower[:2], path="summaries", root="index", name="1/2"),), level=2)
#             orphan_parent = self.summary(connection, (self.pin(connection, *orphan[:2], path="summaries", root="index", name="1/10"),),
#                                          level=2, number=2)
#             blocked_parent = self.summary(connection, (self.pin(connection, *blocked_lower[:2], path="summaries",
#                                                                 root="index", name="1/20"),), level=2, number=3)
#             before = self.fixture.contents(connection)
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 report = snapshot.regeneration_plan()
#                 self.assertEqual([place["address"] for place in report["write"]], [lower[2].address, parent[2].address])
#                 self.assertEqual([place["address"] for place in report["remove"]], [orphan[2].address, orphan_parent[2].address])
#                 self.assertEqual([entry["summary"]["address"] for entry in report["blocked"]],
#                                  [blocked_lower[2].address, blocked_parent[2].address])
#                 self.assertTrue(all(entry["reason"] == "stale_member" for entry in report["blocked"]))
#                 self.assertEqual(snapshot._current[str(old[1])].chunk.version, new[2])
#                 self.assertEqual(len(snapshot._summaries[0].state.members), 1)
#                 self.assertEqual(snapshot._summaries[0].state.members[0].chunk_version, old[2])
#                 self.assertEqual(snapshot.regeneration_plan(), report)
#                 self.assertEqual(report["successPolicy"], "assume_lower_level_success")
#                 self.assertEqual(report["work"][0]["members"][0]["current"]["chunkVersion"], new[2])
#                 self.assertEqual(report["work"][0]["members"][0]["pin"]["chunkVersion"], old[2])
#                 self.assertEqual(report["work"][1]["reason"], "no_members")
#                 self.assertEqual(report["work"][3]["conditionalOn"], [report["write"][0]])
#                 self.assertEqual(report["work"][4]["conditionalOn"], [report["remove"][0]])
#                 self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_read_snapshot_survives_concurrent_changes_and_refuses_expired_use_and_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Read snapshot survives concurrent changes and refuses expired use and writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_read_snapshot_survives_concurrent_changes_and_refuses_expired_use_and_writes(self):
#         with self.connection() as connection, self.connection() as writer:
#             member = self.document(connection)
#             self.summary(connection, (self.pin(connection, *member[1:]),))
#             before = self.fixture.contents(connection)
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 report = snapshot.status()
#                 writer.execute("DELETE FROM public.mycel_locations WHERE chunk_version=%s", (member[2],))
#                 self.assertEqual(snapshot.status(), report)
#                 self.assertEqual(snapshot.regeneration_plan()["work"], [])
#                 with self.assertRaises(Exception) as rejected:
#                     with connection.transaction():
#                         connection.execute("DELETE FROM public.mycel_generated_state")
#                 self.assertEqual(rejected.exception.sqlstate, "25006")
#                 self.assertEqual(self.fixture.contents(connection), before)
#             with self.assertRaises(MycelError):
#                 snapshot.status()
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as after:
#                 self.assertEqual(after.status()["levels"], [{"level": 1, "summaries": 1, "stale": 1}])
#                 self.assertEqual(len(after.regeneration_plan()["remove"]), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_exact_repository_scope_rejects_organizations_even_one_member_and_empty_reports_succeed
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Exact repository scope rejects organizations even one member and empty reports succeed.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_repository_scope_rejects_organizations_even_one_member_and_empty_reports_succeed(self):
#         settings = self.settings(organization=True)
#         values = {**settings.values, "repos": {name: {**value, "enabled": name == "fixture"}
#                                                for name, value in settings.values["repos"].items()}}
#         settings = replace(settings, values=_freeze(values))
#         with self.connection() as connection:
#             for names, cwd, code in ((("team",), None, "invalid_input"),
#                                      ((), self.store_fixture.root / "work", "invalid_input"),
#                                      (("fixture", "other"), None, "invalid_input"),
#                                      (("disabled",), None, "refused")):
#                 with self.subTest(names=names, cwd=cwd), self.assertRaises(MycelError) as rejected:
#                     with StoreSummaries(connection, settings).snapshot(names, cwd=cwd):
#                         self.fail("invalid summary scope must refuse")
#                 self.assertEqual(rejected.exception.code, code)
#             self.assertEqual(summary_repository(settings, cwd=self.store_fixture.root / "work" / "fixture"), "fixture")
#             with StoreSummaries(connection, settings).snapshot(("fixture",)) as snapshot:
#                 self.assertEqual(snapshot.status(), {"repository": "fixture", "commandSet": False, "levels": [],
#                     "numericalVersions": {},
#                     "sections": {"inSummary": 0, "inNone": 0, "notEmbedded": 0}})
#                 self.assertEqual(snapshot.build_plan()["requests"], 0)
#                 self.assertEqual(snapshot.regeneration_plan()["work"], [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_incompatible_published_state_fails_closed_without_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Incompatible published state fails closed without writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_incompatible_published_state_fails_closed_without_writes(self):
#         with self.connection() as connection:
#             member = self.document(connection)
#             summary = self.summary(connection, (self.pin(connection, *member[1:]),))
#             valid = connection.execute("SELECT state FROM public.mycel_generated_state WHERE chunk_id=%s", (summary[0],)).fetchone()[0]
#             cases = []
#             for field, value in (("schemaVersion", 2), ("chunkVersion", summary[1] + 1), ("members", None)):
#                 changed = json.loads(json.dumps(valid))
#                 changed[field] = value
#                 cases.append(changed)
#             for field, value in (("groupingProfile", "unknown-profile"), ("build", "1a"),
#                                  ("build", True), ("numericalVersions", {"numpy": "only-one"})):
#                 changed = json.loads(json.dumps(valid))
#                 changed["set"][field] = value
#                 cases.append(changed)
#             changed = json.loads(json.dumps(valid))
#             changed["members"] *= 2
#             cases.append(changed)
#             changed = json.loads(json.dumps(valid))
#             changed["members"][0]["place"] = "other:@artifact/note.md#Section"
#             cases.append(changed)
#             for state in cases:
#                 with self.subTest(state=state):
#                     connection.execute("UPDATE public.mycel_generated_state SET state=%s WHERE chunk_id=%s",
#                                        (Jsonb(state), summary[0]))
#                     before = self.fixture.contents(connection)
#                     with self.assertRaises(MycelError) as rejected:
#                         with StoreSummaries(connection, self.settings()).snapshot(("fixture",)):
#                             self.fail("unsupported handoff must refuse")
#                     self.assertEqual(rejected.exception.code, "store_format")
#                     self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_self_same_and_higher_level_generated_summary_members_are_stale_and_blocked
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Self same and higher level generated summary members are stale and blocked.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_self_same_and_higher_level_generated_summary_members_are_stale_and_blocked(self):
#         with self.connection() as connection:
#             section = self.document(connection)
#             leaf = self.summary(connection, (self.pin(connection, *section[1:]),), number=1)
#             same = self.summary(connection, (self.pin(connection, *leaf[:2], root="index", path="summaries", name="1/1"),),
#                                 number=2)
#             higher = self.summary(connection, (self.pin(connection, *section[1:]),), level=2)
#             own = self.summary(connection, (self.pin(connection, *higher[:2], root="index", path="summaries", name="2/1"),),
#                                number=3)
#             connection.execute("UPDATE public.mycel_generated_state SET state=jsonb_set(state,'{members}',%s) "
#                                "WHERE chunk_id=%s", (Jsonb([self.pin(connection, *leaf[:2], root="index", path="summaries", name="1/1")]), leaf[0]))
#             before = self.fixture.contents(connection)
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 report = snapshot.regeneration_plan()
#                 self.assertEqual(report["write"], [])
#                 self.assertEqual(report["remove"], [])
#                 self.assertEqual([entry["summary"]["address"] for entry in report["blocked"]],
#                                  [leaf[2].address, same[2].address, own[2].address])
#                 self.assertEqual(snapshot.status()["levels"], [{"level": 1, "summaries": 3, "stale": 3},
#                                                               {"level": 2, "summaries": 1, "stale": 0}])
#                 self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_unsupported_surviving_member_kinds_are_reported_stale_and_never_planned_for_writing
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unsupported surviving member kinds are reported stale and never planned for writing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unsupported_surviving_member_kinds_are_reported_stale_and_never_planned_for_writing(self):
#         with self.connection() as connection:
#             code = self.fixture.seed(connection, path="code.py")
#             overview = self.summary(connection, (), kind="overview")
#             code_summary = self.summary(connection, (self.pin(connection, *code[1:], root="code", path="code.py", name="Symbol"),))
#             overview_summary = self.summary(connection, (self.pin(connection, *overview[:2], root="index", path="overview", name="Overview1"),),
#                                             number=2)
#             before = self.fixture.contents(connection)
#             with StoreSummaries(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 report = snapshot.regeneration_plan()
#                 self.assertEqual(report["write"], [])
#                 self.assertEqual(report["remove"], [])
#                 self.assertEqual([entry["summary"]["address"] for entry in report["blocked"]],
#                                  [code_summary[2].address, overview_summary[2].address])
#                 self.assertTrue(all(work["reason"] == "invalid_member" and len(work["invalidMembers"]) == 1
#                                     for work in report["work"]))
#                 self.assertEqual(snapshot.status()["levels"], [{"level": 1, "summaries": 2, "stale": 2}])
#                 self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_public_cli_registration_returns_complete_status_and_dry_run_replies
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public cli registration returns complete status and dry run replies.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_cli_registration_returns_complete_status_and_dry_run_replies(self):
#         with self.connection() as connection, ExitStack() as stack:
#             self.no_effects(stack)
#             self.document(connection)
#             settings = self.settings()
#             stack.enter_context(patch("mycel._cli.load_settings", return_value=settings))
#             before = self.fixture.contents(connection)
#             for action in ("status", "build", "regenerate"):
#                 arguments = ["summaries", action, "--repo", "fixture"]
#                 if action != "status":
#                     arguments.append("--dry-run")
#                 output, error = io.StringIO(), io.StringIO()
#                 status = run(arguments, stdout=output, stderr=error)
#                 reply = json.loads(output.getvalue())
#                 self.assertEqual(status, 0, reply)
#                 self.assertEqual(error.getvalue(), "")
#                 self.assertEqual(reply["repository"], "fixture")
#                 if action == "status":
#                     self.assertEqual(reply["sections"], {"inSummary": 0, "inNone": 1, "notEmbedded": 0})
#                     self.assertEqual(reply["levels"], [])
#                     for optional in ("builtAt", "groupingProfile", "build"):
#                         self.assertNotIn(optional, reply)
#                 elif action == "build":
#                     self.assertEqual((reply["sections"], reply["requests"], reply["estimated"]), (1, 0, True))
#                 else:
#                     self.assertEqual((reply["write"], reply["remove"], reply["blocked"], reply["work"]), ([], [], [], []))
#             for arguments in (["summaries", "status", "--repo", "fixture", "--repo", "fixture"],
#                               ["summaries", "status", "--dry-run", "--repo", "fixture"]):
#                 output, error = io.StringIO(), io.StringIO()
#                 self.assertEqual(run(arguments, stdout=output, stderr=error), 1)
#                 self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
#                 self.assertEqual(error.getvalue(), "")
#             organization_settings = self.settings(organization=True)
#             organization_settings = replace(organization_settings, values=_freeze({**organization_settings.values,
#                 "repos": {name: {**value, "enabled": name == "fixture"}
#                           for name, value in organization_settings.values["repos"].items()}}))
#             with patch("mycel._cli.load_settings", return_value=organization_settings), \
#                  patch("mycel._cli.invocation_store", side_effect=AssertionError("organization reached store")):
#                 output, error = io.StringIO(), io.StringIO()
#                 self.assertEqual(run(["summaries", "build", "--repo", "team"], stdout=output, stderr=error), 1)
#                 self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
#                 self.assertEqual(error.getvalue(), "")
#             self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_summary_store.py::SummaryStoreTests.test_handler_reports_are_read_only_and_pending_actual_mutations_refuse_before_store_use
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Handler reports are read only and pending actual mutations refuse before store use.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_summary_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_handler_reports_are_read_only_and_pending_actual_mutations_refuse_before_store_use(self):
#         with self.connection() as connection, ExitStack() as stack:
#             self.no_effects(stack)
#             self.document(connection)
#             settings = self.settings()
#             before = self.fixture.contents(connection)
#             for arguments in (("status",), ("build", "--dry-run"), ("regenerate", "--dry-run")):
#                 reply = handle_summaries(Invocation("summaries", repositories=("fixture",),
#                                                    arguments=arguments, settings=settings))
#                 self.assertEqual(reply.status, 0)
#                 self.assertEqual(reply.value["repository"], "fixture")
#             self.assertEqual(self.fixture.contents(connection), before)
#             pending_settings = replace(settings, values=_freeze({**settings.values,
#                 "summaries": {"at_once": 4, "command": ["fictional-writer"]}}))
#             with patch("mycel._cli.invocation_store", side_effect=AssertionError("pending mutation touched store")):
#                 for arguments in (("build",), ("regenerate",), ("remove",)):
#                     with self.subTest(arguments=arguments), self.assertRaises(MycelError) as rejected:
#                         handle_summaries(Invocation("summaries", repositories=("fixture",),
#                                                    arguments=arguments, settings=pending_settings))
#                     self.assertEqual(rejected.exception.code, "refused")
#             for arguments in (("status", "--dry-run"), ("build", "--dry-run", "--dry-run")):
#                 with self.subTest(arguments=arguments), self.assertRaises(MycelError) as rejected:
#                     handle_summaries(Invocation("summaries", repositories=("fixture",),
#                                                arguments=arguments, settings=settings))
#                 self.assertEqual(rejected.exception.code, "invalid_input")
#             # Complete reply contracts are prepared for the later publishers;
#             # constructing a result never runs or fakes a mutation handler.
#             with StoreSummaries(connection, settings).snapshot(("fixture",)):
#                 self.assertEqual(summary_removal_reply("fixture", 0), {"repository": "fixture", "removed": 0})
#                 self.assertEqual(summary_removal_reply("fixture", 3), {"repository": "fixture", "removed": 3})
#                 self.assertEqual(summary_result_reply("fixture", written=0, deleted=0, replaced=False),
#                     {"repository": "fixture", "written": 0, "deleted": 0, "replaced": False,
#                      "failed": [], "blocked": [], "cut": []})
#                 first = SourceAddress("fixture", "index", "summaries", "1/2")
#                 later = SourceAddress("fixture", "index", "summaries", "1/12")
#                 parent = SourceAddress("fixture", "index", "summaries", "2/1")
#                 reply = summary_result_reply("fixture", written=2, deleted=1, replaced=False,
#                     failed=({"summary": later.address, "reason": "embedding_failed"},
#                             {"summary": first.address, "reason": "timeout"}),
#                     blocked=({"summary": parent, "reason": "inputs_changed"},),
#                     cut=(SourceAddress("fixture", "artifact", "note.md", "Section"),), stopped="failed")
#                 self.assertEqual([item["summary"] for item in reply["failed"]], [first.address, later.address])
#                 self.assertEqual(reply["blocked"][0]["summary"]["address"], parent.address)
#                 self.assertEqual((reply["written"], reply["deleted"], reply["stopped"]), (2, 1, "failed"))
#                 for count in (-1, True, "0"):
#                     with self.assertRaises(MycelError):
#                         summary_removal_reply("fixture", count)
#                 for changes in ({"written": True}, {"deleted": -1}, {"replaced": 1}, {"stopped": "other"},
#                         {"failed": ({"summary": first.address, "reason": "unredacted diagnostic"},)},
#                         {"blocked": ({"summary": parent, "reason": "other"},)},
#                         {"cut": (SourceAddress("other", "artifact", "note.md", "Section"),)}):
#                     with self.subTest(changes=changes), self.assertRaises(MycelError):
#                         summary_result_reply("fixture", **{**{"written": 0, "deleted": 0, "replaced": False}, **changes})
#                 self.assertEqual(self.fixture.contents(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
