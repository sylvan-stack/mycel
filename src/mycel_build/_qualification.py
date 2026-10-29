"""Independent frozen check inventory and closed automatic qualification data.

This receiver uses only the standard library and frozen bytes. It never imports
the tests, product, providers or a database, and cannot accept on-demand proof
objects or a result list as its expected inventory.
"""
from __future__ import annotations

import ast
import re

from ._core import BuildError, digest, json_bytes
from ._credential_contract import credential_probe_passed


def _test_classes(tree):
    """Resolve local test methods and `check_kind` with Python's C3 order, without imports.

    External fixture/stdlib bases are opaque: any inherited test they add is
    still caught by the independent runtime-inventory equality check.
    """
    classes = {}
    own = {}
    kinds = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name in classes:
            raise ValueError('repeated frozen class')
        classes[node.name] = node
        methods = [method for method in node.body
                   if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and method.name.startswith('test')]
        own[node.name] = {method.name: method for method in methods}
        if len(own[node.name]) != len(methods):
            raise ValueError('repeated frozen test method')
        declared = [statement for statement in node.body if isinstance(statement, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'check_kind' for target in statement.targets)]
        if len(declared) > 1:
            raise ValueError('repeated frozen check kind')
        if declared:
            kinds[node.name] = ast.literal_eval(declared[0].value)
    orders = {}
    def linearize(name, active=()):
        if name not in classes:
            return [name]
        if name in active:
            raise ValueError('cyclic frozen class inheritance')
        if name not in orders:
            bases = [ast.unparse(base) for base in classes[name].bases]
            if len(set(bases)) != len(bases):
                raise ValueError('repeated frozen base')
            pending = [linearize(base, (*active, name))[:] for base in bases] + [bases[:]]
            result = [name]
            while any(pending):
                pending = [order for order in pending if order]
                first = next((order[0] for order in pending
                              if all(order[0] not in other[1:] for other in pending)), None)
                if first is None:
                    raise ValueError('inconsistent frozen method order')
                result.append(first)
                for order in pending:
                    if order[0] == first:
                        order.pop(0)
            orders[name] = result
        return orders[name]
    result = {}
    for name in classes:
        methods = {}
        order = linearize(name)
        for base in reversed(order):
            methods.update(own.get(base, {}))
        result[name] = (methods, next((kinds[base] for base in order if base in kinds), 'unit'))
    return result


def automatic_contract(frozen: dict[str, bytes]) -> dict:
    """Derive every automatic check and its class kind independently from the captured test sources."""
    try:
        declarations = {}
        if any(path.startswith('tests/mid/') and b'# TEST-TIER-DISABLED-BEGIN' in raw
               for path, raw in frozen.items()):
            raise BuildError('refused', 'Mid-tier tests are commented. Full qualification requires an explicitly requested testing task; see MID_TIER.md.')
        for path, raw in sorted(frozen.items()):
            if not re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', path):
                continue
            if b'# TEST-TIER-DISABLED-BEGIN ' in raw:
                raise BuildError('refused', 'Mid-tier tests are commented. Full qualification requires an explicitly requested testing task; see TESTS.md.')
            module = path.removeprefix('tests/').removesuffix('.py')
            for class_name, (methods, kind) in _test_classes(ast.parse(raw)).items():
                if kind not in {'unit', 'store', 'eval', 'live'}:
                    raise ValueError('check kind')
                for method in methods.values():
                    name = f'{module}.{class_name}.{method.name}'
                    if name in declarations:
                        raise ValueError('duplicate declaration')
                    declarations[name] = {'name': name, 'kind': kind}
        automatic = [row for _, row in sorted(declarations.items()) if row['kind'] in {'unit', 'store'}]
        if not automatic:
            raise ValueError('empty automatic inventory')
        return {'schemaVersion': 2, 'declarations': automatic, 'inventorySha256': digest(json_bytes(automatic))}
    except (AttributeError, KeyError, TypeError, ValueError, SyntaxError):
        raise BuildError('refused', 'Frozen test sources or their check kinds are incomplete or invalid.') from None


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
    if (automatic.get('completeFrozenInventory') is not True or automatic.get('gateErrorCount') != 0
            or type(automatic.get('build')) is not int or automatic['build'] != int(number, 16)
            or automatic.get('sourceInputsSha256') != source['inputsSha256']):
        return None
    if publication:
        credential = by_name['private_dummy_keychain_installed_credentials_probe']
        if not credential_probe_passed(credential, number=number, target=target,
                source_sha256=source['inputsSha256'], program_sha256=program_sha256, check_inputs=check_inputs):
            return None
    identity = {'schemaVersion': 2, 'build': number, 'source': source, 'checkInputsSha256': digest(json_bytes(check_inputs)),
                'programManifestSha256': program_sha256, 'launcherBundleSha256': launcher_sha256,
                'target': target, 'runtime': runtime, 'resultsSha256': digest(json_bytes(results)),
                'automaticInventorySha256': automatic['inventorySha256']}
    return {**identity, 'sha256': digest(json_bytes(identity))}
