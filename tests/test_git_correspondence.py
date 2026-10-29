# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Private Git fixtures for read-only rename evidence; no store acceptance."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from mycel import _git_correspondence as correspondence
from mycel._capture import FileAlias


class GitCorrespondenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mycel_git_correspondence_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.git('init', '--initial-branch=fixture-main')

    def git(self, *arguments):
        reply = subprocess.run(['/usr/bin/git', *arguments], cwd=self.base, capture_output=True,
            check=True, timeout=10, env={**os.environ, 'PATH': '/usr/bin:/bin',
                'LC_ALL': 'C', 'GIT_TERMINAL_PROMPT': '0'})
        return reply.stdout.decode().strip()

    def commit(self):
        self.git('add', '--all')
        self.git('commit', '--message', 'Fixture')
        return self.git('rev-parse', 'HEAD')

    def snapshot(self, commit, path, raw):
        info = self.base.stat()
        return correspondence.GitFileSnapshot(correspondence.GitPlace(str(self.base),
            (info.st_dev, info.st_ino), path), commit, raw, (FileAlias('code', path),))

    def rename(self, raw=b'# Guide\nExact complete text.\n'):
        old, new = 'old name.md', 'new name.md'
        (self.base / old).write_bytes(raw)
        first = self.commit()
        (self.base / old).unlink()
        (self.base / new).write_bytes(raw)
        second = self.commit()
        return self.snapshot(first, old, raw), self.snapshot(second, new, raw)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
