"""Offline independent bootstrap bundles and an explicit atomic owned install."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

from ._core import (BuildError, RUNTIME_HASHES, atomic_json, digest, extract_runtime,
                    file_manifest, json_bytes, load_lock, read_json, seal_program,
                    snapshot_asset, validate_manifest)


_PROBE = r'''
import json, pathlib, platform, runpy, sys, sysconfig
assert sys.flags.isolated and sys.dont_write_bytecode
assert platform.python_implementation() == 'CPython' and platform.python_version() == '3.14.7'
assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
assert not sysconfig.get_config_var('Py_GIL_DISABLED')
module = runpy.run_path(sys.argv[1], run_name='mycel_launcher_bootstrap_probe')
assert all(callable(module[name]) for name in ('select_build', 'main', 'current_target'))
assert not any(name == 'mycel' or name.startswith(('mycel.', 'mycel_build')) for name in sys.modules)
print(json.dumps({'isolated': True, 'dontWriteBytecode': True, 'python': platform.python_version(),
                  'machine': platform.machine(), 'standaloneSelector': True}))
'''


def _remove_private(path):
    # Only fresh TemporaryDirectory staging/probe copies reach this helper.
    if not path.exists():
        return
    for member in path.rglob('*'):
        if member.is_dir() and not member.is_symlink():
            member.chmod(0o700)
    path.chmod(0o700)
    shutil.rmtree(path)


def probe_launcher(program: Path, target: str, *, source_root=None) -> dict:
    """Load the pinned bootstrap and standalone payload at two private paths."""
    if (target != 'macos-arm64' or platform.system() != 'Darwin' or platform.machine() != 'arm64'
            or not Path('/usr/bin/sandbox-exec').is_file()):
        return {'passed': False, 'executed': False, 'target': target,
                'reason': 'Native isolated launcher checks are unavailable.'}
    expected = file_manifest(program)
    fingerprint = digest(json_bytes(expected))
    relocations = []
    with tempfile.TemporaryDirectory(prefix='mycel-launcher-relocation-') as temporary:
        base = Path(temporary)
        try:
            for label in ('first installation', 'second relocated installation'):
                copy = base / label
                shutil.copytree(program, copy, symlinks=True)
                validate_manifest(copy, expected, fingerprint)
                policy = '(version 1)(allow default)(deny network*)(deny file-write*)'
                if source_root is not None:
                    policy += '(deny file-read* (subpath ' + json.dumps(str(Path(source_root).resolve())) + '))'
                policy += '(deny file-read* (subpath ' + json.dumps(str(Path(sys.executable).resolve().parents[1])) + '))'
                reply = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy,
                    str(copy / 'runtime/bin/python3'), '-I', '-B', '-c', _PROBE, str(copy / 'launcher.py')],
                    capture_output=True, timeout=60)
                if reply.returncode != 0 or reply.stderr:
                    raise ValueError('bootstrap probe')
                evidence = json.loads(reply.stdout)
                if evidence != {'isolated': True, 'dontWriteBytecode': True, 'python': '3.14.7',
                                'machine': 'arm64', 'standaloneSelector': True}:
                    raise ValueError('bootstrap evidence')
                validate_manifest(copy, expected, fingerprint)
                relocations.append({'label': label, **evidence})
        except (OSError, ValueError, subprocess.SubprocessError):
            return {'passed': False, 'executed': True, 'target': target,
                    'reason': 'The isolated launcher checks failed.', 'relocations': relocations}
        finally:
            for label in ('first installation', 'second relocated installation'):
                _remove_private(base / label)
    return {'passed': True, 'executed': True, 'target': target, 'relocations': relocations,
            'sourceReadDenied': source_root is not None, 'networkAndWritesDenied': True,
            'automaticQualification': False}


def stage_launcher(source_root: Path, lock_path: Path, assets: Path, destination: Path,
                   target: str, *, frozen=None) -> dict:
    """Create a complete private bundle using copied, hash-verified local assets."""
    lock, row = load_lock(lock_path, target)
    if frozen is None:
        from ._staging import source_inputs
        _, frozen = source_inputs(source_root)
    if json.loads(frozen['packaging/build-lock.json']) != lock:
        raise BuildError('busy', 'The launcher lock changed during source capture.')
    raw = frozen['src/mycel_build/_launcher_runtime.py']
    compile(raw, 'launcher.py', 'exec')
    destination = Path(destination).absolute()
    if os.path.lexists(destination):
        raise BuildError('refused', 'The launcher bundle destination already exists.')
    destination.mkdir()
    program = destination / 'program'
    program.mkdir()
    with tempfile.TemporaryDirectory(prefix='mycel-launcher-assets-') as temporary:
        snapshot = snapshot_asset(row['runtime'], assets, Path(temporary))
        extract_runtime(snapshot, program / 'runtime')
    (program / 'launcher.py').write_bytes(raw)
    (program / 'licenses').mkdir()
    for licence in row['runtime']['licenses']:
        content = frozen['packaging/' + licence['path']]
        if digest(content) != licence['sha256']:
            raise BuildError('refused', 'The launcher runtime licence differs from its pin.')
        name = licence['path'].removeprefix('licenses/')
        (program / 'licenses' / name).write_bytes(content)
    atomic_json(program / 'bootstrap-pin.json', {'schemaVersion': 1, 'target': target, 'runtime': row['runtime']})
    seal_program(program)
    manifest = file_manifest(program)
    fingerprint = digest(json_bytes(manifest))
    atomic_json(destination / 'files.json', manifest)
    checks = probe_launcher(program, target, source_root=source_root)
    record = {'schemaVersion': 1, 'kind': 'mycel-launcher', 'target': target,
              'runtime': row['runtime'], 'program': 'program', 'filesManifest': 'files.json',
              'filesSha256': fingerprint, 'payloadSha256': digest(raw), 'checks': checks}
    atomic_json(destination / 'bundle.json', record)
    validate_manifest(program, manifest, fingerprint)
    for name in ('files.json', 'bundle.json'):
        (destination / name).chmod(0o444)
    destination.chmod(0o555)
    return record


def _validate_bundle(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir() or bundle.stat().st_mode & 0o222:
        raise BuildError('refused', 'The launcher bundle is missing or unsafe.')
    for name in ('bundle.json', 'files.json'):
        member = bundle / name
        if member.is_symlink() or not member.is_file() or member.stat().st_nlink != 1 or member.stat().st_mode & 0o222:
            raise BuildError('refused', 'The launcher bundle metadata is not immutable.')
    record = read_json(bundle / 'bundle.json')
    try:
        checks, runtime = record['checks'], record['runtime']
        probes = checks['relocations']
        if (type(record['schemaVersion']) is not int or record['schemaVersion'] != 1
                or record['kind'] != 'mycel-launcher' or record['target'] != 'macos-arm64'
                or record['program'] != 'program' or record['filesManifest'] != 'files.json'
                or runtime['python'] != '3.14.7'
                or runtime['distribution'] != 'python-build-standalone/20260901/install_only_stripped'
                or runtime['sha256'] != RUNTIME_HASHES['macos-arm64']
                or checks['passed'] is not True or checks['executed'] is not True
                or checks['target'] != record['target'] or not isinstance(probes, list) or len(probes) != 2
                or any(not isinstance(probe, dict) or probe.get('python') != '3.14.7'
                       or probe.get('machine') != 'arm64' or probe.get('isolated') is not True
                       or probe.get('dontWriteBytecode') is not True or probe.get('standaloneSelector') is not True
                       for probe in probes)
                or [probe.get('label') for probe in probes] != ['first installation', 'second relocated installation']
                or checks.get('networkAndWritesDenied') is not True
                or checks.get('sourceReadDenied') is not True):
            raise ValueError('bundle record')
        manifest = read_json(bundle / 'files.json')
        validate_manifest(bundle / 'program', manifest, record['filesSha256'])
        if digest((bundle / 'program/launcher.py').read_bytes()) != record['payloadSha256']:
            raise ValueError('payload')
        pin = read_json(bundle / 'program/bootstrap-pin.json')
        if pin != {'schemaVersion': 1, 'target': record['target'], 'runtime': runtime}:
            raise ValueError('pin')
        interpreter = bundle / 'program/runtime/bin/python3'
        if not interpreter.is_file() or not os.access(interpreter, os.X_OK) or not interpreter.resolve().is_relative_to((bundle / 'program').resolve()):
            raise ValueError('interpreter')
        expected = {'program', 'files.json', 'bundle.json'}
        if (bundle / 'mycel').exists():
            entry = bundle / 'mycel'
            if (entry.is_symlink() or not entry.is_file() or entry.stat().st_nlink != 1
                    or entry.stat().st_mode & 0o222 or not os.access(entry, os.X_OK)):
                raise ValueError('entry')
            expected.add('mycel')
        if {p.name for p in bundle.iterdir()} != expected:
            raise ValueError('bundle members')
    except (KeyError, ValueError, TypeError, OSError):
        raise BuildError('refused', 'The launcher bundle is incomplete, damaged or unchecked.') from None
    return record


def _trampoline(bundle):
    # Quote full paths, including spaces, apostrophes and shell metacharacters.
    python = shlex.quote(str(bundle / 'program/runtime/bin/python3'))
    payload = shlex.quote(str(bundle / 'program/launcher.py'))
    return ('#!/bin/sh\nexec ' + python + ' -I -B ' + payload + ' "$@"\n').encode()


def _directory(path):
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise BuildError('refused', 'A launcher installation directory has uncertain ownership.')
    if not path.exists():
        _directory(path.parent)
        path.mkdir()


def _sync_tree(root):
    for path in [*root.rglob('*'), root]:
        if not path.is_symlink():
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def _owned_entry(entry, launchers):
    if not os.path.lexists(entry):
        return None
    if not entry.is_symlink():
        raise BuildError('refused', 'The existing command is not an owned Mycel launcher.')
    target = (entry.parent / os.readlink(entry)).resolve()
    if (target.name != 'mycel' or target.parent.parent != launchers.resolve()
            or not re.fullmatch(r'[0-9a-f]{64}', target.parent.name)):
        raise BuildError('refused', 'The existing command is not an owned Mycel launcher.')
    record = _validate_bundle(target.parent)
    if target.parent.name != digest(json_bytes(record)):
        raise BuildError('refused', 'The existing launcher bundle has an unrecognized installation identity.')
    if (target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1
            or target.read_bytes() != _trampoline(target.parent) or target.stat().st_mode & 0o222):
        raise BuildError('refused', 'The existing command has uncertain launcher ownership.')
    return os.readlink(entry)


def install_launcher(bundle: Path, *, home=None) -> dict:
    """Explicitly stage a verified independent bundle, then atomically cut over."""
    source = Path(bundle).absolute()
    record = _validate_bundle(source)
    home = (Path.home() if home is None else Path(home)).resolve()
    launchers, entry = home / '.mycel/launcher', home / '.local/bin/mycel'
    # Refuse uncertain parents/entry before creating any installation files.
    for path in (home / '.mycel', launchers, home / '.local', home / '.local/bin'):
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise BuildError('refused', 'A launcher installation directory has uncertain ownership.')
    previous = _owned_entry(entry, launchers)
    _directory(launchers)
    _directory(entry.parent)
    destination = None
    lock = os.open(launchers / '.install.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise BuildError('refused', 'The launcher installation lock is unsafe.')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BuildError('busy', 'Another launcher installation is in progress.') from None
        if _owned_entry(entry, launchers) != previous:
            raise BuildError('busy', 'The launcher entry point changed during preparation.')
        identity = digest(json_bytes(record))
        destination = launchers / identity
        if os.path.lexists(destination):
            if _validate_bundle(destination) != record or (destination / 'mycel').read_bytes() != _trampoline(destination):
                raise BuildError('refused', 'The retained launcher bundle differs from this installation.')
        else:
            temporary = Path(tempfile.mkdtemp(prefix='.install-', dir=launchers))
            stage = temporary
            try:
                shutil.copytree(source, stage, symlinks=True, dirs_exist_ok=True)
                stage.chmod(0o755)
                if (stage / 'mycel').exists():
                    raise BuildError('refused', 'A staged source bundle already contains an install-specific command.')
                with (stage / 'mycel').open('xb') as output:
                    output.write(_trampoline(destination))
                    output.flush()
                    os.fsync(output.fileno())
                (stage / 'mycel').chmod(0o555)
                stage.chmod(0o555)
                if _validate_bundle(stage) != record:
                    raise BuildError('busy', 'The launcher bundle changed while being copied.')
                _validate_bundle(source)
                _sync_tree(stage)
                os.rename(stage, destination)
                directory = os.open(launchers, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                _remove_private(temporary)
        _owned_entry(entry, launchers)
        if (os.readlink(entry) if entry.is_symlink() else None) != previous:
            raise BuildError('busy', 'The launcher entry point changed before cutover.')
        fd, name = tempfile.mkstemp(prefix='.mycel-launcher-', dir=entry.parent)
        os.close(fd)
        temporary_entry = Path(name)
        try:
            temporary_entry.unlink()
            temporary_entry.symlink_to(destination / 'mycel')
            os.replace(temporary_entry, entry)
            directory = os.open(entry.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary_entry.unlink(missing_ok=True)
        return {'installed': True, 'entrypoint': str(entry), 'bundle': str(destination),
                'target': record['target'], 'previousLauncherRetained': previous is not None,
                'settingsChanged': False, 'storeChanged': False}
    except (BuildError, OSError, KeyboardInterrupt) as error:
        # A late fsync can fail after the durable bundle or command cutover.
        # Report what is actually present; never pretend to roll it back.
        staged = installed = False
        try:
            staged = destination is not None and _validate_bundle(destination) == record
            owned = _owned_entry(entry, launchers)
            installed = staged and owned is not None and (entry.parent / owned).resolve() == destination / 'mycel'
        except (BuildError, OSError, ValueError, RuntimeError):
            pass
        partial = {'installed': installed, 'bundleStaged': staged, 'entrypoint': str(entry),
                   'bundle': str(destination) if destination is not None else None,
                   'settingsChanged': False, 'storeChanged': False}
        if isinstance(error, (BuildError, KeyboardInterrupt)):
            error.partialResult = partial
            raise
        failure = BuildError('internal', 'Launcher installation failed; inspect the actual partial result.')
        failure.partialResult = partial
        raise failure from None
    finally:
        os.close(lock)
