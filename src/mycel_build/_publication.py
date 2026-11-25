"""Publish the sealed Build under the registry lock, writing the working record last."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import stat
import tempfile
import tomllib

from ._core import BuildError, RUNTIME_HASHES, atomic_json, digest, file_manifest, json_bytes, read_json, utc_now, validate_manifest
from ._launcher import _validate_bundle
from ._launcher_runtime import payload_directory
from ._registry import _folder, _ledger, build_number, delivery_checks, maintenance, read_record, registry_path
from ._staging import check_input_manifest, input_manifest


KEYCHAIN_CHECK = 'private_dummy_keychain_installed_credentials_probe'
FINAL_LOG = "Sealed Mycel Build published. Qualification was not run.\n"


def _require(condition, message='The staged Mycel package is incomplete or inconsistent.'):
    if not condition:
        raise BuildError('refused', message)


def _metadata(folder, name):
    path = folder / name
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 32 * 1024 * 1024,
             'A retained publication input is missing, aliased or unsafe.')
    return path


def _verify(folder, package, record, frozen, identity):
    """Read all independent inputs while the registry mutation lock is held."""
    _require(record['status'] in {'building', 'working'} and 'prunedAt' not in record)
    _require((record['status'], record.get('phase')) in {('building', 'staged'), ('working', 'working')}
             and record.get('automaticQualification') is False)
    _require(record['source'] == identity and record['target'] == 'macos-arm64'
             and record['program'] == 'program' and record['filesManifest'] == 'files.json'
             and record['checkInputs'] == 'check-inputs.json' and record['launcherBundle'] == 'launcher-bundle')
    inputs = input_manifest(frozen)
    check_inputs = check_input_manifest(inputs)
    _require(digest(json_bytes(inputs)) == identity['inputsSha256'])
    _require(read_json(_metadata(folder, 'source-inputs.json')) == inputs
             and read_json(_metadata(folder, 'check-inputs.json')) == check_inputs
             and record['checkManifestSha256'] == digest(json_bytes(check_inputs)))
    _require(package.resolve() == package)
    program = package / 'program'
    manifest = read_json(_metadata(folder, 'files.json'))
    validate_manifest(program, manifest, record['filesSha256'])
    _require(all((program / row['path']).stat().st_nlink == 1 for row in manifest
                 if not row.get('directory') and 'link' not in row))
    launcher = _validate_bundle(package / 'launcher-bundle')
    _require(record['launcherBundleSha256'] == digest(json_bytes(launcher)))
    _require(all((package / 'launcher-bundle/program' / row['path']).stat().st_nlink == 1
                 for row in file_manifest(package / 'launcher-bundle/program')
                 if not row.get('directory') and 'link' not in row))
    _require((package / 'launcher-bundle/program/launcher.py').read_bytes()
             == frozen['src/mycel_build/_launcher_runtime.py'])
    lock_raw = frozen['packaging/build-lock.json']
    lock = json.loads(lock_raw)
    _require(lock['schemaVersion'] == 1 and lock['python'] == '3.14.7'
             and set(lock['targets']) == {'macos-arm64'})
    pin = lock['targets']['macos-arm64']
    runtime = pin['runtime']
    _require(runtime['python'] == '3.14.7' and runtime['sha256'] == RUNTIME_HASHES['macos-arm64']
             and runtime['distribution'] == 'python-build-standalone/20260901/install_only_stripped'
             and record['runtime'] == runtime and launcher['runtime'] == runtime
             and record['dependencies'] == pin['dependencies'] and record['lockSha256'] == digest(lock_raw)
             and (program / 'build-lock.json').read_bytes() == lock_raw)
    for row in runtime['licenses']:
        _require((package / 'launcher-bundle/program' / row['path']).read_bytes()
                 == frozen['packaging/' + row['path']])
    site = program / 'runtime/lib/python3.14/site-packages'
    for name, raw in frozen.items():
        if not name.startswith('src/mycel/'):
            continue
        path = site / name.removeprefix('src/')
        _require(not path.exists() if name == 'src/mycel/data/development-identity.json' else path.read_bytes() == raw)
    _require(read_json(site / 'mycel/data/build-identity.json')
             == {'schemaVersion': 1, 'build': build_number(record['build'])})
    project = tomllib.loads(frozen['pyproject.toml'].decode())['project']
    _require(record['version'] == project['version'])
    dist = site / ('mycel-' + project['version'] + '.dist-info')
    metadata = ['Metadata-Version: 2.4', 'Name: mycel', 'Version: ' + project['version'],
                'Summary: A finite command line for maintained repository knowledge',
                'Requires-Python: ' + project['requires-python']]
    metadata += ['Requires-Dist: ' + dependency for dependency in project['dependencies']]
    _require((dist / 'METADATA').read_bytes() == ('\n'.join(metadata) + '\n').encode()
             and (dist / 'WHEEL').read_bytes() == b'Wheel-Version: 1.0\nGenerator: mycel_build (stdlib)\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
             and (dist / 'entry_points.txt').read_bytes() == b'[console_scripts]\nmycel = mycel._cli:main\n')
    constants = [ast.literal_eval(node.value) for node in ast.parse(frozen['src/mycel/_store.py']).body
                 if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name)
                     and name.id == 'STORE_FORMAT' for name in node.targets)]
    _require(len(constants) == 1 and record['storeFormat'] == constants[0] and record['searchReply'] == 3)
    licenses = set()
    for asset in [runtime, *pin['dependencies']]:
        for row in asset['licenses']:
            licenses.add(row['path'])
            _require((program / row['path']).read_bytes() == frozen['packaging/' + row['path']]
                     and digest(frozen['packaging/' + row['path']]) == row['sha256'])
    data = [row for row in manifest if '/mycel/data/' in row['path'] or row['path'].startswith('licenses/')]
    _require(record['dataFiles'] == data
             and {row['path'] for row in data if row['path'].startswith('licenses/')} == licenses)
    _require(record['checks'] == {'required': 0, 'passed': 0, 'failed': 0, 'report': 'checks.json'})
    return read_json(_metadata(folder, 'checks.json'))


def _write_log(path, text):
    fd, temporary = tempfile.mkstemp(prefix='.publication-log-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode()); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish(registry: Path, number: str, *, frozen: dict[str, bytes], source_identity: dict) -> dict:
    """Publish only checked frozen bytes; the working record is the last write."""
    root = registry_path(registry)
    build_number(number)
    with maintenance(root):
        folder = _folder(root, number)
        wrote = False
        try:
            for name in ('build.json', 'checks.json', 'build.log', 'run.lock'):
                _metadata(folder, name)
            record = read_record(root, number)
            _metadata(root, '.allocations.json')
            initial = _ledger(root)['allocations'][number]
            _require(all(record[key] == initial[key] for key in
                         ('schemaVersion', 'build', 'version', 'target', 'source', 'startedAt')),
                     'Publication differs from its immutable allocation identity.')
            package = payload_directory(root, number)
            checks = _verify(folder, package, record, frozen, source_identity)
            final_checks = delivery_checks(source_identity['inputsSha256'])
            _require(checks in (delivery_checks(), final_checks),
                     'An interrupted publication has inconsistent delivery metadata.')
            if record['status'] == 'working':
                _require(record['phase'] == 'working' and checks == final_checks
                         and (folder / 'build.log').read_text() == FINAL_LOG)
                return record
            if checks != final_checks:
                wrote = True
                atomic_json(folder / 'checks.json', final_checks)
            if (folder / 'build.log').read_text() != FINAL_LOG:
                wrote = True
                _write_log(folder / 'build.log', FINAL_LOG)
            final = {**record, 'status': 'working', 'phase': 'working', 'finishedAt': utc_now(),
                     'reason': 'Sealed package published without qualification.'}
            wrote = True
            atomic_json(folder / 'build.json', final)
            return final
        except BaseException as error:
            actual = None
            if wrote:
                try:
                    actual = read_record(root, number)
                except (BuildError, OSError):
                    pass
            if isinstance(error, (KeyboardInterrupt, BuildError)):
                if actual is not None:
                    error.partialResult = actual
                raise
            failure = BuildError('internal', 'Working publication could not complete; the retained record reports its actual state.')
            if actual is not None:
                failure.partialResult = actual
            raise failure from None
