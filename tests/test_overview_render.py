"""Offline proofs for the deterministic, complete structural outline."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mycel._code import chunk_code
from mycel._disk_reconciliation import _metadata
from mycel._overview_render import OverviewFile, OverviewSymbol, render_sections


def parsed(path, source):
    chunks = chunk_code(path, source)
    result = []
    for index, chunk in enumerate(chunks):
        metadata = _metadata(SimpleNamespace(parsed=chunks), index)
        span = chunk.declaration_name_span
        display = None
        if span is not None:
            leaf = chunk.text.encode()[span[0]:span[1]].decode()
            family = metadata.get('family')
            display = leaf if family is None else family + '.' + leaf
        result.append(OverviewSymbol(chunk.symbol, chunk.kind, chunk.byte_start,
                                     metadata.get('family'), display))
    return OverviewFile(path, tuple(result))


class OverviewRenderTests(unittest.TestCase):
    def test_all_files_classes_eight_caps_order_and_complete_counts_are_offline(self):
        source = 'class Zed:\n' + ''.join(f'    def m{i}(self):\n        return {i}\n' for i in range(11))
        source += '\nclass Alpha:\n    def only(self):\n        pass\n'
        source += ''.join(f'\ndef f{i}():\n    return {i}\n' for i in range(10))
        files = (parsed('src/net/client.py', source), parsed('src/net/run.sh', 'echo hello\n'),
                 parsed('src/net/empty.py', ''), parsed('top.py', 'answer = 1\n'))
        with patch('socket.socket', side_effect=AssertionError('network must not run')):
            sections = render_sections(files)
            self.assertEqual(sections, render_sections(tuple(reversed(files))))
        self.assertEqual([section['directory'] for section in sections], ['.', 'src/net'])
        section = sections[1]
        self.assertEqual((section['files'], section['symbols']), (3, 24))
        self.assertEqual(section['text'], '## src/net\n\n'
            '- **client.py** — Alpha (only); Zed (m0, m1, m2, m3, m4, m5, m6, m7, +3 more); '
            'f0, f1, f2, f3, f4, f5, f6, f7, +2 more\n- **empty.py**\n- **run.sh**\n')
        self.assertEqual(sections[0]['text'], '## .\n\n- **top.py**\n')

    def test_duplicate_nested_classes_continuations_kind_and_position_ties(self):
        file = parsed('same.py', 'class A:\n    value = 1\n    def first(self):\n        pass\n'
            '    class Inner:\n        def nested(self):\n            pass\n    value = 2\n'
            'class A:\n    def second(self):\n        pass\n')
        section = render_sections((file,))[0]
        self.assertEqual(section['symbols'], 6)
        self.assertEqual(section['text'], '## .\n\n- **same.py** — A (first); A (second); A.Inner (nested)\n')
        symbol = OverviewSymbol('thing', 'interface', 4)
        function = OverviewSymbol('thing', 'function', 4)
        self.assertNotEqual(render_sections((OverviewFile('a.ts', (symbol,)),)),
                            render_sections((OverviewFile('a.ts', (function,)),)))
        tied = OverviewFile('a.py', (OverviewSymbol('z', 'function', 8), OverviewSymbol('a', 'function', 8)))
        self.assertIn('a, z', render_sections((tied,))[0]['text'])
        repeated = parsed('many.py', ''.join(f'class C:\n    def m{i}(self):\n        pass\n' for i in range(1, 12)))
        repeated_section = render_sections((repeated,))[0]
        self.assertEqual(repeated_section['symbols'], 22)
        self.assertIn('; '.join(f'C (m{i})' for i in range(1, 12)), repeated_section['text'])
