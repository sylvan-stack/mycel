"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_architecture as _support
# from test_architecture import (
#     ArchitectureTests,
#     Path,
#     ROOT,
#     unittest,
# )


# class ArchitectureTests(_support.ArchitectureTests):
# TEST-TIER-DISABLED-BEGIN tests/test_architecture.py::ArchitectureTests.test_product_surface_is_one_independent_cli
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
# TEST-TIER-DISABLED-END tests/test_architecture.py::ArchitectureTests.test_product_surface_is_one_independent_cli

# TEST-TIER-DISABLED-BEGIN tests/test_architecture.py::ArchitectureTests.test_program_version_matches_package_metadata
#     def test_program_version_matches_package_metadata(self):
#         version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
#         self.assertEqual(help_reply()["version"], version)
#         self.assertEqual(json.loads((ROOT / "package.json").read_text())["version"], version)
# TEST-TIER-DISABLED-END tests/test_architecture.py::ArchitectureTests.test_program_version_matches_package_metadata


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_architecture.py:1
# import ast
# TEST-TIER-IMPORTS-END tests/test_architecture.py:1

# TEST-TIER-IMPORTS-BEGIN tests/test_architecture.py:2
# import json
# TEST-TIER-IMPORTS-END tests/test_architecture.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_architecture.py:4
# import tomllib
# TEST-TIER-IMPORTS-END tests/test_architecture.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_architecture.py:7
# from mycel._commands import help_reply
# TEST-TIER-IMPORTS-END tests/test_architecture.py:7

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
