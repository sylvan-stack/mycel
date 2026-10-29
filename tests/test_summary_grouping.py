# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Offline grouping profile and estimated-level proofs."""

import unittest
from hashlib import sha256

import numpy as np

from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._source_refs import SourceAddress
from mycel._summary_grouping import SummaryNode
from mycel._summary_request import SummarySection


def node(number, vector=(1.0, 0.0), *, path=None, position=None, root="artifact", text=None):
    place = SourceAddress("fixture", root, path or f"{number:04}.md", f"Section{number}")
    position = number if position is None else position
    section = None
    if text is not None:
        raw = text.encode()
        chunk = ResolvedChunk(str(number), 1, place.name, "document", raw, sha256(raw).hexdigest())
        section = SummarySection(SelectionMember(place, chunk), position)
    return SummaryNode(str(number), place, position, vector, section)


class _Mixture:
    def __init__(self, matrix, components, bic, probabilities=None, *, converged=True):
        self.n_components = components
        self.matrix = matrix
        self.score = bic
        self.probabilities = probabilities
        self.converged_ = converged

    def fit(self, matrix):
        self.matrix = matrix
        return self

    def bic(self, matrix):
        return self.score

    def predict_proba(self, matrix):
        if self.probabilities is not None:
            return self.probabilities
        values = np.zeros((len(matrix), self.n_components))
        values[:, 0] = 1
        return values


class SummaryGroupingTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
