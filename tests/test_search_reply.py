# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public search contract proofs without stores, providers or file reads."""
from dataclasses import replace
import json

from mycel._errors import MycelError
from mycel._freshness import (ChunkRequirement, DependencyFault, FreshnessResult,
                             FreshnessScope, RepositoryStatus)
from mycel._search_reply import search_reply


import unittest

from mycel._freshness import (
    ChunkRequirement,
    FreshnessResult,
    FreshnessScope,
    RepositoryStatus,
)
from mycel._ranking import RankEntry, RepositoryRanking
from mycel._retrieval import Candidate, RetrievalChunk
from mycel._retrieval_store import RepositoryCandidates


def chunk(identifier, *, root="code", path="src/step.py", name="Policy.step",
          repository="fixture", origin="code", kind="method", version=1, text="def step(): pass\n"):
    return RetrievalChunk(identifier, version, repository, root, path, name, kind, origin, text)


def entry(member, *, via=None, documented=(), meaning_rank=1, wording_rank=2, score=.8):
    return RankEntry(member, score, "scored" if meaning_rank is not None else "wording_tail",
                     meaning_rank, wording_rank, score if meaning_rank is not None else None,
                     .75 if via is not None else None, via, documented)


def candidates(*members, meaning=True):
    return RepositoryCandidates("fixture", tuple(members),
        tuple(Candidate(member, .8) for member in members) if meaning else (),
        tuple(Candidate(member, 1.5) for member in members), len(members))


def ranking(*entries, route="question", meaning=True, without=1):
    return RepositoryRanking("fixture", route, meaning, without, tuple(entries))


def freshness(*members, states=None, finished=True):
    owners = {member.repository for member in members}
    rows = states or tuple(RepositoryStatus(owner, "done") for owner in sorted(owners))
    return FreshnessResult(FreshnessScope(("fixture",)), rows, (), finished, True,
        tuple(row.repository for row in rows if row.status != "done"),
        tuple(ChunkRequirement(member.repository, member.key, (member.repository,)) for member in members))


class SearchReplyTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
