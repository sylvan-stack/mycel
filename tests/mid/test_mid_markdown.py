"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_markdown as _support
from test_markdown import (
    COMPARISON_REVISION,
    FrozenInstanceError,
    MarkdownDecodeError,
    MarkdownTests,
    Path,
    RequirementWithdrawalTests,
    ResolvedChunk,
    ResolvedFile,
    SettingsSnapshot,
    SourceAddress,
    SourceResolver,
    UNICODE_VERSION,
    _freeze,
    comparison_hash,
    document_comparisons,
    normalize_comparison,
    parse_source_address,
    sha256,
    split_markdown,
    unittest,
    uuid4,
)


class MarkdownTests(_support.MarkdownTests):
# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_nested_sections_own_only_until_next_heading_with_exact_preamble_and_spans
    def test_nested_sections_own_only_until_next_heading_with_exact_preamble_and_spans(self):
        source = "Preface\n\n# Setup\nParent body\n## Database\nChild body\n### Backups\nDeep body\n## Other\nSibling body\n# Finish\n"
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks],
                         ["<preamble>", "Setup", "Setup > Database", "Setup > Database > Backups", "Setup > Other", "Finish"])
        self.assertEqual([chunk.text for chunk in document.chunks],
                         ["Preface\n\n", "# Setup\nParent body\n", "## Database\nChild body\n",
                          "### Backups\nDeep body\n", "## Other\nSibling body\n", "# Finish\n"])
        self.assertEqual([(chunk.span.line_start, chunk.span.line_end) for chunk in document.chunks],
                         [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 11)])
        self.assertEqual(document.chunks[1].body, "Parent body\n")
        self.assertEqual(document.chunks[2].heading_path, ("Setup", "Database"))
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_nested_sections_own_only_until_next_heading_with_exact_preamble_and_spans

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_backtick_and_tilde_fences_hide_headings_and_need_matching_long_enough_closers
    def test_backtick_and_tilde_fences_hide_headings_and_need_matching_long_enough_closers(self):
        source = ("# Real\n````python\n# Hidden\n```\n## Still hidden\n~~~~\n### Still hidden\n````\n"
                  "## Visible\n~~~ shell\n# Hidden tilde\n```\n~~~~ text\n# Still hidden\n~~~~\n# End\n")
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "Real > Visible", "End"])
        self.assertIn("## Still hidden", document.chunks[0].body)
        self.assertIn("# Still hidden", document.chunks[1].body)
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_backtick_and_tilde_fences_hide_headings_and_need_matching_long_enough_closers

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_unclosed_fence_keeps_remaining_source_in_one_section
    def test_unclosed_fence_keeps_remaining_source_in_one_section(self):
        document = split_markdown("# Start\n~~~\n# Not a heading\nEnd without closer")
        self.assertEqual(len(document.chunks), 1)
        self.assertEqual(document.chunks[0].name, "Start")
        self.assertIn("# Not a heading", document.chunks[0].body)
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_unclosed_fence_keeps_remaining_source_in_one_section

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_list_and_quote_container_fences_hide_pseudoheadings_and_close_in_their_container
    def test_list_and_quote_container_fences_hide_pseudoheadings_and_close_in_their_container(self):
        containers = (("- ", "  "), ("1. ", "   "), ("12) ", "    "),
                      ("> ", "> "), ("> > ", "> > "),
                      ("> - ", ">   "), ("- > ", "  > "),
                      ("> > 1. ", "> >    "), ("- - ", "    "))
        for newline in ("\n", "\r\n", "\r"):
            for opener, continuation in containers:
                for fence in ("```", "~~~~"):
                    with self.subTest(newline=repr(newline), opener=opener, fence=fence):
                        source = newline.join(("# Real", opener + fence + "python", continuation + "# Hidden",
                                               continuation + "## Also hidden", continuation + fence + fence[0], "# End", ""))
                        document = split_markdown(source)
                        self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
                        self.assertEqual(document.chunks[1].span.line_start, 6)
                        self.assertIn("# Hidden", document.chunks[0].body)
                        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_list_and_quote_container_fences_hide_pseudoheadings_and_close_in_their_container

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_inherited_list_fences_and_unclosed_container_fences_end_at_container_boundaries
    def test_inherited_list_fences_and_unclosed_container_fences_end_at_container_boundaries(self):
        cases = ("# Real\n- item\n\n  ```\n  # Hidden\n  ```\n# End\n",
                 "# Real\n- item\n  - child\n    ```\n    # Hidden\n    ```\n# End\n",
                 "# Real\n- ```\n  # Hidden\n# End\n",
                 "# Real\n> ```\n> # Hidden\n# End\n",
                 "# Real\n- > ```\n  > # Hidden\n# End\n",
                 "# Real\n> - ```\n>   # Hidden\n# End\n")
        for source in cases:
            with self.subTest(source=source):
                document = split_markdown(source)
                self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
                self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_inherited_list_fences_and_unclosed_container_fences_end_at_container_boundaries

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_opaque_html_comments_raw_tags_processing_declarations_and_cdata_hide_headings
    def test_opaque_html_comments_raw_tags_processing_declarations_and_cdata_hide_headings(self):
        pairs = (("<!--", "-->"), ("<pre>", "</pre>"), ("<ScRiPt>", "</sCrIpT>"),
                 ("<style type='text/css'>", "</style>"), ("<textarea>", "</textarea>"),
                 ("<?php", "?>"), ("<!DOCTYPE html", ">"), ("<![CDATA[", "]]>"))
        for newline in ("\n", "\r\n", "\r"):
            for opening, closing in pairs:
                with self.subTest(newline=repr(newline), opening=opening):
                    source = newline.join(("# Real", opening, "# Hidden", "Title hidden", "---", "```", closing, "# End", ""))
                    document = split_markdown(source)
                    self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
                    self.assertEqual(document.chunks[1].span.line_start, 8)
                    self.assertIn(opening, document.chunks[0].body)
                    self.assert_exact(document)
        source = "# Real\n- <pre>\n  # Hidden\n  </pre>\n# End\n"
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_opaque_html_comments_raw_tags_processing_declarations_and_cdata_hide_headings

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_html_blank_terminated_blocks_end_on_blank_lines_and_single_line_blocks_end_immediately
    def test_html_blank_terminated_blocks_end_on_blank_lines_and_single_line_blocks_end_immediately(self):
        for tag in ("div", "table", "custom-element"):
            source = ("# Real\n<" + tag + " data='a>b'>\n# Hidden\n</" + tag
                      + ">\n# Still hidden\n\n# End\n")
            with self.subTest(tag=tag):
                document = split_markdown(source)
                self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
                self.assertIn("# Still hidden", document.chunks[0].body)
                self.assert_exact(document)
        for block in ("<!-- one line -->", "<pre>one line</pre>", "<?php ?>", "<!DOCTYPE html>", "<![CDATA[one line]]>"):
            source = "# Real\n" + block + "\n# End\n"
            document = split_markdown(source)
            self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
            self.assert_exact(document)
        # Four-space indentation is code rather than an HTML block opener.
        source = "# Real\n    <!--\n# End\n"
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_html_blank_terminated_blocks_end_on_blank_lines_and_single_line_blocks_end_immediately

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_incomplete_html_attribute_text_does_not_hide_later_headings_or_discard_long_lines
    def test_incomplete_html_attribute_text_does_not_hide_later_headings_or_discard_long_lines(self):
        source = "# Real\n<custom-element " + " " * 100000 + "!\n# End\n"
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks], ["Real", "End"])
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_incomplete_html_attribute_text_does_not_hide_later_headings_or_discard_long_lines

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_atx_syntax_handles_indentation_closing_marks_empty_titles_and_escaped_marks
    def test_atx_syntax_handles_indentation_closing_marks_empty_titles_and_escaped_marks(self):
        source = ("#no separator\n####### Seven\n    # Indented code\n\t# Tab code\n"
                  "   ## Title ###  \nBody\n# ###\n# Escaped \\#\n# Literal#\n# Nonclosing # text\n")
        document = split_markdown(source)
        self.assertEqual([chunk.title for chunk in document.chunks], [None, "Title", "", "Escaped \\#", "Literal#", "Nonclosing # text"])
        self.assertEqual(document.chunks[1].heading_level, 2)
        self.assertEqual(document.chunks[1].text, "   ## Title ###  \nBody\n")
        self.assertEqual(document.chunks[2].body, "")
        self.assertEqual(document.chunks[2].title_hash, sha256(b"").hexdigest())
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_atx_syntax_handles_indentation_closing_marks_empty_titles_and_escaped_marks

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_setext_heading_lines_are_excluded_from_body_and_keep_multiline_title
    def test_setext_heading_lines_are_excluded_from_body_and_keep_multiline_title(self):
        source = "Preface\n\nTop title\ncontinued\n===\nBody\n\nChild\n---\nChild body\n\n---\nThematic body\n"
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks], ["<preamble>", "Top title continued", "Top title continued > Child"])
        self.assertEqual(document.chunks[1].heading_end_line, 5)
        self.assertEqual(document.chunks[1].body, "Body\n\n")
        self.assertEqual(document.chunks[2].body, "Child body\n\n---\nThematic body\n")
        self.assertEqual(document.chunks[1].title_hash, comparison_hash("Top title continued"))
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_setext_heading_lines_are_excluded_from_body_and_keep_multiline_title

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_link_reference_definitions_are_not_setext_heading_paragraphs
    def test_link_reference_definitions_are_not_setext_heading_paragraphs(self):
        for source, expected in (
            ("[foo]: /url\n---\n# Next\n", ["<preamble>", "Next"]),
            ("[foo]: /url\n===\n# Next\n", ["<preamble>", "Next"]),
            ("[foo]: /url\nbar\n===\nBody\n", ["<preamble>", "bar"]),
            ("[foo]: /url\n[other]: /other\nbar\n---\nBody\n", ["<preamble>", "bar"]),
        ):
            with self.subTest(source=source):
                document = split_markdown(source)
                self.assertEqual([chunk.name for chunk in document.chunks], expected)
                self.assertTrue(document.chunks[0].text.startswith("[foo]: /url\n"))
                if expected[-1] == "bar":
                    self.assertEqual(document.chunks[-1].body, "Body\n")
                    self.assertEqual(document.chunks[-1].title_hash, comparison_hash("bar"))
                self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_link_reference_definitions_are_not_setext_heading_paragraphs

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_complete_reference_destinations_labels_and_optional_titles_are_consumed_before_setext
    def test_complete_reference_destinations_labels_and_optional_titles_are_consumed_before_setext(self):
        definitions = ("[foo]:\n  </url>\n",
                       "[foo]: /url\n\"Title\"\n",
                       "[foo]: /url 'Title'\n",
                       "[foo]: /url (Title)\n",
                       "[long\nlabel]: /url\n",
                       "[f\\]oo]: /url(a(b))\n",
                       "[foo]: /url\n\"Multiline\n# still title text\nend\"\n")
        for newline in ("\n", "\r\n", "\r"):
            for definition in definitions:
                source = (definition + "bar\n===\nBody\n").replace("\n", newline)
                with self.subTest(definition=definition, newline=repr(newline)):
                    document = split_markdown(source)
                    self.assertEqual([chunk.name for chunk in document.chunks], ["<preamble>", "bar"])
                    self.assertEqual(document.chunks[0].text, definition.replace("\n", newline))
                    self.assertEqual(document.chunks[1].span.line_start, definition.count("\n") + 1)
                    self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_complete_reference_destinations_labels_and_optional_titles_are_consumed_before_setext

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_invalid_definitions_and_failed_title_lookahead_keep_ordinary_heading_text
    def test_invalid_definitions_and_failed_title_lookahead_keep_ordinary_heading_text(self):
        for source, names in (
            ("[foo]: /url extra\n---\n", ["[foo]: /url extra"]),
            ("[foo]: /url \"unclosed\n---\n", ["[foo]: /url \"unclosed"]),
            ("paragraph\n[foo]: /url\n---\n", ["paragraph [foo]: /url"]),
            ("[foo]: /url\n\"unclosed\n---\n", ["<preamble>", "\"unclosed"]),
            ("[foo]: /url\n\"title\" trailing\n---\n", ["<preamble>", "\"title\" trailing"]),
        ):
            with self.subTest(source=source):
                document = split_markdown(source)
                self.assertEqual([chunk.name for chunk in document.chunks], names)
                self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_invalid_definitions_and_failed_title_lookahead_keep_ordinary_heading_text

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_indented_paragraph_continuations_remain_part_of_multiline_setext_titles
    def test_indented_paragraph_continuations_remain_part_of_multiline_setext_titles(self):
        for newline in ("\n", "\r\n", "\r"):
            source = newline.join(("Foo", "    bar", "\tbaz", "---", "Body", ""))
            with self.subTest(newline=repr(newline)):
                document = split_markdown(source)
                self.assertEqual([chunk.name for chunk in document.chunks], ["Foo bar baz"])
                self.assertEqual(document.chunks[0].heading_end_line, 4)
                self.assertEqual(document.chunks[0].body, "Body" + newline)
                self.assertEqual(document.chunks[0].title_hash, comparison_hash("Foo bar baz"))
                self.assert_exact(document)
        document = split_markdown("[foo]: /url\nFoo\n    bar\n---\nBody\n")
        self.assertEqual([chunk.name for chunk in document.chunks], ["<preamble>", "Foo bar"])
        self.assertEqual(document.chunks[1].span.line_start, 2)
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_indented_paragraph_continuations_remain_part_of_multiline_setext_titles

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_duplicate_names_reserve_literal_suffixes_before_allocating_numbers
    def test_duplicate_names_reserve_literal_suffixes_before_allocating_numbers(self):
        document = split_markdown("# Setup\n# Setup\n# Setup (2)\n# Setup\n# Setup (3)\n# Setup (2)\n")
        self.assertEqual([chunk.name for chunk in document.chunks],
                         ["Setup", "Setup (4)", "Setup (2)", "Setup (5)", "Setup (3)", "Setup (2) (2)"])
        self.assertEqual(len(set(chunk.name for chunk in document.chunks)), 6)
        self.assertTrue(all(chunk.body == "" for chunk in document.chunks))
        self.assertEqual([chunk.name for chunk in split_markdown(document.source).chunks], [chunk.name for chunk in document.chunks])
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_duplicate_names_reserve_literal_suffixes_before_allocating_numbers

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_duplicate_heading_paths_and_literal_path_separators_never_merge_sections
    def test_duplicate_heading_paths_and_literal_path_separators_never_merge_sections(self):
        source = "# A\n## B\n# A\n## B\n# A > B\n# <preamble>\n"
        document = split_markdown("Leading\n\n" + source)
        self.assertEqual([chunk.name for chunk in document.chunks],
                         ["<preamble>", "A", "A > B", "A (2)", "A > B (2)", "A > B (3)", "<preamble> (2)"])
        self.assertEqual(document.chunks[2].heading_path, ("A", "B"))
        self.assertEqual(document.chunks[5].heading_path, ("A > B",))
        self.assertEqual(len(document.chunks), 7)
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_duplicate_heading_paths_and_literal_path_separators_never_merge_sections

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_untitled_headings_remain_exact_addressable_sections_and_names_do_not_collide
    def test_untitled_headings_remain_exact_addressable_sections_and_names_do_not_collide(self):
        source = ("#\nFirst\n# <untitled>\nLiteral\n#\nSecond\n"
                  "# <untitled> (2)\nReserved\n# Parent\n##\nNested\n"
                  "#\n## Child\nChild\n##\nEmpty nested\n")
        document = split_markdown(source)
        self.assertEqual([chunk.name for chunk in document.chunks],
                         ["<untitled>", "<untitled> (3)", "<untitled> (4)",
                          "<untitled> (2)", "Parent", "Parent > ",
                          "<untitled> (5)", " > Child", " > "])
        self.assertEqual(document.chunks[0].title, "")
        self.assertEqual(document.chunks[0].heading_path, ("",))
        self.assertEqual(document.chunks[0].text, "#\nFirst\n")
        self.assertEqual(document.chunks[0].body, "First\n")
        self.assertEqual(document.chunks[1].title, "<untitled>")
        self.assertEqual(document.chunks[5].heading_path, ("Parent", ""))
        self.assertEqual(document.chunks[8].heading_path, ("", ""))
        self.assert_exact(document)
        self.assertEqual([chunk.name for chunk in split_markdown(document.source).chunks],
                         [chunk.name for chunk in document.chunks])
        fixtures = (document, *(split_markdown(source) for source in
                    (b"#\nBody\n", b"## \r\nBody\r\n", b"# ###\nBody\n",
                     b" \n===\nBody\n", b"\n---\nBody\n", b"Setext\n===\nBody\n")))
        settings = SettingsSnapshot(Path("/fictional/settings.toml"), _freeze({
            "repos": {"fixture": {"enabled": True}}, "store": {}}), True, True)
        for parsed in fixtures:
            with self.subTest(source=parsed.source):
                self.assert_exact(parsed)
                primary = SourceAddress("fixture", "artifact", "untitled.md")
                members = tuple(ResolvedChunk(str(uuid4()), number, chunk.name, "document",
                    chunk.text.encode("utf-8"), chunk.snapshot_hash,
                    (chunk.span.byte_start, chunk.span.byte_end), chunk.title,
                    comparison=document_comparisons(chunk.body, chunk.title or ""),
                    body=chunk.body.encode("utf-8"),
                    body_span=(len(chunk.text.encode("utf-8")) - len(chunk.body.encode("utf-8")),
                               len(chunk.text.encode("utf-8"))))
                    for number, chunk in enumerate(parsed.chunks, 1))
                file = ResolvedFile(str(uuid4()), "fixture", primary, (primary,),
                                    parsed.source, parsed.file_hash, members)
                resolver = SourceResolver(settings, (file,))
                self.assertEqual(resolver.resolve(primary.address).selection.file, file)
                for member in members:
                    address = SourceAddress("fixture", "artifact", "untitled.md", member.name)
                    self.assertEqual(parse_source_address(address.address), address)
                    selection = resolver.resolve(address.address, purpose="endpoint").selection
                    self.assertEqual(selection.members[0].chunk, member)
                if parsed.source in {b" \n===\nBody\n", b"\n---\nBody\n"}:
                    # Setext requires a paragraph: a blank title is preserved
                    # as ordinary preamble rather than an invented heading.
                    self.assertEqual([chunk.title for chunk in parsed.chunks], [None])
                    self.assertEqual([chunk.name for chunk in parsed.chunks], ["<preamble>"])
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_untitled_headings_remain_exact_addressable_sections_and_names_do_not_collide

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_nfkc_unicode_whitespace_normalization_uses_fixed_sha256_vectors
    def test_nfkc_unicode_whitespace_normalization_uses_fixed_sha256_vectors(self):
        self.assertEqual(normalize_comparison("\tＦoo\u00a0bar\n\r\v baz  "), "Foo bar baz")
        self.assertEqual(comparison_hash("\tＦoo\u00a0bar\n\r\v baz  "),
                         "4653841ef41adb4f201cc4e019409e5c2a8fce1fa88e22d6dbf6549e4965c9a1")
        self.assertEqual(comparison_hash("Cafe\u0301"), comparison_hash("Caf\u00e9"))
        self.assertEqual(comparison_hash(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_nfkc_unicode_whitespace_normalization_uses_fixed_sha256_vectors

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_rewrapped_unicode_equivalent_bodies_match_but_exact_text_and_title_changes_differ
    def test_rewrapped_unicode_equivalent_bodies_match_but_exact_text_and_title_changes_differ(self):
        old = split_markdown("# Before\nCafe\u0301 and\nＦoo\u00a0bar\n").chunks[0]
        new = split_markdown("# After\nCaf\u00e9 and Foo bar\n").chunks[0]
        self.assertEqual(old.content_hash, new.content_hash)
        self.assertNotEqual(old.title_hash, new.title_hash)
        self.assertNotEqual(old.snapshot_hash, new.snapshot_hash)
        self.assertNotEqual(old.text, new.text)
        self.assertEqual(old.comparison_revision, COMPARISON_REVISION)
        self.assertEqual(old.unicode_version, UNICODE_VERSION)
        equivalent_title = split_markdown("# Ａfter\nDifferent body\n").chunks[0]
        self.assertEqual(new.title_hash, equivalent_title.title_hash)
        self.assertNotEqual(new.content_hash, equivalent_title.content_hash)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_rewrapped_unicode_equivalent_bodies_match_but_exact_text_and_title_changes_differ

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_safe_yaml_metadata_handles_quotes_inline_lists_comments_and_long_blocks
    def test_safe_yaml_metadata_handles_quotes_inline_lists_comments_and_long_blocks(self):
        source = ("---\nrole: 'authored'\nsources: [\"project:docs/a.md#One\", 'other:src.py#run']\n"
                  "generated: true # YAML comment\nnotes: |\n  retained note\n  # not a Markdown heading\n"
                  + "".join(f"unused-{index}: value\n" for index in range(100))
                  + "---\n# Title\nBody\n")
        document = split_markdown(source)
        self.assertTrue(document.frontmatter_present)
        self.assertTrue(document.frontmatter_valid)
        self.assertEqual(document.frontmatter["role"], "authored")
        self.assertEqual(document.frontmatter["sources"], ("project:docs/a.md#One", "other:src.py#run"))
        self.assertIs(document.frontmatter["generated"], True)
        self.assertEqual(document.frontmatter["unused-99"], "value")
        self.assertEqual(document.frontmatter["notes"], "retained note\n# not a Markdown heading\n")
        self.assertEqual(document.chunks[0].text, "# Title\nBody\n")
        self.assertEqual(document.diagnostics, ())
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_safe_yaml_metadata_handles_quotes_inline_lists_comments_and_long_blocks

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_frontmatter_changes_metadata_and_file_hash_without_changing_chunk_text
    def test_frontmatter_changes_metadata_and_file_hash_without_changing_chunk_text(self):
        first = split_markdown("---\nrole: authored\n---\n# Title\nBody\n")
        second = split_markdown("---\nrole: derived\n---\n# Title\nBody\n")
        self.assertNotEqual(first.frontmatter, second.frontmatter)
        self.assertNotEqual(first.file_hash, second.file_hash)
        self.assertEqual(first.chunks[0].text, second.chunks[0].text)
        self.assertEqual(first.chunks[0].content_hash, second.chunks[0].content_hash)
        self.assertEqual(first.chunks[0].title_hash, second.chunks[0].title_hash)
        self.assertEqual(first.chunks[0].snapshot_hash, second.chunks[0].snapshot_hash)
        self.assertEqual(first.chunks[0].span.byte_start - second.chunks[0].span.byte_start, 1)
        self.assert_exact(first)
        self.assert_exact(second)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_frontmatter_changes_metadata_and_file_hash_without_changing_chunk_text

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

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_empty_frontmatter_and_yaml_end_marker_are_valid_and_only_leading_blocks_parse
    def test_empty_frontmatter_and_yaml_end_marker_are_valid_and_only_leading_blocks_parse(self):
        for source in ("---\n---\n# Title\n", "---\nrole: authored\n...\n# Title\n"):
            document = split_markdown(source)
            self.assertTrue(document.frontmatter_valid)
            self.assertTrue(document.frontmatter_present)
            self.assertEqual(document.chunks[0].name, "Title")
            self.assert_exact(document)
        later = split_markdown("Preamble\n\n---\nrole: authored\n---\n# Title\n")
        self.assertFalse(later.frontmatter_present)
        self.assertEqual(later.frontmatter, {})
        self.assert_exact(later)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_empty_frontmatter_and_yaml_end_marker_are_valid_and_only_leading_blocks_parse

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_malformed_unclosed_non_mapping_and_duplicate_yaml_are_reported_and_retained
    def test_malformed_unclosed_non_mapping_and_duplicate_yaml_are_reported_and_retained(self):
        cases = ("---\nrole: [broken\n---\n# Title\n",
                 "---\nrole: authored\n# No delimiter\n",
                 "---\n- authored\n---\n# Title\n",
                 "---\nrole: authored\nrole: derived\n---\n# Title\n",
                 "---\n1: authored\n---\n# Title\n")
        for source in cases:
            with self.subTest(source=source):
                document = split_markdown(source)
                self.assertTrue(document.frontmatter_present)
                self.assertFalse(document.frontmatter_valid)
                self.assertEqual(len(document.diagnostics), 1)
                self.assertTrue(document.diagnostics[0].code.startswith("frontmatter_"))
                self.assertEqual(document.frontmatter, {})
                self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_malformed_unclosed_non_mapping_and_duplicate_yaml_are_reported_and_retained

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

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_parsed_settings_and_chunk_records_are_immutable_and_dates_stay_text
    def test_parsed_settings_and_chunk_records_are_immutable_and_dates_stay_text(self):
        document = split_markdown("---\nrole: authored\nwhen: 2026-10-09\nsource: &source [one, two]\nsources: *source\n---\n# Title\n")
        self.assertEqual(document.frontmatter["when"], "2026-10-09")
        self.assertIs(document.frontmatter["source"], document.frontmatter["sources"])
        with self.assertRaises(TypeError):
            document.frontmatter["role"] = "derived"
        with self.assertRaises(TypeError):
            document.frontmatter["sources"][0] = "changed"
        with self.assertRaises(FrozenInstanceError):
            document.chunks[0].name = "changed"
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_parsed_settings_and_chunk_records_are_immutable_and_dates_stay_text

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_yaml_anchor_merges_allow_explicit_overrides_and_nested_settings_are_immutable
    def test_yaml_anchor_merges_allow_explicit_overrides_and_nested_settings_are_immutable(self):
        source = ("---\nbase: &base {role: authored, generated: false}\n<<: *base\nrole: derived\n"
                  "extra: !!set {one: null, two: null}\nordered: !!omap [{one: {nested: [value]}}]\n---\n# Title\n")
        document = split_markdown(source)
        self.assertTrue(document.frontmatter_valid)
        self.assertEqual(document.frontmatter["role"], "derived")
        self.assertIs(document.frontmatter["generated"], False)
        self.assertEqual(document.frontmatter["extra"], frozenset({"one", "two"}))
        self.assertEqual(document.frontmatter["ordered"][0][1]["nested"], ("value",))
        with self.assertRaises(TypeError):
            document.frontmatter["ordered"][0][1]["nested"] = "changed"
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_yaml_anchor_merges_allow_explicit_overrides_and_nested_settings_are_immutable

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_empty_files_blank_preambles_and_empty_heading_sections_preserve_all_bytes
    def test_empty_files_blank_preambles_and_empty_heading_sections_preserve_all_bytes(self):
        empty = split_markdown(b"")
        self.assertEqual(empty.chunks, ())
        self.assert_exact(empty)
        whitespace = split_markdown(" \n\n\t")
        self.assertEqual(len(whitespace.chunks), 1)
        self.assertEqual(whitespace.chunks[0].name, "<preamble>")
        self.assertEqual(whitespace.chunks[0].content_hash, comparison_hash(""))
        self.assert_exact(whitespace)
        empty_sections = split_markdown("# One\n## Two\n## Two\n")
        self.assertEqual(len(empty_sections.chunks), 3)
        self.assertEqual([chunk.name for chunk in empty_sections.chunks], ["One", "One > Two", "One > Two (2)"])
        self.assertTrue(all(chunk.body == "" for chunk in empty_sections.chunks))
        self.assert_exact(empty_sections)
        only_settings = split_markdown("---\nrole: authored\n---")
        self.assertEqual(only_settings.chunks, ())
        self.assert_exact(only_settings)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_empty_files_blank_preambles_and_empty_heading_sections_preserve_all_bytes

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_unicode_whitespace_is_body_content_and_does_not_create_markdown_line_boundaries
    def test_unicode_whitespace_is_body_content_and_does_not_create_markdown_line_boundaries(self):
        document = split_markdown("# Title\nBody\u2028# not a new heading\u0085still body\n# End\n")
        self.assertEqual([chunk.name for chunk in document.chunks], ["Title", "End"])
        self.assertEqual(document.chunks[0].span.line_end, 2)
        self.assert_exact(document)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_unicode_whitespace_is_body_content_and_does_not_create_markdown_line_boundaries

# TEST-TIER-BEGIN tests/test_markdown.py::MarkdownTests.test_non_utf8_and_unpaired_surrogates_are_explicit_decode_failures
    def test_non_utf8_and_unpaired_surrogates_are_explicit_decode_failures(self):
        for source in (b"# Title\n\xff", "# Title\n\ud800"):
            with self.assertRaises(MarkdownDecodeError):
                split_markdown(source)
# TEST-TIER-END tests/test_markdown.py::MarkdownTests.test_non_utf8_and_unpaired_surrogates_are_explicit_decode_failures



class RequirementWithdrawalTests(_support.RequirementWithdrawalTests):
# TEST-TIER-BEGIN tests/test_markdown.py::RequirementWithdrawalTests.test_withdrawn_objects_in_an_active_requirement_do_not_withdraw_the_row
    def test_withdrawn_objects_in_an_active_requirement_do_not_withdraw_the_row(self):
        from mycel._markdown import split_markdown
        for text in ('permit a withdrawn Build only when explicitly named',
                     'keep withdrawn IDs reserved', 'allow a mark to be withdrawn'):
            raw = ('---\nstatus: accepted\n---\n# Contract\n\n'
                   '| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n'
                   '| MYC-1.1 <!-- 11111111-2222-4333-8444-555555555555 --> | ' + text + ' | New | unit |\n')
            with self.subTest(text=text):
                self.assertEqual(split_markdown(raw).entities[0].status, 'accepted')
# TEST-TIER-END tests/test_markdown.py::RequirementWithdrawalTests.test_withdrawn_objects_in_an_active_requirement_do_not_withdraw_the_row

# TEST-TIER-BEGIN tests/test_markdown.py::RequirementWithdrawalTests.test_explicit_withdrawal_markers_preserve_the_reserved_entity
    def test_explicit_withdrawal_markers_preserve_the_reserved_entity(self):
        from mycel._markdown import split_markdown
        for text in ('Withdrawn', 'Withdrawn: moved to MYC-14.1',
                     'Withdrawn 8 October 2026; moved to MYC-14.1'):
            raw = ('---\nstatus: accepted\n---\n# Contract\n\n'
                   '| Former requirement | Current requirement |\n|---|---|\n'
                   '| MYC-7.1 <!-- 11111111-2222-4333-8444-555555555555 --> | ' + text + ' |\n')
            with self.subTest(text=text):
                row, = split_markdown(raw).entities
                self.assertEqual((row.id, row.status), ('MYC-7.1', 'withdrawn'))
# TEST-TIER-END tests/test_markdown.py::RequirementWithdrawalTests.test_explicit_withdrawal_markers_preserve_the_reserved_entity
