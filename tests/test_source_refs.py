# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Document declaration and portable address acceptance, without a store."""
from dataclasses import FrozenInstanceError

from mycel._source_refs import (SourceAddress, SourceAddressError,
                               format_source_address, parse_source_address,
                               read_document_declarations)


import unittest

from mycel._markdown import split_markdown
from mycel._source_refs import parse_source_address, read_document_declarations


class SourceAddressTests(unittest.TestCase):
    pass  # Shared fixtures; case bodies live in top/ and mid/.


class DocumentDeclarationTests(unittest.TestCase):
    def declarations(self, source, file="docs/notes.md"):
        return read_document_declarations(split_markdown(source), file=file)

    def refs(self, declarations):
        return tuple(source for chunk in declarations.chunk_sources for source in chunk.sources)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
