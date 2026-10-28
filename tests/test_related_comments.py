"""Declared relations share Markdown exclusions without becoming sources."""
import unittest

import test_capture as capture_fixtures
import test_resolver as resolver_fixtures

from mycel._markdown import split_markdown
from mycel._resolver import SourceResolver
from mycel._source_refs import read_document_declarations


class RelatedCommentTests(unittest.TestCase):
    def declarations(self, source):
        return read_document_declarations(split_markdown(source), file='docs/guide.md')

    def relations(self, source):
        return tuple(ref for group in self.declarations(source).chunk_relations
                     for ref in group.relations)

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_related_groups_cover_every_chunk_and_stay_distinct_from_sources
#     def test_related_groups_cover_every_chunk_and_stay_distinct_from_sources(self):
#         declarations = self.declarations(
#             '---\nsources: [repo:whole]\nrelated: [repo:ignored]\n---\n'
#             'Preface\n<!-- related: repo:preface -->\n# First\n'
#             '<!-- sources: repo:source -->\n<!-- related:\nrepo:one\nrepo:two#Name\n-->\n'
#             '## Empty\nBody\n')
#         self.assertEqual([group.chunk for group in declarations.chunk_relations],
#                          ['<preamble>', 'First', 'First > Empty'])
#         self.assertEqual([[ref.ref for ref in group.relations] for group in declarations.chunk_relations],
#                          [['repo:preface'], ['repo:one', 'repo:two#Name'], []])
#         self.assertEqual([[ref.ref for ref in group.sources] for group in declarations.chunk_sources],
#                          [['repo:whole'], ['repo:source'], []])
#         self.assertNotIn('related', declarations.metadata)
#         self.assertEqual(self.declarations('---\nrelated: [repo:ignored]\n---\n').chunk_relations, ())
#         with self.assertRaises(FrozenInstanceError):
#             declarations.chunk_relations[0].relations[0].ref = 'changed'
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_related_groups_cover_every_chunk_and_stay_distinct_from_sources

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_mixed_comments_keep_duplicate_occurrences_and_exact_physical_lines
#     def test_mixed_comments_keep_duplicate_occurrences_and_exact_physical_lines(self):
#         for newline in ('\n', '\r\n', '\r'):
#             with self.subTest(newline=repr(newline)):
#                 source = newline.join(('# Ω', '> <!-- ReLaTeD:', '>   repo:@code/猫.py#A > B  ',
#                                        '> repo:@code/猫.py#A > B', '> not a ref', '> repo:@code/a%2Fb',
#                                        '> repo:bad\0path', '> -->', '<!-- sources: repo:source -->',
#                                        '- <!-- related:', '  repo:listed', '  -->', ''))
#                 refs = self.relations(source)
#                 self.assertEqual([ref.ref for ref in refs],
#                     ['repo:@code/猫.py#A > B', 'repo:@code/猫.py#A > B', 'not a ref',
#                      'repo:@code/a%2Fb', 'repo:bad\0path', 'repo:listed'])
#                 self.assertEqual([ref.fault for ref in refs],
#                                  [None, None, 'not_a_ref', 'not_a_ref', 'not_a_ref', None])
#                 self.assertEqual([ref.line for ref in refs], [3, 4, 5, 6, 7, 11])
#                 self.assertEqual(refs[0].declared, '  repo:@code/猫.py#A > B  ')
#                 self.assertEqual(refs[0].raw_line, '>   repo:@code/猫.py#A > B  ' + newline)
#                 self.assertEqual(refs[-1].raw_line, '  repo:listed' + newline)
#                 self.assertTrue(all(ref.chunk == 'Ω' and ref.origin == 'comment' for ref in refs))
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_mixed_comments_keep_duplicate_occurrences_and_exact_physical_lines

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_unclosed_related_comment_retains_each_entry_as_fault_and_reports_file
#     def test_unclosed_related_comment_retains_each_entry_as_fault_and_reports_file(self):
#         declarations = self.declarations('# A\n<!-- related:\nrepo:a\nnot a ref\n')
#         refs = declarations.chunk_relations[0].relations
#         self.assertEqual([ref.ref for ref in refs], ['repo:a', 'not a ref'])
#         self.assertTrue(all(ref.address is None and ref.fault == 'not_a_ref' for ref in refs))
#         self.assertEqual([(item.file, item.code, item.line) for item in declarations.diagnostics],
#                          [('docs/guide.md', 'related_comment_unclosed', 2)])
#         self.assertEqual(declarations.chunk_sources[0].sources, ())
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_unclosed_related_comment_retains_each_entry_as_fault_and_reports_file

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_one_line_is_one_reference_and_nested_comments_are_not_declarations
#     def test_one_line_is_one_reference_and_nested_comments_are_not_declarations(self):
#         source = ('# A\n<!-- related:\n\nrepo:a, repo:b\n<!-- sources:\n-->\n'
#                   '<!-- ordinary\n<!-- related: repo:nested -->\n<!-- related: repo:after -->\n')
#         refs = self.relations(source)
#         self.assertEqual([ref.ref for ref in refs],
#                          ['repo:a, repo:b', '<!-- sources:', 'repo:after'])
#         self.assertEqual(refs[0].address.path, 'a, repo:b')
#         self.assertEqual(refs[1].fault, 'not_a_ref')
#         self.assertEqual(self.declarations(source).chunk_sources[0].sources, ())
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_one_line_is_one_reference_and_nested_comments_are_not_declarations

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_fences_indent_code_and_raw_html_hide_related_comments
#     def test_fences_indent_code_and_raw_html_hide_related_comments(self):
#         for opening, continuation in (('', ''), ('- ', '  '), ('1. ', '   '),
#                                       ('> ', '> '), ('> - ', '>   '), ('- > ', '  > ')):
#             for marker in ('````', '~~~~'):
#                 with self.subTest(opening=opening, marker=marker):
#                     source = '\n'.join(('# A', opening + marker + 'text',
#                         continuation + '<!-- related: repo:hidden -->', continuation + marker[:3],
#                         continuation + '<!-- related: repo:also_hidden -->', continuation + marker,
#                         '<!-- related: repo:visible -->', ''))
#                     self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:visible'])
#         source = ('# A\n\n    <!-- related: repo:indented -->\n\n'
#                   '<pre>\n<!-- related: repo:pre -->\n</pre>\n'
#                   '<script>\n<!-- related: repo:script -->\n</script>\n'
#                   '<textarea>\n<!-- related: repo:textarea -->\n</textarea>\n'
#                   '<!-- related: repo:visible -->\n')
#         self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:visible'])
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_fences_indent_code_and_raw_html_hide_related_comments

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_inline_code_lazy_containers_and_block_boundaries_share_source_rules
#     def test_inline_code_lazy_containers_and_block_boundaries_share_source_rules(self):
#         source = ('# A\n`<!-- related: repo:hidden -->` and <!-- related: repo:one -->\n\n'
#                   '``literal ` <!-- related: repo:hidden2 --> ``\n\n'
#                   'Example `<!-- related:\nrepo:hidden3\n-->` tail\n\n'
#                   'unmatched ` <!-- related: repo:two -->\n\n'
#                   '\\` <!-- related: repo:three --> \\`\n\n'
#                   '<!-- related: repo:four#tick`name --> then `ordinary code`\n')
#         self.assertEqual([ref.ref for ref in self.relations(source)],
#                          ['repo:one', 'repo:two', 'repo:three', 'repo:four#tick`name'])
#         for opening in ('> `open', '- `open', '1. `open', '> - `open'):
#             with self.subTest(opening=opening):
#                 source = '# A\n' + opening + '\ncontinued <!-- related: repo:hidden -->`\n\n<!-- related: repo:after -->\n'
#                 self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:after'])
#         source = '# A\nunmatched `\n\n<!-- related: repo:blank -->\nclosing `\n# Next\n<!-- related: repo:heading -->\n`\n'
#         self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:blank', 'repo:heading'])
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_inline_code_lazy_containers_and_block_boundaries_share_source_rules

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_link_titles_reference_definitions_html_attributes_and_autolinks_are_opaque
#     def test_link_titles_reference_definitions_html_attributes_and_autolinks_are_opaque(self):
#         for opaque in (
#                 '[label](dest "<!-- related: repo:hidden --> `")',
#                 "![label](dest '<!-- related: repo:hidden --> `')",
#                 '[nested [label]](<dest with spaces> "<!-- related: repo:hidden --> `")',
#                 "<a title='<!-- related: repo:hidden --> `'>",
#                 '<https://example.com/tick`>'):
#             with self.subTest(opaque=opaque):
#                 source = '# A\n' + opaque + ' <!-- related: repo:visible --> `ordinary`\n'
#                 self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:visible'])
#         for newline in ('\n', '\r\n', '\r'):
#             source = newline.join(('# A', '', '[id]: /target "<!-- related: repo:hidden --> `"',
#                 '', '[outer [id]](/outer "<!-- related: repo:visible -->")', ''))
#             self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:visible'])
#         source = '# A\n[label](dest "missing <!-- related: repo:visible -->)\n'
#         self.assertEqual([ref.ref for ref in self.relations(source)], ['repo:visible'])
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_link_titles_reference_definitions_html_attributes_and_autolinks_are_opaque

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCommentTests.test_unreadable_frontmatter_never_exposes_its_related_example
#     def test_unreadable_frontmatter_never_exposes_its_related_example(self):
#         for source in ('---\nrole: [broken\n<!-- related: repo:hidden -->\n---\n# A\n',
#                        '---\nrelated: [repo:hidden]\n<!-- related: repo:hidden -->\n'):
#             with self.subTest(source=source):
#                 declarations = self.declarations(source)
#                 self.assertEqual(tuple(ref for group in declarations.chunk_relations
#                                        for ref in group.relations), ())
#                 self.assertTrue(declarations.diagnostics)
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCommentTests.test_unreadable_frontmatter_never_exposes_its_related_example


class RelatedCaptureTests(capture_fixtures._CaptureFixture, unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCaptureTests.test_rereader_preserves_asserted_header_selection_in_fresh_catalog
#     def test_rereader_preserves_asserted_header_selection_in_fresh_catalog(self):
#         code_source = 'class Policy:\n    def run(self):\n        pass\n'
#         guide_source = '# Guide\nBody\n'
#         self.write(self.code, 'policy.py', code_source)
#         self.write(self.artifact, 'guide.md', guide_source)
#         settings = self.settings()
#         header = resolver_fixtures.chunk('Policy', 'class Policy:\n', kind='class')
#         method = resolver_fixtures.chunk('Policy.run', '    def run(self):\n        pass\n',
#                                         kind='method', family='Policy', number=2)
#         code = resolver_fixtures.file('policy.py', code_source, root='code', members=(header, method))
#         guide = resolver_fixtures.file('guide.md', guide_source,
#                                       members=(resolver_fixtures.chunk('Guide', guide_source),))
#         base = SourceResolver(settings, (code, guide))
#         raw = 'fixture:@code/policy.py#Policy'
#         catalog = RetainedDependencyResolver(base, {}, endpoint_refs=(raw,))
#         dependant = catalog.resolve('fixture:@artifact/guide.md#Guide', purpose='endpoint')
#         resolution = catalog.resolve(raw)
#         expected = PinInputs(settings, dependant.selection.members[0], guide, resolution.selection,
#                              CaptureLocation('disk'), resolution, catalog)
#         manifest = self.read(settings)
#         connection = object()
#         inputs = DependencyCaptureInputs(connection, settings, settings_home=self.home,
#                                          guarded_repositories=('fixture',))
#         with patch.object(SourceResolver, 'from_transaction', return_value=base) as reader, \
#                 patch.object(inputs, 'observe', side_effect=lambda repository: self.read(settings)), \
#                 patch('mycel._locks.require_transaction_guards') as guard:
#             fresh = inputs.rereader(manifest.disk.id, 'fixture', None)(expected)
#         reader.assert_called_once_with(connection, settings, kind='disk', location='disk',
#                                        guarded_repositories=('fixture',), catalogs=None)
#         guard.assert_called_once_with(connection, ('fixture',))
#         self.assertEqual(fresh.catalog.endpoint_refs, frozenset((raw,)))
#         self.assertEqual(fresh.selection.kind, 'chunk')
#         self.assertEqual(tuple(member.chunk for member in fresh.selection.members), (header,))
#         self.assertEqual(fresh.resolution, expected.resolution)
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCaptureTests.test_rereader_preserves_asserted_header_selection_in_fresh_catalog

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCaptureTests.test_exact_capture_and_parse_history_preserve_relations_without_parsing_code_comments
#     def test_exact_capture_and_parse_history_preserve_relations_without_parsing_code_comments(self):
#         document = '# Guide\n<!-- sources: fixture:source -->\n<!-- related: fixture:other -->\n# Empty\nBody\n'
#         self.write(self.code, 'README.md', document)
#         self.write(self.code, 'module.py', '# <!-- related: fixture:ignored -->\ndef run():\n    pass\n')
#         manifest = self.read(self.settings(artifact=False))
#         captured = next(file for file in manifest.disk.files if file.corpus == 'documents')
#         record = _capture.parse_history_record(captured, manifest.policy_hash)
#         restored = _capture.file_from_parse_history(captured.source, captured.corpus,
#             captured.primary, captured.aliases, record)
#         self.assertIsNotNone(restored)
#         original = read_document_declarations(captured.parsed, file=captured.primary.path)
#         self.assertEqual(read_document_declarations(restored.parsed, file=restored.primary.path), original)
#         self.assertEqual([[ref.ref for ref in group.relations] for group in original.chunk_relations],
#                          [['fixture:other'], []])
#         self.assertEqual([[ref.ref for ref in group.sources] for group in original.chunk_sources],
#                          [['fixture:source'], []])
#         code = next(file for file in manifest.disk.files if file.corpus == 'code')
#         self.assertIsInstance(code.parsed, tuple)
#         self.assertFalse(hasattr(code.parsed, 'chunk_relations'))
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCaptureTests.test_exact_capture_and_parse_history_preserve_relations_without_parsing_code_comments

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelatedCaptureTests.test_declaration_parser_revision_invalidates_unchanged_capture_policy
#     def test_declaration_parser_revision_invalidates_unchanged_capture_policy(self):
#         before = _capture._parser_revision()
#         read_bytes = Path.read_bytes
#         declarations_path = Path(_capture._source_refs.__file__)
#         def changed(path):
#             source = read_bytes(path)
#             return source + b'\n# changed declaration grammar\n' if path == declarations_path else source
#         with patch.object(Path, 'read_bytes', changed):
#             self.assertNotEqual(_capture._parser_revision(), before)
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelatedCaptureTests.test_declaration_parser_revision_invalidates_unchanged_capture_policy


class RelationEndpointResolverTests(unittest.TestCase):
    def catalog(self):
        header = resolver_fixtures.chunk('Policy', 'class Policy:\n', kind='class')
        method = resolver_fixtures.chunk('Policy.run', ' def run(self): pass\n',
                                        kind='method', family='Policy', number=2)
        file = resolver_fixtures.file('policy.py', 'complete bytes', root='code', members=(header, method))
        return SourceResolver(resolver_fixtures.settings(), (file,)), file, header

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelationEndpointResolverTests.test_asserted_class_is_header_and_declared_class_is_family
#     def test_asserted_class_is_header_and_declared_class_is_family(self):
#         base, file, header = self.catalog()
#         raw = 'fixture:policy.py#Policy'
#         asserted = RetainedDependencyResolver(base, {}, endpoint_refs=(raw,)).resolve(raw)
#         declared = RetainedDependencyResolver(base, {}).resolve(raw)
#         self.assertEqual((asserted.selection.kind, tuple(member.chunk for member in asserted.selection.members)),
#                          ('chunk', (header,)))
#         self.assertEqual((declared.selection.kind, len(declared.selection.members)), ('family', 2))
#         raw_file = 'fixture:policy.py'
#         self.assertEqual(RetainedDependencyResolver(base, {}, endpoint_refs=(raw_file,)).resolve(raw_file).fault,
#                          'one_chunk_required')
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelationEndpointResolverTests.test_asserted_class_is_header_and_declared_class_is_family

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelationEndpointResolverTests.test_retained_file_moves_and_class_renames_keep_endpoint_semantics
#     def test_retained_file_moves_and_class_renames_keep_endpoint_semantics(self):
#         base, file, header = self.catalog()
#         old = 'fixture:old.py#Policy'
#         moved = replace(file, recognized_moves=(SourceAddress('fixture', 'code', 'old.py'),))
#         catalog = SourceResolver(base.settings, (moved,))
#         selection = RetainedDependencyResolver(catalog, {old: header.identifier}, endpoint_refs=(old,)).resolve(old)
#         self.assertEqual(selection.declaration, old)
#         self.assertEqual((selection.selection.kind, len(selection.selection.members)), ('chunk', 1))
#         raw = 'fixture:policy.py#Former'
#         selection = RetainedDependencyResolver(base, {raw: header.identifier}, endpoint_refs=(raw,)).resolve(raw)
#         self.assertEqual((selection.selection.kind, len(selection.selection.members)), ('chunk', 1))
#         self.assertEqual(selection.selection.place.name, 'Policy')
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelationEndpointResolverTests.test_retained_file_moves_and_class_renames_keep_endpoint_semantics

# TEST-TIER-DISABLED-BEGIN tests/test_related_comments.py::RelationEndpointResolverTests.test_endpoint_selection_never_overrides_syntax_eligibility_or_ambiguity_faults
#     def test_endpoint_selection_never_overrides_syntax_eligibility_or_ambiguity_faults(self):
#         base, file, header = self.catalog()
#         raw = 'fixture:policy.py#Policy'
#         syntax = RetainedDependencyResolver(base, {}, {raw: 'not_a_ref'}, endpoint_refs=(raw,))
#         self.assertEqual(syntax.resolve(raw).fault, 'not_a_ref')
#         disabled = SourceResolver(resolver_fixtures.settings(enabled=False), (file,))
#         self.assertEqual(RetainedDependencyResolver(disabled, {raw: header.identifier}, endpoint_refs=(raw,))
#                          .resolve(raw).fault, 'disabled_repository')
#         other = resolver_fixtures.file('policy.py', 'other', members=(header,))
#         ambiguous = SourceResolver(base.settings, (file, other))
#         self.assertEqual(RetainedDependencyResolver(ambiguous, {raw: header.identifier}, endpoint_refs=(raw,))
#                          .resolve(raw).fault, 'ambiguous_path')
# TEST-TIER-DISABLED-END tests/test_related_comments.py::RelationEndpointResolverTests.test_endpoint_selection_never_overrides_syntax_eligibility_or_ambiguity_faults


if __name__ == '__main__':
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:2
# from dataclasses import FrozenInstanceError, replace
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:3
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:5
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:7
# from mycel import _capture
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:8
# from mycel._dependency_application import RetainedDependencyResolver
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:9
# from mycel._dependency_inputs import DependencyCaptureInputs
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:9
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:10
# from mycel._evidence import CaptureLocation, PinInputs
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_related_comments.py:13
# from mycel._source_refs import SourceAddress, read_document_declarations
# TEST-TIER-IMPORTS-END tests/test_related_comments.py:13
