"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_architecture as _support
from test_architecture import (
    ArchitectureTests,
    Path,
    ROOT,
    ast,
    help_reply,
    json,
    tomllib,
    unittest,
)


class ArchitectureTests(_support.ArchitectureTests):
# TEST-TIER-BEGIN tests/test_architecture.py::ArchitectureTests.test_product_surface_is_one_independent_cli
    def test_product_surface_is_one_independent_cli(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["scripts"], {"mycel": "mycel._cli:main"})
        public = ast.parse((ROOT / "src/mycel/__init__.py").read_text())
        self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                              ast.ClassDef, ast.Assign)) for node in public.body))
        for path in (ROOT / "src/mycel").glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name.split(".")[0] in {"arbol", "infer", "watchdog"}
                                     for name in imports), str(path))
        commands = {command["name"] for command in help_reply()["commands"]}
        self.assertTrue(commands.isdisjoint({"serve", "daemon", "watch", "schedule", "worktree"}))
# TEST-TIER-END tests/test_architecture.py::ArchitectureTests.test_product_surface_is_one_independent_cli

# TEST-TIER-BEGIN tests/test_architecture.py::ArchitectureTests.test_program_version_matches_package_metadata
    def test_program_version_matches_package_metadata(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual(help_reply()["version"], version)
        self.assertEqual(json.loads((ROOT / "package.json").read_text())["version"], version)
# TEST-TIER-END tests/test_architecture.py::ArchitectureTests.test_program_version_matches_package_metadata
