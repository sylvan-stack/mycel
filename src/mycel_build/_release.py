"""Development create orchestration; staging remains an independent seam."""
from pathlib import Path

from ._core import BuildError, read_json
from ._keychain_probe import probe_private_keychain
from ._publication import KEYCHAIN_CHECK, publish
from ._qualification import qualification_certificate
from ._registry import registry_path, update_staging
from ._staging import create_stage, source_inputs


def create_release(source_root: Path, lock_path: Path, assets: Path, registry: Path, target: str,
                   *, store_settings: Path | None = None) -> dict:
    """Run fresh qualification, recapture its source, then publish the same Build."""
    record = create_stage(source_root, lock_path, assets, registry, target, store_settings=store_settings)
    if record['status'] == 'failed':
        return record
    root = registry_path(registry)
    folder = root / record['build']
    try:
        identity, frozen = source_inputs(source_root)
        if identity != record['source']:
            return update_staging(root, record['build'], failed=True, fields={
                'automaticQualification': False, 'reason': 'Source changed after qualification; working publication refused.'})
        checks = read_json(folder / 'checks.json')
        staged_certificate = qualification_certificate(number=record['build'], source=identity,
            check_inputs=read_json(folder / 'check-inputs.json'), program_sha256=record['filesSha256'],
            launcher_sha256=record['launcherBundleSha256'], target=target, runtime=record['runtime'],
            results=checks['results'])
        if (record['status'] != 'building' or record.get('phase') != 'qualified'
                or record.get('automaticQualification') is not True or staged_certificate is None
                or record.get('qualification') != staged_certificate):
            raise BuildError('refused', 'The complete current staged qualification is required before final credential work.')
        keychain = probe_private_keychain(folder / record['program'], target,
            source_root=source_root, number=record['build'], source_identity=identity,
            program_manifest=read_json(folder / 'files.json'))
        checks['results'].append({'name': KEYCHAIN_CHECK, **keychain})
        checks['pending'] = ['publication']
        counts = {**record['checks'], 'required': record['checks']['required'] + 1,
                  'passed': record['checks']['passed'] + int(keychain['passed']),
                  'failed': record['checks']['failed'] + int(not keychain['passed'])}
        certificate = qualification_certificate(number=record['build'], source=identity,
            check_inputs=read_json(folder / 'check-inputs.json'), program_sha256=record['filesSha256'],
            launcher_sha256=record['launcherBundleSha256'], target=target, runtime=record['runtime'],
            results=checks['results'], publication=True)
        record = update_staging(root, record['build'], checks=checks, failed=certificate is None, fields={
            'checks': counts, 'automaticQualification': certificate is not None,
            'qualification': certificate, 'phase': 'qualified' if certificate is not None else 'qualification_failed',
            'reason': ('All required installed checks passed; publication pending.' if certificate is not None else
                       'The required private dummy Keychain check failed or could not run.')})
    except BaseException as error:
        try:
            if 'checks' in locals() and not any(row['name'] == KEYCHAIN_CHECK for row in checks['results']):
                checks['results'].append({'name': KEYCHAIN_CHECK, 'passed': False, 'executed': False,
                    'target': target, 'reason': 'The required private Keychain check did not complete.'})
                counts = {**record['checks'], 'required': record['checks']['required'] + 1,
                          'failed': record['checks']['failed'] + 1}
            else:
                counts = record['checks']
            actual = update_staging(root, record['build'], failed=True, fields={
                'automaticQualification': False, 'checks': counts,
                'reason': 'Final installed qualification did not complete.'},
                checks=checks if 'checks' in locals() else None)
            error.partialResult = actual
        except (BuildError, OSError):
            pass
        raise
    if record['status'] == 'failed':
        return record
    # Publication owns its own partial-outcome handling. In particular no outer
    # staging cleanup may downgrade a record whose final replacement succeeded.
    return publish(root, record['build'], frozen=frozen, source_identity=identity)
