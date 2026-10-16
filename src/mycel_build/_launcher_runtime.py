"""Standalone installed selector: standard library, distribution reads and exec only.

The builder copies this file into a separately pinned bootstrap bundle. It must
never import mycel, mycel_build, settings, providers or a database driver.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys


class LauncherError(Exception):
    def __init__(self, code, message, runnable=()):
        super().__init__(message)
        self.code, self.runnable = code, tuple(runnable)


@dataclass(frozen=True)
class SelectedBuild:
    number: str
    program: Path
    arguments: tuple[str, ...]
    run_fd: int
    warning: str | None = None
    runnable: tuple[str, ...] = ()


def _refuse():
    raise LauncherError('refused', 'This Build is unavailable, damaged or incompatible.')


def _number(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9a-f][0-9a-f]*', value):
        raise LauncherError('invalid_input', 'A Build number must be canonical positive lowercase hexadecimal.')
    return int(value, 16)


def _json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 32 * 1024 * 1024:
        _refuse()
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                _refuse()
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: _refuse())


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def current_target():
    try:
        version = tuple(int(value) for value in platform.mac_ver()[0].split('.')[:2])
        if platform.system() == 'Darwin' and platform.machine() == 'arm64' and version >= (14,):
            return 'macos-arm64'
    except (ValueError, TypeError):
        pass
    raise LauncherError('refused', 'No Mycel Build is supported on this host.')


def _manifest(program):
    if program.is_symlink() or not program.is_dir():
        _refuse()
    result = [{'path': '.', 'directory': True, 'mode': stat.S_IMODE(program.stat().st_mode)}]
    for path in sorted(program.rglob('*')):
        name = path.relative_to(program).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            link = os.readlink(path)
            if not link or '\\' in link or '\0' in link or link.startswith('/'):
                _refuse()
            if not path.exists() or not path.resolve().is_relative_to(program.resolve()):
                _refuse()
            result.append({'path': name, 'link': link, 'sha256': _digest(link.encode())})
        elif path.is_file():
            if path.stat().st_nlink != 1:
                _refuse()
            result.append({'path': name, 'sha256': _digest(path.read_bytes()),
                           'size': path.stat().st_size, 'mode': mode})
        elif path.is_dir():
            result.append({'path': name, 'directory': True, 'mode': mode})
        else:
            _refuse()
    if any(row.get('mode', 0) & 0o222 for row in result):
        _refuse()
    return result


def _available(root, number, target, *, withdrawn=False):
    folder = root / number
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):
        _refuse()
    for name in ('build.json', 'checks.json', 'build.log', 'run.lock'):
        member = folder / name
        if member.is_symlink() or not member.is_file() or member.stat().st_nlink != 1:
            _refuse()
    record = _json(folder / 'build.json')
    if (type(record['schemaVersion']) is not int or record['schemaVersion'] != 1
            or record['build'] != number or record['target'] != target
            or record['status'] not in ({'working', 'withdrawn'} if withdrawn else {'working'})
            or 'prunedAt' in record or record.get('program') != 'program'
            or record.get('filesManifest') != 'files.json'
            or type(record['storeFormat']) is not int or record['storeFormat'] < 1
            or type(record['searchReply']) is not int or record['searchReply'] < 1
            or not isinstance(record['version'], str) or not record['version']
            or not isinstance(record['startedAt'], str) or not isinstance(record['source'], dict)):
        _refuse()
    source, checks = record['source'], record['checks']
    if (type(source['dirty']) is not bool or not re.fullmatch(r'[0-9a-f]{64}', source['inputsSha256'])
            or not re.fullmatch(r'[0-9a-f]{40}|uncommitted', source['commit'])
            or checks['report'] != 'checks.json' or type(checks['required']) is not int or checks['required'] < 1
            or type(checks['passed']) is not int or checks['passed'] != checks['required']
            or type(checks['failed']) is not int or checks['failed'] != 0):
        _refuse()
    program = folder / 'program'
    manifest = _json(folder / 'files.json')
    if _digest(_bytes(manifest)) != record['filesSha256'] or _manifest(program) != manifest:
        _refuse()
    runtime = record['runtime']
    if not isinstance(runtime, dict):
        _refuse()
    archive = runtime.get('archiveSha256', runtime.get('sha256'))
    if (runtime['python'] != '3.14.7'
            or runtime['distribution'] != 'python-build-standalone/20260901/install_only_stripped'
            or archive != '4632cb1a6edad9e73d3c81b6d2e69131637d995173e3e85005df14102b0592ba'
            or 'sha256' in runtime and runtime['sha256'] != archive
            or not re.fullmatch(r'[0-9a-f]{64}', record['lockSha256'])):
        _refuse()
    lock_path = program / 'build-lock.json'
    lock = _json(lock_path)
    locked_runtime = lock['targets'][target]['runtime']
    if (type(lock['schemaVersion']) is not int or lock['schemaVersion'] != 1 or lock['python'] != '3.14.7'
            or _digest(lock_path.read_bytes()) != record['lockSha256']
            or locked_runtime['python'] != runtime['python']
            or locked_runtime['distribution'] != runtime['distribution'] or locked_runtime['sha256'] != archive
            or 'sha256' in runtime and runtime != locked_runtime
            or 'dependencies' in record and record['dependencies'] != lock['targets'][target]['dependencies']):
        _refuse()
    evidence = _json(folder / 'checks.json')
    results = evidence['results']
    if (type(evidence['schemaVersion']) is not int or evidence['schemaVersion'] != 1
            or not isinstance(results, list) or not results or evidence['pending'] != []
            or any(not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name']
                   or row.get('passed') is not True or row.get('executed', True) is not True for row in results)
            or len({row['name'] for row in results}) != len(results)):
        _refuse()
    interpreter = program / 'runtime/bin/python3'
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK) or not interpreter.resolve().is_relative_to(program.resolve()):
        _refuse()
    identity = _json(program / 'runtime/lib/python3.14/site-packages/mycel/data/build-identity.json')
    if (set(identity) != {'schemaVersion', 'build'} or type(identity['schemaVersion']) is not int
            or identity['schemaVersion'] != 1 or type(identity['build']) is not int or identity['build'] != _number(number)):
        _refuse()
    reason = None
    if record['status'] == 'withdrawn':
        reason = record.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            _refuse()
    return program, reason


def select_build(root: Path, arguments, *, target=None):
    """Return an inheritable shared run lease, acquired under registry SH|NB."""
    root = Path(root).absolute()
    arguments = tuple(arguments)
    explicit, input_error = None, None
    if arguments[:1] == ('-v',):
        if len(arguments) < 2:
            input_error = 'Use -v followed by a Build number as the first option.'
        else:
            explicit, arguments = arguments[1], arguments[2:]
            try:
                _number(explicit)
            except LauncherError as error:
                input_error = str(error)
    if not os.path.lexists(root) and explicit is not None and input_error is None:
        raise LauncherError('invalid_input', 'That Build number is unknown.')
    if root.is_symlink() or not root.is_dir():
        raise LauncherError('invalid_input' if input_error else 'refused',
                            input_error or 'No runnable Mycel Build is available.')
    descriptor, runnable = None, ()
    try:
        target = current_target() if target is None else target
        if target != 'macos-arm64':
            raise LauncherError('refused', 'No Mycel Build is supported on this host.')
        descriptor = os.open(root / '.registry.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_nlink != 1:
            _refuse()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LauncherError('busy', 'Another release operation holds the Build registry lock.') from None
        numbers = sorted((path.name for path in root.iterdir()
                          if re.fullmatch(r'[1-9a-f][0-9a-f]*', path.name)), key=_number)
        available = {}
        for number in numbers:
            try:
                available[number] = _available(root, number, target, withdrawn=True)
            except (LauncherError, OSError, ValueError, TypeError, KeyError, RuntimeError):
                pass  # A damaged record cannot hide another intact working Build.
        runnable = tuple(available)
        if input_error:
            raise LauncherError('invalid_input', input_error, runnable)
        if explicit is not None:
            known = os.path.lexists(root / explicit)
            if not known and (root / '.allocations.json').exists():
                known = explicit in _json(root / '.allocations.json')['allocations']
            if not known:
                raise LauncherError('invalid_input', 'That Build number is unknown.', runnable)
            try:
                program, warning = _available(root, explicit, target, withdrawn=True)
            except (LauncherError, OSError, ValueError, TypeError, KeyError, RuntimeError):
                raise LauncherError('refused', 'This Build is unavailable, damaged or incompatible.', runnable) from None
            number = explicit
        else:
            working = {number: item for number, item in available.items() if item[1] is None}
            if not working:
                raise LauncherError('refused', 'No runnable Mycel Build is available.', runnable)
            number = next(reversed(working))
            program, warning = working[number]
        run_fd = os.open(root / number / 'run.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(run_fd).st_mode) or os.fstat(run_fd).st_nlink != 1:
                _refuse()
            try:
                fcntl.flock(run_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LauncherError('busy', 'The selected Build is held by release maintenance.', runnable) from None
            os.set_inheritable(run_fd, True)
            return SelectedBuild(number, program, arguments, run_fd, warning, runnable)
        except BaseException:
            os.close(run_fd)
            raise
    except LauncherError as error:
        if input_error and error.code != 'invalid_input':
            raise LauncherError('invalid_input', input_error, runnable) from None
        if not error.runnable and runnable:
            error.runnable = runnable
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        raise LauncherError('invalid_input' if input_error else 'refused',
                            input_error or 'The Mycel Build registry is unavailable or damaged.', runnable) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(arguments=None, *, registry=None, target=None, stdout=None, stderr=None, execute=None):
    stdout, stderr = sys.stdout if stdout is None else stdout, sys.stderr if stderr is None else stderr
    selected = None
    try:
        selected = select_build(Path.home() / '.mycel/builds' if registry is None else registry,
                                sys.argv[1:] if arguments is None else arguments, target=target)
        if selected.warning is not None:
            reason = json.dumps(selected.warning, ensure_ascii=True)[1:-1]
            stderr.write('mycel: Build ' + selected.number + ' is withdrawn: ' + reason + '\n')
            stderr.flush()
        command = [str(selected.program / 'runtime/bin/python3'), '-I', '-B', '-m', 'mycel.cli', *selected.arguments]
        (os.execv if execute is None else execute)(command[0], command)
        return 0
    except LauncherError as error:
        stdout.write(json.dumps({'error': {'code': error.code, 'message': str(error)},
                                'runnable': list(error.runnable)}, separators=(',', ':')) + '\n')
        stdout.flush()
        return 1
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, TypeError):
        stdout.write(json.dumps({'error': {'code': 'refused', 'message': 'The selected Build could not be started.'},
                                'runnable': list(selected.runnable) if selected is not None else []},
                               separators=(',', ':')) + '\n')
        stdout.flush()
        return 1
    finally:
        if selected is not None:
            os.close(selected.run_fd)


if __name__ == '__main__':
    raise SystemExit(main())
