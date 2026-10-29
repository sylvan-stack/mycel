
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_fill_names_passing_checks_of_the_own_kind_and_most_specific_first
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Fill names passing checks of the own kind and most specific first.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fill_names_passing_checks_of_the_own_kind_and_most_specific_first(self):
#         status, out, err = self.fill()
#         self.assertEqual((status, err), (0, ""))
#         self.assertIn("1 of 2 specifications implemented", out)
#         self.assertIn("FIX-2 held back by FIX-2.2", out)
#         water = (self.specs / "01-water.md").read_text(encoding="utf-8")
#         self.assertIn("| `FIX-1.1` | store | `test_level.LevelStoreTests.test_keeps`, "
#                       "`test_level.LevelTests.test_rounds`, `test_level.LevelTests.test_reports` |\n", water)
#         self.assertIn("| `FIX-1.2` | unit | `test_light.LightTests.test_reports`, `test_shared.ReportTests.test_b`, "
#                       "`test_shared.ReportTests.test_c` and 3 more |\n", water)
#         self.assertNotIn("FIX-1.3", water.split("## Named checks")[1])
#         self.assertNotIn("test_gone", water)
#         light = (self.specs / "02-light.md").read_text(encoding="utf-8")
#         self.assertIn("| `FIX-2.2` | eval | no on-demand report yet |\n", light)
#         self.assertTrue(water.startswith("---\nrole: authored\nspec: FIX-1\nstatus: implemented\n---\n"))
#         self.assertIn("status: accepted\n", light)
#         index = (self.specs / "README.md").read_text(encoding="utf-8")
#         self.assertIn("| [FIX-1](01-water.md) | Water | implemented |\n", index)
#         self.assertIn("| [FIX-2](02-light.md) | Light | accepted, held back by FIX-2.2 |\n", index)
#         self.assertIn("| [FIX-3](03-soil.md) | Soil | draft |\n", index)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_fill_changes_no_requirement_row_or_draft_and_is_repeatable
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Fill changes no requirement row or draft and is repeatable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fill_changes_no_requirement_row_or_draft_and_is_repeatable(self):
#         self.assertEqual(self.fill()[0], 0)
#         for name in ("01-water.md", "02-light.md"):
#             text = (self.specs / name).read_text(encoding="utf-8")
#             before = self.rows[name].replace("status: accepted", "status: implemented") if name == "01-water.md" else self.rows[name]
#             self.assertEqual(text.split("\n\n## Named checks")[0] + "\n", before)
#         self.assertEqual((self.specs / "03-soil.md").read_text(encoding="utf-8"), self.rows["03-soil.md"])
#         first = {path.name: path.read_bytes() for path in self.specs.iterdir()}
#         self.assertEqual(self.fill()[0], 0)
#         self.assertEqual({path.name: path.read_bytes() for path in self.specs.iterdir()}, first)
#         self.assertEqual(self.check()[0], 0)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_check_refuses_a_named_check_that_did_not_pass_or_no_longer_exists
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Check refuses a named check that did not pass or no longer exists.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_check_refuses_a_named_check_that_did_not_pass_or_no_longer_exists(self):
#         self.assertEqual(self.fill()[0], 0)
#         remaining = {name: kind for name, kind in self.checks.items() if name != "test_level.LevelStoreTests.test_keeps"}
#         status, _, err = self.check(self.write_report(Path(self.directory.name) / "later.json", remaining))
#         self.assertEqual(status, 1)
#         self.assertIn("FIX-1.1: test_level.LevelStoreTests.test_keeps did not pass in the reports", err)
#         self.assertIn("01-water.md: status implemented, its Named checks say accepted", err)
#         self.assertIn("README.md: an index status differs from its chapter", err)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_check_refuses_hand_edits_and_status_drift
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Check refuses hand edits and status drift.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_check_refuses_hand_edits_and_status_drift(self):
#         self.assertEqual(self.fill()[0], 0)
#         water = self.specs / "01-water.md"
#         original = water.read_text(encoding="utf-8")
#         water.write_text(original.replace("`test_level.LevelTests.test_reports` |", "`test_level.LevelTests.test_reports` (best) |"),
#                          encoding="utf-8")
#         status, _, err = self.check()
#         self.assertEqual(status, 1)
#         self.assertIn("unreadable Checks cell", err)
#         water.write_text(original.replace("store |", "unit |", 1), encoding="utf-8")
#         self.assertIn("the Named checks rows differ from its active requirements", self.check()[2])
#         water.write_text(original.replace("status: implemented", "status: accepted"), encoding="utf-8")
#         self.assertIn("01-water.md: status accepted, its Named checks say implemented", self.check()[2])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_check_accepts_an_on_demand_report_only_for_named_checks
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Check accepts an on demand report only for named checks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_check_accepts_an_on_demand_report_only_for_named_checks(self):
#         self.assertEqual(self.fill()[0], 0)
#         light = self.specs / "02-light.md"
#         light.write_text(light.read_text(encoding="utf-8").replace(
#             "| eval | no on-demand report yet |", "| eval | `test_eval.EvalSetTests.test_finds_windows` |")
#             .replace("status: accepted", "status: implemented"), encoding="utf-8")
#         index = self.specs / "README.md"
#         index.write_text(index.read_text(encoding="utf-8").replace("accepted, held back by FIX-2.2", "implemented"),
#                          encoding="utf-8")
#         self.assertIn("FIX-2.2: test_eval.EvalSetTests.test_finds_windows did not pass in the reports", self.check()[2])
#         on_demand = self.write_report(Path(self.directory.name) / "eval.json",
#                                       {"test_eval.EvalSetTests.test_finds_windows": "eval"})
#         status, out, err = self.check(self.report, on_demand)
#         self.assertEqual((status, err), (0, ""))
#         self.assertIn("2 of 2 specifications implemented", out)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_name_checks.py::NameChecksTests.test_fill_refuses_a_failed_report_or_a_row_without_one_kind_and_writes_nothing
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Fill refuses a failed report or a row without one kind and writes nothing.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_name_checks.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_fill_refuses_a_failed_report_or_a_row_without_one_kind_and_writes_nothing(self):
#         failed = self.write_report(Path(self.directory.name) / "failed.json", self.checks, passed=False)
#         status, _, err = self.run_script("fill", "--specifications", str(self.specs), "--origins", str(self.origins),
#                                          "--report", str(failed))
#         self.assertEqual(status, 1)
#         self.assertIn("not a passing schema 2 check report", err)
#         (self.specs / "02-light.md").write_text(self.rows["02-light.md"].replace("| eval |", "| eval, live |"),
#                                                 encoding="utf-8")
#         status, _, err = self.fill()
#         self.assertEqual(status, 1)
#         self.assertIn("FIX-2.2 has Verified by 'eval, live', not one kind", err)
#         self.assertEqual((self.specs / "01-water.md").read_text(encoding="utf-8"), self.rows["01-water.md"])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
