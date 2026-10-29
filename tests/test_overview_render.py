# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Offline proofs for the deterministic, complete structural outline."""
import unittest
from types import SimpleNamespace

from mycel._code import chunk_code
from mycel._disk_reconciliation import _metadata
from mycel._overview_render import OverviewFile, OverviewSymbol


def parsed(path, source):
    chunks = chunk_code(path, source)
    result = []
    for index, chunk in enumerate(chunks):
        metadata = _metadata(SimpleNamespace(parsed=chunks), index)
        span = chunk.declaration_name_span
        display = None
        if span is not None:
            leaf = chunk.text.encode()[span[0]:span[1]].decode()
            family = metadata.get('family')
            display = leaf if family is None else family + '.' + leaf
        result.append(OverviewSymbol(chunk.symbol, chunk.kind, chunk.byte_start,
                                     metadata.get('family'), display))
    return OverviewFile(path, tuple(result))


class OverviewRenderTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
