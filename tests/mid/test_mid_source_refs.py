"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_source_refs as _support
from test_source_refs import (
    DocumentDeclarationTests,
    FrozenInstanceError,
    SourceAddress,
    SourceAddressError,
    SourceAddressTests,
    format_source_address,
    parse_source_address,
    read_document_declarations,
    split_markdown,
    unittest,
)


class SourceAddressTests(_support.SourceAddressTests):
# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_qualified_roots_select_distinct_literal_places
    def test_qualified_roots_select_distinct_literal_places(self):
        for root in ("code", "artifact"):
            with self.subTest(root=root):
                address = parse_source_address(f"cellar:@{root}/README.md#Setup")
                self.assertEqual(address, SourceAddress("cellar", root, "README.md", "Setup"))
                self.assertEqual(address.address, f"cellar:@{root}/README.md#Setup")
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_qualified_roots_select_distinct_literal_places

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_unicode_spaces_delimiters_and_percent_canonicalize_once
    def test_unicode_spaces_delimiters_and_percent_canonicalize_once(self):
        address = parse_source_address("café%3A案:@artifact/docs/naïve%23plan%25.md#Limits > Ω%3A%23%25/名")
        self.assertEqual((address.repository, address.path, address.name),
                         ("café:案", "docs/naïve#plan%.md", "Limits > Ω:#%/名"))
        canonical = "caf%C3%A9%3A%E6%A1%88:@artifact/docs/na%C3%AFve%23plan%25.md#Limits%20%3E%20%CE%A9%3A%23%25%2F%E5%90%8D"
        self.assertEqual(format_source_address(address), canonical)
        self.assertEqual(parse_source_address(canonical), address)
        self.assertEqual(format_source_address(parse_source_address(canonical)), canonical)
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_unicode_spaces_delimiters_and_percent_canonicalize_once

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_lowercase_escapes_format_uppercase_with_all_unreserved_ascii_unchanged
    def test_lowercase_escapes_format_uppercase_with_all_unreserved_ascii_unchanged(self):
        address = parse_source_address("a-z_A.Z~09:@code/na%c3%afve%20x.py#%e2%82%ac")
        self.assertEqual(address.address, "a-z_A.Z~09:@code/na%C3%AFve%20x.py#%E2%82%AC")
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_lowercase_escapes_format_uppercase_with_all_unreserved_ascii_unchanged

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_no_unicode_normalization_or_case_folding
    def test_no_unicode_normalization_or_case_folding(self):
        composed = parse_source_address("Répo:@code/café.py#ABC")
        decomposed = parse_source_address("Répo:@code/café.py#abc")
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(parse_source_address(composed.address), composed)
        self.assertEqual(parse_source_address(decomposed.address), decomposed)
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_no_unicode_normalization_or_case_folding

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_legacy_percent_sequences_and_spaces_are_literal_and_have_no_guessed_root
    def test_legacy_percent_sequences_and_spaces_are_literal_and_have_no_guessed_root(self):
        for ref in ("repo:docs/a%20b.md#Limits > Backoff", "repo:src/%ZZ.py#%2F",
                    "répo:docs/猫.md#A#B", "repo:summaries#1/7", "repo:overview#src/net"):
            with self.subTest(ref=ref):
                address = parse_source_address(ref)
                self.assertIsNone(address.root)
                self.assertEqual(address.address, ref)
        self.assertEqual(parse_source_address("repo:docs/a%20b.md").path, "docs/a%20b.md")
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_legacy_percent_sequences_and_spaces_are_literal_and_have_no_guessed_root

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_reserved_prefixes_and_real_folders_are_explicit
    def test_reserved_prefixes_and_real_folders_are_explicit(self):
        address = parse_source_address("repo:@code/@code/file.md")
        self.assertEqual((address.root, address.path), ("code", "@code/file.md"))
        self.assertEqual(address.address, "repo:@code/%40code/file.md")
        self.assertEqual(parse_source_address("repo:@Code/file.md").root, None)
        self.assertEqual(parse_source_address("repo:@code%2Ffile.md").path, "@code%2Ffile.md")
        self.assertEqual(parse_source_address("repo:@code").path, "@code")
        with self.assertRaises(SourceAddressError):
            format_source_address(SourceAddress("repo", None, "@artifact/file.md"))
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_reserved_prefixes_and_real_folders_are_explicit

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_index_namespaces_and_name_paths
    def test_index_namespaces_and_name_paths(self):
        for ref, name, canonical in (("repo:@index/summaries#1/7", "1/7", "repo:@index/summaries#1%2F7"),
                                     ("repo:@index/overview#src/net", "src/net", "repo:@index/overview#src%2Fnet")):
            address = parse_source_address(ref)
            self.assertEqual((address.root, address.name, address.address), ("index", name, canonical))
        for path in ("other", "Summaries", "summaries/node", "overview/", ""):
            with self.subTest(path=path), self.assertRaises(SourceAddressError):
                parse_source_address("repo:@index/" + path)
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_index_namespaces_and_name_paths

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_encoded_separator_traversal_and_backslashes_are_refused
    def test_encoded_separator_traversal_and_backslashes_are_refused(self):
        paths = ("/absolute", "a//b", "a/", ".", "..", "a/../b", "a/./b", "a\\b",
                 "%2e%2e/b", "a/%2E/b", "a%2fb", "a%2Fb", "%2fabsolute", "a%5Cb", "%00")
        for path in paths:
            with self.subTest(path=path), self.assertRaises(SourceAddressError) as error:
                parse_source_address("repo:@code/" + path)
            self.assertEqual(error.exception.fault, "not_a_ref")
        for path in ("/absolute", "a//b", "a/", ".", "..", "a/../b", "a\\b"):
            with self.subTest(legacy=path), self.assertRaises(SourceAddressError):
                parse_source_address("repo:" + path)
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_encoded_separator_traversal_and_backslashes_are_refused

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_malformed_utf8_escapes_empty_components_and_controls_are_visible
    def test_malformed_utf8_escapes_empty_components_and_controls_are_visible(self):
        refs = ("", "no separator", ":path", "repo:", "repo:path#", "repo:@code/", "repo:@code/path#",
                "repo:@code/%", "repo:@code/%0", "repo:@code/%GG", "repo:@code/%FF", "repo:@code/%C0%AF",
                "repo:@code/%ED%A0%80", "repo:@code/%E2%82", "r%ZZ:@code/a", "r:@code/a#%FF",
                "repo:@code/a:b", "repo:@code/a#b:c", "repo:@code/a#b#c", "r#x:@code/a",
                "repo:@code/a%0A", "repo:@code/a#%7F", "repo:@code/a#%C2%85", "repo:path\t", "repo:path\x00",
                "\ud800:@code/a")
        for ref in refs:
            with self.subTest(ref=repr(ref)), self.assertRaises(SourceAddressError) as error:
                parse_source_address(ref)
            self.assertEqual(error.exception.fault, "not_a_ref")
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_malformed_utf8_escapes_empty_components_and_controls_are_visible

# TEST-TIER-BEGIN tests/test_source_refs.py::SourceAddressTests.test_formatter_validates_constructed_addresses_and_dataclass_is_immutable
    def test_formatter_validates_constructed_addresses_and_dataclass_is_immutable(self):
        for address in (SourceAddress("", "code", "a"), SourceAddress("r", "bad", "a"),
                        SourceAddress("r", "artifact", "a//b"), SourceAddress("r", "code", "a", ""),
                        SourceAddress("r", "index", "other"), SourceAddress("r:x", None, "a")):
            with self.subTest(address=address), self.assertRaises(SourceAddressError):
                format_source_address(address)
        address = SourceAddress("repo", "artifact", "file.md", "name")
        with self.assertRaises(FrozenInstanceError):
            address.path = "changed"
# TEST-TIER-END tests/test_source_refs.py::SourceAddressTests.test_formatter_validates_constructed_addresses_and_dataclass_is_immutable



class DocumentDeclarationTests(_support.DocumentDeclarationTests):
# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_quoted_yaml_anchors_flow_sources_and_freeform_heartwood_pins
    def test_quoted_yaml_anchors_flow_sources_and_freeform_heartwood_pins(self):
        declarations = self.declarations("---\nrole: 'derived'\nstatus: \"heartwood\"\nimplemented: 2026-03\n"
                                         "outdated: 'last commit: café'\ngenerated: true\n"
                                         "sources: &refs ['repo:@code/a.py#run', 'repo:docs/a.md#Title']\n"
                                         "other: *refs\n---\n# Notes\nBody\n")
        self.assertEqual(dict(declarations.metadata), {"role": "derived", "heartwood": True,
                                                     "implemented": "2026-03", "outdated": "last commit: café",
                                                     "generated": True,
                                                     "sources": ("repo:@code/a.py#run", "repo:docs/a.md#Title")})
        self.assertEqual((declarations.role, declarations.heartwood, declarations.generated), ("derived", True, True))
        self.assertEqual([source.chunk for source in declarations.frontmatter_sources], ["Notes", "Notes"])
        self.assertEqual(declarations.diagnostics, ())
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_quoted_yaml_anchors_flow_sources_and_freeform_heartwood_pins

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_yaml_false_is_false_and_unrelated_fields_never_set_flags
    def test_yaml_false_is_false_and_unrelated_fields_never_set_flags(self):
        declarations = self.declarations("---\ngenerated: false\nrole: authored\nheartwood: true\n"
                                         "implemented: before\noutdated: after\nunknown: {generated: true}\n---\n# A\n")
        self.assertEqual(dict(declarations.metadata), {"generated": False, "role": "authored"})
        self.assertFalse(declarations.generated)
        self.assertFalse(declarations.heartwood)
        self.assertEqual(declarations.diagnostics, ())
        self.assertEqual(dict(self.declarations("# Plain\n").metadata), {})
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_yaml_false_is_false_and_unrelated_fields_never_set_flags

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_metadata_and_diagnostic_values_remain_immutable
    def test_metadata_and_diagnostic_values_remain_immutable(self):
        declarations = self.declarations("---\nstatus: heartwood\nsources: [repo:a, {bad: [one, two]}]\n---\n# A\n")
        with self.assertRaises(TypeError):
            declarations.metadata["generated"] = True
        with self.assertRaises(TypeError):
            declarations.metadata["sources"][1]["bad"] = ()
        with self.assertRaises(FrozenInstanceError):
            declarations.frontmatter_sources[0].ref = "changed"
        self.assertEqual(declarations.diagnostics[0].key, "sources[1]")
        self.assertEqual(declarations.diagnostics[0].value["bad"], ("one", "two"))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_metadata_and_diagnostic_values_remain_immutable

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_each_known_wrong_value_reports_its_file_and_key
    def test_each_known_wrong_value_reports_its_file_and_key(self):
        declarations = self.declarations("---\nrole: false\nstatus: accepted\ngenerated: 'false'\n"
                                         "implemented: [a, b]\noutdated: {date: yesterday}\nsources: repo:a\n---\n# A\n",
                                         file="docs/invalid.md")
        self.assertEqual({diagnostic.key for diagnostic in declarations.diagnostics},
                         {"role", "status", "generated", "implemented", "outdated", "sources"})
        self.assertTrue(all(diagnostic.file == "docs/invalid.md" and diagnostic.code == "frontmatter_value"
                            for diagnostic in declarations.diagnostics))
        self.assertEqual(dict(declarations.metadata), {})
        for generated in (1, "true", None, [], {}):
            import yaml
            declaration = self.declarations("---\ngenerated: " + yaml.safe_dump(generated).replace("\n...\n", "\n") + "---\n# A\n")
            self.assertTrue(declaration.diagnostics)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_each_known_wrong_value_reports_its_file_and_key

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_unreadable_yaml_is_reported_and_never_trusted_as_metadata_or_sources
    def test_unreadable_yaml_is_reported_and_never_trusted_as_metadata_or_sources(self):
        for source in ("---\nrole: [broken\n<!-- sources:\nrepo:a\n-->\n---\n# A\n",
                       "---\nrole: derived\nrole: authored\n---\n# A\n",
                       "---\nsources: [repo:a]\n<!-- sources: repo:b -->\n"):
            with self.subTest(source=source):
                declarations = self.declarations(source, file="bad.md")
                self.assertEqual(dict(declarations.metadata), {})
                self.assertEqual(self.refs(declarations), ())
                self.assertTrue(declarations.diagnostics)
                self.assertTrue(all(diagnostic.file == "bad.md" for diagnostic in declarations.diagnostics))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_unreadable_yaml_is_reported_and_never_trusted_as_metadata_or_sources

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_frontmatter_sources_attach_to_first_preamble_chunk_only
    def test_frontmatter_sources_attach_to_first_preamble_chunk_only(self):
        declarations = self.declarations("---\nsources: [repo:whole.md]\n---\nPreface\n\n# First\n"
                                         "<!-- sources:\nrepo:one.py#f\nrepo:two.md#A > B\n-->\n"
                                         "## Second\n<!-- sources: repo:three -->\n")
        self.assertEqual([chunk.chunk for chunk in declarations.chunk_sources], ["<preamble>", "First", "First > Second"])
        self.assertEqual([[source.ref for source in chunk.sources] for chunk in declarations.chunk_sources],
                         [["repo:whole.md"], ["repo:one.py#f", "repo:two.md#A > B"], ["repo:three"]])
        self.assertEqual([source.line for source in self.refs(declarations)], [None, 8, 9, 12])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_frontmatter_sources_attach_to_first_preamble_chunk_only

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_malformed_entries_and_duplicate_declarations_are_retained_in_source_order
    def test_malformed_entries_and_duplicate_declarations_are_retained_in_source_order(self):
        declarations = self.declarations("---\nsources: [not a ref, repo:a, repo:a, 'repo:@code/%FF']\n---\n# A\n"
                                         "<!-- sources:\n  repo:a  \n  nonsense  \nrepo:@code/a%2Fb\n\nrepo:a, repo:b\n-->\n")
        refs = self.refs(declarations)
        self.assertEqual([source.ref for source in refs], ["not a ref", "repo:a", "repo:a", "repo:@code/%FF",
                                                         "repo:a", "nonsense", "repo:@code/a%2Fb", "repo:a, repo:b"])
        self.assertEqual([source.fault for source in refs[:7]], ["not_a_ref", None, None, "not_a_ref", None, "not_a_ref", "not_a_ref"])
        self.assertEqual(refs[4].declared, "  repo:a  ")
        self.assertEqual(refs[4].raw_line, "  repo:a  \n")
        self.assertEqual(refs[7].address.path, "a, repo:b")
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_malformed_entries_and_duplicate_declarations_are_retained_in_source_order

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_empty_body_still_retains_frontmatter_declarations_without_inventing_a_chunk
    def test_empty_body_still_retains_frontmatter_declarations_without_inventing_a_chunk(self):
        declarations = self.declarations("---\nsources: [repo:a]\n---\n")
        self.assertEqual(len(declarations.frontmatter_sources), 1)
        self.assertIsNone(declarations.frontmatter_sources[0].chunk)
        self.assertEqual(declarations.chunk_sources, ())
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_empty_body_still_retains_frontmatter_declarations_without_inventing_a_chunk

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_crlf_cr_and_unicode_keep_original_lines_and_do_not_split_unicode_whitespace
    def test_crlf_cr_and_unicode_keep_original_lines_and_do_not_split_unicode_whitespace(self):
        for newline in ("\n", "\r\n", "\r"):
            source = newline.join(("# Ω", "<!-- sources:", "répo:docs/猫.md#A\u2028B", "repo:two", "-->", ""))
            document = split_markdown(source)
            declarations = read_document_declarations(document, file="猫.md")
            refs = self.refs(declarations)
            self.assertEqual([ref.ref for ref in refs], ["répo:docs/猫.md#A\u2028B", "repo:two"])
            self.assertEqual([ref.line for ref in refs], [3, 4])
            self.assertEqual(refs[0].raw_line, "répo:docs/猫.md#A\u2028B" + newline)
            self.assertEqual("".join(chunk.text for chunk in document.chunks), source)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_crlf_cr_and_unicode_keep_original_lines_and_do_not_split_unicode_whitespace

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_backtick_tilde_and_container_fences_hide_comments_until_a_valid_closer
    def test_backtick_tilde_and_container_fences_hide_comments_until_a_valid_closer(self):
        containers = (("", ""), ("- ", "  "), ("1. ", "   "), ("> ", "> "),
                      ("> > ", "> > "), ("> - ", ">   "), ("- > ", "  > "))
        for newline in ("\n", "\r\n"):
            for opening, continuation in containers:
                for marker in ("````", "~~~~"):
                    with self.subTest(opening=opening, marker=marker):
                        source = newline.join(("# A", opening + marker + "text", continuation + "<!-- sources:",
                                               continuation + "repo:hidden", continuation + "-->",
                                               continuation + marker[:3], continuation + "<!-- sources: repo:also_hidden -->",
                                               continuation + marker, "<!-- sources: repo:visible -->", ""))
                        self.assertEqual([source.ref for source in self.refs(self.declarations(source))], ["repo:visible"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_backtick_tilde_and_container_fences_hide_comments_until_a_valid_closer

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_inherited_list_fences_and_container_dedent
    def test_inherited_list_fences_and_container_dedent(self):
        for source in ("# A\n- item\n\n  ```\n  <!-- sources: repo:hidden -->\n  ```\n<!-- sources: repo:visible -->\n",
                       "# A\n> ```\n> <!-- sources: repo:hidden -->\n<!-- sources: repo:visible -->\n",
                       "# A\n- > ```\n  > <!-- sources: repo:hidden -->\n<!-- sources: repo:visible -->\n"):
            with self.subTest(source=source):
                self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))], ["repo:visible"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_inherited_list_fences_and_container_dedent

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_lazy_quote_and_list_paragraphs_keep_code_spans_across_physical_lines
    def test_lazy_quote_and_list_paragraphs_keep_code_spans_across_physical_lines(self):
        for newline in ("\n", "\r\n", "\r"):
            for opening in ("> `open", "- `open", "1. `open", "> - `open", "> > `open"):
                with self.subTest(newline=repr(newline), opening=opening):
                    source = newline.join(("# A", opening,
                                           "continued <!-- sources: repo:hidden -->`", "",
                                           "<!-- sources:", "repo:after", "-->",
                                           "# Outside", "<!-- sources: repo:outside -->", ""))
                    refs = self.refs(self.declarations(source))
                    self.assertEqual([ref.ref for ref in refs], ["repo:after", "repo:outside"])
                    self.assertEqual([ref.line for ref in refs], [6, 9])
                    self.assertEqual([ref.chunk for ref in refs], ["A", "Outside"])
                    self.assertEqual([ref.raw_line for ref in refs],
                                     ["repo:after" + newline, "<!-- sources: repo:outside -->" + newline])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_lazy_quote_and_list_paragraphs_keep_code_spans_across_physical_lines

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_lazy_setext_text_keeps_code_span_but_actual_block_starts_end_it
    def test_lazy_setext_text_keeps_code_span_but_actual_block_starts_end_it(self):
        for newline in ("\n", "\r\n", "\r"):
            for opening in ("> `open", "- `open"):
                source = newline.join(("# A", opening, "===",
                                       "continued <!-- sources: repo:hidden -->`", ""))
                self.assertEqual(self.refs(self.declarations(source)), ())
                source = newline.join(("# A", opening,
                                       "<!-- sources: repo:outside -->`", "",
                                       "# Other", "<!-- sources: repo:heading -->", ""))
                refs = self.refs(self.declarations(source))
                self.assertEqual([ref.ref for ref in refs], ["repo:outside", "repo:heading"])
                self.assertEqual([ref.line for ref in refs], [3, 6])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_lazy_setext_text_keeps_code_span_but_actual_block_starts_end_it

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_inline_code_equal_length_runs_escapes_and_unmatched_backticks
    def test_inline_code_equal_length_runs_escapes_and_unmatched_backticks(self):
        source = ("# A\n`<!-- sources: repo:hidden -->` and <!-- sources: repo:one -->\n\n"
                  "``literal ` <!-- sources: repo:hidden2 --> ``\n\n"
                  "Example `<!-- sources:\nrepo:hidden3\n-->` tail\n\n"
                  "unmatched ` <!-- sources: repo:two -->\n\n"
                  "\\` <!-- sources: repo:three --> \\`\n\n"
                  "<!-- sources: repo:four#tick`name --> then `ordinary code`\n")
        self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))],
                         ["repo:one", "repo:two", "repo:three", "repo:four#tick`name"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_inline_code_equal_length_runs_escapes_and_unmatched_backticks

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_code_spans_do_not_cross_blank_lines_headings_or_html_block_boundaries
    def test_code_spans_do_not_cross_blank_lines_headings_or_html_block_boundaries(self):
        source = ("# A\nunmatched `\n\n<!-- sources: repo:blank -->\nclosing `\n"
                  "# Next\n<!-- sources: repo:heading -->\n`\n"
                  "<!-- sources:\nrepo:block\n-->\n`\n")
        self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))],
                         ["repo:blank", "repo:heading", "repo:block"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_code_spans_do_not_cross_blank_lines_headings_or_html_block_boundaries

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_indented_code_raw_html_and_nested_ordinary_comments_hide_examples
    def test_indented_code_raw_html_and_nested_ordinary_comments_hide_examples(self):
        source = ("# A\n\n    <!-- sources: repo:indented -->\n\n"
                  "<pre>\n<!-- sources: repo:pre -->\n</pre>\n"
                  "<script>\n<!-- sources: repo:script -->\n</script>\n"
                  "<textarea>\n<!-- sources: repo:textarea -->\n</textarea>\n"
                  "<!-- ordinary comment\n<!-- sources: repo:nested -->\n"
                  "<!-- sources: repo:visible -->\n")
        self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))], ["repo:visible"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_indented_code_raw_html_and_nested_ordinary_comments_hide_examples

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_real_html_tags_have_precedence_over_backticks_and_comment_literals_in_attributes
    def test_real_html_tags_have_precedence_over_backticks_and_comment_literals_in_attributes(self):
        source = ("# A\nA tag <a title='`'> <!-- sources: repo:visible --> followed by `literal`\n\n"
                  "A tag <a title='<!-- sources: repo:attribute -->'> <!-- sources: repo:other -->\n")
        self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))], ["repo:visible", "repo:other"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_real_html_tags_have_precedence_over_backticks_and_comment_literals_in_attributes

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_complete_inline_link_destinations_and_titles_are_opaque
    def test_complete_inline_link_destinations_and_titles_are_opaque(self):
        links = (
            '[label](dest "<!-- sources: repo:hidden -->")',
            "[label](dest '<!-- sources: repo:hidden -->')",
            '[label](dest (<!-- sources: repo:hidden -->))',
            r'[la\]bel](deep(one(two(three))) "escaped \" <!-- sources: repo:hidden --> `")',
            r"[label](dest 'escaped \' <!-- sources: repo:hidden --> `')",
            r'[label](dest (escaped \) <!-- sources: repo:hidden --> `))',
            '[nested [label]](<dest with spaces> "<!-- sources: repo:hidden --> `")',
            '[label](tick`destination "<!-- sources: repo:hidden -->")',
            '[label](dest"tick`")',
            '![label](dest "<!-- sources: repo:hidden --> `")',
        )
        for newline in ("\n", "\r\n", "\r"):
            for link in links:
                with self.subTest(newline=newline, link=link):
                    line = link + " <!-- sources: repo:visible --> `ordinary`"
                    source = newline.join(("# Ω", line, ""))
                    document = split_markdown(source)
                    declarations = read_document_declarations(document, file="docs/notes.md")
                    refs = self.refs(declarations)
                    self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                    self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                     [(2, "Ω", line + newline)])
                    self.assertEqual("".join(chunk.text for chunk in document.chunks), source)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_complete_inline_link_destinations_and_titles_are_opaque

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_multiline_inline_titles_preserve_following_declaration_lines
    def test_multiline_inline_titles_preserve_following_declaration_lines(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                source = newline.join(("# Ω", "[label](deep(one(two(three)))",
                                       '  "title',
                                       r'continued \" <!-- sources: repo:hidden --> `") <!-- sources:',
                                       "repo:visible", "--> `ordinary`", ""))
                refs = self.refs(self.declarations(source))
                self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                 [(5, "Ω", "repo:visible" + newline)])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_multiline_inline_titles_preserve_following_declaration_lines

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_link_labels_keep_actual_comments_and_inline_code_precedence
    def test_link_labels_keep_actual_comments_and_inline_code_precedence(self):
        cases = (
            ('[label <!-- sources: repo:label -->](dest "<!-- sources: repo:hidden -->")',
             ["repo:label"]),
            ('[label `] <!-- sources: repo:code -->` end](dest "<!-- sources: repo:hidden -->")', []),
            ('[outer [inner](dest)](dest "<!-- sources: repo:ordinary -->")', ["repo:ordinary"]),
            (r'\[label](dest "<!-- sources: repo:ordinary -->")', ["repo:ordinary"]),
            (r'[label\](dest "<!-- sources: repo:ordinary -->")', ["repo:ordinary"]),
            ('`[label](dest "` <!-- sources: repo:ordinary -->")', ["repo:ordinary"]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual([ref.ref for ref in self.refs(self.declarations("# A\n" + source + "\n"))],
                                 expected)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_link_labels_keep_actual_comments_and_inline_code_precedence

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_malformed_inline_link_suffixes_leave_visible_comments_in_prose
    def test_malformed_inline_link_suffixes_leave_visible_comments_in_prose(self):
        malformed = (
            '[label](dest "missing <!-- sources: repo:visible -->)',
            '[label](dest "<!-- sources: repo:visible -->" extra)',
            '[label](dest (nested (<!-- sources: repo:visible -->)))',
            '[label](unbalanced(one "<!-- sources: repo:visible -->")',
            '[label](<dest <bad> "<!-- sources: repo:visible -->")',
            '[label]( "no destination <!-- sources: repo:visible -->")',
            '[label](dest"<!-- sources: repo:visible -->")',
        )
        for newline in ("\n", "\r\n", "\r"):
            for line in malformed:
                with self.subTest(newline=newline, line=line):
                    refs = self.refs(self.declarations(newline.join(("# A", line, ""))))
                    self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                    self.assertEqual([ref.line for ref in refs], [2])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_malformed_inline_link_suffixes_leave_visible_comments_in_prose

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_reference_definition_titles_are_opaque_before_following_prose
    def test_reference_definition_titles_are_opaque_before_following_prose(self):
        definitions = (
            '[label]: dest "<!-- sources: repo:hidden --> `"',
            "[label]: dest '<!-- sources: repo:hidden --> `'",
            '[label]: dest (<!-- sources: repo:hidden --> `)',
            r'[la\]bel]: deep(one(two(three))) "escaped \" <!-- sources: repo:hidden --> `"',
            r"[label]: <dest with spaces> 'escaped \' <!-- sources: repo:hidden --> `'",
            r'[label]: dest (escaped \) <!-- sources: repo:hidden --> `)',
        )
        for newline in ("\n", "\r\n", "\r"):
            for definition in definitions:
                with self.subTest(newline=newline, definition=definition):
                    visible = "text <!-- sources: repo:visible --> `ordinary`"
                    source = newline.join(("# Ω", "", definition, visible, ""))
                    document = split_markdown(source)
                    refs = self.refs(read_document_declarations(document, file="docs/notes.md"))
                    self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                    self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                     [(4, "Ω", visible + newline)])
                    self.assertEqual("".join(chunk.text for chunk in document.chunks), source)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_reference_definition_titles_are_opaque_before_following_prose

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_multiline_and_consecutive_reference_titles_keep_physical_spans
    def test_multiline_and_consecutive_reference_titles_keep_physical_spans(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                source = newline.join(("# Ω", "", "[first]:", "  deep(one(two(three)))",
                                       '  "title',
                                       r'continued \" <!-- sources: repo:hidden --> `"',
                                       "[second]: <dest> (<!-- sources: repo:also_hidden --> `)",
                                       "text <!-- sources:", "repo:visible", "--> `ordinary`", ""))
                refs = self.refs(self.declarations(source))
                self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                 [(9, "Ω", "repo:visible" + newline)])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_multiline_and_consecutive_reference_titles_keep_physical_spans

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_invalid_or_paragraph_internal_reference_titles_remain_prose
    def test_invalid_or_paragraph_internal_reference_titles_remain_prose(self):
        cases = (
            ('[label]: dest "<!-- sources: repo:visible -->" extra', 3),
            ('paragraph\n[label]: dest "<!-- sources: repo:visible -->"', 4),
            ('[label]: dest\n"<!-- sources: repo:visible -->" extra', 4),
            ('[label]: dest "incomplete\n<!-- sources: repo:visible -->"', 4),
            (r'\[label]: dest "<!-- sources: repo:visible -->"', 3),
            (r'[label\]: dest "<!-- sources: repo:visible -->"', 3),
        )
        for newline in ("\n", "\r\n", "\r"):
            for body, physical_line in cases:
                with self.subTest(newline=newline, body=body):
                    source = newline.join(("# A", "", *body.split("\n"), ""))
                    refs = self.refs(self.declarations(source))
                    self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                    self.assertEqual([ref.line for ref in refs], [physical_line])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_invalid_or_paragraph_internal_reference_titles_remain_prose

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_nested_full_collapsed_and_shortcut_references_reject_outer_link_titles
    def test_nested_full_collapsed_and_shortcut_references_reject_outer_link_titles(self):
        for newline in ("\n", "\r\n", "\r"):
            for inner in ("[text][id]", "[id][]", "[id]"):
                for definition_first in (False, True):
                    with self.subTest(newline=newline, inner=inner, definition_first=definition_first):
                        definition = '[id]: /target "<!-- sources: repo:definition --> `"'
                        visible = '[outer ' + inner + '](/outer "<!-- sources: repo:visible -->")'
                        paragraphs = (definition, visible) if definition_first else (visible, definition)
                        source = newline.join(("# Ω", "", paragraphs[0], "", paragraphs[1], ""))
                        document = split_markdown(source)
                        refs = self.refs(read_document_declarations(document, file="docs/notes.md"))
                        self.assertEqual([ref.ref for ref in refs], ["repo:visible"])
                        self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                         [(5 if definition_first else 3, "Ω", visible + newline)])
                        self.assertEqual("".join(chunk.text for chunk in document.chunks), source)
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_nested_full_collapsed_and_shortcut_references_reject_outer_link_titles

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_reference_labels_use_raw_escapes_casefold_and_collapsed_whitespace
    def test_reference_labels_use_raw_escapes_casefold_and_collapsed_whitespace(self):
        cases = (
            ("[text][a B]", "[ A  b ]: /target", True),
            ("[a\tb][]", "[a b]: /target", True),
            ("[ A\n B ]", "[a b]: /target", True),
            ("[text][STRASSE]", "[Straße]: /target", True),
            (r"[text][a\!]", r"[a\!]: /target", True),
            (r"[a\]b][]", r"[a\]b]: /target", True),
            (r"[a\[b]", r"[a\[b]: /target", True),
            (r"[text][a!]", r"[a\!]: /target", False),
            (r"[text][a\!]", r"[a!]: /target", False),
        )
        for newline in ("\n", "\r\n", "\r"):
            for inner, definition, matched in cases:
                with self.subTest(newline=newline, inner=inner, definition=definition):
                    visible = '[outer ' + inner + '](/outer "<!-- sources: repo:outer -->") <!-- sources: repo:after -->'
                    source = newline.join(("# A", "", *visible.split("\n"), "", definition, ""))
                    refs = self.refs(self.declarations(source))
                    self.assertEqual([ref.ref for ref in refs],
                                     ["repo:outer", "repo:after"] if matched else ["repo:after"])
                    self.assertEqual([ref.line for ref in refs],
                                     [3 + inner.count("\n")] * (2 if matched else 1))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_reference_labels_use_raw_escapes_casefold_and_collapsed_whitespace

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_unknown_or_malformed_full_reference_labels_preserve_outer_title_context
    def test_unknown_or_malformed_full_reference_labels_preserve_outer_title_context(self):
        cases = (
            ("[id][missing]", False),
            ("[id][ ]", False),
            ("[id][bad[nested]]", True),
            ("[id](bad <!-- sources: repo:inside -->)", True),
            ("[id] (/ordinary)", True),
            ("[id[unknown]]", False),
            (r"\[id]", True),
            ("`[id]`", False),
        )
        for inner, matched in cases:
            with self.subTest(inner=inner):
                visible = '[outer ' + inner + '](/outer "<!-- sources: repo:outer -->") <!-- sources: repo:after -->'
                source = "# A\n\n[id]: /target\n\n" + visible + "\n"
                refs = self.refs(self.declarations(source))
                expected = (["repo:inside"] if "repo:inside" in inner else [])
                if matched:
                    expected.append("repo:outer")
                expected.append("repo:after")
                self.assertEqual([ref.ref for ref in refs], expected)
                self.assertTrue(all(ref.line == 5 for ref in refs))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_unknown_or_malformed_full_reference_labels_preserve_outer_title_context

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_only_eligible_definition_blocks_bind_references
    def test_only_eligible_definition_blocks_bind_references(self):
        definitions = (
            ("[id]: /target", True),
            ("> [id]: /target", True),
            ("- [id]: /target", True),
            ("    [id]: /target", False),
            ("```\n[id]: /target\n```", False),
            ("<pre>\n[id]: /target\n</pre>", False),
            ("<div>\n[id]: /target\n</div>", False),
            ("paragraph\n[id]: /target", False),
            ('[id]: /target "invalid" extra', False),
            ("[id]: unbalanced(one", False),
            (r"\[id]: /target", False),
        )
        for newline in ("\n", "\r\n", "\r"):
            for definition, matched in definitions:
                with self.subTest(newline=newline, definition=definition):
                    visible = '[outer [id]](/outer "<!-- sources: repo:outer -->") <!-- sources: repo:after -->'
                    source = newline.join(("# A", "", visible, "", *definition.split("\n"), ""))
                    refs = self.refs(self.declarations(source))
                    self.assertEqual([ref.ref for ref in refs],
                                     ["repo:outer", "repo:after"] if matched else ["repo:after"])
                    self.assertTrue(all(ref.line == 3 for ref in refs))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_only_eligible_definition_blocks_bind_references

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_duplicate_and_multiline_definitions_bind_without_consuming_real_comments
    def test_duplicate_and_multiline_definitions_bind_without_consuming_real_comments(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                visible = '[outer [text][a b]](/outer "<!-- sources: repo:outer -->")'
                source = newline.join(("# Ω", "", visible, "", "[A", "  B]:", "  deep(one(two(three)))",
                                       '  "title', 'continued <!-- sources: repo:hidden --> `"',
                                       '[a b]: /second "<!-- sources: repo:duplicate --> `"',
                                       '[A B]: /bad "<!-- sources: repo:malformed -->" extra', ""))
                refs = self.refs(self.declarations(source))
                self.assertEqual([ref.ref for ref in refs], ["repo:outer", "repo:malformed"])
                self.assertEqual([(ref.line, ref.chunk, ref.raw_line) for ref in refs],
                                 [(3, "Ω", visible + newline),
                                  (11, "Ω", '[A B]: /bad "<!-- sources: repo:malformed -->" extra' + newline)])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_duplicate_and_multiline_definitions_bind_without_consuming_real_comments

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_reference_label_length_limit_and_definition_late_title_fallback
    def test_reference_label_length_limit_and_definition_late_title_fallback(self):
        for size in (999, 1000):
            with self.subTest(size=size):
                label = "a" * size
                source = ('# A\n\n[outer [text][' + label + ']](/outer "<!-- sources: repo:outer -->")\n\n['
                          + label + ']: /target\n')
                self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))],
                                 ["repo:outer"] if size == 999 else [])
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                source = newline.join(("# A", "", '[outer [id][]](/outer "<!-- sources: repo:outer -->")', "",
                                       "[id]: /target", '"<!-- sources: repo:ordinary -->" extra', ""))
                refs = self.refs(self.declarations(source))
                self.assertEqual([ref.ref for ref in refs], ["repo:outer", "repo:ordinary"])
                self.assertEqual([ref.line for ref in refs], [3, 6])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_reference_label_length_limit_and_definition_late_title_fallback

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_autolink_brackets_and_backticks_remain_literal_in_link_labels
    def test_autolink_brackets_and_backticks_remain_literal_in_link_labels(self):
        for newline in ("\n", "\r\n", "\r"):
            for literal in ("<https://example.com/?search=][id]>", "<https://example.com/tick`>", "<tick`@example.com>"):
                with self.subTest(newline=newline, literal=literal):
                    linked = '[outer ' + literal + '](/outer "<!-- sources: repo:hidden -->") <!-- sources: repo:after --> `ordinary`'
                    plain = literal + " <!-- sources: repo:plain --> `ordinary`"
                    source = newline.join(("# A", "", "[id]: /target", "", linked, "", plain, ""))
                    refs = self.refs(self.declarations(source))
                    self.assertEqual([ref.ref for ref in refs], ["repo:after", "repo:plain"])
                    self.assertEqual([ref.line for ref in refs], [5, 7])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_autolink_brackets_and_backticks_remain_literal_in_link_labels

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_fence_tokens_in_ordinary_html_blocks_are_literal_and_do_not_hide_declarations
    def test_fence_tokens_in_ordinary_html_blocks_are_literal_and_do_not_hide_declarations(self):
        source = ("# A\n<div>\n```\n<!-- sources: repo:html -->\n</div>\n\n"
                  "```\n<!-- sources: repo:code -->\n```\n<!-- sources: repo:after -->\n")
        self.assertEqual([ref.ref for ref in self.refs(self.declarations(source))], ["repo:html", "repo:after"])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_fence_tokens_in_ordinary_html_blocks_are_literal_and_do_not_hide_declarations

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_container_prose_comments_keep_physical_source_and_scope
    def test_container_prose_comments_keep_physical_source_and_scope(self):
        source = "# A\n> <!-- sources:\n> repo:quoted\n> -->\n- <!-- sources:\n  repo:listed\n  -->\n"
        refs = self.refs(self.declarations(source))
        self.assertEqual([ref.ref for ref in refs], ["repo:quoted", "repo:listed"])
        self.assertEqual([ref.raw_line for ref in refs], ["> repo:quoted\n", "  repo:listed\n"])
        self.assertEqual([ref.line for ref in refs], [3, 6])
        self.assertTrue(all(ref.chunk == "A" for ref in refs))
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_container_prose_comments_keep_physical_source_and_scope

# TEST-TIER-BEGIN tests/test_source_refs.py::DocumentDeclarationTests.test_unclosed_sources_comment_keeps_refs_as_faults_and_reports_file
    def test_unclosed_sources_comment_keeps_refs_as_faults_and_reports_file(self):
        declarations = self.declarations("# A\n<!-- sources:\nrepo:a\nnot a ref\n")
        self.assertEqual([ref.ref for ref in self.refs(declarations)], ["repo:a", "not a ref"])
        self.assertTrue(all(ref.fault == "not_a_ref" for ref in self.refs(declarations)))
        self.assertEqual([(diagnostic.file, diagnostic.code, diagnostic.line) for diagnostic in declarations.diagnostics],
                         [("docs/notes.md", "sources_comment_unclosed", 2)])
# TEST-TIER-END tests/test_source_refs.py::DocumentDeclarationTests.test_unclosed_sources_comment_keeps_refs_as_faults_and_reports_file
