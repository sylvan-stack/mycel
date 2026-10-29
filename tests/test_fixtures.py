
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_fixtures.py::RepositoryFixtureTests.test_real_git_locations_are_read_without_touching_the_generated_checkout
# Reason: Verifies names and content just written by the repository fixture, using a disposable store that the test never accesses; it does not exercise product capture.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_fixtures.py
# Retained evidence at review: Actual disk/branch/stash capture and reconciliation tests retain repository immutability and exact source behavior.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_git_locations_are_read_without_touching_the_generated_checkout(self):
#         self.assertTrue(self.store_fixture.backend.real_store)
#         with repository_fixture() as fixture:
#             before = fixture.snapshot()
#             refs = run_git(["for-each-ref", "--format=%(refname)", "refs/heads"], cwd=fixture.code)
#             self.assertIn(b"refs/heads/fixture-base", refs.stdout)
#             self.assertIn(b"refs/heads/fixture-second", refs.stdout)
#             branch = run_git(["show", "fixture-second:README.md"], cwd=fixture.code)
#             stash = run_git(["show", "refs/stash:docs/guide.md"], cwd=fixture.code)
#             self.assertIn(b"Second branch text", branch.stdout)
#             self.assertIn(b"Stashed guide text", stash.stdout)
#             self.assertIn("Disk and base branch text", (fixture.code / "README.md").read_text())
#             self.assertIn("A checkout document", (fixture.code / "docs/guide.md").read_text())
#             self.assertEqual(fixture.snapshot(), before)
#             self.assertEqual((fixture.overlapping_artifacts / "guide.md").resolve(),
#                              (fixture.code / "docs/guide.md").resolve())
#             self.assertNotEqual((fixture.artifacts / "README.md").resolve(),
#                                 (fixture.code / "README.md").resolve())
#             self.assertNotEqual(sha256((fixture.artifacts / "README.md").read_bytes()).hexdigest(),
#                                 sha256((fixture.code / "README.md").read_bytes()).hexdigest())
#             root = fixture.root
#         self.assertFalse(root.exists())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_fixtures.py::ServiceFixtureTests.test_each_service_failure_is_controllable_and_attempts_remain_counted
# Reason: Tests that a scripted stand-in raises its configured failure and returns its configured response mutation; retry/provider orchestration already observes its attempt counts.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_fixtures.py
# Retained evidence at review: tests/test_voyage.py covers retries, cancellation, input isolation and recorded request counts through the actual client.
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_each_service_failure_is_controllable_and_attempts_remain_counted(self):
#         for kind in sorted(EmbeddingStandIn.FAILURES):
#             with self.subTest(kind=kind):
#                 service = EmbeddingStandIn(lambda text, input_type: 1)
#                 service.fail_attempt(1, kind)
#                 with self.assertRaises(EmbeddingFixtureFailure) as fault:
#                     service.embed(["fictional text"], model="voyage-code-4", dimensions=256,
#                                   input_type="document")
#                 self.assertEqual(fault.exception.kind, kind)
#                 self.assertEqual(service.attempts[0].failure, kind)
#                 service.embed(["fictional text"], model="voyage-code-4", dimensions=256,
#                               input_type="document")
#                 self.assertEqual(len(service.attempts), 2)
#                 self.assertIsNone(service.attempts[1].failure)
#         service = EmbeddingStandIn(lambda text, input_type: 1)
#         service.reject_input = lambda text: text == "bad content"
#         with self.assertRaises(EmbeddingFixtureFailure):
#             service.embed(["good", "bad content"], model="voyage-code-4", dimensions=256,
#                           input_type="document")
#         service.response_mutator = lambda response: {**response, "data": []}
#         self.assertEqual(service.embed(["good"], model="voyage-code-4", dimensions=256,
#                                       input_type="document")["data"], [])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
