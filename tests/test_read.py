# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Exact-read unit proofs over independently retained source selections."""
from dataclasses import replace

from mycel._errors import MycelError
from mycel._freshness import (ChunkRequirement, DependencyFault, FreshnessResult,
                             FreshnessScope, RepositoryStatus)
from mycel._read import read_chunk, select_chunk


import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress


def chunk(name, text, *, kind="function", title=None, family=None, span=None, number=1):
    raw = text.encode("utf-8")
    return ResolvedChunk(str(uuid4()), number, name, kind, raw, sha256(raw).hexdigest(),
                         span, title, family)


def file(path, text, members, *, root="code", repository="fixture", aliases=()):
    raw = text.encode("utf-8")
    primary = SourceAddress(repository, root, path)
    return ResolvedFile(str(uuid4()), repository, primary, aliases or (primary,), raw,
                        sha256(raw).hexdigest(), tuple(members))


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mycel_exact_read_")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.code, self.artifact = self.home / "code", self.home / "artifact"
        self.code.mkdir()
        self.artifact.mkdir()
        config = self.home / "settings.toml"
        config.write_text('[store]\naddress="postgresql://mycel@localhost/mycel"\n'
            '[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(self.code))
            + '\nartifact_root=' + json.dumps(str(self.artifact))
            + '\n[repos.disabled]\nenabled=false\n', encoding="utf-8")
        self.settings = load_settings(path=config, home=self.home)
        self.settings.require_valid()

    def resolver(self, *files, index=()):
        return SourceResolver(self.settings, tuple(files), index=tuple(index))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
