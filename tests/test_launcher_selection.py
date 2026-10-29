# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Selection and actual exec proofs; fixture runtimes are not release qualification.

The tiny runtime adapter uses a real exec chain and the current test interpreter.
It deliberately makes no claim about the separately checked pinned distribution.
Product-mode fixtures copy genuine Mycel modules and package-local Build identity.
"""
import io
import signal
import tempfile
from unittest.mock import patch

from mycel_build import _launcher_runtime as launcher


import json
import os
import selectors
import shlex
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

from mycel._store import STORE_FORMAT
from mycel_build._core import (
    atomic_json,
    digest,
    file_manifest,
    json_bytes,
    seal_program,
)
from mycel_build._registry import allocate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {"commit": "a" * 40, "dirty": False, "inputsSha256": "b" * 64}


def ready_line(process):
    deadline, output = time.monotonic() + 5, bytearray()
    with selectors.DefaultSelector() as selected:
        selected.register(process.stdout, selectors.EVENT_READ)
        while b'\n' not in output:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selected.select(remaining):
                raise AssertionError('fixture process did not become ready promptly')
            part = os.read(process.stdout.fileno(), 65536)
            if not part:
                raise AssertionError('fixture process ended before readiness')
            output.extend(part)
    assert output.endswith(b'\n') and output.count(b'\n') == 1
    return bytes(output)


def tree_state(root):
    """Catch new logs/caches, byte or mode changes and replacement writes."""
    if not root.exists():
        return None
    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        value = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            value.st_mode, value.st_mtime_ns,
            ("link", os.readlink(path)) if path.is_symlink() else
            ("file", path.read_bytes()) if path.is_file() else ("directory",))
    return result


def thaw(root):
    if root.exists():
        for path in (root, *root.rglob("*")):
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)


PROBE = r'''
import json, os, signal, sys
from pathlib import Path
assert sys.argv[1:5] == ['-I', '-B', '-m', 'mycel.cli'], sys.argv
arguments = sys.argv[5:]
program = Path(__file__).resolve().parent
if arguments and arguments[0] == 'probe':
    print(json.dumps({'pid': os.getpid(), 'cwd': os.getcwd(), 'argv': arguments[1:],
        'isolated': sys.flags.isolated, 'noBytecode': sys.dont_write_bytecode,
        'config': os.environ.get('MYCEL_CONFIG')}), flush=True)
elif arguments and arguments[0] == 'binary':
    os.write(1, b'out\x00' + sys.stdin.buffer.read())
    os.write(2, b'err\xff\n')
    raise SystemExit(int(arguments[1]))
elif arguments and arguments[0] == 'hold':
    if len(arguments) > 1 and arguments[1] == 'handle':
        def finish(number, frame):
            os.write(2, b'handled SIGTERM\n')
            raise SystemExit(73)
        signal.signal(signal.SIGTERM, finish)
    print(json.dumps({'pid': os.getpid(), 'ready': True}), flush=True)
    while True:
        signal.pause()
else:
    # A copied genuine product package, not a replaced CLI implementation.
    sys.path.insert(0, str(program / 'runtime/lib/python3.14/site-packages'))
    from mycel._cli import main
    sys.argv = ['mycel', *arguments]
    raise SystemExit(main())
'''


class LauncherFixture:
    def __init__(self, directory):
        self.base = Path(directory).resolve()
        self.registry = self.base / 'private registry'
        self.home = self.base / 'private home'
        self.home.mkdir()
        self.cwd = self.base / 'caller directory'
        self.cwd.mkdir()
        self.config = self.home / 'invalid.toml'
        self.config.write_text('not valid TOML = [\n')
        self.bootstrap = self.base / 'invoke launcher.py'
        runtime_source = ROOT / 'src/mycel_build/_launcher_runtime.py'
        self.bootstrap.write_text('import os,runpy,sys\nfrom pathlib import Path\n'
            'def audit(event,args):\n'
            '    if event == "open" and str(args[0]) == os.environ.get("MYCEL_CONFIG"):\n'
            '        raise AssertionError("selection read settings")\n'
            '    if event == "socket.connect":\n'
            '        raise AssertionError("selection opened a connection")\n'
            '    if event == "import" and (args[0] == "mycel" or args[0].startswith(("mycel.","mycel_build"))):\n'
            '        raise AssertionError("selection imported product")\n'
            'sys.addaudithook(audit)\n'
            f'module=runpy.run_path({str(runtime_source)!r})\n'
            'raise SystemExit(module["main"](sys.argv[2:],registry=Path(sys.argv[1]),target="macos-arm64"))\n')

    def build(self, number=None, *, status='working', product=False, store_format=2, reason=None):
        wanted = int(number, 16) if number else None
        while True:
            record = allocate(self.registry, target='macos-arm64', version='2.0.0', source=SOURCE)
            if wanted is None or int(record['build'], 16) == wanted:
                break
            if int(record['build'], 16) > wanted:
                raise AssertionError('fixture requested an already allocated Build')
        number = record['build']
        folder = self.registry / number
        program = folder / 'program'
        interpreter = program / 'runtime/bin/python3'
        interpreter.parent.mkdir(parents=True)
        site = program / 'runtime/lib/python3.14/site-packages'
        package = site / 'mycel'
        if product:
            shutil.copytree(ROOT / 'src/mycel', package,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'build-identity.json'))
            thaw(package)
            store = package / '_store.py'
            raw = store.read_text()
            assert raw.count(f'STORE_FORMAT = {STORE_FORMAT}') == 1
            store.write_text(raw.replace(f'STORE_FORMAT = {STORE_FORMAT}', f'STORE_FORMAT = {store_format}'))
        else:
            (package / 'data').mkdir(parents=True)
            (package / '__init__.py').write_text('')
        atomic_json(package / 'data/build-identity.json', {'schemaVersion': 1, 'build': int(number, 16)})
        (program / 'probe.py').write_text(PROBE)
        # Both shell exec and the launcher's exec preserve the same PID. -I/-B
        # apply to the actual interpreter; all launcher arguments reach probe.
        interpreter.write_text('#!/bin/sh\n'
            'here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
            f'exec {shlex.quote(sys.executable)} -I -B "$here/../../probe.py" "$@"\n')
        interpreter.chmod(0o755)
        pin = json.loads((ROOT / 'packaging/build-lock.json').read_bytes())['targets']['macos-arm64']['runtime']
        lock = {'schemaVersion': 1, 'python': '3.14.7',
            'targets': {'macos-arm64': {'runtime': pin, 'dependencies': []}}}
        atomic_json(program / 'build-lock.json', lock)
        seal_program(program)
        manifest = file_manifest(program)
        atomic_json(folder / 'files.json', manifest)
        record.update(status=status, program='program', filesManifest='files.json',
            filesSha256=digest(json_bytes(manifest)), storeFormat=store_format, searchReply=3,
            runtime=pin, lockSha256=digest(json_bytes(lock)),
            checks={'required': 1, 'passed': 1, 'failed': 0, 'report': 'checks.json'})
        if reason is not None:
            record['reason'] = reason
        atomic_json(folder / 'build.json', record)
        atomic_json(folder / 'checks.json', {'schemaVersion': 1,
            'results': [{'name': 'synthetic_fixture_only', 'passed': True, 'executed': True}], 'pending': []})
        return record

    def record(self, number, **changes):
        path = self.registry / number / 'build.json'
        value = json.loads(path.read_bytes())
        value.update(changes)
        atomic_json(path, value)

    def command(self, *arguments):
        return [sys.executable, '-I', '-B', str(self.bootstrap), str(self.registry), *arguments]

    def environment(self, **changes):
        return {**os.environ, 'HOME': str(self.home), 'PATH': os.defpath,
            'MYCEL_CONFIG': str(self.config), 'PYTHONDONTWRITEBYTECODE': '1', **changes}

    def run(self, *arguments, input=None, **options):
        return subprocess.run(self.command(*arguments), cwd=self.cwd,
            env=self.environment(), input=input, capture_output=True, timeout=10, **options)

    @contextmanager
    def running(self, *arguments):
        process = subprocess.Popen(self.command(*arguments), cwd=self.cwd,
            env=self.environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


class LauncherSelectionTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class LauncherProcessTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
