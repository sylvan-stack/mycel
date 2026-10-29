"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_code as _support


class CodeTests(_support.CodeTests):


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
