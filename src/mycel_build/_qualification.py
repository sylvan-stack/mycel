"""Independent frozen check inventory and closed automatic qualification data.

This receiver uses only the standard library and frozen bytes. It never imports
the tests, product, providers or a database, and cannot accept on-demand proof
objects or a result list as its expected inventory.
"""
from __future__ import annotations

import ast
import json
import re

from ._core import BuildError, digest, json_bytes
from ._credential_contract import credential_probe_passed
from mycel._coverage import ACTIVE_REQUIREMENTS, REQUIREMENT_ID, SPECIFICATION_COUNT, SPECIFICATION_STATUSES


def automatic_contract(frozen: dict[str, bytes]) -> dict:
    """Derive every declaration independently from the captured test sources."""
    try:
        data = json.loads(frozen['src/mycel/data/requirements.json'])
        registry = {row['id']: row for row in data['requirements']}
        if (type(data['schema_version']) is not int or data['schema_version'] != 1
                or len(data['requirements']) != len(registry) or len(registry) != ACTIVE_REQUIREMENTS
                or len(data['specifications']) != SPECIFICATION_COUNT
                or any(row['specification_status'] not in SPECIFICATION_STATUSES
                       for row in data['specifications'].values())
                or {row['specification'] for row in registry.values()} != {f'MYC-{n}' for n in range(SPECIFICATION_COUNT)}
                or any(not REQUIREMENT_ID.fullmatch(key)
                       or row['kind'] not in {'unit', 'store', 'eval', 'live'}
                       or row['specification'] != key.split('.')[0] for key, row in registry.items())):
            raise ValueError('registry')
        raw_claims = json.loads(frozen['checks/claims.json'])
        if (set(raw_claims) != {'schema_version', 'implemented'}
                or type(raw_claims['schema_version']) is not int or raw_claims['schema_version'] != 1
                or not isinstance(raw_claims['implemented'], dict)):
            raise ValueError('claims')
        declarations = {}
        for path, raw in sorted(frozen.items()):
            if not re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', path):
                continue
            module = path.removeprefix('tests/').removesuffix('.py')
            for cls in ast.parse(raw).body:
                if not isinstance(cls, ast.ClassDef):
                    continue
                for method in cls.body:
                    if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or not method.name.startswith('test'):
                        continue
                    decorators = [node for node in method.decorator_list if isinstance(node, ast.Call)
                                  and isinstance(node.func, ast.Name) and node.func.id == 'proves']
                    if len(decorators) != 1:
                        raise ValueError('declaration')
                    node = decorators[0]
                    requirements = [ast.literal_eval(arg) for arg in node.args]
                    kinds = [ast.literal_eval(kw.value) for kw in node.keywords if kw.arg == 'kind']
                    if len(kinds) > 1 or any(kw.arg != 'kind' for kw in node.keywords):
                        raise ValueError('declaration options')
                    kind = kinds[0] if kinds else 'unit'
                    if (kind not in {'unit', 'store', 'eval', 'live'} or not requirements
                            or len(set(requirements)) != len(requirements)
                            or any(key not in registry or registry[key]['kind'] != kind for key in requirements)):
                        raise ValueError('declaration requirements')
                    name = f'{module}.{cls.name}.{method.name}'
                    if name in declarations:
                        raise ValueError('duplicate declaration')
                    declarations[name] = {'name': name, 'kind': kind, 'requirements': requirements}
        if not declarations:
            raise ValueError('empty inventory')
        claims = raw_claims['implemented']
        for key, names in claims.items():
            if (key not in registry or not isinstance(names, list) or not names
                    or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names)):
                raise ValueError('claim')
            for name in names:
                if (name not in declarations or key not in declarations[name]['requirements']
                        or declarations[name]['kind'] != registry[key]['kind']):
                    raise ValueError('unmapped claim')
        automatic = [row for _, row in sorted(declarations.items()) if row['kind'] in {'unit', 'store'}]
        if not automatic:
            raise ValueError('empty automatic inventory')
        return {'schemaVersion': 1, 'declarations': automatic, 'registry': registry, 'claims': claims,
                'registrySha256': digest(frozen['src/mycel/data/requirements.json']),
                'claimsSha256': digest(frozen['checks/claims.json']),
                'inventorySha256': digest(json_bytes(automatic))}
    except (AttributeError, KeyError, TypeError, ValueError, SyntaxError):
        raise BuildError('refused', 'Frozen requirement claims or check declarations are incomplete or invalid.') from None


def requirement_results(contract: dict, checks: list[dict]) -> dict:
    """Reconstruct all proof rows from this run's exact passing outcomes."""
    by_name = {row['name']: row for row in checks}
    result = {}
    for key, row in contract['registry'].items():
        names = contract['claims'].get(key, [])
        implemented = bool(names) and all(name in by_name and by_name[name]['status'] == 'passed'
            and key in by_name[name]['requirements'] and by_name[name]['kind'] == row['kind'] for name in names)
        result[key] = {'specification': row['specification'], 'specification_status': 'accepted',
                       'kind': row['kind'], 'status': 'implemented' if implemented else 'pending',
                       'verified_by': list(names) if implemented else []}
    return result


def required_packaged_cases(number: str) -> tuple[str, ...]:
    """Freeze the exact ordered obligation of each numbered relocation."""
    if not isinstance(number, str) or re.fullmatch('[1-9a-f][0-9a-f]*', number) is None:
        raise ValueError('canonical Build number')
    return (
        'json_missing.toml_--help', 'json_missing.toml_info', 'json_missing.toml_-v_' + number + '_info',
        'json_invalid.toml_--help', 'json_invalid.toml_info', 'json_invalid.toml_-v_' + number + '_info',
        'default_skips_higher_damaged', 'withdrawn_not_default', 'withdrawn_explicit',
        'cwd_repository_empty_retrieval', 'grep_matched_literal_arguments', 'grep_empty_literal_argument',
        'grep_no_match', 'grep_pattern_error', 'selected_pid_signal_2', 'selected_pid_signal_15')


def _relocations_passed(by_name: dict, *, number: str, target: str) -> bool:
    """A group-level boolean alone is not complete relocation evidence."""
    labels = ['first installation', 'second relocated installation']
    native = by_name['installed_native_and_two_path_probe']
    launcher = by_name['independent_launcher_bootstrap_two_path_probe']
    packaged = by_name['packaged_selector_and_cli_two_path_probe']
    for row in (native, launcher, packaged):
        if (row.get('target') != target or row.get('sourceReadDenied') is not True
                or row.get('networkAndWritesDenied') is not True
                or not isinstance(row.get('relocations'), list) or len(row['relocations']) != 2):
            return False
    for row in native['relocations']:
        if (row.get('build') != int(number, 16) or type(row.get('build')) is not int
                or row.get('python') != '3.14.7' or row.get('machine') != 'arm64'
                or row.get('isolated') is not True or row.get('dontWriteBytecode') is not True):
            return False
    if [row.get('label') for row in launcher['relocations']] != labels:
        return False
    for row in launcher['relocations']:
        if (row.get('python') != '3.14.7' or row.get('machine') != 'arm64'
                or row.get('isolated') is not True or row.get('dontWriteBytecode') is not True
                or row.get('standaloneSelector') is not True):
            return False
    if (packaged.get('retainedInputsUnchanged') is not True
            or packaged.get('developerReadDenied') is not True or packaged.get('ownerStateDenied') is not True
            or [row.get('label') for row in packaged['relocations']] != labels):
        return False
    for row in packaged['relocations']:
        cases = row.get('cases')
        if (row.get('passed') is not True or row.get('executed') is not True
                or row.get('privateWorkingRecordFixtureOnly') is not True or row.get('ownerPublished') is not False
                or not isinstance(cases, list)
                or tuple(case.get('name') for case in cases) != required_packaged_cases(number)
                or any(case.get('passed') is not True or case.get('executed') is not True for case in cases)):
            return False
    return True


def qualification_certificate(*, number: str, source: dict, check_inputs: list[dict], program_sha256: str,
                              launcher_sha256: str, target: str, runtime: dict, results: list[dict],
                              publication: bool = False) -> dict | None:
    """Describe automatic eligibility; never publish or mark a Build working."""
    if type(publication) is not bool:
        return None
    required = {'installed_native_and_two_path_probe', 'independent_launcher_bootstrap_two_path_probe',
                'installed_automatic_unit_store_gate', 'packaged_selector_and_cli_two_path_probe'}
    if publication:
        required.add('private_dummy_keychain_installed_credentials_probe')
    if (len(results) != len(required) or {row.get('name') for row in results} != required
            or any(row.get('passed') is not True or row.get('executed') is not True for row in results)):
        return None
    by_name = {row['name']: row for row in results}
    if target != 'macos-arm64' or runtime.get('python') != '3.14.7' or not _relocations_passed(by_name, number=number, target=target):
        return None
    automatic = next(row for row in results if row['name'] == 'installed_automatic_unit_store_gate')
    if (automatic.get('completeFrozenInventory') is not True or not isinstance(automatic.get('requirements'), dict)
            or len(automatic['requirements']) != ACTIVE_REQUIREMENTS or automatic.get('gateErrorCount') != 0
            or type(automatic.get('build')) is not int or automatic['build'] != int(number, 16)
            or automatic.get('sourceInputsSha256') != source['inputsSha256']):
        return None
    # Passing the currently declared suite cannot promote missing automatic
    # requirement proofs. Eval/live stay pending until explicitly requested.
    if any(row['kind'] in {'unit', 'store'} and row['status'] != 'implemented'
           for row in automatic['requirements'].values()):
        return None
    if publication:
        credential = by_name['private_dummy_keychain_installed_credentials_probe']
        if not credential_probe_passed(credential, number=number, target=target,
                source_sha256=source['inputsSha256'], program_sha256=program_sha256, check_inputs=check_inputs):
            return None
    identity = {'schemaVersion': 1, 'build': number, 'source': source, 'checkInputsSha256': digest(json_bytes(check_inputs)),
                'programManifestSha256': program_sha256, 'launcherBundleSha256': launcher_sha256,
                'target': target, 'runtime': runtime, 'resultsSha256': digest(json_bytes(results)),
                'automaticInventorySha256': automatic['inventorySha256'],
                'requirementsSha256': digest(json_bytes(automatic['requirements']))}
    return {**identity, 'sha256': digest(json_bytes(identity))}
