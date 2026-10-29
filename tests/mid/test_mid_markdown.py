"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_markdown as _support
from test_markdown import (split_markdown)


class MarkdownTests(_support.MarkdownTests):


# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_bom_crlf_non_ascii_and_missing_final_newline_have_exact_source_spans
    def test_bom_crlf_non_ascii_and_missing_final_newline_have_exact_source_spans(self):
        source = "\ufeff---\r\nrole: authored\r\n---\r\n前書き\r\n\r\n# Café\r\n本文".encode("utf-8")
        document = split_markdown(source)
        self.assertEqual(document.frontmatter_span.line_end, 3)
        self.assertEqual(document.chunks[0].text, "前書き\r\n\r\n")
        self.assertEqual(document.chunks[1].text, "# Café\r\n本文")
        self.assertEqual((document.chunks[1].span.line_start, document.chunks[1].span.line_end), (6, 7))
        self.assertEqual(document.chunks[1].span.byte_end, len(source))
        self.assert_exact(document)
        bom_heading = split_markdown("\ufeff# Title\nBody")
        self.assertEqual(bom_heading.chunks[0].name, "Title")
        self.assert_exact(bom_heading)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_bom_crlf_non_ascii_and_missing_final_newline_have_exact_source_spans


# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_safe_yaml_refuses_object_construction_and_recursive_aliases_with_no_partial_metadata
    def test_safe_yaml_refuses_object_construction_and_recursive_aliases_with_no_partial_metadata(self):
        cases = ("---\nrole: !!python/object/apply:os.system ['unexpected']\n---\n# Title\n",
                 "---\nvalue: &loop [*loop]\n---\n# Title\n")
        for source in cases:
            document = split_markdown(source)
            self.assertFalse(document.frontmatter_valid)
            self.assertEqual(document.frontmatter, {})
            self.assertEqual(len(document.diagnostics), 1)
            self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_safe_yaml_refuses_object_construction_and_recursive_aliases_with_no_partial_metadata
