import ast
import json
from pathlib import Path
import tomllib
import unittest

from mycel._commands import help_reply


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
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

    def test_program_version_matches_package_metadata(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual(help_reply()["version"], version)
        self.assertEqual(json.loads((ROOT / "package.json").read_text())["version"], version)
