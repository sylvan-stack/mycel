# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Lossless document section, YAML and comparison acceptance checks."""

import unittest
from hashlib import sha256


class MarkdownTests(unittest.TestCase):
    def assert_exact(self, document):
        start = document.frontmatter_span.byte_end if document.frontmatter_valid and document.frontmatter_present else 0
        self.assertEqual("".join(chunk.text for chunk in document.chunks).encode("utf-8"), document.source[start:])
        for chunk in document.chunks:
            self.assertEqual(document.source[chunk.span.byte_start:chunk.span.byte_end], chunk.text.encode("utf-8"))
            self.assertEqual(chunk.snapshot_hash, sha256(chunk.text.encode("utf-8")).hexdigest())
        self.assertEqual(document.file_hash, sha256(document.source).hexdigest())




class RequirementWithdrawalTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
