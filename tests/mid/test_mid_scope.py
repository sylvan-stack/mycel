
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_organization_derives_checkout_and_document_folders_with_provenance
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Organization derives checkout and document folders with provenance.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_organization_derives_checkout_and_document_folders_with_provenance(self):
#         checkout = self.checkout("orchard", "presses")
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"}},
#                                    {"presses": {"enabled": True}})
#         repository, = locations.named("presses")
#         self.assertEqual(repository.organization, "Orchard")
#         self.assertEqual(repository.code.path, checkout)
#         self.assertEqual(repository.code.source, "organization")
#         self.assertEqual(repository.documents.path, self.home / "Artifacts/orchard/repos/presses")
#         self.assertEqual(repository.documents.source, "organization")
#         repository.require_folders()
#         self.assertEqual(locations.repositories_reply(), {
#             "organizations": [{"name": "Orchard", "root": str(self.home / "orchard"),
#                                "documents": str(self.home / "Artifacts/orchard")}],
#             "repositories": [{"name": "presses", "enabled": True, "organization": "Orchard",
#                               "code": {"folder": str(checkout), "from": "organization"},
#                               "documents": {"folder": str(self.home / "Artifacts/orchard/repos/presses"),
#                                             "from": "organization"}}]})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_repository_folders_override_each_organization_folder_independently
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Repository folders override each organization folder independently.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repository_folders_override_each_organization_folder_independently(self):
#         checkout = self.checkout("orchard", "presses")
#         artifact = self.home / "manuals"
#         locations = self.locations({"Orchard": {"root": self.home / "orchard",
#                                                 "artifact_root": self.home / "organization-documents"}},
#                                    {"presses": {"artifact_root": artifact},
#                                     "alias": {"code_root": checkout, "code_subdirs": ["src", "tests"]},
#                                     "standalone": {"code_root": self.home / "other", "artifact_root": artifact}})
#         presses, = locations.named("presses")
#         self.assertEqual(presses.code.source, "organization")
#         self.assertEqual(presses.documents.path, artifact)
#         self.assertEqual(presses.documents.source, "repository")
#         alias, = locations.named("alias")
#         self.assertEqual(alias.organization, "Orchard")
#         self.assertEqual(alias.code.source, "repository")
#         self.assertEqual(alias.documents.path, self.home / "organization-documents/repos/alias")
#         self.assertEqual(alias.code_roots, (checkout / "src", checkout / "tests"))
#         self.assertEqual(alias.code.report(code=True)["subfolders"], ["src", "tests"])
#         standalone, = locations.named("standalone")
#         self.assertIsNone(standalone.organization)
#         self.assertEqual(standalone.documents.path, artifact)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_empty_code_subdirs_means_whole_code_and_documents_keep_both_roots
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Empty code subdirs means whole code and documents keep both roots.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_empty_code_subdirs_means_whole_code_and_documents_keep_both_roots(self):
#         code, documents = self.home / "source", self.home / "documents"
#         locations = self.locations(repositories={"project": {"code_root": code, "artifact_root": documents,
#                                                               "code_subdirs": []},
#                                                    "manual": {"artifact_root": documents}})
#         project, = locations.named("project")
#         self.assertEqual(project.code_roots, (code,))
#         self.assertEqual(tuple(folder.path for folder in project.document_roots), (code, documents))
#         self.assertNotIn("subfolders", project.report()["code"])
#         manual, = locations.named("manual")
#         self.assertEqual(manual.code_roots, ())
#         self.assertEqual(tuple(folder.path for folder in manual.document_roots), (documents,))
#         manual.require_folders()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_members_are_only_configured_direct_children_with_checkout_markers
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Members are only configured direct children with checkout markers.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_members_are_only_configured_direct_children_with_checkout_markers(self):
#         direct = self.checkout("orchard", "direct", worktree=True)
#         self.checkout("orchard", "unconfigured")
#         self.checkout("orchard/nested", "deep")
#         (self.home / "orchard/not-a-checkout").mkdir()
#         (self.home / "orchard/symlink").symlink_to(direct, target_is_directory=True)
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"}},
#                                    {"direct": {"enabled": True}, "deep": {}, "not-a-checkout": {}, "symlink": {}})
#         self.assertEqual(self.names(locations.repositories), ("deep", "direct", "not-a-checkout", "symlink"))
#         self.assertEqual(self.names(locations.named("Orchard")), ("direct",))
#         self.assert_refused(lambda: locations.named("unconfigured"), code="unknown_repository")
#         for name in ("deep", "not-a-checkout", "symlink"):
#             repository, = locations.named(name)
#             self.assertIsNone(repository.organization)
#             self.assertIsNotNone(repository.fault)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_explicit_code_membership_uses_direct_parent_and_not_repository_name
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Explicit code membership uses direct parent and not repository name.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_explicit_code_membership_uses_direct_parent_and_not_repository_name(self):
#         root = self.home / "orchard"
#         locations = self.locations({"Orchard": {"root": root}},
#                                    {"alias": {"code_root": root / "physical-name", "enabled": True},
#                                     "nested": {"code_root": root / "inside/deep", "enabled": True},
#                                     "root-itself": {"code_root": root, "enabled": True}})
#         self.assertEqual(self.names(locations.named("Orchard")), ("alias",))
#         self.assertEqual(locations.named("alias")[0].organization, "Orchard")
#         self.assertIsNone(locations.named("nested")[0].organization)
#         self.assertIsNone(locations.named("root-itself")[0].organization)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_named_scope_preserves_exact_names_without_environment_or_fallback_aliases
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Named scope preserves exact names without environment or fallback aliases.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_named_scope_preserves_exact_names_without_environment_or_fallback_aliases(self):
#         locations = self.locations(repositories={"Project": {"code_root": self.home / "p"},
#                                                    "project": {"code_root": self.home / "q"},
#                                                    "Repository with spaces": {"artifact_root": self.home / "r"}})
#         with patch.dict(os.environ, {"MYCEL_REPO": "wrong", "ARBOL_REPO": "wrong", "ARBOL_OVERLAY": "wrong"}):
#             self.assertEqual(self.names(locations.resolve_scope(["Project", "project", "Project"])), ("Project", "project"))
#             self.assertEqual(self.names(locations.resolve_scope(["Repository with spaces"])), ("Repository with spaces",))
#             self.assert_refused(lambda: locations.named("PROJECT"), code="unknown_repository")
#             self.assert_refused(lambda: locations.resolve_scope(cwd=self.home / "elsewhere"), code="unknown_repository")
#         self.assertEqual(set(locations.snapshot.values["repos"]), {"Project", "project", "Repository with spaces"})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_disabled_explicit_and_cwd_selection_but_enabled_organization_and_all_sweeps
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Disabled explicit and cwd selection but enabled organization and all sweeps.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disabled_explicit_and_cwd_selection_but_enabled_organization_and_all_sweeps(self):
#         self.checkout("orchard", "on")
#         off = self.checkout("orchard", "off")
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"}},
#                                    {"on": {"enabled": True}, "off": {"enabled": False},
#                                     "outside": {"enabled": True, "artifact_root": self.home / "outside"}})
#         self.assertEqual(self.names(locations.resolve_scope(["off"])), ("off",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=off / "src")), ("off",))
#         self.assertEqual(self.names(locations.resolve_scope(["Orchard"])), ("on",))
#         self.assertEqual(self.names(locations.resolve_scope(all_repositories=True)), ("on", "outside"))
#         self.assertEqual(self.names(locations.resolve_scope(["Orchard", "outside", "on"])), ("on", "outside"))
#         self.assert_refused(lambda: locations.resolve_scope(["on"], all_repositories=True), code="invalid_input")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_longest_containing_code_or_document_root_wins_on_component_boundaries
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Longest containing code or document root wins on component boundaries.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_longest_containing_code_or_document_root_wins_on_component_boundaries(self):
#         locations = self.locations(repositories={"wide": {"code_root": self.home / "repos", "artifact_root": self.home / "docs"},
#                                                    "narrow": {"code_root": self.home / "repos/project", "artifact_root": self.home / "docs/project"}})
#         self.assertEqual(self.names(locations.resolve_scope(cwd=self.home / "repos/project/src")), ("narrow",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=self.home / "docs/project/guide")), ("narrow",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=self.home / "repos/project-other")), ("wide",))
#         self.assert_refused(lambda: locations.resolve_scope(cwd=self.home / "repos-other"), code="unknown_repository")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_organization_cwd_outside_members_expands_enabled_members_for_both_folders
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Organization cwd outside members expands enabled members for both folders.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_organization_cwd_outside_members_expands_enabled_members_for_both_folders(self):
#         member = self.checkout("orchard", "member")
#         self.checkout("orchard", "off")
#         locations = self.locations({"Orchard": {"root": self.home / "orchard", "artifact_root": self.home / "org-docs"}},
#                                    {"member": {"enabled": True}, "off": {}})
#         for cwd in (self.home / "orchard", self.home / "orchard/admin", self.home / "org-docs/plans"):
#             self.assertEqual(self.names(locations.resolve_scope(cwd=cwd)), ("member",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=member / "src")), ("member",))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_empty_organization_and_all_scope_refuse_instead_of_false_success
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Empty organization and all scope refuse instead of false success.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_empty_organization_and_all_scope_refuse_instead_of_false_success(self):
#         self.checkout("orchard", "off")
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"}}, {"off": {}})
#         self.assert_refused(lambda: locations.resolve_scope(["Orchard"]), code="refused")
#         self.assert_refused(lambda: locations.resolve_scope(cwd=self.home / "orchard"), code="refused")
#         self.assert_refused(lambda: locations.resolve_scope(all_repositories=True), code="refused")
#         empty = self.locations()
#         self.assert_refused(lambda: empty.resolve_scope(all_repositories=True), code="refused")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_equal_longest_roots_or_repo_organization_name_collisions_are_explicit_faults
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Equal longest roots or repo organization name collisions are explicit faults.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_equal_longest_roots_or_repo_organization_name_collisions_are_explicit_faults(self):
#         locations = self.locations({"collision": {"root": self.home / "org"}},
#                                    {"first": {"code_root": self.home / "same"},
#                                     "second": {"artifact_root": self.home / "same"},
#                                     "collision": {"code_root": self.home / "other"}})
#         error = self.assert_refused(lambda: locations.resolve_scope(cwd=self.home / "same"), code="unknown_repository")
#         self.assertIn("first", str(error))
#         self.assertIn("second", str(error))
#         self.assert_refused(lambda: locations.named("collision"), code="unknown_repository")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_ambiguous_membership_is_local_lists_organizations_and_keeps_other_repos_usable
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Ambiguous membership is local lists organizations and keeps other repos usable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_ambiguous_membership_is_local_lists_organizations_and_keeps_other_repos_usable(self):
#         orchard = self.checkout("orchard", "presses")
#         vineyard = self.checkout("vineyard", "presses")
#         good = self.home / "healthy"
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"},
#                                     "Vineyard": {"root": self.home / "vineyard"}},
#                                    {"presses": {"enabled": True}, "good": {"enabled": True, "code_root": good}})
#         ambiguous, = locations.named("presses")
#         error = self.assert_refused(ambiguous.require_folders, code="settings")
#         self.assertIn("Orchard", str(error))
#         self.assertIn("Vineyard", str(error))
#         self.assertIn("code_root", str(error))
#         for cwd in (orchard / "src", vineyard / "src"):
#             self.assertEqual(self.names(locations.resolve_scope(cwd=cwd)), ("presses",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=good / "src")), ("good",))
#         locations.named("good")[0].require_folders()
#         self.assertEqual(self.names(locations.resolve_scope(["Orchard"])), ("presses",))
#         self.assertEqual(self.names(locations.resolve_scope(all_repositories=True)), ("good", "presses"))
#         report = locations.repositories_reply()
#         self.assertEqual(len(report["repositories"]), 2)
#         self.assertIn("fault", next(row for row in report["repositories"] if row["name"] == "presses"))
#         self.assertNotIn("fault", next(row for row in report["repositories"] if row["name"] == "good"))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_explicit_code_root_disambiguates_organizations_and_allows_a_second_name
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Explicit code root disambiguates organizations and allows a second name.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_explicit_code_root_disambiguates_organizations_and_allows_a_second_name(self):
#         orchard = self.checkout("orchard", "presses")
#         vineyard = self.checkout("vineyard", "presses")
#         locations = self.locations({"Orchard": {"root": self.home / "orchard"},
#                                     "Vineyard": {"root": self.home / "vineyard"}},
#                                    {"presses": {"enabled": True, "code_root": orchard},
#                                     "vineyard-presses": {"enabled": True, "code_root": vineyard}})
#         self.assertEqual(self.names(locations.named("Orchard")), ("presses",))
#         self.assertEqual(self.names(locations.named("Vineyard")), ("vineyard-presses",))
#         for repository in locations.repositories:
#             repository.require_folders()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_listing_includes_disabled_and_folderless_repositories_and_fresh_json_copies
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Listing includes disabled and folderless repositories and fresh json copies.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_listing_includes_disabled_and_folderless_repositories_and_fresh_json_copies(self):
#         locations = self.locations(repositories={"folderless": {}, "disabled": {"artifact_root": self.home / "docs"}})
#         report = locations.repositories_reply()
#         self.assertEqual([row["name"] for row in report["repositories"]], ["disabled", "folderless"])
#         self.assertTrue(all(row["enabled"] is False for row in report["repositories"]))
#         self.assertNotIn("fault", report["repositories"][0])
#         self.assertIn("fault", report["repositories"][1])
#         self.assert_refused(locations.named("folderless")[0].require_folders, code="settings")
#         report["repositories"][0]["documents"]["folder"] = "changed"
#         self.assertEqual(locations.repositories_reply()["repositories"][0]["documents"]["folder"], str(self.home / "docs"))
#         json.dumps(locations.repositories_reply(), allow_nan=False)
#         with self.assertRaises(FrozenInstanceError):
#             locations.repositories[0].name = "changed"
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_relative_paths_that_follow_symlinks_outside_roots_are_local_faults
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Relative paths that follow symlinks outside roots are local faults.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_relative_paths_that_follow_symlinks_outside_roots_are_local_faults(self):
#         code, documents, outside = self.home / "code", self.home / "docs", self.home / "outside"
#         code.mkdir()
#         documents.mkdir()
#         outside.mkdir()
#         (code / "escape").symlink_to(outside, target_is_directory=True)
#         (documents / "escape").symlink_to(outside, target_is_directory=True)
#         locations = self.locations(repositories={"bad-code": {"code_root": code, "code_subdirs": ["escape/src"]},
#                                                    "bad-evaluation": {"artifact_root": documents, "evaluation": "escape/questions.json"},
#                                                    "good": {"code_root": code, "code_subdirs": ["src"]}})
#         self.assertIn("outside code_root", locations.named("bad-code")[0].fault)
#         self.assertIn("outside artifact_root", locations.named("bad-evaluation")[0].fault)
#         locations.named("good")[0].require_folders()
#         self.assertIsNone(locations.named("good")[0].fault)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_explicit_roots_are_configured_paths_and_do_not_need_existing_files
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Explicit roots are configured paths and do not need existing files.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_explicit_roots_are_configured_paths_and_do_not_need_existing_files(self):
#         locations = self.locations(repositories={"future": {"code_root": self.home / "not-created"},
#                                                    "documents-only": {"artifact_root": self.home / "docs"},
#                                                    "bad-subdir": {"artifact_root": self.home / "docs", "code_subdirs": ["src"]},
#                                                    "bad-evaluation": {"code_root": self.home / "code", "evaluation": "questions.json"}})
#         for name in ("future", "documents-only"):
#             locations.named(name)[0].require_folders()
#         self.assertIn("requires a code_root", locations.named("bad-subdir")[0].fault)
#         self.assertIn("requires an artifact_root", locations.named("bad-evaluation")[0].fault)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_physical_path_resolution_handles_cwd_aliases_without_path_prefix_tricks
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Physical path resolution handles cwd aliases without path prefix tricks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_physical_path_resolution_handles_cwd_aliases_without_path_prefix_tricks(self):
#         code = self.home / "physical"
#         code.mkdir()
#         alias = self.home / "alias"
#         alias.symlink_to(code, target_is_directory=True)
#         locations = self.locations(repositories={"project": {"code_root": alias}})
#         self.assertEqual(self.names(locations.resolve_scope(cwd=code / "src")), ("project",))
#         self.assertEqual(self.names(locations.resolve_scope(cwd=alias / "src")), ("project",))
#         self.assertEqual(locations.repositories_reply()["repositories"][0]["code"]["folder"], str(alias))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_scope.py::ScopeTests.test_resolution_uses_loaded_snapshot_without_re_read_store_process_or_file_mutation
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Resolution uses loaded snapshot without re read store process or file mutation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_scope.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_resolution_uses_loaded_snapshot_without_re_read_store_process_or_file_mutation(self):
#         locations = self.locations(repositories={"project": {"enabled": True, "code_root": self.home / "project"}})
#         before = locations.snapshot.file.read_bytes()
#         with patch.object(Path, "read_bytes", side_effect=AssertionError("settings re-read")), \
#                 patch("subprocess.run", side_effect=AssertionError("process started")), \
#                 patch.object(Path, "write_text", side_effect=AssertionError("file written")):
#             self.assertEqual(self.names(locations.resolve_scope(["project"])), ("project",))
#             self.assertEqual(self.names(locations.resolve_scope(cwd=self.home / "project/src")), ("project",))
#             self.assertEqual(len(locations.repositories_reply()["repositories"]), 1)
#         self.assertEqual(locations.snapshot.file.read_bytes(), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
