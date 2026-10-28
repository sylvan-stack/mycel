"""Dedicated MYC-10 parser, scope, text and real inherited-process proofs.

Future preparation only. These methods are authored/compiled, not executed by
their author. Provider/store seams are controlled; primary grep is a real child.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from mycel._settings import load_settings

SOURCE = Path(__file__).resolve().parents[1] / 'src'


def configured(root):
    folders = {}
    for name in ('alpha', 'beta', 'disabled'):
        folders[name] = root / 'team' / name
        folders[name].mkdir(parents=True)
        (root / 'documents' / name).mkdir(parents=True)
    (folders['alpha'] / 'nested').mkdir()
    (root / 'outside').mkdir()
    (root / 'org-documents').mkdir()
    config = root / 'settings.toml'
    text = '[store]\naddress="postgresql://fixture@localhost/fixture"\n'
    text += '[search]\nshared_documents=[]\n'
    text += '[organizations.team]\nroot=' + json.dumps(str(root / 'team'))
    text += '\nartifact_root=' + json.dumps(str(root / 'org-documents')) + '\n'
    for name, folder in folders.items():
        text += '[repos.' + name + ']\nenabled=' + ('false' if name == 'disabled' else 'true')
        text += '\ncode_root=' + json.dumps(str(folder))
        text += '\nartifact_root=' + json.dumps(str(root / 'documents' / name)) + '\n'
    text += '[repos.nested]\nenabled=true\ncode_root=' + json.dumps(str(folders['alpha'] / 'nested')) + '\n'
    config.write_text(text)
    return load_settings(path=config), folders


def document(owner='alpha', *, identifier='doc-a', root='artifact', path='guide.md', name='Start', **marks):
    return {'id': identifier, 'repository': owner, 'root': root, 'path': path,
            'name': name, 'document': name, 'address': f'{owner}:@{root}/{path}#{name}',
            'stale': False, 'heartwood': False, **marks}


def payload():
    first = document(stale=True, heartwood=True)
    foreign = document('beta', identifier='doc-b')
    return {'schema': 3, 'repository': 'alpha', 'route': 'identifier',
            'meaning': {'used': True}, 'results': [
        {'id': 'code-a', 'repository': 'alpha', 'root': 'code', 'path': 'src/work.py',
         'name': 'Work', 'address': 'alpha:@code/src/work.py#Work', 'origin': 'code',
         'kind': 'function', 'lines': {'start': 4, 'end': 7}, 'score': .987654321,
         'via': first, 'documentedIn': [first, first, foreign], 'stale': False, 'heartwood': False},
        {'id': 'code-b', 'repository': 'alpha', 'root': 'code', 'path': 'other.py',
         'name': 'Other', 'address': 'alpha:@code/other.py#Other', 'origin': 'code',
         'kind': 'function', 'lines': {'start': 9, 'end': 9}, 'score': .87654321,
         'documentedIn': [first, foreign], 'stale': False, 'heartwood': False}]}


class GrepTailUnitTests(unittest.TestCase):
# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_explicit_attached_clustered_and_late_patterns_preserve_paths_conservatively
#     def test_explicit_attached_clustered_and_late_patterns_preserve_paths_conservatively(self):
#         cases = [
#             (('-rn', 'needle', 'src', 'other'), 'needle', ('src', 'other')),
#             (('-rA', '3', 'needle', 'src'), 'needle', ('src',)),
#             (('-rA3', 'needle', 'src'), 'needle', ('src',)),
#             (('--regexp=needle', 'src'), 'needle', ('src',)),
#             (('-eneedle', 'src'), 'needle', ('src',)),
#             (('src', '-e', 'first', '-e', 'second', 'other'), 'first', ('src', 'other')),
#             (('--regexp', 'first', '--regexp=second', 'src'), 'first', ('src',)),
#             (('-i', '--', '-needle', 'src'), '-needle', ('src',)),
#             (('--color', 'needle', 'src'), 'needle', ('src',)),
#             (('--color=never', '-B2', 'needle', 'src'), 'needle', ('src',)),
#         ]
#         for arguments, pattern, paths in cases:
#             with self.subTest(arguments=arguments):
#                 original = tuple(arguments)
#                 selection = parse_grep_args(arguments)
#                 self.assertTrue(selection.eligible)
#                 self.assertEqual(selection.pattern, pattern)
#                 self.assertEqual(selection.paths, paths)
#                 self.assertEqual(arguments, original)
#         for arguments in (('--clearly-unknown-option', 'needle', 'src'),
#                           ('-rY', 'needle', 'src'), ('-A',), ('-e',)):
#             with self.subTest(arguments=arguments):
#                 self.assertFalse(parse_grep_args(arguments).eligible)
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_explicit_attached_clustered_and_late_patterns_preserve_paths_conservatively

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_every_accepted_suppression_precedes_settings_and_optional_search
#     def test_every_accepted_suppression_precedes_settings_and_optional_search(self):
#         suppressed = [
#             ('-c', 'needle'), ('-rc', 'needle'), ('--count', 'needle'),
#             ('-l', 'needle'), ('--files-with-matches', 'needle'),
#             ('-L', 'needle'), ('--files-without-match', 'needle'),
#             ('-q', 'needle'), ('--quiet', 'needle'), ('--silent', 'needle'),
#             ('-f', 'patterns.txt', 'src'), ('-fpatterns.txt', 'src'),
#             ('--file=patterns.txt', 'src'), ('--file', 'patterns.txt', 'src'),
#             ('--unknown-flag', 'needle'), ('ab',), ('a.b',), ('[a]+',),
#         ]
#         for arguments in suppressed:
#             with self.subTest(arguments=arguments):
#                 loader, search = Mock(side_effect=AssertionError('settings accessed')), Mock()
#                 out, err = io.StringIO(), io.StringIO()
#                 append_tail(Invocation('grep', arguments=arguments), 0, stdout=out, stderr=err,
#                             settings_loader=loader, search=search, environ={})
#                 self.assertEqual((out.getvalue(), err.getvalue()), ('', ''))
#                 loader.assert_not_called()
#                 search.assert_not_called()
#         for status, environment in ((2, {}), (127, {}), (130, {}), (0, {'MYCEL_GREP_PLAIN': '1'})):
#             loader, search = Mock(), Mock()
#             append_tail(Invocation('grep', arguments=('needle',)), status, stdout=io.StringIO(),
#                         stderr=io.StringIO(), settings_loader=loader, search=search, environ=environment)
#             loader.assert_not_called()
#             search.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_every_accepted_suppression_precedes_settings_and_optional_search

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_dotted_identifiers_survive_and_other_signs_become_spaces_before_literal_minimum
#     def test_dotted_identifiers_survive_and_other_signs_become_spaces_before_literal_minimum(self):
#         self.assertEqual(semantic_query('session.renew'), 'session.renew')
#         self.assertEqual(' '.join(semantic_query('foo[ab]+(bar)|baz$').split()), 'foo ab bar baz')
#         for pattern in ('a.b', 'ab', '[a]+', '.*', 'é雪'):
#             self.assertIsNone(semantic_query(pattern))
#         self.assertEqual(semantic_query('é雪a'), 'é雪a')
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_dotted_identifiers_survive_and_other_signs_become_spaces_before_literal_minimum

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_first_path_actual_folders_longest_root_and_single_member_organization_boundary
#     def test_first_path_actual_folders_longest_root_and_single_member_organization_boundary(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             settings, folders = configured(root)
#             self.assertEqual(resolve_tail_repository(settings, cwd=folders['alpha']), 'alpha')
#             self.assertEqual(resolve_tail_repository(settings, (str(folders['alpha'] / 'file.py'),
#                 str(folders['beta'] / 'other.py')), cwd=folders['beta']), 'alpha')
#             self.assertEqual(resolve_tail_repository(settings, ('../alpha/file.py',), cwd=folders['beta']), 'alpha')
#             self.assertEqual(resolve_tail_repository(settings, cwd=folders['alpha'] / 'nested'), 'nested')
#             self.assertEqual(resolve_tail_repository(settings,
#                 (str(root / 'documents' / 'alpha' / 'guide.md'),), cwd=root / 'outside'), 'alpha')
#             for anchor in (root / 'outside', folders['disabled'], root / 'team', root / 'org-documents'):
#                 self.assertIsNone(resolve_tail_repository(settings, cwd=anchor))
#             one = replace(settings, values=_freeze({**settings.values,
#                 'repos': {'alpha': settings.values['repos']['alpha']}}))
#             self.assertIsNone(resolve_tail_repository(one, cwd=root / 'team'))
#             self.assertEqual(resolve_tail_repository(one, cwd=folders['alpha']), 'alpha')
#             outer = replace(one, values=_freeze({**one.values, 'repos': {'alpha': {
#                 **one.values['repos']['alpha'], 'code_root': str(root)}}}))
#             # An explicit broad repository root cannot swallow a deeper
#             # organization anchor, even when it has only one enabled member.
#             for anchor in (root / 'team', root / 'org-documents'):
#                 self.assertIsNone(resolve_tail_repository(outer, cwd=anchor))
#             self.assertEqual(resolve_tail_repository(outer, cwd=root / 'outside'), 'alpha')
#             broad_artifacts = replace(one, values=_freeze({**one.values, 'repos': {'alpha': {
#                 **one.values['repos']['alpha'], 'artifact_root': str(root)}}}))
#             self.assertIsNone(resolve_tail_repository(broad_artifacts, cwd=root / 'org-documents'))
#             self.assertEqual(resolve_tail_repository(broad_artifacts, cwd=folders['alpha']), 'alpha')
#             ambiguous = replace(settings, values=_freeze({**settings.values, 'repos': {
#                 **settings.values['repos'], 'duplicate': settings.values['repos']['alpha']}}))
#             # Ambiguous settings can surface either as an unavailable scope or
#             # its existing typed settings fault. Neither may reach search.
#             search = Mock()
#             out, err = io.StringIO(), io.StringIO()
#             append_tail(Invocation('grep', arguments=('needle',), settings=ambiguous), 0,
#                 stdout=out, stderr=err, cwd=folders['alpha'], search=search, environ={})
#             self.assertEqual(out.getvalue(), '')
#             self.assertLessEqual(len(err.getvalue().splitlines()), 1)
#             search.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_first_path_actual_folders_longest_root_and_single_member_organization_boundary

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_delimited_ordered_tail_has_exact_places_lines_delivery_and_unique_marked_sections_without_scores
#     def test_delimited_ordered_tail_has_exact_places_lines_delivery_and_unique_marked_sections_without_scores(self):
#         data = payload()
#         rendered = render_tail(data)
#         self.assertIn('── mycel: related search results (not grep output) ──', rendered)
#         self.assertIn('── mycel: documented in ──', rendered)
#         results, docs = rendered.split('── mycel: documented in ──', 1)
#         self.assertLess(results.index('alpha:@code/src/work.py#Work'), results.index('alpha:@code/other.py#Other'))
#         self.assertIn('L4-7', results)
#         self.assertIn('L9-9', results)
#         self.assertIn('⇐ via alpha:@artifact/guide.md › Start', results)
#         self.assertEqual(docs.count('alpha:@artifact/guide.md › Start'), 1)
#         self.assertEqual(docs.count('beta:@artifact/guide.md › Start'), 1)
#         self.assertIn('⚠ stale', docs)
#         self.assertIn('[heartwood]', docs)
#         self.assertNotIn('score', rendered.lower())
#         self.assertNotIn('.987654321', rendered)
#         self.assertNotIn('.87654321', rendered)
#         self.assertEqual(render_tail({**data, 'results': []}), '')
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_delimited_ordered_tail_has_exact_places_lines_delivery_and_unique_marked_sections_without_scores

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_document_identity_dedup_and_control_characters_cannot_forge_tail_lines
#     def test_document_identity_dedup_and_control_characters_cannot_forge_tail_lines(self):
#         data = payload()
#         original = document(identifier='stable', path='same.md', name='A')
#         alias = document(identifier='stable', path='alias.md', name='A')
#         second = document(identifier='separate', path='same.md', name='B')
#         no_id = document(identifier=None, path='none.md', name='Section')
#         data['results'][0]['documentedIn'] = [original, alias, second, no_id, dict(no_id)]
#         data['results'][1]['documentedIn'] = [alias, second]
#         docs = render_tail(data).split('── mycel: documented in ──', 1)[1]
#         self.assertEqual(docs.count('same.md › A'), 1)
#         self.assertNotIn('alias.md', docs)
#         self.assertEqual(docs.count('same.md › B'), 1)
#         self.assertEqual(docs.count('none.md › Section'), 1)
#         data['results'][0]['name'] = 'Work\nINJECTED\r\x1b[31m'
#         data['results'][0]['address'] = 'alpha:@code/src/work.py#Work\nINJECTED\r\x1b[31m'
#         rendered = render_tail(data)
#         self.assertNotIn('\nINJECTED', rendered)
#         self.assertNotIn('\r', rendered)
#         self.assertNotIn('\x1b', rendered)
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_document_identity_dedup_and_control_characters_cannot_forge_tail_lines

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_explicit_plain_silences_invalid_settings_while_selected_failure_is_one_private_line
#     def test_explicit_plain_silences_invalid_settings_while_selected_failure_is_one_private_line(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             missing = load_settings(path=root / 'missing.toml')
#             search = Mock(side_effect=AssertionError('invalid settings reached search'))
#             out, err = io.StringIO(), io.StringIO()
#             append_tail(Invocation('grep', arguments=('needle',), settings=missing), 1,
#                         stdout=out, stderr=err, search=search, environ={})
#             self.assertEqual(out.getvalue(), '')
#             self.assertEqual(len(err.getvalue().splitlines()), 1)
#             self.assertNotIn('"error"', err.getvalue())
#             search.assert_not_called()
#             err = io.StringIO()
#             append_tail(Invocation('grep', arguments=('needle',), settings=missing, grep_plain=True), 1,
#                 stdout=io.StringIO(), stderr=err, search=search, environ={'MYCEL_GREP_PLAIN': '1'})
#             self.assertEqual(err.getvalue(), '')
#             settings, folders = configured(root)
#             selected = Mock(return_value=payload())
#             out, err = io.StringIO(), io.StringIO()
#             append_tail(Invocation('grep', arguments=('needle',), settings=settings), 0,
#                 stdout=out, stderr=err, cwd=folders['alpha'], search=selected,
#                 environ={'MYCEL_GREP_PLAIN': '0', 'BETTER_GREP_PLAIN': '1'})
#             self.assertTrue(out.getvalue())
#             self.assertEqual(err.getvalue(), '')
#             selected.assert_called_once_with(settings, 'needle', 'alpha')
#             for error in (MycelError('store_unavailable', 'A safe store refusal.'),
#                           RuntimeError('private-sentinel\ninjected'), KeyboardInterrupt()):
#                 out, err = io.StringIO(), io.StringIO()
#                 append_tail(Invocation('grep', arguments=('needle',), settings=settings), 1,
#                     stdout=out, stderr=err, cwd=folders['alpha'], environ={},
#                     search=Mock(side_effect=error))
#                 self.assertEqual(out.getvalue(), '')
#                 self.assertEqual(len(err.getvalue().splitlines()), 1)
#                 self.assertNotIn('private-sentinel', err.getvalue())
#                 self.assertNotIn('"error"', err.getvalue())
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_explicit_plain_silences_invalid_settings_while_selected_failure_is_one_private_line

    def executable(self, folder, *, status=0, label=b'FIRST', wait=False):
        folder.mkdir()
        report = folder.parent / (folder.name + '.json')
        script = '#!' + sys.executable + '\nimport json,os,sys,time\n'
        script += 'with open(' + repr(str(report)) + ',"w") as out:\n json.dump({"argv":sys.argv[1:],"cwd":os.getcwd(),"pid":os.getpid(),"pgid":os.getpgrp(),"private":[key for key in ("VOYAGE_API_KEY","MYCEL_API_KEY","PGPASSWORD") if key in os.environ]},out)\n'
        if wait:
            script += 'sys.stderr.write("fixture-ready\\n");sys.stderr.flush();time.sleep(60)\n'
        else:
            script += 'data=sys.stdin.buffer.read();sys.stdout.buffer.write(' + repr(label + b'\x00\xff\n') + '+data);sys.stdout.buffer.flush();sys.stderr.buffer.write(b"grep-own-error\\x00\\xff\\n");sys.stderr.flush()\n'
        script += 'raise SystemExit(' + str(status) + ')\n'
        path = folder / 'grep'
        path.write_text(script)
        path.chmod(0o755)
        return report

    def invoke(self, root, settings, arguments, *, status=0, mode='normal', plain=False, input=b'needle\xff\n'):
        folder = root / ('bin-' + str(status) + '-' + mode)
        report = self.executable(folder, status=status)
        second = root / ('second-' + str(status) + '-' + mode)
        self.executable(second, status=99, label=b'SECOND')
        script = 'import json,os,sys\nfrom pathlib import Path\nfrom mycel._coverage import no_network\nimport mycel._grep as g\nimport mycel._cli as cli\nimport mycel._settings as settings_module\nfrom mycel._cli import main\n'
        script += 'real_load=settings_module.load_settings\n'
        script += 'def after_primary(*args,**kwargs):\n observed=json.loads(Path(' + repr(str(report)) + ').read_text())\n'
        script += ' try: os.kill(observed["pid"],0)\n except ProcessLookupError: pass\n else: raise AssertionError("optional settings preceded completed primary grep")\n return real_load(*args,**kwargs)\n'
        script += 'settings_module.load_settings=after_primary\ncli.load_settings=after_primary\n'
        script += 'g.search_tail=lambda *args,**kwargs:' + repr(payload()) + '\n'
        if mode in {'search', 'cancel', 'exit'}:
            error = ('KeyboardInterrupt()' if mode == 'cancel' else 'SystemExit(37)' if mode == 'exit'
                     else 'RuntimeError("private-sentinel\\ninjected")')
            script += 'def fail(*args,**kwargs): raise ' + error + '\ng.search_tail=fail\n'
        elif mode == 'render':
            script += 'def fail(*args,**kwargs): raise RuntimeError("private-sentinel\\ninjected")\ng.render_tail=fail\n'
        elif mode == 'stdout-close':
            script += 'def close_output(*args,**kwargs):\n os.close(1)\n return ' + repr(payload()) + '\ng.search_tail=close_output\n'
        elif mode == 'stderr-close':
            script += 'def fail(*args,**kwargs):\n os.close(2)\n raise RuntimeError("private-sentinel")\ng.search_tail=fail\n'
        elif mode in {'write', 'flush'}:
            script += 'real=sys.stdout\nclass Faulty:\n def write(self,text):\n'
            script += '  raise BrokenPipeError()\n' if mode == 'write' else '  return real.write(text)\n'
            script += ' def flush(self):\n'
            script += '  raise OSError("private-sentinel")\n' if mode == 'flush' else '  return real.flush()\n'
            script += 'sys.stdout=Faulty()\n'
        script += 'with no_network():\n code=main()\n'
        if mode in {'write', 'flush'}:
            script += 'sys.stdout=real\n'
        script += 'raise SystemExit(code)\n'
        env = {'PATH': str(folder) + os.pathsep + str(second), 'HOME': str(root),
            'PYTHONPATH': str(SOURCE), 'PYTHONDONTWRITEBYTECODE': '1',
            'MYCEL_CONFIG': str(settings.file), 'LC_ALL': 'C', 'VOYAGE_API_KEY': 'private-sentinel',
            'MYCEL_API_KEY': 'private-sentinel', 'PGPASSWORD': 'private-sentinel'}
        if plain:
            env['MYCEL_GREP_PLAIN'] = '1'
        result = subprocess.run([sys.executable, '-B', '-c', script, 'grep', *arguments],
            cwd=root / 'team' / 'alpha', env=env, input=input, capture_output=True, timeout=10)
        return result, json.loads(report.read_text())

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_real_path_first_child_receives_literal_argv_binary_streams_and_unchanged_cwd_without_settings
#     def test_real_path_first_child_receives_literal_argv_binary_streams_and_unchanged_cwd_without_settings(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             settings, folders = configured(root)
#             missing = replace(settings, file=root / 'missing.toml')
#             data = b'needle\x00\xff\nother\n'
#             arguments = ['-rA', '3', '-e', 'needle $(literal)', '--', 'a path', '-dash']
#             result, report = self.invoke(root, missing, arguments, plain=True, input=data)
#             self.assertEqual(result.returncode, 0)
#             self.assertEqual(result.stdout, b'FIRST\x00\xff\n' + data)
#             self.assertEqual(result.stderr, b'grep-own-error\x00\xff\n')
#             self.assertEqual({key: report[key] for key in ('argv', 'cwd', 'private')},
#                              {'argv': arguments, 'cwd': str(folders['alpha'].resolve()), 'private': []})
#             self.assertEqual(report['pid'], report['pgid'])
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_real_path_first_child_receives_literal_argv_binary_streams_and_unchanged_cwd_without_settings

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_real_child_help_version_noargs_no_match_error_and_eligible_pipe_preserve_grep_prefix_and_status
#     def test_real_child_help_version_noargs_no_match_error_and_eligible_pipe_preserve_grep_prefix_and_status(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             settings, _ = configured(root)
#             cases = [(['--help'], 0), (['--version'], 0), ([], 2),
#                      (['needle'], 1), (['needle'], 2), (['needle'], 0)]
#             for index, (arguments, status) in enumerate(cases):
#                 # Each fixture has a distinct directory, so no cleanup/reuse can
#                 # accidentally supply an earlier process outcome.
#                 case = root / str(index)
#                 case.mkdir()
#                 current, _ = configured(case)
#                 result, report = self.invoke(case, current, arguments, status=status)
#                 self.assertEqual(result.returncode, status)
#                 prefix = b'FIRST\x00\xff\nneedle\xff\n'
#                 self.assertTrue(result.stdout.startswith(prefix))
#                 self.assertEqual(report['argv'], arguments)
#                 if arguments == ['needle'] and status in (0, 1):
#                     # capture_output gives the actual wrapper non-TTY pipes;
#                     # accepted MYC-10 does not suppress their eligible tail.
#                     self.assertIn('── mycel: related search results'.encode(), result.stdout[len(prefix):])
#                 else:
#                     self.assertEqual(result.stdout, prefix)
#             case = root / 'unterminated'
#             case.mkdir()
#             current, _ = configured(case)
#             data = b'last-line-without-a-newline'
#             result, _ = self.invoke(case, current, ['needle'], input=data)
#             prefix = b'FIRST\x00\xff\n' + data
#             self.assertTrue(result.stdout.startswith(prefix))
#             self.assertTrue(result.stdout[len(prefix):].startswith(b'\n' + '── mycel:'.encode()))
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_real_child_help_version_noargs_no_match_error_and_eligible_pipe_preserve_grep_prefix_and_status

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_real_child_status_survives_search_render_write_flush_and_tail_cancellation_faults
#     def test_real_child_status_survives_search_render_write_flush_and_tail_cancellation_faults(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             for mode in ('search', 'render', 'write', 'flush', 'cancel', 'exit', 'stdout-close', 'stderr-close'):
#                 case = root / mode
#                 case.mkdir()
#                 settings, _ = configured(case)
#                 result, _ = self.invoke(case, settings, ['needle'], status=1, mode=mode)
#                 self.assertEqual(result.returncode, 1, (mode, result.stderr))
#                 self.assertTrue(result.stdout.startswith(b'FIRST\x00\xff\nneedle\xff\n'))
#                 explanation = result.stderr.removeprefix(b'grep-own-error\x00\xff\n')
#                 self.assertEqual(len(explanation.splitlines()), 0 if mode == 'stderr-close' else 1,
#                                  (mode, result.stderr))
#                 self.assertNotIn(b'private-sentinel', result.stdout + result.stderr)
#                 self.assertNotIn(b'"error"', result.stdout + result.stderr)
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_real_child_status_survives_search_render_write_flush_and_tail_cancellation_faults

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group
#     def test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             settings, folders = configured(root)
#             binary = root / 'waiting-bin'
#             report = self.executable(binary, wait=True)
#             script = ('from mycel._cli import main\nfrom mycel._coverage import no_network\n'
#                       'with no_network():\n raise SystemExit(main())\n')
#             env = {'PATH': str(binary), 'HOME': str(root), 'PYTHONPATH': str(SOURCE),
#                    'PYTHONDONTWRITEBYTECODE': '1', 'MYCEL_CONFIG': str(settings.file)}
#             process = subprocess.Popen([sys.executable, '-B', '-c', script, 'grep', 'needle'],
#                 cwd=folders['alpha'], env=env, stdin=subprocess.DEVNULL,
#                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#             try:
#                 with selectors.DefaultSelector() as ready:
#                     ready.register(process.stderr, selectors.EVENT_READ)
#                     self.assertTrue(ready.select(10), 'Primary grep did not reach its ready marker.')
#                 self.assertEqual(process.stderr.readline(), b'fixture-ready\n')
#                 process.send_signal(signal.SIGINT)
#                 out, err = process.communicate(timeout=10)
#                 self.assertEqual(process.returncode, 128 + signal.SIGINT)
#                 self.assertNotIn(b'"error"', out + err)
#                 observed = json.loads(report.read_text())
#                 self.assertEqual(observed['argv'], ['needle'])
#                 with self.assertRaises(ProcessLookupError):
#                     os.killpg(observed['pgid'], 0)
#             finally:
#                 if process.poll() is None:
#                     process.kill()
#                 if report.exists():
#                     try:
#                         os.killpg(json.loads(report.read_text())['pgid'], signal.SIGKILL)
#                     except ProcessLookupError:
#                         pass
#                 process.communicate(timeout=5)
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group

# TEST-TIER-DISABLED-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_only_mycel_console_entry_and_raw_grep_command_are_exposed
#     def test_only_mycel_console_entry_and_raw_grep_command_are_exposed(self):
#         root = Path(__file__).resolve().parents[1]
#         project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
#         self.assertEqual(set(project['scripts']), {'mycel'})
#         self.assertNotIn('better-grep', project['scripts'])
#         arguments = ('--help', '--version', '--repo', 'literal', '--', '-needle')
#         self.assertEqual(parse(['grep', *arguments]).arguments, arguments)
#         commands = help_reply()['commands']
#         self.assertEqual(sum(row['name'] == 'grep' for row in commands), 1)
#         self.assertFalse(any(row['name'] == 'better-grep' for row in commands))
# TEST-TIER-DISABLED-END tests/test_grep_tail.py::GrepTailUnitTests.test_only_mycel_console_entry_and_raw_grep_command_are_exposed

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:6
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:7
# import io
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:11
# import selectors
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:12
# import signal
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:15
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:16
# import tomllib
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:18
# from unittest.mock import Mock
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:18
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:20
# from mycel._cli import Invocation, parse
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:20
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:21
# from mycel._commands import help_reply
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:21
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:22
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:22
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:23
# from mycel._grep import (append_tail, parse_grep_args, render_tail,
#                          resolve_tail_repository, semantic_query)
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:23
# TEST-TIER-IMPORTS-BEGIN tests/test_grep_tail.py:25
# from mycel._settings import _freeze, load_settings
# TEST-TIER-IMPORTS-END tests/test_grep_tail.py:25
