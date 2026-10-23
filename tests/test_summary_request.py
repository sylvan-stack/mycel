from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
import io

from mycel._cli import run
from mycel._errors import MycelError
from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._settings import _freeze, load_settings
from mycel._source_refs import parse_source_address
from mycel._summary_request import (CUT_NOTICE, REQUEST_LIMIT, SummaryPrompts,
    SummarySection, load_summary_prompts, plan_summary_requests, summary_command)


def section(path, name, source, position=0, *, identifier=None, repository='fixture'):
    raw = source.encode('utf-8')
    place = parse_source_address(f'{repository}:@artifact/{path}#{name}')
    chunk = ResolvedChunk(identifier or path + ':' + name, 1, name, 'document', raw, sha256(raw).hexdigest())
    return SummarySection(SelectionMember(place, chunk), position)


class SummaryRequestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'config.toml'
        self.config.write_text('')
        self.settings = load_settings(path=self.config)
        self.prompts = load_summary_prompts(self.settings)

    def test_packaged_legacy_wording_and_complete_canonical_path_position_order(self):
        members = (section('z.md', 'Last', 'full z\r\ntext 雪'),
                   section('a.md', 'Later', '# Later\n' + 'x' * 3000, 70),
                   section('a.md', 'First', '# First\n🙂 first', 10))
        request, = plan_summary_requests(members, self.prompts)
        self.assertEqual(request.sections, (members[2], members[1], members[0]))
        expected = ('You summarise clusters of related project documentation so the summary can be retrieved on its own. Be faithful and self-contained.\n\n'
                    'Write a concise, self-contained summary of the following related documentation sections. Capture the key points and how they relate, with no preamble.\n\n'
                    'a.md › First\n# First\n🙂 first\n\n---\n\na.md › Later\n# Later\n' + 'x' * 3000 +
                    '\n\n---\n\nz.md › Last\nfull z\r\ntext 雪')
        self.assertEqual(request.request, expected.encode())
        self.assertEqual(request.sent_texts, tuple(s.member.chunk.source for s in request.sections))
        self.assertEqual(plan_summary_requests(tuple(reversed(members)), self.prompts), (request,))
        self.assertEqual(request.hash, sha256(expected.encode()).hexdigest())
        self.assertEqual(request.cut, ())

    def test_recursive_halves_cover_every_member_with_complete_unicode_budgets(self):
        sections = tuple(section(f'{i:02}.md', 'Section', f'{i}: ' + '🙂e\u0301' * 6000) for i in range(9))
        requests = plan_summary_requests(tuple(reversed(sections)), self.prompts)
        self.assertGreater(len(requests), 2)
        self.assertEqual(tuple(s for r in requests for s in r.sections), sections)
        for request in requests:
            self.assertLessEqual(len(request.request.decode()), REQUEST_LIMIT)
            self.assertEqual(request.cut, ())
            for s, sent in zip(request.sections, request.sent_texts):
                self.assertEqual(sent, s.member.chunk.source)
                self.assertIn(s.place_line.encode() + b'\n' + sent, request.request)
        self.assertEqual(plan_summary_requests((), self.prompts), ())

    def test_single_oversized_section_retains_unicode_prefix_notice_and_disclosed_place(self):
        s = section('large.md', 'Huge', '雪🙂' * 30000)
        request, = plan_summary_requests((s,), self.prompts)
        self.assertEqual(len(request.request.decode()), REQUEST_LIMIT)
        sent = request.sent_texts[0].decode()
        self.assertTrue(sent.endswith('\n\n' + CUT_NOTICE))
        self.assertTrue(s.member.chunk.source.decode().startswith(sent.removesuffix('\n\n' + CUT_NOTICE)))
        self.assertEqual(request.cut, (s.member.place.address,))
        self.assertEqual(request.report()['cut'], list(request.cut))
        self.assertEqual(s.member.chunk.source, ('雪🙂' * 30000).encode())

    def test_exact_limit_is_not_cut_and_one_character_over_is_reported(self):
        framing = self.prompts.render('same.md › Exact\n')
        room = REQUEST_LIMIT - len(framing)
        exact = section('same.md', 'Exact', 'x' * room)
        request, = plan_summary_requests((exact,), self.prompts)
        self.assertEqual(request.cut, ())
        self.assertEqual(len(request.request.decode()), REQUEST_LIMIT)
        oversized = section('same.md', 'Exact', 'x' * (room + 1))
        request, = plan_summary_requests((oversized,), self.prompts)
        self.assertEqual(request.cut, (oversized.member.place.address,))
        self.assertEqual(len(request.request.decode()), REQUEST_LIMIT)

    def test_override_files_are_read_once_exactly_and_replace_single_marker(self):
        instruction = b'  custom instruction\r\n'
        task = ' before 雪\n$sections\nafter  '.encode()
        (self.root / 'raptor-summary.md').write_bytes(instruction)
        (self.root / 'raptor-request.md.tmpl').write_bytes(task)
        settings = replace(self.settings, values=_freeze({**self.settings.values,
            'summaries': {'instructions': str(self.root), 'at_once': 4}}))
        prompts = load_summary_prompts(settings)
        self.assertEqual((prompts.instruction, prompts.task, prompts.profile), (instruction, task, 'override'))
        (self.root / 'raptor-summary.md').unlink()
        request, = plan_summary_requests((section('a.md', 'One', 'complete'),), prompts)
        self.assertEqual(request.request, 'custom instruction\n\nbefore 雪\na.md › One\ncomplete\nafter'.encode())
        self.assertEqual(prompts.hashes['task'], sha256(task).hexdigest())

    def test_missing_writer_refuses_generation_but_report_and_dry_run_plan_need_no_command(self):
        for operation in ('build', 'regenerate'):
            with self.assertRaises(MycelError) as caught:
                summary_command(self.settings, operation=operation)
            self.assertEqual(caught.exception.code, 'settings')
            self.assertIsNone(summary_command(self.settings, operation=operation, dry_run=True))
        for operation in ('status', 'remove', 'search'):
            self.assertIsNone(summary_command(self.settings, operation=operation))
        self.assertEqual(len(plan_summary_requests((section('a.md', 'One', 'text'),), self.prompts)), 1)
        settings = replace(self.settings, values=_freeze({**self.settings.values,
            'summaries': {'command': ['/literal/writer', '$(literal)', '~literal'], 'at_once': 2}}))
        self.assertEqual(summary_command(settings, operation='build'), ('/literal/writer', '$(literal)', '~literal'))

    def test_cli_missing_command_checks_generation_before_pending_handler(self):
        from unittest.mock import patch
        self.config.write_text('[store]\naddress="postgresql://fixture@localhost/disposable"\n'
                               '[repos.fixture]\nenabled=true\ncode_root="' + str(self.root) + '"\n')
        with patch.dict('os.environ', {'MYCEL_CONFIG': str(self.config)}), \
                patch('mycel._cli.invocation_store', side_effect=MycelError('refused', 'The injected store boundary is pending.')):
            for args, code in [(['build'], 'settings'), (['regenerate'], 'settings'),
                               (['build', '--dry-run'], 'refused'), (['regenerate', '--dry-run'], 'refused'),
                               (['status'], 'refused'), (['remove'], 'refused')]:
                out = io.StringIO()
                self.assertEqual(run(['summaries', *args, '--repo', 'fixture'], stdout=out), 1)
                import json
                self.assertEqual(json.loads(out.getvalue())['error']['code'], code)

    def test_invalid_argv_and_overrides_refuse_before_requests_with_redacted_settings(self):
        for command in ((), ('',), ('  ',), ('writer', '\0private-sentinel')):
            values = {**self.settings.values, 'summaries': {'command': command, 'at_once': 1}}
            with self.assertRaises(MycelError) as caught:
                summary_command(replace(self.settings, values=_freeze(values)), operation='build')
            self.assertEqual(caught.exception.code, 'settings')
            self.assertNotIn('private-sentinel', caught.exception.message)
        (self.root / 'raptor-summary.md').write_text('instruction')
        settings = replace(self.settings, values=_freeze({**self.settings.values,
            'summaries': {'command': ['writer'], 'instructions': str(self.root), 'at_once': 1}}))
        for raw in (None, b'no marker', b'$sections and $sections', b'\xff$sections', b'   ',
                    ('x' * REQUEST_LIMIT + '$sections').encode()):
            task = self.root / 'raptor-request.md.tmpl'
            if raw is None:
                task.unlink(missing_ok=True)
            else:
                task.write_bytes(raw)
            with self.assertRaises(MycelError) as caught:
                summary_command(settings, operation='regenerate')
            self.assertEqual(caught.exception.code, 'settings')

    def test_framing_and_place_line_leave_room_for_cut_notice_or_refuse(self):
        for instruction in ('x' * (REQUEST_LIMIT - 2), 'x' * REQUEST_LIMIT):
            with self.assertRaises(MycelError) as caught:
                SummaryPrompts(instruction.encode(), b'$sections', 'override')
            self.assertEqual(caught.exception.code, 'settings')
        prompts = SummaryPrompts(('x' * (REQUEST_LIMIT - 35)).encode(), b'$sections', 'override')
        with self.assertRaises(MycelError) as caught:
            plan_summary_requests((section('a.md', 'One', 'z' * 200),), prompts)
        self.assertEqual(caught.exception.code, 'settings')

    def test_duplicate_or_cross_repository_members_and_corrupt_source_are_refused(self):
        one = section('a.md', 'One', 'text')
        for members in ((one, one), (one, section('b.md', 'Two', 'text', repository='other'))):
            with self.assertRaises(MycelError):
                plan_summary_requests(members, self.prompts)
        with self.assertRaises(MycelError):
            SummarySection(replace(one.member, chunk=replace(one.member.chunk, source=b'changed')), 0)
        invalid = replace(one.member.chunk, source=b'\xff', snapshot_hash=sha256(b'\xff').hexdigest())
        with self.assertRaises(MycelError):
            SummarySection(replace(one.member, chunk=invalid), 0)


if __name__ == '__main__':
    unittest.main()
