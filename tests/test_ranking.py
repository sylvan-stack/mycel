# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Independent fixtures for accepted ranking constants and ordering rules."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from mycel._ranking import RankingGraph, rank_repository
from mycel._retrieval import RetrievalChunk
from mycel._retrieval_store import RepositoryCandidates
from mycel._settings import load_settings


def chunk(identifier, *, cosine=None, repository="orchard", path=None,
          name="step", root="code", origin="code", kind="function", **values):
    vectors = () if cosine is None else ((cosine, math.sqrt(max(0.0, 1 - cosine ** 2))),)
    values.setdefault("fully_embedded", cosine is not None)
    values.setdefault("part_vectors", vectors)
    return RetrievalChunk(identifier, 1, repository, root, path or identifier + ".py",
                          name, kind, origin, "", **values)


def document(identifier, cosine=None, **values):
    values.setdefault("root", "artifact")
    values.setdefault("path", identifier + ".md")
    return chunk(identifier, cosine=cosine, origin="documents", kind="section", **values)


def candidates(chunks, *, meaning=(), wording=()):
    return RepositoryCandidates("orchard", tuple(chunks), tuple(meaning), tuple(wording),
                                sum(not item.fully_embedded for item in chunks))


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.settings = self.load()

    def load(self, *, orchard_patterns="", handbook_patterns=""):
        source = f'''[store]
address = "postgresql://mycel@localhost/mycel"
[repos.orchard]
enabled = true
code_root = {json.dumps(str(self.home / "orchard"))}
artifact_root = {json.dumps(str(self.home / "orchard-docs"))}
{orchard_patterns}
[repos.handbook]
enabled = true
artifact_root = {json.dumps(str(self.home / "handbook"))}
{handbook_patterns}
[search]
shared_documents = [{{repo="handbook", paths=["visible"]}}]
'''
        path = self.home / "settings.toml"
        path.write_text(source)
        settings = load_settings(path=path, home=self.home)
        settings.require_valid()
        return settings

    def rank(self, query, inputs, graph=RankingGraph(), vector=(1.0, 0.0), **options):
        return rank_repository(self.settings, query, inputs, graph, vector, **options)

    def by_id(self, reply):
        return {entry.chunk.identifier: entry for entry in reply.results}



# Archived complete imports; restore needed names in their original scope, not at this file tail.
