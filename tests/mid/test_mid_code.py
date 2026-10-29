"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_code as _support
from test_code import (
    CodeTests,
    chunk_code,
    language_for_path,
    patch,
    re,
    unittest,
    version,
)


class CodeTests(_support.CodeTests):
# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_python_functions_async_class_headers_methods_and_attached_comments
    def test_python_functions_async_class_headers_methods_and_attached_comments(self):
        source = ("import os\nLIMIT = 2\n\n"
                  "# function guide\n# another guide\n@wrap(\n    'x'\n)\nasync def renew(key):\n"
                  "    return key\n\n"
                  "# class guide\n@register\nclass Store(Base):\n"
                  "    \"\"\"Class docstring.\"\"\"\n    category = 'fixture'\n\n"
                  "    # getter guide\n    @property\n    def value(self):\n        return 1\n\n"
                  "    # setter guide\n    @value.setter\n    def value(self, new):\n        pass\n\n"
                  "    async def close(self):\n        async def inner():\n            pass\n        await inner()\n\n"
                  "if __name__ == '__main__':\n    print(LIMIT)\n")
        chunks = self.partition("module.py", source)
        names = {chunk.symbol: chunk for chunk in chunks}
        self.assertEqual(set(names), {"<before renew>", "renew", "Store", "Store.value", "Store.value:2", "Store.close", "<end>"})
        self.assertTrue(all(chunk.language == "python" for chunk in chunks))
        self.assertEqual(names["renew"].kind, "function")
        self.assertTrue(names["renew"].text.startswith("# function guide\n# another guide\n@wrap("))
        self.assertIn("async def renew", names["renew"].text)
        self.assertEqual(names["Store"].kind, "class")
        self.assertIn("# class guide\n@register\nclass Store", names["Store"].text)
        self.assertIn("category = 'fixture'", names["Store"].text)
        self.assertNotIn("# getter guide", names["Store"].text)
        self.assertTrue(names["Store.value"].text.startswith("    # getter guide\n    @property"))
        self.assertTrue(names["Store.value:2"].text.startswith("    # setter guide\n    @value.setter"))
        self.assertEqual(names["Store.close"].kind, "method")
        self.assertIn("async def inner", names["Store.close"].text)
# TEST-TIER-END tests/test_code.py::CodeTests.test_python_functions_async_class_headers_methods_and_attached_comments

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_typescript_declarations_class_methods_multiline_comments_and_decorators
    def test_typescript_declarations_class_methods_multiline_comments_and_decorators(self):
        source = ("import { x } from './x';\n"
                  "/**\n * Renew docs.\n */\nexport async function renew(key: string): Promise<string> { return key; }\n"
                  "// class docs\n@register()\nexport abstract class Store {\n"
                  "  category = 'fixture';\n  /** Getter docs. */\n  @logged()\n  get value(): number { return 1; }\n"
                  "  // Setter docs\n  set value(next: number) {}\n  abstract close(): void;\n}\n"
                  "interface Input { key: string }\ntype Alias = Input | null;\nenum State { Open, Closed }\n"
                  "namespace Tools { export function parse() {} }\n"
                  "declare function external(key: string): void;\n"
                  "export const arrow = (key: string) => key;\n")
        chunks = self.partition("module.ts", source)
        names = {chunk.symbol: chunk for chunk in chunks}
        self.assertNotEqual(len(chunks), 1)
        for symbol, kind in {"renew": "function", "Store": "class", "Store.value": "method",
                             "Store.value:2": "method", "Store.close": "method", "Input": "interface",
                             "Alias": "type", "State": "enum", "Tools": "namespace",
                             "external": "function", "arrow": "function"}.items():
            self.assertEqual(names[symbol].kind, kind)
            self.assertEqual(names[symbol].language, "typescript")
        self.assertTrue(names["renew"].text.startswith("/**\n * Renew docs."))
        self.assertTrue(names["Store"].text.startswith("// class docs\n@register()\nexport abstract class"))
        self.assertTrue(names["Store.value"].text.startswith("  /** Getter docs. */\n  @logged()"))
        self.assertIn("category = 'fixture'", names["Store"].text)
        self.assertTrue(names["Store.value:2"].text.startswith("  // Setter docs"))
# TEST-TIER-END tests/test_code.py::CodeTests.test_typescript_declarations_class_methods_multiline_comments_and_decorators

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_javascript_jsx_tsx_arrow_factory_generator_and_multiple_declarators
    def test_javascript_jsx_tsx_arrow_factory_generator_and_multiple_declarators(self):
        fixtures = {
            "component.tsx": ("import React from 'react';\nexport const View = (p: {value: string}) => <div>{p.value}</div>;\n", "tsx", {"View"}),
            "component.jsx": ("export const View = memo(() => <div/>);\n", "javascript", {"View"}),
            "module.js": ("export function* stream() { yield 1; }\nconst first = () => 1, second = function () { return 2; };\nexport default class { run() {} }\n", "javascript", {"stream", "first", "second", "default", "default.run"}),
            "mixed.ts": ("const plain = 1, run = () => 2, other = 3, finish = () => 4;\n", "typescript", {"run", "finish"}),
            "class.js": ("const Holder = class { get value() { return 1; } };\n", "javascript", {"Holder", "Holder.value"}),
            "default.js": ("export default () => 1;\n", "javascript", {"default"}),
        }
        for path, (source, language, symbols) in fixtures.items():
            with self.subTest(path=path):
                chunks = self.partition(path, source)
                self.assertTrue(symbols.issubset({chunk.symbol for chunk in chunks}))
                self.assertTrue(all(chunk.language == language for chunk in chunks))
                self.assertFalse(any(chunk.kind == "file" for chunk in chunks))
# TEST-TIER-END tests/test_code.py::CodeTests.test_javascript_jsx_tsx_arrow_factory_generator_and_multiple_declarators

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_every_supported_ending_has_its_correct_language_and_whole_file_types_are_unparsed
    def test_every_supported_ending_has_its_correct_language_and_whole_file_types_are_unparsed(self):
        fixtures = {
            ".py": ("def x():\n    pass\n", "python"),
            ".ts": ("function x(): void {}", "typescript"),
            ".mts": ("function x(): void {}", "typescript"),
            ".cts": ("function x(): void {}", "typescript"),
            ".tsx": ("const X = () => <div/>;", "tsx"),
            ".js": ("function x() {}", "javascript"),
            ".jsx": ("const X = () => <div/>;", "javascript"),
            ".mjs": ("function x() {}", "javascript"),
            ".cjs": ("function x() {}", "javascript"),
            ".svelte": ("<script>let x = 1;</script><p>{x}</p>", "svelte"),
            ".sh": ("#!/bin/sh\nprintf '%s' hello\n", "shell"),
            ".bash": ("#!/bin/bash\nfunction x() { echo hi; }\n", "shell"),
            ".plist": ("<?xml version='1.0'?><plist><dict/></plist>\n", "plist"),
            ".plist.in": ("<plist>${PLACEHOLDER}</plist>\n", "plist"),
            ".swift": ("struct View { func show() {} }\n", "swift"),
        }
        for ending, (source, language) in fixtures.items():
            with self.subTest(ending=ending):
                chunks = self.partition("file" + ending, source)
                self.assertEqual(language_for_path("file" + ending), language)
                self.assertTrue(all(chunk.language == language for chunk in chunks))
                if language in {"shell", "plist", "swift"}:
                    self.assertEqual([(chunk.symbol, chunk.kind) for chunk in chunks], [("<file>", "file")])
# TEST-TIER-END tests/test_code.py::CodeTests.test_every_supported_ending_has_its_correct_language_and_whole_file_types_are_unparsed

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_svelte_blocks_markup_quoted_attributes_comments_and_inline_byte_boundaries
    def test_svelte_blocks_markup_quoted_attributes_comments_and_inline_byte_boundaries(self):
        source = ("<p title='<script>not a block</script>'>préface</p>\n"
                  "<!-- module guide -->\n<!-- second guide -->\n<script context='module' data='a>b'>export const x = 1;</script>\n"
                  "<script lang='ts'>let value: string = 'λ';</script>\n"
                  "<div>{value}</div><style data=\"a>b\">div { color: red; }</style><footer>fin</footer>\n")
        chunks = self.partition("component.svelte", source)
        names = {chunk.symbol: chunk for chunk in chunks}
        self.assertEqual({"script", "script:2", "style"}.intersection(names), {"script", "script:2", "style"})
        self.assertTrue(names["script"].text.startswith("<!-- module guide -->\n<!-- second guide -->\n<script"))
        self.assertEqual(names["script:2"].kind, "script")
        self.assertEqual(names["style"].kind, "style")
        self.assertEqual(names["<before script>"].kind, "markup")
        self.assertIn("not a block", names["<before script>"].text)
        self.assertEqual(names["<before style>"].text, "\n<div>{value}</div>")
        self.assertIn("<footer>fin</footer>", names["<end>"].text)
        self.assertTrue(all(chunk.language == "svelte" for chunk in chunks))
# TEST-TIER-END tests/test_code.py::CodeTests.test_svelte_blocks_markup_quoted_attributes_comments_and_inline_byte_boundaries

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_loose_runs_use_the_following_symbol_and_unrelated_names_survive_insertions_removals
    def test_loose_runs_use_the_following_symbol_and_unrelated_names_survive_insertions_removals(self):
        fixtures = (
            ("module.py", "def renew():\n    pass\n\nRETRIES = {}\n\ndef expire():\n    pass\n\nrun()\n", "import time\nLIMIT = 3\n\n"),
            ("module.ts", "function renew() {}\nconst RETRIES = {};\nfunction expire() {}\nrun();\n", "import { x } from './x';\nconst LIMIT = 3;\n"),
        )
        for path, source, prefix in fixtures:
            with self.subTest(path=path):
                original = self.partition(path, source)
                inserted = self.partition(path, prefix + source)
                original_names = {chunk.symbol for chunk in original}
                self.assertEqual({chunk.symbol for chunk in inserted} - original_names, {"<before renew>"})
                for name in ("renew", "<before expire>", "expire", "<end>"):
                    self.assertIn(name, original_names)
                    old = next(chunk for chunk in original if chunk.symbol == name)
                    new = next(chunk for chunk in inserted if chunk.symbol == name)
                    self.assertEqual(new.text, old.text)
                self.assertEqual(chunk_code(path, (prefix + source)[len(prefix):]), original)
                self.assertFalse(any("module:" in chunk.symbol for chunk in inserted))
# TEST-TIER-END tests/test_code.py::CodeTests.test_loose_runs_use_the_following_symbol_and_unrelated_names_survive_insertions_removals

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_duplicate_functions_classes_getters_and_setters_are_unique_without_silent_merges
    def test_duplicate_functions_classes_getters_and_setters_are_unique_without_silent_merges(self):
        fixtures = {
            "module.py": "def same():\n    return 1\ndef same():\n    return 2\nclass C:\n    @property\n    def x(self):\n        return 1\n    @x.setter\n    def x(self,v):\n        pass\nclass C:\n    def x(self):\n        return 3\n",
            "module.ts": "function same() { return 1; }\nfunction same() { return 2; }\nclass C { get x() { return 1; } set x(v:number) {} }\nclass C { x() { return 3; } }\n",
        }
        for path, source in fixtures.items():
            with self.subTest(path=path):
                chunks = self.partition(path, source)
                symbols = {chunk.symbol for chunk in chunks}
                self.assertTrue({"same", "same:2", "C", "C:2", "C.x", "C.x:2", "C.x:3"}.issubset(symbols))
                self.assertEqual(sum(chunk.kind == "method" for chunk in chunks), 3)
                self.assertEqual(sum(chunk.kind == "function" for chunk in chunks), 2)
# TEST-TIER-END tests/test_code.py::CodeTests.test_duplicate_functions_classes_getters_and_setters_are_unique_without_silent_merges

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_unicode_crlf_indentation_blank_lines_and_no_final_newline_are_preserved
    def test_unicode_crlf_indentation_blank_lines_and_no_final_newline_are_preserved(self):
        fixtures = {
            "module.py": "\r\n# café 🪴\r\ndef café():\r\n    return 'λ'\r\n\r\nVALUE = '🌿'",
            "module.ts": "\r\n/** café 🪴 */\r\nexport const café = () => 'λ';\r\n\r\nconst VALUE = '🌿';",
            "component.svelte": "\r\n<script>const café = 'λ';</script>\r\n\r\n<p>🌿</p>",
        }
        for path, source in fixtures.items():
            with self.subTest(path=path):
                chunks = self.partition(path, source)
                self.assertFalse(any(chunk.kind == "file" for chunk in chunks))
                self.assertEqual(chunks[-1].byte_end, len(source.encode("utf-8")))
                self.assertGreater(chunks[-1].byte_end, len(source))
                for chunk in chunks:
                    self.assertNotIn("\ufffd", chunk.text)
# TEST-TIER-END tests/test_code.py::CodeTests.test_unicode_crlf_indentation_blank_lines_and_no_final_newline_are_preserved

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_universal_line_endings_and_inline_class_method_decorators_keep_their_structure
    def test_universal_line_endings_and_inline_class_method_decorators_keep_their_structure(self):
        for newline in ("\n", "\r\n", "\r"):
            source = newline.join(("# docs", "def first():", "    pass", "", "def second():", "    pass", ""))
            with self.subTest(newline=repr(newline)):
                chunks = self.partition("module.py", source)
                self.assertEqual([chunk.symbol for chunk in chunks], ["first", "second"])
                self.assertEqual(chunks[0].line_start, 1)
                self.assertEqual(chunks[1].line_start, 5)
                self.assertEqual(chunks[1].line_end, 6)
        source = "class C { /** docs */ @logged() method() {} }"
        chunks = self.partition("module.ts", source)
        method = next(chunk for chunk in chunks if chunk.symbol == "C.method")
        self.assertTrue(method.text.startswith("/** docs */ @logged()"))
# TEST-TIER-END tests/test_code.py::CodeTests.test_universal_line_endings_and_inline_class_method_decorators_keep_their_structure

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_malformed_source_is_one_complete_whole_file_chunk_in_its_actual_language
    def test_malformed_source_is_one_complete_whole_file_chunk_in_its_actual_language(self):
        fixtures = {
            "broken.py": "# comment\n@decorator\ndef broken(:\n    pass\n",
            "broken.ts": "/* comment */\nexport function broken( {\n",
            "broken.tsx": "const View = () => <div>missing;\n",
            "broken.js": "class C { method( {\n",
            "broken.svelte": "<p>λ</p><script>let value = 1;\n",
            "closing.svelte": "<p>λ</p></style>\n",
            "comment.svelte": "<!-- unfinished >\n<script>let x=1;</script>",
        }
        for path, source in fixtures.items():
            with self.subTest(path=path):
                chunks = self.partition(path, source)
                self.assertEqual(len(chunks), 1)
                self.assertEqual(chunks[0].symbol, "<file>")
                self.assertEqual(chunks[0].kind, "file")
                self.assertEqual(chunks[0].language, language_for_path(path))
# TEST-TIER-END tests/test_code.py::CodeTests.test_malformed_source_is_one_complete_whole_file_chunk_in_its_actual_language

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_unavailable_or_failed_grammar_falls_back_without_partial_source
    def test_unavailable_or_failed_grammar_falls_back_without_partial_source(self):
        source = "// λ\nfunction x() {}\nconst after = 1;\n"
        for error in (ImportError("fixture"), RuntimeError("fixture"), ValueError("fixture")):
            with self.subTest(error=type(error).__name__), patch("mycel._code._tree_parser", side_effect=error):
                chunks = self.partition("module.ts", source)
                self.assertEqual([(chunk.symbol, chunk.kind) for chunk in chunks], [("<file>", "file")])
# TEST-TIER-END tests/test_code.py::CodeTests.test_unavailable_or_failed_grammar_falls_back_without_partial_source

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_empty_whitespace_and_declaration_free_files_keep_every_byte
    def test_empty_whitespace_and_declaration_free_files_keep_every_byte(self):
        for ending in (".py", ".ts", ".tsx", ".js", ".svelte", ".sh", ".plist", ".swift"):
            for source in ("", " \t\r\n\r\n"):
                with self.subTest(ending=ending, source_length=len(source)):
                    chunks = self.partition("empty" + ending, source)
                    self.assertEqual(len(chunks), 1)
        for path, source in (("module.py", "import os\nVALUE = 1\n"),
                             ("module.ts", "import { x } from './x';\nconst VALUE = 1;\n"),
                             ("component.svelte", "<p>hello</p>\n")):
            chunks = self.partition(path, source)
            self.assertEqual(chunks[0].symbol, "<end>")
            self.assertEqual(chunks[0].kind, "markup" if path.endswith(".svelte") else "module")
# TEST-TIER-END tests/test_code.py::CodeTests.test_empty_whitespace_and_declaration_free_files_keep_every_byte

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_large_logical_chunks_are_complete_and_never_split_to_model_limits
    def test_large_logical_chunks_are_complete_and_never_split_to_model_limits(self):
        body = "λ🌿" * 70000
        source = "def long_document():\n    return " + repr(body) + "\n"
        chunks = self.partition("large.py", source)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].symbol, "long_document")
        self.assertEqual(chunks[0].text, source)
        self.assertGreater(len(chunks[0].text), 100000)
        malformed = source + "def broken(:\n"
        chunks = self.partition("large.py", malformed)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].symbol, "<file>")
# TEST-TIER-END tests/test_code.py::CodeTests.test_large_logical_chunks_are_complete_and_never_split_to_model_limits

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_official_pinned_grammars_are_installed_and_used_for_structural_results
    def test_official_pinned_grammars_are_installed_and_used_for_structural_results(self):
        self.assertEqual(version("tree-sitter"), "0.26.0")
        self.assertEqual(version("tree-sitter-typescript"), "0.23.2")
        self.assertEqual(version("tree-sitter-javascript"), "0.25.0")
        for path, source in (("module.ts", "interface Input { value: string }"),
                             ("module.tsx", "const View = () => <div/>;"),
                             ("module.js", "function parse() {}")):
            chunks = self.partition(path, source)
            self.assertFalse(any(chunk.kind == "file" for chunk in chunks))
# TEST-TIER-END tests/test_code.py::CodeTests.test_official_pinned_grammars_are_installed_and_used_for_structural_results

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_class_fields_between_and_after_methods_remain_owned_by_the_class
    def test_class_fields_between_and_after_methods_remain_owned_by_the_class(self):
        fixtures = {
            "class.py": ("class A:\n    head = 1\n    def first(self):\n        pass\n"
                         "    # retained field\n    between = '雪'\n    def second(self):\n        pass\n"
                         "    tail = 3\n\ndef outside():\n    pass\n"),
            "class.ts": ("class A {\n  head = 1;\n  first() {}\n"
                         "  // retained field\n  between = '雪';\n  /** second docs */\n  @logged()\n  second() {}\n"
                         "  tail = 3;\n}\nfunction outside() {}\n"),
            "class.js": "class A { first() {} field = '雪'; second() {} }\nfunction outside() {}\n",
        }
        for path, source in fixtures.items():
            with self.subTest(path=path):
                chunks = self.partition(path, source)
                by_name = {chunk.symbol: chunk for chunk in chunks}
                self.assertEqual(by_name["A"].kind, "class")
                self.assertEqual(by_name["A.first"].kind, "method")
                self.assertEqual(by_name["A.second"].kind, "method")
                self.assertEqual(by_name["A.<before A.second>"].kind, "class")
                self.assertIn("雪", by_name["A.<before A.second>"].text)
                self.assertEqual(by_name["outside"].kind, "function")
                self.assertFalse(any(chunk.kind == "module" for chunk in chunks))
                if path != "class.js":
                    self.assertEqual(by_name["A.<end>"].kind, "class")
                    self.assertIn("tail = 3", by_name["A.<end>"].text)
                if path == "class.ts":
                    self.assertTrue(by_name["A.second"].text.startswith("  /** second docs */\n  @logged()"))
                inserted = self.partition(path, "const extra = 1;\n" + source) if path.endswith((".ts", ".js")) else self.partition(path, "extra = 1\n" + source)
                for name, chunk in by_name.items():
                    self.assertEqual(next(item.text for item in inserted if item.symbol == name), chunk.text)
# TEST-TIER-END tests/test_code.py::CodeTests.test_class_fields_between_and_after_methods_remain_owned_by_the_class

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_python_nested_classes_recursively_have_headers_methods_and_class_continuations
    def test_python_nested_classes_recursively_have_headers_methods_and_class_continuations(self):
        source = ("# outer docs\nclass A:\n    before = 1\n"
                  "    # inner docs\n    @decorate\n    class B:\n        inner_value = '雪'\n"
                  "        # method docs\n        @property\n        def value(self):\n            return self.inner_value\n"
                  "        after = 2\n        class C:\n            def last(self):\n                return '😀'\n"
                  "    outer_after = 3\n    def first(self):\n        pass\n")
        chunks = self.partition("nested.py", source)
        names = {chunk.symbol: chunk for chunk in chunks}
        for name in ("A", "A.B", "A.B.C"):
            self.assertEqual(names[name].kind, "class")
        for name in ("A.B.value", "A.B.C.last", "A.first"):
            self.assertEqual(names[name].kind, "method")
        self.assertTrue(names["A.B"].text.startswith("    # inner docs\n    @decorate\n    class B:"))
        self.assertTrue(names["A.B.value"].text.startswith("        # method docs\n        @property"))
        self.assertIn("after = 2", names["A.B.<before A.B.C>"].text)
        self.assertIn("outer_after = 3", names["A.<before A.first>"].text)
        self.assertFalse(any(chunk.kind == "module" for chunk in chunks))
# TEST-TIER-END tests/test_code.py::CodeTests.test_python_nested_classes_recursively_have_headers_methods_and_class_continuations

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_svelte_css_closing_literals_comments_and_markup_expressions_are_not_blocks
    def test_svelte_css_closing_literals_comments_and_markup_expressions_are_not_blocks(self):
        for newline in ("\n", "\r\n", "\r"):
            source = newline.join((
                "<script>let x=1;</script>",
                "<p>{'<script>hello</script>'}</p>",
                '<p title={"<style>not a block</style>"}>{`<script>${"</script>"}</script>`}</p>',
                '<p>{/}<script>/.test("x") ? "yes" : "no"}</p>',
                "<!-- style docs -->",
                "<style>",
                '/* </style> */ .x::after { content: "</style>"; }',
                '.x { background: url("</style>"); --raw: "{ </style> }"; }',
                "</style>",
                "{#if x}<p>{x / 2}</p>{/if}",
                ""))
            with self.subTest(newline=repr(newline)):
                chunks = self.partition("component.svelte", source)
                blocks = [chunk for chunk in chunks if chunk.kind in {"script", "style"}]
                self.assertEqual([chunk.symbol for chunk in blocks], ["script", "style"])
                self.assertIn('content: "</style>"', blocks[1].text)
                self.assertTrue(blocks[1].text.startswith("<!-- style docs -->"))
                self.assertEqual(blocks[1].text.count("</style>"), 5)
                self.assertFalse(any(chunk.kind == "file" for chunk in chunks))
# TEST-TIER-END tests/test_code.py::CodeTests.test_svelte_css_closing_literals_comments_and_markup_expressions_are_not_blocks

# TEST-TIER-BEGIN tests/test_code.py::CodeTests.test_svelte_lexer_failures_and_excessive_nesting_keep_one_complete_file
    def test_svelte_lexer_failures_and_excessive_nesting_keep_one_complete_file(self):
        fixtures = (
            '<script>const literal = "</script>";</script><p>Hello</p>',
            '<style>.x { content: "unterminated; }</style>',
            '<style>/* unfinished </style>',
            '<script>x()</script><p>{"unfinished}</p>',
            '<script>x()</script><p>{`unfinished}</p>',
            '<script>x()</script><p>{' + '{' * 300 + '0' + '}' * 301 + '</p>',
        )
        for source in fixtures:
            with self.subTest(source_length=len(source)):
                chunks = self.partition("broken.svelte", source)
                self.assertEqual([(chunk.symbol, chunk.kind) for chunk in chunks], [("<file>", "file")])
# TEST-TIER-END tests/test_code.py::CodeTests.test_svelte_lexer_failures_and_excessive_nesting_keep_one_complete_file
