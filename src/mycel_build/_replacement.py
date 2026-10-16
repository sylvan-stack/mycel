"""Read-only replacement plans and evidence-bound operator reports.

This module never runs a command, opens a database, unlinks a path or edits a
shell file. SQL and argv are reviewable operator instructions, not an executor.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from ._core import BuildError

_ROLES = {'runtime', 'launcher', 'source_corpus', 'document_corpus', 'unrelated', 'uncertain'}
_REMOVE = {'runtime', 'launcher'}
_IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_BASE_STEPS = ('inventory_review', 'qualification_and_launcher', 'new_private_store',
               'optional_paid_operations', 'command_cutover')


def _fail(message='Replacement inventory, plan or verification is invalid or changed.', code='refused'):
    raise BuildError(code, message)


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        _fail(code='invalid_input')
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        _fail(code='invalid_input')
    return value


def _path(value):
    _text(value)
    if (not value.startswith('/') or os.path.normpath(value) != value
            or any(c in value for c in '*?[]{}~') or '..' in Path(value).parts):
        _fail('Use exact absolute paths without aliases, traversal or patterns.', 'invalid_input')
    return Path(value)


def _identifier(value):
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        _fail('Use separate exact schema and table identifiers.', 'invalid_input')
    return value


def _zero(value):
    return type(value) is int and value == 0


def _command_present(value):
    path = _path(value)
    try:
        kind = 'symlink' if path.is_symlink() else 'file'
        _file_state(str(path), kind)
        return True
    except BuildError:
        return False


def _fingerprint(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail(code='invalid_input')
    return value


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n').encode()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _finite_number(value):
    number = float(value)
    if not math.isfinite(number):
        _fail('Non-finite JSON numbers are refused.', 'invalid_input')
    return number


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('Duplicate JSON keys are refused.', 'invalid_input')
        result[key] = value
    return result


def _regular_bytes(path):
    path = _path(str(path))
    try:
        for parent in path.parents:
            if parent.is_symlink():
                _fail('A replacement evidence path has an ambiguous directory alias.')
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                _fail('Evidence must be one ordinary independently retained file.')
            parts = []
            while block := os.read(fd, 1024 * 1024):
                parts.append(block)
            after = os.fstat(fd)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                _fail('A replacement input changed while it was read.')
            return b''.join(parts)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        _fail('A replacement input is missing, unsafe or unavailable.')


def _decode(data, message='Replacement inputs must be strict JSON.'):
    try:
        return json.loads(data, object_pairs_hook=_unique,
                          parse_constant=_finite_number, parse_float=_finite_number)
    except (UnicodeError, ValueError, TypeError):
        _fail(message, 'invalid_input')


def _load(path):
    return _decode(_regular_bytes(path))


def _binding(path):
    return {'path': str(_path(str(path))), 'sha256': _digest(_regular_bytes(path))}


def _verify_binding(row):
    _keys(row, ('path', 'sha256'))
    _fingerprint(row['sha256'])
    data = _regular_bytes(row['path'])
    if _digest(data) != row['sha256']:
        _fail('Replacement ownership or verification evidence changed.')
    return data


def _bound(row):
    return _decode(_verify_binding(row), 'A verification record must be strict JSON.')


def _time(value):
    try:
        selected = datetime.fromisoformat(value)
        if selected.tzinfo is None or selected.utcoffset() is None:
            _fail(code='invalid_input')
        return selected.astimezone(timezone.utc)
    except (TypeError, ValueError):
        _fail(code='invalid_input')


def _fresh(value, now):
    seconds = (now - _time(value)).total_seconds()
    if not -300 <= seconds <= 86400:
        _fail('Replacement evidence is stale or dated in the future; observe it again.')


def _file_state(path, kind):
    path = _path(path)
    try:
        if any(parent.is_symlink() for parent in path.parents):
            _fail('An inventoried path has an ambiguous parent alias.')
        actual = path.lstat()
        if kind == 'file' and stat.S_ISREG(actual.st_mode):
            return _digest(_regular_bytes(path))
        if kind == 'symlink' and stat.S_ISLNK(actual.st_mode):
            return _digest(os.fsencode(os.readlink(path)))
        if kind == 'directory' and stat.S_ISDIR(actual.st_mode) and not path.is_symlink():
            return None
    except OSError:
        pass
    _fail('An inventoried path is missing or has a changed type.')



def _tree_fingerprint(path):
    path = _path(str(path)); rows = []
    for directory, folders, files in os.walk(path, followlinks=False, onerror=lambda error: _fail('A preserved corpus cannot be completely observed.')):
        for name in sorted(folders + files):
            selected = Path(directory) / name
            relative = selected.relative_to(path).as_posix()
            if selected.is_symlink():
                rows.append({'path': relative, 'kind': 'symlink', 'sha256': _digest(os.fsencode(os.readlink(selected)))})
            elif selected.is_dir():
                rows.append({'path': relative, 'kind': 'directory'})
            else:
                rows.append({'path': relative, 'kind': 'file', 'sha256': _digest(_regular_bytes(selected))})
    return _digest(_json_bytes(sorted(rows, key=lambda row: row['path'])))


def _ownership(binding, subject, now):
    """Bind inspectable facts; an operator must still review their meaning."""
    if binding is None:
        return False
    evidence = _bound(binding)
    _keys(evidence, ('schemaVersion', 'observedAt', 'product', 'subject', 'basis'))
    if type(evidence['schemaVersion']) is not int or evidence['schemaVersion'] != 1 or evidence['product'] != 'mycel1' or evidence['subject'] != subject:
        _fail('Ownership evidence does not describe this exact Mycel 1 object.')
    _fresh(evidence['observedAt'], now)
    if not isinstance(evidence['basis'], list) or not evidence['basis']:
        _fail('An ownership flag alone is not independently inspectable evidence.')
    for basis in evidence['basis']:
        _keys(basis, ('artifact', 'locator', 'finding'))
        _verify_binding(basis['artifact'])
        _text(basis['locator']); _text(basis['finding'])
    return True


def _catalog(binding, now):
    value = _bound(binding)
    _keys(value, ('schemaVersion', 'observedAt', 'database', 'objects', 'dependencies'))
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        _fail(code='invalid_input')
    _fresh(value['observedAt'], now); _text(value['database'])
    objects = {}
    if not isinstance(value['objects'], list) or not isinstance(value['dependencies'], list):
        _fail(code='invalid_input')
    for item in value['objects']:
        _keys(item, ('schema', 'name', 'kind', 'oid', 'definitionSha256'))
        key = (_identifier(item['schema']), _identifier(item['name']))
        if (key in objects or item['kind'] not in {'table', 'view', 'index', 'sequence', 'constraint'}
                or type(item['oid']) is not int or item['oid'] <= 0):
            _fail(code='invalid_input')
        _fingerprint(item['definitionSha256']); objects[key] = item
    for edge in value['dependencies']:
        _keys(edge, ('owner', 'dependent', 'automatic'))
        for end in ('owner', 'dependent'):
            _keys(edge[end], ('schema', 'name'))
            if tuple(edge[end][key] for key in ('schema', 'name')) not in objects:
                _fail('The supplied catalog omits a dependency endpoint.')
        if type(edge['automatic']) is not bool:
            _fail(code='invalid_input')
    return value, objects


def _quoted(key):
    return '.'.join('"' + _identifier(value) + '"' for value in key)


def _sql(tables):
    if not tables:
        return None
    names = ', '.join(_quoted((row['schema'], row['name'])) for row in tables)
    guards = '\n'.join("  IF pg_catalog.to_regclass('" + _quoted((row['schema'], row['name']))
        + "')::oid IS DISTINCT FROM " + str(row['oid'])
        + " THEN RAISE EXCEPTION 'Inventoried Mycel 1 table identity changed'; END IF;" for row in tables)
    return ('BEGIN;\nLOCK TABLE ' + names + ' IN ACCESS EXCLUSIVE MODE NOWAIT;\n'
            'DO $mycel_replacement$\nBEGIN\n' + guards + '\nEND;\n$mycel_replacement$;\n'
            'DROP TABLE ' + names + ' RESTRICT;\nCOMMIT;\n')


def replacement_plan(inventory_path, *, now=None):
    """Observe only the explicit input; emit instructions without applying them."""
    now = now or datetime.now(timezone.utc)
    inventory_path = _path(str(inventory_path))
    inventory_data = _regular_bytes(inventory_path)
    value = _decode(inventory_data)
    _keys(value, ('schemaVersion', 'observedAt', 'oldDatabase', 'newDatabase', 'previousCommand',
                  'newCommand', 'files', 'aliases', 'tables', 'paidOperationsRequested'))
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or type(value['paidOperationsRequested']) is not bool:
        _fail(code='invalid_input')
    _fresh(value['observedAt'], now)
    _keys(value['oldDatabase'], ('identity', 'catalog'))
    if _text(value['oldDatabase']['identity']) == _text(value['newDatabase']):
        _fail('Replacement requires a distinct new private database; no old state is copied.')
    _path(value['previousCommand']); _path(value['newCommand'])
    catalog, objects = _catalog(value['oldDatabase']['catalog'], now)
    if catalog['database'] != value['oldDatabase']['identity']:
        _fail('The catalog belongs to another database.')
    for key in ('files', 'aliases', 'tables'):
        if not isinstance(value[key], list):
            _fail(code='invalid_input')
    protected = []
    files, blocked, ids, paths = [], [], set(), set()
    for row in value['files']:
        _keys(row, ('id', 'path', 'role', 'kind', 'sha256', 'ownership', 'uncertainty'))
        name = _text(row['id']); path = _path(row['path'])
        if row['uncertainty'] is not None: _text(row['uncertainty'])
        if name in ids or str(path) in paths or row['role'] not in _ROLES or row['kind'] not in {'file', 'symlink', 'directory'}:
            _fail(code='invalid_input')
        ids.add(name); paths.add(str(path))
        if row['kind'] != 'directory': _fingerprint(row['sha256'])
        elif row['sha256'] is not None: _fail(code='invalid_input')
        if _file_state(str(path), row['kind']) != row['sha256']:
            _fail('Inventoried file bytes or link targets changed.')
        if row['role'] in {'source_corpus', 'document_corpus'}: protected.append(path)
        if row['role'] not in _REMOVE:
            if row['role'] == 'uncertain': blocked.append({'object': name, 'reason': _text(row['uncertainty'])})
            continue
        if row['uncertainty'] is not None or row['kind'] == 'directory':
            blocked.append({'object': name, 'reason': row['uncertainty'] or 'Directory-wide removal is forbidden.'}); continue
        subject = {key: row[key] for key in ('path', 'role', 'kind', 'sha256')}
        if not _ownership(row['ownership'], subject, now):
            blocked.append({'object': name, 'reason': 'Ownership is unverified; preserve this object.'}); continue
        files.append(row)
    for row in list(files):
        path = Path(row['path'])
        if any(path == p or path.is_relative_to(p) for p in protected):
            blocked.append({'object': row['id'], 'reason': 'Source and document corpora are never removal targets.'})
            files.remove(row)
    aliases, alias_snapshots = [], {}
    for row in value['aliases']:
        _keys(row, ('id', 'name', 'sourceFile', 'definition', 'sourceSha256', 'ownership', 'uncertainty'))
        _text(row['id']);
        if row['uncertainty'] is not None: _text(row['uncertainty'])
        if not isinstance(row['name'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9-]*', row['name']): _fail(code='invalid_input')
        _path(row['sourceFile']); _text(row['definition']); _fingerprint(row['sourceSha256'])
        if row['sourceFile'] not in alias_snapshots:
            alias_snapshots[row['sourceFile']] = _regular_bytes(row['sourceFile'])
        data = alias_snapshots[row['sourceFile']]
        if _digest(data) != row['sourceSha256'] or data.splitlines().count(row['definition'].encode()) != 1:
            _fail('The exact inventoried alias definition changed or is ambiguous.')
        subject = {key: row[key] for key in ('name', 'sourceFile', 'definition', 'sourceSha256')}
        if row['uncertainty'] is not None or not _ownership(row['ownership'], subject, now):
            blocked.append({'object': row['id'], 'reason': row['uncertainty'] or 'Alias ownership is unverified.'})
        if any(Path(row['sourceFile']) == p or Path(row['sourceFile']).is_relative_to(p) for p in protected):
            blocked.append({'object': row['id'], 'reason': 'A source corpus is not an installed alias target.'})
        else:
            aliases.append(row)
    tables, target_keys, owned_dependents = [], set(), set()
    for row in value['tables']:
        _keys(row, ('schema', 'name', 'oid', 'definitionSha256', 'ownedDependents', 'ownership', 'uncertainty'))
        key = (_identifier(row['schema']), _identifier(row['name']))
        if row['uncertainty'] is not None: _text(row['uncertainty'])
        if key in target_keys or key not in objects: _fail('An inventoried table is duplicate or missing.')
        target_keys.add(key)
        subject = objects[key]
        if subject['kind'] != 'table' or subject['oid'] != row['oid'] or subject['definitionSha256'] != row['definitionSha256']:
            _fail('An inventoried table identity or definition changed.')
        if not isinstance(row['ownedDependents'], list): _fail(code='invalid_input')
        for dependent in row['ownedDependents']:
            _keys(dependent, ('schema', 'name'))
            dep = (_identifier(dependent['schema']), _identifier(dependent['name']))
            if dep not in objects or dep in owned_dependents: _fail('An owned dependent object is missing or duplicated.')
            owned_dependents.add(dep)
        evidence_subject = {'database': catalog['database'], 'table': subject, 'ownedDependents': [objects[(d['schema'], d['name'])] for d in row['ownedDependents']]}
        if row['uncertainty'] is not None or not _ownership(row['ownership'], evidence_subject, now):
            blocked.append({'object': _quoted(key), 'reason': row['uncertainty'] or 'Table ownership is unverified.'})
        tables.append(row)
    for edge in catalog['dependencies']:
        owner = tuple(edge['owner'][k] for k in ('schema', 'name')); dep = tuple(edge['dependent'][k] for k in ('schema', 'name'))
        if owner in target_keys and dep not in target_keys and not (edge['automatic'] and dep in owned_dependents):
            blocked.append({'object': _quoted(owner), 'reason': 'An uninventoried dependent object prevents RESTRICT removal.'})
    # Each shell file is one manual edit, preserving every uninventoried line.
    alias_groups = {}
    for row in aliases:
        group = alias_groups.setdefault(row['sourceFile'], {'id': _digest(row['sourceFile'].encode())[:16],
            'sourceFile': row['sourceFile'], 'sourceSha256': row['sourceSha256'], 'definitions': [], 'names': []})
        if group['sourceSha256'] != row['sourceSha256'] or row['definition'] in group['definitions']:
            _fail('An alias source observation is inconsistent or duplicate.')
        group['definitions'].append(row['definition']); group['names'].append(row['name'])
    for group in alias_groups.values():
        definitions = {item.encode() for item in group['definitions']}
        group['remainingSha256'] = _digest(b''.join(line for line in alias_snapshots[group['sourceFile']].splitlines(keepends=True)
            if line.rstrip(b'\r\n') not in definitions))
    aliases = list(alias_groups.values())
    if value['previousCommand'] not in paths or value['previousCommand'] == value['newCommand']:
        _fail('The previous command needs its own exact inventory entry; the new command must differ.')
    # Evidence must survive removals and manual alias edits for later inspection.
    cleanup_paths = {item['path'] for item in files} | {item['sourceFile'] for item in aliases}
    ownership_evidence = {}
    for row in [*value['files'], *value['aliases'], *value['tables']]:
        ownership = row['ownership']
        if ownership is not None:
            evidence = _bound(ownership)
            ownership_evidence[ownership['path']] = ownership
            for item in evidence['basis']:
                ownership_evidence[item['artifact']['path']] = item['artifact']
            if ownership['path'] in cleanup_paths or any(item['artifact']['path'] in cleanup_paths for item in evidence['basis']):
                _fail('Ownership evidence must survive cleanup.')
    steps = [{'id': name, 'required': name != 'optional_paid_operations' or value['paidOperationsRequested']} for name in _BASE_STEPS]
    steps += [{'id': 'remove_file:' + row['id'], 'required': True} for row in files]
    steps += [{'id': 'remove_alias:' + row['id'], 'required': True} for row in aliases]
    if tables: steps.append({'id': 'remove_old_tables', 'required': True})
    steps.append({'id': 'verify_survivors', 'required': True})
    if len({row['id'] for row in steps}) != len(steps): _fail('Replacement step identities are duplicate.')
    plan = {'schemaVersion': 1, 'kind': 'mycel-one-time-replacement-plan', 'inventory': {'path': str(inventory_path), 'sha256': _digest(inventory_data)},
            'observedAt': value['observedAt'], 'previousCommand': value['previousCommand'], 'newCommand': value['newCommand'],
            'oldDatabase': value['oldDatabase'], 'newDatabase': value['newDatabase'], 'files': files,
            'preservedFiles': [row for row in value['files'] if row not in files],
            'preservedTrees': {row['path']: _tree_fingerprint(row['path']) for row in value['files']
                if row['role'] in {'source_corpus', 'document_corpus'} and row['kind'] == 'directory'}, 'aliases': aliases,
            'tables': tables, 'catalog': catalog, 'ownershipEvidence': [ownership_evidence[k] for k in sorted(ownership_evidence)],
            'blocked': blocked, 'steps': steps,
            'operatorSql': None if blocked else _sql(tables), 'version1StateToCopy': [],
            'executionAuthorized': False, 'shellFilesEdited': False, 'operatorOwnershipReviewRequired': True}
    plan['sha256'] = _digest(_json_bytes(plan))
    return {'plan': plan, 'report': {'schemaVersion': 1, 'planSha256': plan['sha256'],
        'steps': [{'id': row['id'], 'status': 'pending', 'verification': None} for row in steps]}}


def validate_replacement_report(plan_path, report_path, *, expected_plan_sha256, now=None):
    """Validate concrete operator observations; never perform a reported action."""
    now = now or datetime.now(timezone.utc)
    _fingerprint(expected_plan_sha256)
    plan_data = _regular_bytes(plan_path)
    if _digest(plan_data) != expected_plan_sha256:
        _fail('The operator-reviewed plan file changed.')
    plan = _decode(plan_data); report = _load(report_path)
    if type(plan) is not dict or plan.get('kind') != 'mycel-one-time-replacement-plan': _fail(code='invalid_input')
    fingerprint = plan.get('sha256'); body = {k: v for k, v in plan.items() if k != 'sha256'}
    if _digest(_json_bytes(body)) != fingerprint or plan.get('executionAuthorized') is not False or plan.get('version1StateToCopy') != []:
        _fail('The replacement plan changed or proposes importing old state.')
    _keys(plan, ('schemaVersion', 'kind', 'inventory', 'observedAt', 'previousCommand', 'newCommand',
                 'oldDatabase', 'newDatabase', 'files', 'preservedFiles', 'preservedTrees', 'aliases', 'tables', 'catalog', 'ownershipEvidence',
                 'blocked', 'steps', 'operatorSql', 'version1StateToCopy', 'executionAuthorized',
                 'shellFilesEdited', 'operatorOwnershipReviewRequired', 'sha256'))
    if plan['operatorSql'] != (None if plan['blocked'] else _sql(plan['tables'])):
        _fail('The reviewed SQL no longer names the exact restrictive table operation.')
    _bound(plan['inventory'])
    _keys(report, ('schemaVersion', 'planSha256', 'steps'))
    if type(report['schemaVersion']) is not int or report['schemaVersion'] != 1 or report['planSha256'] != fingerprint or not isinstance(report['steps'], list): _fail(code='invalid_input')
    if any(type(row) is not dict for row in report['steps']): _fail(code='invalid_input')
    if [row.get('id') for row in report['steps']] != [row['id'] for row in plan['steps']]: _fail('The replacement step sequence changed.')
    completed, effects, pending_required, cutover = [], [], False, False
    for wanted, row in zip(plan['steps'], report['steps']):
        _keys(row, ('id', 'status', 'verification'))
        if row['status'] not in {'pending', 'completed', 'blocked', 'failed'}: _fail(code='invalid_input')
        if row['status'] == 'pending':
            if row['verification'] is not None: _fail(code='invalid_input')
        else:
            observation = _bound(row['verification'])
            _keys(observation, ('schemaVersion', 'planSha256', 'step', 'status', 'observedAt', 'facts'))
            if (type(observation['schemaVersion']) is not int or observation['schemaVersion'] != 1 or observation['planSha256'] != fingerprint
                    or observation['step'] != row['id'] or observation['status'] != row['status']
                    or type(observation['facts']) is not dict or not observation['facts']): _fail('A step lacks concrete matching verification.')
            _fresh(observation['observedAt'], now)
            facts = observation['facts']
            if row['status'] == 'completed' and plan['blocked']:
                _fail('Unresolved ownership or dependency blockers prevent completion.')
            if row['id'] == 'inventory_review' and row['status'] == 'completed':
                if facts.get('inventorySha256') != plan['inventory']['sha256'] or facts.get('uncertainObjects') != [] or facts.get('reviewedBasis') != plan['ownershipEvidence']:
                    _fail('The exact inventory and independent ownership basis have not been reviewed.')
                for basis in facts['reviewedBasis']: _verify_binding(basis)
            if row['id'] == 'qualification_and_launcher' and row['status'] == 'completed':
                build = _bound(facts.get('workingBuild'))
                if (build.get('status') != 'working' or build.get('automaticQualification') is not True
                        or facts.get('launcher') != plan['newCommand'] or not _command_present(plan['newCommand'])):
                    _fail('A checked working Build and installed independent launcher are not verified.')
            if row['id'] == 'optional_paid_operations' and row['status'] == 'completed':
                authorization = _bound(facts.get('authorization'))
                if authorization.get('explicitlyRequested') is not True or not isinstance(facts.get('actualReports'), list) or not facts['actualReports']:
                    _fail('Paid operations require separate explicit authorization and actual reports.')
                for actual in facts['actualReports']: _bound(actual)
            if facts.get('copiedVersion1State', []) != []: _fail('No version 1 index state may be copied.')
            if row['id'].startswith('remove_') and not cutover: _fail('Old runtime cleanup precedes verified command cutover.')
            if row['id'].startswith('remove_file:'):
                target = next((x for x in plan['files'] if row['id'] == 'remove_file:' + x['id']), None)
                if target is None or facts.get('path') != target['path'] or facts.get('beforeSha256') != target['sha256']: _fail('A removal is not an exact inventoried file.')
                if facts.get('after') == 'absent':
                    if os.path.lexists(target['path']): _fail('A reported removed file still exists.')
                    effects.append({'removedFile': target['path']})
                elif row['status'] == 'completed': _fail('A completed removal lacks an observed absent file.')
            elif row['id'].startswith('remove_alias:') and (row['status'] == 'completed' or facts.get('editCommitted') is True):
                target = next((x for x in plan['aliases'] if row['id'] == 'remove_alias:' + x['id']), None)
                if (target is None or facts.get('sourceFile') != target['sourceFile']
                        or facts.get('beforeSha256') != target['sourceSha256']
                        or _digest(_regular_bytes(target['sourceFile'])) != target['remainingSha256']):
                    _fail('Alias removal changed uninventoried shell-file content.')
                effects.append({'removedAliases': target['names'], 'shellFileEditedByOperator': target['sourceFile']})
            elif row['id'] == 'new_private_store' and row['status'] == 'completed':
                if facts.get('database') != plan['newDatabase'] or not all(_zero(facts.get(key)) for key in ('initExitCode', 'localIngestExitCode', 'nonpaidChecksExitCode')): _fail('New private store verification is incomplete.')
            elif row['id'] == 'command_cutover' and (row['status'] == 'completed' or facts.get('cutoverCommitted') is True):
                if facts.get('command') != plan['newCommand'] or facts.get('database') != plan['newDatabase'] or not _zero(facts.get('infoExitCode')) or not _command_present(plan['newCommand']): _fail('Command cutover is not verified.')
                cutover = True
                effects.append({'commandCutoverObserved': plan['newCommand']})
            elif row['id'] == 'remove_old_tables' and (row['status'] == 'completed' or facts.get('transactionCommitted') is True):
                expected = [{'schema': x['schema'], 'name': x['name']} for x in plan['tables']]
                if facts.get('removedTables') != expected or facts.get('restrict') is not True or facts.get('transactionCommitted') is not True: _fail('Old table removal is not the exact restrictive transaction.')
                after_catalog, after_objects = _catalog(facts.get('catalogAfter'), now)
                removed = {(x['schema'], x['name']) for x in plan['tables']}
                removed.update((x['schema'], x['name']) for row in plan['tables'] for x in row['ownedDependents'])
                survivors = {(x['schema'], x['name']): x for x in plan['catalog']['objects'] if (x['schema'], x['name']) not in removed}
                if after_catalog['database'] != plan['oldDatabase']['identity'] or after_objects != survivors:
                    _fail('Unrelated database objects did not survive the exact table removal.')
                effects.append({'removedTables': expected})
            elif row['id'] == 'verify_survivors' and row['status'] == 'completed':
                after_catalog, after_objects = _catalog(facts.get('catalogAfter'), now)
                removed = {(x['schema'], x['name']) for x in plan['tables']}
                removed.update((x['schema'], x['name']) for row in plan['tables'] for x in row['ownedDependents'])
                expected = {(x['schema'], x['name']): x for x in plan['catalog']['objects'] if (x['schema'], x['name']) not in removed}
                if after_catalog['database'] != plan['oldDatabase']['identity'] or after_objects != expected:
                    _fail('Final unrelated database objects differ from their inventory.')
                for tree, fingerprint in plan['preservedTrees'].items():
                    if _tree_fingerprint(tree) != fingerprint: _fail('A preserved source or document corpus changed.')
                for retained in plan['preservedFiles']:
                    if _file_state(retained['path'], retained['kind']) != retained['sha256']:
                        _fail('A preserved file or source corpus changed.')
                if facts.get('unrelatedObjectsVerified') is not True or facts.get('sourceCorporaVerified') is not True:
                    _fail('Surviving objects and source corpora still need verification.')
        if row['status'] == 'completed':
            if pending_required: _fail('The report invents completion beyond an unfinished required step.')
            completed.append(row['id'])
        elif wanted['required']:
            pending_required = True
    available = 'mycel2_verified' if cutover else 'unverified'
    if not cutover:
        previous = next((row for row in plan['files'] + plan['preservedFiles'] if row['path'] == plan['previousCommand']), None)
        try:
            if previous is not None and _file_state(previous['path'], previous['kind']) == previous['sha256']:
                available = 'previous_command_present'
        except BuildError:
            pass
    return {'schemaVersion': 1, 'planSha256': fingerprint, 'complete': not pending_required,
            'partial': bool(completed or effects) and pending_required, 'steps': report['steps'],
            'completedPrefix': completed, 'observedEffects': effects, 'commandAvailability': available,
            'remaining': [x['id'] for x in report['steps'] if x['status'] != 'completed'],
            'ownerReplacementPerformedByValidator': False, 'databaseConnections': 0, 'shellFilesEdited': False}
