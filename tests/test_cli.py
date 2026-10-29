
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_cli.py::CliTests.test_repository_selection_is_literal_and_repeatable
# Reason: Copies straightforward parser output for --repo, --all and the empty selection; it does not exercise scope resolution.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_cli.py
# Retained evidence at review: ScopeTests and public search/embed scope tests retain actual repository selection and error boundaries.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repository_selection_is_literal_and_repeatable(self):
#         invocation = parse(["embed", "--repo", "Cellar", "--repo", "Other space"])
#         self.assertEqual(invocation.repositories, ("Cellar", "Other space"))
#         self.assertTrue(parse(["embed", "--all"]).all_repositories)
#         self.assertEqual(parse(["search", "question"]).repositories, ())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_cli.py::CliTests.test_partial_repository_results_are_preserved
# Reason: Repeats the repository_result wrapper, which returns the supplied list and chooses status from its error members.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_cli.py
# Retained evidence at review: Public multi-repository command tests retain mixed successful/failed work, interruption and per-repository output.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_partial_repository_results_are_preserved(self):
#         entries = [{"repository": "one", "result": {"done": True}},
#                    {"repository": "two", "error": {"code": "busy", "message": "Busy."}}]
#         result = repository_result(entries)
#         self.assertEqual(result.status, 1)
#         self.assertEqual(result.value["repositories"], entries)
#         self.assertEqual(repository_result(entries[:1]).status, 0)
#         self.assertEqual(repository_result(entries[1:]).value, {"repositories": entries[1:]})
#         self.assertEqual(repository_result(entries[1:], started=True).value, {"repositories": entries[1:]})
#         refused = [{"repository": "three", "error": {"code": "refused", "message": "Disabled."}}]
#         self.assertEqual(repository_result(entries[1:] + refused).value["repositories"], entries[1:] + refused)
#         self.assertEqual(repository_result(entries[1:] + refused).status, 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_cli.py::CliTests.test_build_selection_is_explicitly_unavailable
# Reason: Exercises only the unconditional -v refusal branch; generic invalid-argument and installed-launcher boundary tests already distinguish launcher and product arguments.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_cli.py
# Retained evidence at review: test_invalid_arguments_have_one_closed_error and tests/test_launcher_selection.py.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_build_selection_is_explicitly_unavailable(self):
#         out = io.StringIO()
#         self.assertEqual(run(["-v", "a3", "search", "query"], stdout=out), 1)
#         self.assertEqual(json.loads(out.getvalue())["error"]["code"], "refused")
# LOW-TIER-SOURCE-END
# LOW-TIER-END
