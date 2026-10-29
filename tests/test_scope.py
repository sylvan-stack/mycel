# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Repository membership and scope with private folders and exact names."""
from dataclasses import FrozenInstanceError
import os
from unittest.mock import patch


import json
import tempfile
import unittest
from pathlib import Path

from mycel._errors import MycelError
from mycel._scope import RepositoryLocations
from mycel._settings import load_settings


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.counter = 0

    def checkout(self, organization, name, *, worktree=False):
        folder = self.home / organization / name
        folder.mkdir(parents=True)
        marker = folder / ".git"
        if worktree:
            marker.write_text("gitdir: /private/worktree-metadata\n")
        else:
            marker.mkdir()
        return folder

    def locations(self, organizations=None, repositories=None):
        self.counter += 1
        path = self.home / f"settings-{self.counter}.toml"
        content = '[store]\naddress = "postgresql://mycel@localhost/mycel"\n'
        for name, value in (organizations or {}).items():
            content += f"\n[organizations.{json.dumps(name)}]\n"
            for key, member in value.items():
                content += f"{key} = {json.dumps(str(member))}\n"
        for name, value in (repositories or {}).items():
            content += f"\n[repos.{json.dumps(name)}]\n"
            for key, member in value.items():
                if isinstance(member, Path):
                    member = str(member)
                content += f"{key} = {json.dumps(member)}\n"
        path.write_text(content)
        return RepositoryLocations(load_settings(path=path, home=self.home))

    def names(self, repositories):
        return tuple(repository.name for repository in repositories)

    def assert_refused(self, function, *, code=None):
        with self.assertRaises(MycelError) as raised:
            function()
        if code is not None:
            self.assertEqual(raised.exception.code, code)
        return raised.exception


# Archived complete imports; restore needed names in their original scope, not at this file tail.
