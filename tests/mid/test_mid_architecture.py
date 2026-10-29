
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_architecture.py::ArchitectureTests.test_product_surface_is_one_independent_cli
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Product surface is one independent cli.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_architecture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_product_surface_is_one_independent_cli(self):
#         project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
#         self.assertEqual(project["scripts"], {"mycel": "mycel._cli:main"})
#         public = ast.parse((ROOT / "src/mycel/__init__.py").read_text())
#         self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
#                                               ast.ClassDef, ast.Assign)) for node in public.body))
#         for path in (ROOT / "src/mycel").glob("*.py"):
#             tree = ast.parse(path.read_text())
#             for node in ast.walk(tree):
#                 if isinstance(node, ast.Import):
#                     imports = [alias.name for alias in node.names]
#                 elif isinstance(node, ast.ImportFrom):
#                     imports = [node.module or ""]
#                 else:
#                     continue
#                 self.assertFalse(any(name.split(".")[0] in {"arbol", "infer", "watchdog"}
#                                      for name in imports), str(path))
#         commands = {command["name"] for command in help_reply()["commands"]}
#         self.assertTrue(commands.isdisjoint({"serve", "daemon", "watch", "schedule", "worktree"}))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_architecture.py::ArchitectureTests.test_program_version_matches_package_metadata
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Program version matches package metadata.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_architecture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_program_version_matches_package_metadata(self):
#         version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
#         self.assertEqual(help_reply()["version"], version)
#         self.assertEqual(json.loads((ROOT / "package.json").read_text())["version"], version)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
