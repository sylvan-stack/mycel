# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Pure capture and private temporary Git observations, never store acceptance."""
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from mycel._errors import MycelError
from mycel._scope import Folder, RepositoryLocations


import json
import os
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from mycel import _capture as capture
from mycel._safeguards import CompletedChild, run_git
from mycel._settings import load_settings


def no_checkout(args, **kwargs):
    return CompletedChild(128, b"", b"private diagnostic must never escape", 0)


class _CaptureFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.code, self.artifact = self.home / "code", self.home / "artifact"
        self.code.mkdir()
        self.artifact.mkdir()
        self.counter = 0

    def settings(self, *, code=True, artifact=True, subfolders=(), scan=None, enabled=True):
        self.counter += 1
        path = self.home / f"settings-{self.counter}.toml"
        lines = ['[store]', 'address="postgresql://fixture@localhost/mycel_check_config_only"',
                 '[repos.fixture]', 'enabled=' + ('true' if enabled else 'false')]
        if code:
            lines.append('code_root=' + json.dumps(str(self.code)))
        if artifact:
            lines.append('artifact_root=' + json.dumps(str(self.artifact)))
        if subfolders:
            lines.append('code_subdirs=' + json.dumps(list(subfolders)))
        if scan is not None:
            lines.append('[scan]')
            lines.extend(key + '=' + json.dumps(value) for key, value in scan.items())
        path.write_text('\n'.join(lines) + '\n')
        return load_settings(path=path, home=self.home)

    def write(self, root, path, source):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(source.encode() if isinstance(source, str) else source)
        return file

    def read(self, settings=None, **kwargs):
        return capture.capture_repository(settings or self.settings(), 'fixture', _git=no_checkout, **kwargs)

    def paths(self, manifest):
        return {(file.primary.root, file.primary.path, file.corpus) for file in manifest.disk.files}


class CaptureTests(_CaptureFixture, unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class TemporaryGitCaptureTests(_CaptureFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.git('init','--initial-branch=main')

    def git(self,*args,cwd=None,request=None):
        environment={**os.environ,'PATH':'/usr/bin:/bin:/usr/sbin:/sbin',
                     'GIT_TERMINAL_PROMPT':'0'}
        process=subprocess.run(['/usr/bin/git','-c','core.fsmonitor=false',*args],cwd=cwd or self.code,env=environment,
            input=request,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr.decode(errors='replace'))
        return process.stdout.decode().strip()

    def commit(self,message='public fixture'):
        self.git('add','--all')
        return self.git('commit','-m',message)

    def read_git(self,settings=None,**kwargs):
        calls=[]
        def reader(args,**options):
            calls.append(args)
            return run_git(args,**options)
        result=capture.capture_repository(settings or self.settings(),'fixture',_git=reader,**kwargs)
        return result,calls

    def state(self):
        return {str(path.relative_to(self.code)):sha256(path.read_bytes()).hexdigest()
                for path in self.code.rglob('*') if path.is_file() and not path.is_symlink()}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
