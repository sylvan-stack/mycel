# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Dedicated MYC-10 parser, scope, text and real inherited-process proofs.

Future preparation only. These methods are authored/compiled, not executed by
their author. Provider/store seams are controlled; primary grep is a real child.
"""
from dataclasses import replace
import io
import selectors
import signal
import tempfile
import tomllib
from unittest.mock import Mock

from mycel._cli import Invocation, parse
from mycel._commands import help_reply
from mycel._errors import MycelError
from mycel._grep import (append_tail, parse_grep_args, render_tail,
                         resolve_tail_repository, semantic_query)
from mycel._settings import _freeze, load_settings

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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
