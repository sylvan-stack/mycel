# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Structural code proofs over exact, complete local source fixtures."""
from importlib.metadata import version
from unittest.mock import patch

from mycel._code import chunk_code, language_for_path


import re
import unittest

from mycel._code import chunk_code


class CodeTests(unittest.TestCase):
    def partition(self, path, source):
        chunks = chunk_code(path, source)
        self.assertTrue(chunks)
        self.assertEqual("".join(chunk.text for chunk in chunks), source)
        self.assertEqual(len({chunk.name for chunk in chunks}), len(chunks))
        raw = source.encode("utf-8")
        cursor = 0
        for chunk in chunks:
            self.assertEqual(chunk.byte_start, cursor)
            self.assertEqual(raw[chunk.byte_start:chunk.byte_end], chunk.text.encode("utf-8"))
            self.assertEqual(chunk.path, path)
            self.assertEqual(chunk.name, path + "#" + chunk.symbol)
            self.assertGreaterEqual(chunk.line_start, 1)
            self.assertGreaterEqual(chunk.line_end, chunk.line_start)
            self.assertEqual(chunk.line_start, len(re.findall(b"\r\n|\r|\n", raw[:chunk.byte_start])) + 1)
            cursor = chunk.byte_end
        self.assertEqual(cursor, len(raw))
        return chunks


# Archived complete imports; restore needed names in their original scope, not at this file tail.
