"""Actual offline selector/CLI checks of two private native relocations.

Fixture working records exist only in disposable private homes. The retained
owner Build remains building; this module neither publishes nor installs there.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from ._core import BuildError, atomic_json, digest, file_manifest, json_bytes, validate_manifest
from ._launcher import install_launcher, _remove_private
from ._process import _defer_cleanup_signals, owned_process, run_group
from ._qualification import required_packaged_cases


def executable_path(pid: int) -> Path:
    """Read only the executable path of one explicitly spawned fixture PID."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('pid')
    if sys.platform == 'darwin':
        library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        library.proc_pidpath.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        library.proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        if library.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            raise OSError('fixture executable is unavailable')
        return Path(os.fsdecode(buffer.value)).resolve()
    # Used by process-helper unit fixtures, never native macOS qualification.
    return Path(os.readlink(f'/proc/{pid}/exe')).resolve()


def child_pids(pid: int) -> tuple[int, ...]:
    """Observe direct children of this fixture PID, never process argv/env."""
    if sys.platform == 'darwin':
        library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        library.proc_listpids.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int)
        library.proc_listpids.restype = ctypes.c_int
        buffer = (ctypes.c_int * 1024)()
        size = library.proc_listpids(6, pid, buffer, ctypes.sizeof(buffer))  # PROC_PPID_ONLY, proc_info.h
        if size < 0 or size >= ctypes.sizeof(buffer) or size % ctypes.sizeof(ctypes.c_int):
            raise OSError('fixture children are unavailable')
        return tuple(value for value in buffer[:size // ctypes.sizeof(ctypes.c_int)] if value > 0)
    return tuple(int(value) for value in Path(f'/proc/{pid}/task/{pid}/children').read_text().split())


def tree_state(root: Path) -> dict:
    result = {}
    for path in (root, *sorted(root.rglob('*'))):
        info = path.lstat()
        result[path.relative_to(root).as_posix()] = [stat.S_IMODE(info.st_mode), info.st_mtime_ns,
            ['link', os.readlink(path)] if path.is_symlink() else
            ['file', digest(path.read_bytes())] if path.is_file() else ['directory']]
    return result


def _policy(source_root: Path) -> str:
    policy = '(version 1)(allow default)(deny network*)(deny file-write*)'
    owner = Path.home().resolve()
    denied = {source_root.resolve(), Path(sys.executable).resolve().parents[1],
              owner / '.mycel', owner / 'Artifacts/arbol', owner / 'repos/arbol',
              Path('/usr/bin/python3'), Path('/usr/local/bin/python3'), Path('/opt/homebrew/bin/python3')}
    for path in sorted(denied):
        policy += '(deny file-read* (subpath ' + json.dumps(str(path)) + '))'
    return policy


def _case(name, command, *, cwd, env, before_root, timeout, input=None, progress=None):
    if progress is not None:
        progress['activeCase'] = name
    before = tree_state(before_root)
    started = time.monotonic()
    reply = run_group(command, cwd=cwd, env=env, input=input, timeout=timeout)
    elapsed = time.monotonic() - started
    if tree_state(before_root) != before:
        raise BuildError('refused', 'A packaged invocation changed its private immutable inputs.')
    return reply, {'name': name, 'passed': True, 'executed': True,
        'elapsedSeconds': elapsed, 'exitStatus': reply.returncode,
        'stdoutSha256': digest(reply.stdout), 'stderrSha256': digest(reply.stderr)}


def _gone(group):
    try:
        os.killpg(group, 0)
        return False
    except ProcessLookupError:
        return True


def _stop_fixture_group(group):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if _gone(group):
            return
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            return
        until = time.monotonic() + 1
        while time.monotonic() < until and not _gone(group):
            time.sleep(0.01)
    if not _gone(group):
        raise BuildError('refused', 'An observed packaged grep group did not terminate.')


def signal_case(command, *, cwd, env, interpreter: Path, grep: Path, stop_signal, timeout=15):
    """Readiness comes from actual grep output; signal only its selected PID."""
    groups = ()
    started = time.monotonic()
    with owned_process(command, cwd=cwd, env=env, stdin=subprocess.PIPE) as process:
        try:
            process.stdin.write(b'packaged readiness\n')
            process.stdin.flush()
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout, selectors.EVENT_READ)
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0 or not selected.select(remaining):
                    raise ValueError('grep readiness')
                if os.read(process.stdout.fileno(), 4096) != b'packaged readiness\n':
                    raise ValueError('grep readiness bytes')
            if executable_path(process.pid) != interpreter.resolve():
                raise ValueError('selected process identity')
            children = child_pids(process.pid)
            if len(children) != 1 or executable_path(children[0]) != grep.resolve() or os.getpgid(children[0]) != children[0]:
                raise ValueError('scoped grep process')
            groups = children
            os.kill(process.pid, signal.SIGSTOP)
            until = min(started + timeout, time.monotonic() + 2)
            while time.monotonic() < until:
                pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                if pid:
                    if not os.WIFSTOPPED(status):
                        process.returncode = os.waitstatus_to_exitcode(status)
                        raise ValueError('selected process stopped unexpectedly')
                    break
                time.sleep(0.01)
            else:
                raise ValueError('selected process did not stop')
            os.kill(process.pid, signal.SIGCONT)
            os.kill(process.pid, stop_signal)
            process.stdin.close()
            process.stdin = None
            output, errors = process.communicate(timeout=max(0.1, started + timeout - time.monotonic()))
            if process.returncode != 128 + stop_signal or output or errors or any(not _gone(group) for group in groups):
                raise ValueError('signal propagation or cleanup')
            return {'name': 'selected_pid_signal_' + str(stop_signal), 'passed': True, 'executed': True,
                    'pidPreserved': True, 'selectedBundledInterpreter': True, 'stopContinueObserved': True,
                    'grepGroupReaped': True, 'exitStatus': process.returncode,
                    'elapsedSeconds': time.monotonic() - started}
        finally:
            # These are only actual observed child groups of this owned fixture.
            with _defer_cleanup_signals():
                if process.poll() is None:
                    try:
                        os.kill(process.pid, signal.SIGCONT)
                    except ProcessLookupError:
                        pass
                for group in groups:
                    _stop_fixture_group(group)


def _relocation(program, bundle, record, target, destination, *, source_root, timeout, progress=None):
    progress = {'label': destination.name, 'activeCase': 'prepare_private_fixture', 'cases': []} if progress is None else progress
    home = destination / 'home'
    registry = home / '.mycel/builds'
    folder = registry / record['build']
    folder.mkdir(parents=True)
    (registry / '.registry.lock').write_bytes(b'')
    (folder / 'run.lock').write_bytes(b'')
    (folder / 'run.lock').chmod(0o444)
    shutil.copytree(program, folder / 'program', symlinks=True)
    manifest = file_manifest(folder / 'program')
    atomic_json(folder / 'files.json', manifest)
    fixture = {**record, 'status': 'working', 'packagedReleaseFixture': True,
        'checks': {'required': 1, 'passed': 1, 'failed': 0, 'report': 'checks.json'}}
    atomic_json(folder / 'build.json', fixture)
    atomic_json(folder / 'checks.json', {'schemaVersion': 1, 'results': [
        {'name': 'private_exact_program_fixture_only', 'passed': True, 'executed': True}], 'pending': []})
    (folder / 'build.log').write_text('Private packaged selector fixture; no owner publication.\n')
    installed = install_launcher(bundle, home=home)
    entry = Path(installed['entrypoint'])
    code, artifacts = destination / 'code', destination / 'documents'
    (code / 'inside').mkdir(parents=True)
    artifacts.mkdir()
    (code / 'inside/mycel.py').write_text("raise RuntimeError('CWD import contamination')\n")
    (artifacts / 'evaluation.toml').write_text('schema_version=1\n')
    config = destination / 'private.toml'
    config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/never_open"\n'
        '[repos.packaged]\nenabled=true\ncode_root=' + json.dumps(str(code)) + '\nartifact_root='
        + json.dumps(str(artifacts)) + '\nevaluation="evaluation.toml"\n')
    invalid = destination / 'invalid.toml'
    invalid.write_text('[invalid\n')
    hostile = destination / 'developer-unavailable'
    hostile.mkdir()
    env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'MYCEL_GREP_PLAIN': '1',
        'MYCEL_CONFIG': str(destination / 'missing.toml'), 'PYTHONHOME': str(hostile),
        'PYTHONPATH': str(hostile), 'PYTHONDONTWRITEBYTECODE': '0', 'OMP_NUM_THREADS': '1'}
    policy = _policy(source_root) + '(deny file-read* (subpath ' + json.dumps(str(hostile)) + '))'
    boundary = ['/usr/bin/sandbox-exec', '-p', policy]
    cwd = code / 'inside'
    cases = progress['cases']
    # Real launcher selection, not runpy or a test-only product entry point.
    for configuration in (destination / 'missing.toml', invalid):
        env['MYCEL_CONFIG'] = str(configuration)
        for args in (['--help'], ['info'], ['-v', record['build'], 'info']):
            reply, row = _case('json_' + configuration.name + '_' + '_'.join(args),
                [*boundary, str(entry), *args], cwd=cwd, env={**env, 'PATH': '/nonexistent'},
                before_root=destination, timeout=timeout, progress=progress)
            value = json.loads(reply.stdout)
            if reply.returncode != 0 or reply.stderr or value.get('version') != record['version'] or 'error' in value:
                raise ValueError('packaged JSON reply')
            if args[-1] == 'info' and value.get('build') != record['build']:
                raise ValueError('packaged Build identity')
            if args == ['--help'] and not value.get('commands'):
                raise ValueError('packaged help')
            cases.append(row)
    # A higher incomplete Build must not replace this exact working fixture.
    higher = registry / format(int(record['build'], 16) + 1, 'x')
    higher.mkdir()
    (higher / 'build.json').write_text('{}\n')
    reply, row = _case('default_skips_higher_damaged', [*boundary, str(entry), 'info'],
        cwd=cwd, env=env, before_root=destination, timeout=timeout, progress=progress)
    if reply.returncode != 0 or reply.stderr or json.loads(reply.stdout).get('build') != record['build']:
        raise ValueError('default selection')
    cases.append(row)
    fixture.update(status='withdrawn', reason='private packaged fixture')
    atomic_json(folder / 'build.json', fixture)
    reply, row = _case('withdrawn_not_default', [*boundary, str(entry), 'info'],
        cwd=cwd, env=env, before_root=destination, timeout=timeout, progress=progress)
    if reply.returncode != 1 or reply.stderr or json.loads(reply.stdout).get('error', {}).get('code') != 'refused':
        raise ValueError('withdrawn default')
    cases.append(row)
    reply, row = _case('withdrawn_explicit', [*boundary, str(entry), '-v', record['build'], 'info'],
        cwd=cwd, env=env, before_root=destination, timeout=timeout, progress=progress)
    if (reply.returncode != 0 or json.loads(reply.stdout).get('build') != record['build']
            or reply.stderr != ('mycel: Build ' + record['build'] + ' is withdrawn: private packaged fixture\n').encode()):
        raise ValueError('explicit withdrawn selection')
    cases.append(row)
    fixture.update(status='working')
    fixture.pop('reason', None)
    atomic_json(folder / 'build.json', fixture)
    env['MYCEL_CONFIG'] = str(config)
    reply, row = _case('cwd_repository_empty_retrieval', [*boundary, str(entry), 'evaluate'],
        cwd=cwd, env=env, before_root=destination, timeout=timeout, progress=progress)
    value = json.loads(reply.stdout)
    if (reply.returncode != 0 or reply.stderr or value.get('repository') != 'packaged'
            or value.get('kind') != 'retrieval' or value.get('results') != [] or value.get('build') != record['build']):
        raise ValueError('preserved CWD selection')
    cases.append(row)
    env['MYCEL_CONFIG'] = str(invalid)
    for name, args, data, status in (
        ('matched_literal_arguments', ['-F', '-x', '-e', '$(literal) with spaces'], b'$(literal) with spaces\nother\n', 0),
        ('empty_literal_argument', ['-F', '-x', '-e', ''], b'\nordinary input\n', 0),
        ('no_match', ['-F', '-e', 'absent'], b'ordinary input\n', 1),
        ('pattern_error', ['['], b'ordinary input\n', 2)):
        progress['activeCase'] = 'grep_' + name
        direct = run_group([*boundary, '/usr/bin/grep', *args], cwd=cwd, env=env, input=data, timeout=timeout)
        reply, row = _case('grep_' + name, [*boundary, str(entry), 'grep', *args], cwd=cwd,
            env=env, input=data, before_root=destination, timeout=timeout, progress=progress)
        if (direct.returncode != status or (reply.returncode, reply.stdout, reply.stderr)
                != (direct.returncode, direct.stdout, direct.stderr)):
            raise ValueError('raw grep streams/status')
        cases.append(row)
    for stop in (signal.SIGINT, signal.SIGTERM):
        progress['activeCase'] = 'selected_pid_signal_' + str(stop)
        before = tree_state(destination)
        row = signal_case([*boundary, str(entry), 'grep', '--line-buffered', '-F', '-e', 'packaged readiness'],
            cwd=cwd, env=env, interpreter=folder / 'program/runtime/bin/python3', grep=Path('/usr/bin/grep'),
            stop_signal=stop, timeout=timeout)
        if tree_state(destination) != before:
            raise ValueError('signal invocation changed inputs')
        cases.append(row)
    progress['activeCase'] = 'retained_manifest'
    validate_manifest(folder / 'program', manifest, record['filesSha256'])
    if tuple(row['name'] for row in cases) != required_packaged_cases(record['build']):
        raise ValueError('incomplete ordered packaged case inventory')
    return {'label': destination.name, 'passed': True, 'executed': True, 'cases': cases,
            'privateWorkingRecordFixtureOnly': True, 'ownerPublished': False}


def probe_packaged_release(program: Path, launcher_bundle: Path, target: str, *, source_root: Path,
                           record: dict, timeout=30) -> dict:
    result = {'passed': False, 'executed': False, 'target': target, 'relocations': [],
              'automaticQualification': False}
    if (target != 'macos-arm64' or platform.system() != 'Darwin' or platform.machine() != 'arm64'
            or not Path('/usr/bin/sandbox-exec').is_file()):
        return {**result, 'reason': 'Native packaged selector/CLI checks are unavailable on this host.'}
    before = file_manifest(program)
    launcher_before = tree_state(launcher_bundle)
    if digest(json_bytes(before)) != record['filesSha256']:
        return {**result, 'reason': 'The packaged check inputs differ from the staged program.'}
    current = None
    try:
        with tempfile.TemporaryDirectory(prefix='mycel-packaged-release-') as temporary:
            base = Path(temporary)
            try:
                for label in ('first installation', 'second relocated installation'):
                    destination = base / label
                    destination.mkdir()
                    current = {'label': label, 'activeCase': 'prepare_private_fixture', 'cases': []}
                    result['executed'] = True
                    result['relocations'].append(_relocation(program, launcher_bundle, record, target, destination,
                        source_root=source_root, timeout=timeout, progress=current))
                    current = None
            finally:
                for label in ('first installation', 'second relocated installation'):
                    _remove_private(base / label)
        if file_manifest(program) != before or tree_state(launcher_bundle) != launcher_before:
            raise ValueError('retained inputs changed')
        return {**result, 'passed': True, 'machine': platform.machine(), 'macOS': platform.mac_ver()[0],
                'runtime': record['runtime']['python'], 'networkAndWritesDenied': True,
                'sourceReadDenied': True, 'developerReadDenied': True, 'ownerStateDenied': True,
                'retainedInputsUnchanged': True, 'reason': 'Both real packaged selector and CLI relocations passed.'}
    except (BuildError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        if current is not None:
            result['relocations'].append({**current, 'passed': False, 'executed': True})
        return {**result, 'reason': 'A required packaged selector/CLI case failed or could not complete.'}
