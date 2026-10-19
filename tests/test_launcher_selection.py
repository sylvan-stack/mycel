"""Selection and actual exec proofs; fixture runtimes are not release qualification.

The tiny runtime adapter uses a real exec chain and the current test interpreter.
It deliberately makes no claim about the separately checked pinned distribution.
Product-mode fixtures copy genuine Mycel modules and package-local Build identity.
"""

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel_build import _launcher_runtime as launcher
from mycel_build._core import atomic_json, digest, file_manifest, json_bytes, seal_program
from mycel_build._registry import allocate
from mycel._store import STORE_FORMAT


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
    @proves('MYC-15.6', kind='unit')
    def test_numeric_default_skips_every_unavailable_status_target_and_damaged_build_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build('f')
            fixture.build('10')
            fixture.build('11', status='withdrawn', reason='regression')
            fixture.build('12', status='building')
            fixture.build('13', status='failed')
            fixture.build('14')
            fixture.record('14', prunedAt='2026-01-01T00:00:00Z')
            fixture.build('15')
            fixture.record('15', target='linux-arm64')
            fixture.build('16')
            damaged = fixture.registry / '16/program/probe.py'
            damaged.chmod(0o644)
            damaged.write_text('damaged installed file\n')
            damaged.chmod(0o444)
            before = tree_state(fixture.base)
            selected = launcher.select_build(fixture.registry, ('probe',), target='macos-arm64')
            try:
                self.assertEqual(selected.number, '10')
                self.assertEqual(selected.arguments, ('probe',))
                self.assertIsNone(selected.warning)
                self.assertTrue(os.get_inheritable(selected.run_fd))
            finally:
                os.close(selected.run_fd)
            for number in ('12', '13', '14', '15', '16'):
                with self.subTest(unavailable=number), self.assertRaises(launcher.LauncherError) as error:
                    launcher.select_build(fixture.registry, ('-v', number, 'probe'), target='macos-arm64')
                self.assertEqual(error.exception.code, 'refused')
            self.assertEqual(tree_state(fixture.base), before)

    @proves('MYC-15.6', kind='unit')
    def test_only_first_selector_is_consumed_and_withdrawn_requires_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build('f')
            fixture.build('10', status='withdrawn', reason='known parser regression')
            for arguments, number, forwarded in (
                (('probe', '-v', '10'), 'f', ('probe', '-v', '10')),
                (('-v', 'f', 'grep', '-v', 'needle'), 'f', ('grep', '-v', 'needle')),
                (('-v', '10', 'probe', ''), '10', ('probe', ''))):
                with self.subTest(arguments=arguments):
                    selected = launcher.select_build(fixture.registry, arguments, target='macos-arm64')
                    try:
                        self.assertEqual((selected.number, selected.arguments), (number, forwarded))
                        if number == '10':
                            self.assertIn('known parser regression', selected.warning)
                    finally:
                        os.close(selected.run_fd)

    @proves('MYC-15.6', kind='unit')
    def test_malformed_unknown_unavailable_and_empty_default_are_sanitized_structured_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build('f')
            fixture.build('10', status='failed')
            for arguments, code in ((('-v',), 'invalid_input'), (('-v', '01'), 'invalid_input'),
                (('-v', 'F'), 'invalid_input'), (('-v', '0'), 'invalid_input'),
                (('-v', '0x10'), 'invalid_input'), (('-v', '17'), 'invalid_input'),
                (('-v', '../private-secret'), 'invalid_input'), (('-v', '10'), 'refused')):
                output, errors = io.StringIO(), io.StringIO()
                with self.subTest(arguments=arguments):
                    status = launcher.main(arguments, registry=fixture.registry, target='macos-arm64',
                        stdout=output, stderr=errors, execute=lambda *args: self.fail('unavailable exec'))
                    self.assertEqual(status, 1)
                    reply = json.loads(output.getvalue())
                    self.assertEqual(reply['error']['code'], code)
                    self.assertNotIn('private-secret', output.getvalue())
                    self.assertEqual(errors.getvalue(), '')
                    self.assertEqual(reply['runnable'], ['f'])
            output, errors = io.StringIO(), io.StringIO()

            def failed_exec(*arguments):
                raise OSError('private executable path must not escape')

            self.assertEqual(launcher.main(('probe',), registry=fixture.registry, target='macos-arm64',
                stdout=output, stderr=errors, execute=failed_exec), 1)
            self.assertEqual(json.loads(output.getvalue())['error']['code'], 'refused')
            self.assertEqual(json.loads(output.getvalue())['runnable'], ['f'])
            self.assertNotIn('private executable', output.getvalue())
            self.assertEqual(errors.getvalue(), '')
            fixture.record('f', status='withdrawn', reason='regression')
            result = fixture.run('probe')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['error']['code'], 'refused')
            self.assertEqual(result.stderr, b'')


class LauncherProcessTests(unittest.TestCase):
    @proves('MYC-15.7', kind='unit')
    def test_actual_exec_preserves_pid_cwd_every_argument_and_environment_without_distribution_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build('f')
            fixture.build('10')
            before = tree_state(fixture.base)
            arguments = ('spaces inside', '', 'éλ', '--literal', '-v', 'f', '$(literal)')
            with fixture.running('-v', 'f', 'probe', *arguments) as process:
                output, errors = process.communicate(timeout=10)
                reply = json.loads(output)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(reply['pid'], process.pid)
                self.assertEqual(reply['cwd'], str(fixture.cwd))
                self.assertEqual(reply['argv'], list(arguments))
                self.assertEqual((reply['isolated'], reply['noBytecode']), (1, True))
                self.assertEqual(reply['config'], str(fixture.config))
                self.assertEqual(errors, b'')
            self.assertEqual(tree_state(fixture.base), before)

    @proves('MYC-15.7', kind='unit')
    def test_actual_binary_streams_stdin_and_arbitrary_exit_status_pass_without_json_wrapping(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build()
            for status in (0, 1, 2, 37):
                with self.subTest(status=status):
                    reply = fixture.run('binary', str(status), input=b'input\x00\xff\n')
                    self.assertEqual(reply.returncode, status)
                    self.assertEqual(reply.stdout, b'out\x00input\x00\xff\n')
                    self.assertEqual(reply.stderr, b'err\xff\n')

    @proves('MYC-15.7', kind='unit')
    def test_real_signal_default_and_selected_process_handler_receive_original_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build()
            for mode, expected, error in (((), -signal.SIGTERM, b''), (('handle',), 73, b'handled SIGTERM\n')):
                with self.subTest(mode=mode), fixture.running('hold', *mode) as process:
                    ready = json.loads(ready_line(process))
                    self.assertEqual(ready['pid'], process.pid)
                    process.send_signal(signal.SIGTERM)
                    output, errors = process.communicate(timeout=10)
                    self.assertEqual((process.returncode, output, errors), (expected, b'', error))

    @proves('MYC-0.9', 'MYC-15.6', 'MYC-15.7', kind='unit')
    def test_info_reports_the_selected_package_identity_and_withdrawn_warning_uses_only_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build('f', product=True)
            fixture.build('10', status='withdrawn', product=True, reason='known parser regression')
            before = tree_state(fixture.base)
            default, explicit = fixture.run('info'), fixture.run('-v', '10', 'info')
            self.assertEqual(default.returncode, 0)
            self.assertEqual(explicit.returncode, 0)
            self.assertEqual(json.loads(default.stdout)['build'], 'f')
            self.assertEqual(json.loads(explicit.stdout)['build'], '10')
            self.assertEqual(default.stderr, b'')
            self.assertIn(b'known parser regression', explicit.stderr)
            self.assertNotIn(b'known parser regression', explicit.stdout)
            self.assertEqual(tree_state(fixture.base), before)

    @proves('MYC-15.7', kind='unit')
    def test_real_product_grep_keeps_raw_stdin_output_error_and_status_under_invalid_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = LauncherFixture(directory)
            fixture.build(product=True)
            executable = shutil.which('grep', path=os.defpath)
            self.assertIsNotNone(executable)
            for arguments, data in ((('needle',), b'needle\x00bytes\n'),
                (('absent',), b'ordinary line\n'), (('[',), b'any\n')):
                with self.subTest(arguments=arguments):
                    expected = subprocess.run([executable, *arguments], input=data, capture_output=True,
                        cwd=fixture.cwd, env=fixture.environment(), timeout=10)
                    actual = fixture.run('grep', *arguments, input=data)
                    self.assertEqual(actual.returncode, expected.returncode)
                    self.assertEqual(actual.stdout, expected.stdout)
                    self.assertTrue(actual.stderr.startswith(expected.stderr))
                    self.assertNotIn(b'"error"', actual.stdout)
