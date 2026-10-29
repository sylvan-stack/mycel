# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Pure whole-file identity decisions; no persistence or automatic pinning."""

import unittest

from mycel._identity import ChunkInput, KnownChunk, KnownVersion
from mycel._markdown import split_markdown


def document(name, body='', *, source=None):
    parsed=split_markdown(source if source is not None else '# '+name+'\n'+body)
    return ChunkInput.document(parsed.chunks[-1])


def known(identifier, chunk, version=1, *, retained=(), current=None):
    versions=(KnownVersion(version,chunk),*retained)
    return KnownChunk(identifier,version if current is None else current,versions)


def identities(plan):
    return {decision.incoming.name:decision.chunk_id for decision in plan.decisions}


class IdentityTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


        # This supplied same-file identity does not infer a genuine file move.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
