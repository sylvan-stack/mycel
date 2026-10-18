"""Last-record working publication, independently revalidated under one lock.

This receiver neither runs tests nor trusts a saved qualification boolean. Its
caller supplies the exact captured source bytes, never a reconstructed proof
object or provider acceptance. No installed product command is added.
"""
from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import tomllib

from ._core import BuildError, RUNTIME_HASHES, atomic_json, digest, file_manifest, json_bytes, read_json, utc_now, validate_manifest
from ._launcher import _validate_bundle
from ._credential_contract import credential_probe_passed
from ._qualification import automatic_contract, qualification_certificate, requirement_results, required_packaged_cases
from ._registry import _folder, _ledger, build_number, maintenance, read_record, registry_path
from ._staging import check_input_manifest, input_manifest


KEYCHAIN_CHECK = 'private_dummy_keychain_installed_credentials_probe'
FINAL_LOG = ('Every required native, bootstrap, automatic and packaged check passed.\n'
             'The separately owned dummy Keychain boundary passed.\n'
             'Working publication committed after all final evidence.\n')


def _require(condition, message='The installed Build qualification is incomplete or inconsistent.'):
    if not condition:
        raise BuildError('refused', message)


def _metadata(folder, name):
    path = folder / name
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 32 * 1024 * 1024,
             'A retained publication input is missing, aliased or unsafe.')
    return path


def _relocations(result, *, number=None):
    rows = result['relocations']
    _require(isinstance(rows, list) and len(rows) == 2)
    for row in rows:
        _require(row['python'] == '3.14.7' and row['machine'] == 'arm64'
                 and row['isolated'] is True and row['dontWriteBytecode'] is True
                 and int(row['macOS'].split('.')[0]) >= 14)
        if number is not None:
            _require(type(row['build']) is int and row['build'] == build_number(number))


def _packaged(result, number):
    _require(result['target'] == 'macos-arm64' and result['runtime'] == '3.14.7'
             and result['machine'] == 'arm64')
    for key in ('networkAndWritesDenied', 'sourceReadDenied', 'developerReadDenied',
                'ownerStateDenied', 'retainedInputsUnchanged'):
        _require(result[key] is True)
    expected = required_packaged_cases(number)
    rows = result['relocations']
    _require([row['label'] for row in rows] == ['first installation', 'second relocated installation'])
    for row in rows:
        cases = row['cases']
        _require(row['passed'] is True and row['executed'] is True
                 and row['privateWorkingRecordFixtureOnly'] is True and row['ownerPublished'] is False)
        _require(tuple(case['name'] for case in cases) == expected)
        for case in cases:
            _require(case['passed'] is True and case['executed'] is True
                     and type(case['elapsedSeconds']) in {int, float}
                     and math.isfinite(case['elapsedSeconds']) and case['elapsedSeconds'] >= 0)


def _automatic(result, frozen, number):
    contract = automatic_contract(frozen)
    expected = contract['declarations']
    checks = result['checks']
    _require(len(checks) == len(expected) and len({row['name'] for row in checks}) == len(checks))
    declarations = []
    for row in checks:
        _require(set(row) == {'name', 'kind', 'requirements', 'status', 'passed', 'detail'}
                 and row['status'] == 'passed' and row['passed'] is True and row['detail'] is None)
        declarations.append({key: row[key] for key in ('name', 'kind', 'requirements')})
    _require(sorted(declarations, key=lambda row: row['name']) == expected)
    _require(result['inventorySha256'] == contract['inventorySha256']
             and result['registrySha256'] == contract['registrySha256']
             and result['claimsSha256'] == contract['claimsSha256'])
    requirements = requirement_results(contract, checks)
    implemented = sum(row['status'] == 'implemented' for row in requirements.values())
    _require(result['requirements'] == requirements
             and result['coverage'] == {'active': 333, 'implemented': implemented, 'pending': 333 - implemented})
    _require(result['build'] == build_number(number) and result['python'] == '3.14.7'
             and result['target'] == 'macos-arm64' and result['gateErrorCount'] == 0
             and result['required'] == result['passedCount'] == len(expected) and result['failedCount'] == 0)
    _require(result['gateErrors'] == [] and all(type(result[key]) is int
             for key in ('build', 'gateErrorCount', 'required', 'passedCount', 'failedCount')))
    for key in ('completeFrozenInventory', 'isolated', 'dontWriteBytecode', 'installedProductImports',
                'networkRestrictedToCheckStore', 'sourceReadDenied', 'developerReadDenied',
                'installedFilesUnchanged', 'verifiedPrivateRelocation'):
        _require(result[key] is True)


def _verify(folder, record, frozen, identity):
    """Read all independent inputs while the registry mutation lock is held."""
    _require(record['status'] in {'building', 'working'} and 'prunedAt' not in record)
    _require(record['phase'] in {'qualified', 'working'} and record['automaticQualification'] is True)
    _require(record['source'] == identity and record['target'] == 'macos-arm64'
             and record['program'] == 'program' and record['filesManifest'] == 'files.json'
             and record['checkInputs'] == 'check-inputs.json' and record['launcherBundle'] == 'launcher-bundle')
    inputs = input_manifest(frozen)
    check_inputs = check_input_manifest(inputs)
    _require(digest(json_bytes(inputs)) == identity['inputsSha256'])
    _require(read_json(_metadata(folder, 'source-inputs.json')) == inputs
             and read_json(_metadata(folder, 'check-inputs.json')) == check_inputs
             and record['checkManifestSha256'] == digest(json_bytes(check_inputs)))
    program = folder / 'program'
    manifest = read_json(_metadata(folder, 'files.json'))
    validate_manifest(program, manifest, record['filesSha256'])
    _require(all((program / row['path']).stat().st_nlink == 1 for row in manifest
                 if not row.get('directory') and 'link' not in row))
    launcher = _validate_bundle(folder / 'launcher-bundle')
    _require(record['launcherBundleSha256'] == digest(json_bytes(launcher)))
    _require(all((folder / 'launcher-bundle/program' / row['path']).stat().st_nlink == 1
                 for row in file_manifest(folder / 'launcher-bundle/program')
                 if not row.get('directory') and 'link' not in row))
    _require((folder / 'launcher-bundle/program/launcher.py').read_bytes()
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
        _require((folder / 'launcher-bundle/program' / row['path']).read_bytes()
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
    checks = read_json(_metadata(folder, 'checks.json'))
    _require(checks['schemaVersion'] == 1 and checks['pending'] in (['publication'], []))
    results = checks['results']
    required = {'installed_native_and_two_path_probe', 'independent_launcher_bootstrap_two_path_probe',
                'installed_automatic_unit_store_gate', 'packaged_selector_and_cli_two_path_probe', KEYCHAIN_CHECK}
    _require(len(results) == len(required) and {row['name'] for row in results} == required
             and all(row['passed'] is True and row['executed'] is True for row in results))
    groups = {row['name']: row for row in results}
    native = groups['installed_native_and_two_path_probe']
    _require(native['target'] == 'macos-arm64' and native['sourceReadDenied'] is True
             and native['networkAndWritesDenied'] is True)
    _relocations(native, number=record['build'])
    _require(groups['independent_launcher_bootstrap_two_path_probe'] == {'name': 'independent_launcher_bootstrap_two_path_probe', **launcher['checks']})
    automatic = groups['installed_automatic_unit_store_gate']
    _automatic(automatic, frozen, record['build'])
    _require(automatic['sourceInputsSha256'] == identity['inputsSha256'])
    _packaged(groups['packaged_selector_and_cli_two_path_probe'], record['build'])
    keychain = groups[KEYCHAIN_CHECK]
    _require(credential_probe_passed(keychain, number=record['build'], target=record['target'],
        source_sha256=identity['inputsSha256'], program_sha256=record['filesSha256'], check_inputs=check_inputs))
    count = len(automatic['checks']) + len(required) - 1
    _require(record['checks'] == {'required': count, 'passed': count, 'failed': 0, 'report': 'checks.json'})
    certificate = qualification_certificate(number=record['build'], source=identity, check_inputs=check_inputs,
        program_sha256=record['filesSha256'], launcher_sha256=record['launcherBundleSha256'],
        target=record['target'], runtime=runtime, results=results, publication=True)
    _require(certificate is not None and record['qualification'] == certificate)
    return checks, certificate


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
            checks, certificate = _verify(folder, record, frozen, source_identity)
            final_checks = {**checks, 'pending': [], 'publication': {
                'qualificationSha256': certificate['sha256'], 'sourceInputsSha256': source_identity['inputsSha256']}}
            if checks['pending'] == []:
                _require(checks == final_checks, 'An interrupted publication has inconsistent final evidence.')
            if record['status'] == 'working':
                _require(record['phase'] == 'working' and checks == final_checks
                         and (folder / 'build.log').read_text() == FINAL_LOG)
                return record
            _require(record['phase'] == 'qualified')
            if checks != final_checks:
                wrote = True
                atomic_json(folder / 'checks.json', final_checks)
            if (folder / 'build.log').read_text() != FINAL_LOG:
                wrote = True
                _write_log(folder / 'build.log', FINAL_LOG)
            final = {**record, 'status': 'working', 'phase': 'working', 'finishedAt': utc_now(),
                     'reason': 'Every required installed check passed; working publication completed.'}
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
