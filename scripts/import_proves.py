"""Prepare the legacy @proves import; apply it to a disposable or the named owner store.

The owner allowed one owner-store import on 23 October 2026 (SYL-261): the plan
must be frozen from the clone and specifications the settings index for the
repository, and the operator names the owner's database. This script never
initializes, ingests or embeds. Plans and receipts belong outside the source
checkout and artifact corpus.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

from mycel._coverage import KINDS, require_check_database
from mycel._errors import MycelError
from mycel._markdown import split_markdown
from mycel._source_refs import format_entity_uri
from mycel._verification import _identity, _time


def source_files(root):
    """Bind every nonignored source input, including new tests before commit."""
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z',
                                   '--cached', '--others', '--exclude-standard'])
    names = sorted(set(raw.decode('utf-8').split('\0')) - {''})
    if not names:
        raise ValueError('The import requires a nonempty source checkout.')
    result = {}
    for name in names:
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('The frozen source has a missing or unsafe input: ' + name)
        result[name] = sha256(path.read_bytes()).hexdigest()
    return result


def requirement_rows(specifications):
    files, rows, uuids = {}, {}, set()
    for path in sorted(specifications.glob('[0-9][0-9]-*.md')):
        raw = path.read_bytes()
        files[path.name] = sha256(raw).hexdigest()
        document = split_markdown(raw)
        if any(fault.code.startswith('entity_') for fault in document.diagnostics):
            raise ValueError('Normalize every entity row before importing: ' + path.name)
        for row in document.entities:
            if row.uuid in uuids:
                raise ValueError('The specifications repeat an entity UUID.')
            uuids.add(row.uuid)
            if row.kind == 'req':
                if row.id in rows:
                    raise ValueError('The specifications repeat a requirement ID.')
                rows[row.id] = {'uuid': row.uuid, 'title': row.title, 'kind': row.verified_by}
    if not files or not rows:
        raise ValueError('The import requires normalized specification chapters.')
    return files, rows


def declarations(root):
    """Read literal decorators without importing or executing a test module.

    Inherited methods name the defining symbol once. Local fixture functions
    inside test methods are deliberately outside this inventory.
    """
    result = []
    for path in sorted((root / 'tests').glob('test_*.py')):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        aliases = {alias.asname or alias.name for node in tree.body
                   if isinstance(node, ast.ImportFrom) and node.module == 'mycel._coverage'
                   for alias in node.names if alias.name == 'proves'}
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for method in cls.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or not method.name.startswith('test_'):
                    continue
                decorators = [node for node in method.decorator_list if isinstance(node, ast.Call)
                              and isinstance(node.func, ast.Name) and node.func.id in aliases]
                if not decorators:
                    continue
                if len(decorators) != 1:
                    raise ValueError('A test repeats its proof declaration.')
                call, = decorators
                try:
                    requirements = [ast.literal_eval(node) for node in call.args]
                    if len(call.keywords) > 1 or any(node.arg != 'kind' for node in call.keywords):
                        raise ValueError()
                    kind = ast.literal_eval(call.keywords[0].value) if call.keywords else 'unit'
                    if kind not in KINDS or not requirements or any(not isinstance(item, str) for item in requirements):
                        raise ValueError()
                    if len(set(requirements)) != len(requirements):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ValueError('A proof declaration is not a literal requirement list and check kind.') from None
                result.append({'file': path.relative_to(root).as_posix(),
                               'symbol': cls.name + '.' + method.name,
                               'kind': kind, 'requirements': requirements})
    if not result or len({(row['file'], row['symbol']) for row in result}) != len(result):
        raise ValueError('The import requires distinct decorated test symbols.')
    return result


def make_plan(root, specifications, *, repository, by, when):
    root, specifications = Path(root).resolve(), Path(specifications).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', repository):
        raise ValueError('The repository code is invalid.')
    _identity(by)
    _time(when)
    files = source_files(root)
    spec_files, requirements = requirement_rows(specifications)
    checks = declarations(root)
    pairs = []
    for check in checks:
        for identifier in check['requirements']:
            if identifier not in requirements:
                raise ValueError('A declaration names an unknown requirement: ' + identifier)
            row = requirements[identifier]
            if row['kind'] != check['kind']:
                raise ValueError('A declaration has the wrong check kind: ' + identifier)
            pairs.append({'chunk': repository + ':@code/' + check['file'] + '#' + check['symbol'],
                          'origin': format_entity_uri('req', row['uuid'], row['title'], repository)})
    # A second read refuses a mixed source/specification capture.
    if files != source_files(root) or spec_files != requirement_rows(specifications)[0]:
        raise ValueError('The import inputs changed while preparing the plan.')
    return {'schemaVersion': 1, 'repository': repository, 'sourceRoot': str(root),
            'specificationsRoot': str(specifications), 'files': files, 'specifications': spec_files,
            'by': by, 'when': when, 'declarations': checks, 'pairs': pairs}


def validate_plan(plan):
    try:
        if type(plan['schemaVersion']) is not int or plan['schemaVersion'] != 1:
            raise ValueError()
        actual = make_plan(plan['sourceRoot'], plan['specificationsRoot'],
                           repository=plan['repository'], by=plan['by'], when=plan['when'])
        if actual != plan:
            raise ValueError()
    except (KeyError, TypeError, OSError, ValueError, subprocess.SubprocessError):
        raise MycelError('invalid_input', 'The frozen legacy import does not match its complete current inputs.') from None


def apply_disposable(connection, settings, plan):
    """No owner override exists; even credential access follows target refusal."""
    from mycel._justify import JustifyStore
    address = settings.values['store']['address']
    database = require_check_database(unquote(urlsplit(address).path).removeprefix('/'))
    validate_plan(plan)
    if connection.execute('SELECT current_database()').fetchone()[0] != database:
        raise MycelError('invalid_input', 'The disposable connection names another database.')
    return JustifyStore(connection).import_proven_pairs(settings,
        [(row['chunk'], row['origin']) for row in plan['pairs']],
        by=plan['by'], captured_at=plan['when'], validate_inputs=lambda: validate_plan(plan))


def apply_owner(connection, settings, plan, *, owner_database):
    """The owner's single authorized import; the plan must name the indexed clone."""
    from mycel._justify import JustifyStore
    database = unquote(urlsplit(settings.values['store']['address']).path).removeprefix('/')
    if not owner_database or database != owner_database:
        raise ValueError('The settings must name the owner database given by --owner-store.')
    try:
        require_check_database(database)
    except ValueError:
        pass
    else:
        raise ValueError('A mycel_check_ database is disposable; use apply-disposable.')
    repository = settings.values['repos'].get(plan['repository'])
    if (not repository or not repository.get('enabled')
            or Path(repository['code_root']).resolve() != Path(plan['sourceRoot'])
            or Path(repository['artifact_root']).resolve() / 'specs' != Path(plan['specificationsRoot'])):
        raise ValueError('The plan must be frozen from the indexed code root and its specifications.')
    validate_plan(plan)
    if connection.execute('SELECT current_database()').fetchone()[0] != database:
        raise MycelError('invalid_input', 'The owner connection names another database.')
    return JustifyStore(connection).import_proven_pairs(settings,
        [(row['chunk'], row['origin']) for row in plan['pairs']],
        by=plan['by'], captured_at=plan['when'], validate_inputs=lambda: validate_plan(plan))


def write_private(path, value, plan):
    path = Path(path).expanduser().resolve()
    if any(path.is_relative_to(Path(plan[key])) for key in ('sourceRoot', 'specificationsRoot')):
        raise ValueError('Keep import plans and receipts outside the source and artifact corpus.')
    # The artifact root normally contains specs/, so reject its parent too.
    if path.is_relative_to(Path(plan['specificationsRoot']).parent):
        raise ValueError('Keep import plans and receipts outside the artifact corpus.')
    with path.open('x', encoding='utf-8') as output:
        output.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--specifications', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--repo', default='mycel')
    prepare.add_argument('--by', default=None)
    prepare.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1],
                         help='the clone to freeze; for the owner import, the indexed code root')
    for name in ('apply-disposable', 'apply-owner'):
        apply = sub.add_parser(name)
        apply.add_argument('--plan', type=Path, required=True)
        apply.add_argument('--plan-sha256', required=True)
        apply.add_argument('--settings', type=Path, required=True)
        apply.add_argument('--receipt', type=Path, required=True)
        if name == 'apply-owner':
            apply.add_argument('--owner-store', required=True,
                               help="the owner's database name, stated by the operator")
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            plan = make_plan(args.source, args.specifications,
                             repository=args.repo, by=_identity(args.by),
                             when=datetime.now(timezone.utc).isoformat(timespec='microseconds'))
            write_private(args.output, plan, plan)
            print(json.dumps({'declarations': len(plan['declarations']), 'pairs': len(plan['pairs']),
                              'planSha256': sha256(args.output.read_bytes()).hexdigest()}))
            return 0
        raw = args.plan.read_bytes()
        if sha256(raw).hexdigest() != args.plan_sha256:
            raise ValueError('The selected import plan hash differs.')
        plan = json.loads(raw)
        validate_plan(plan)
        from mycel._settings import load_settings
        from mycel._credentials import Credentials
        from mycel._database import store_connection
        from mycel._safeguards import InvocationPolicy
        settings = load_settings(path=args.settings)
        settings.require_valid()
        owner = args.command == 'apply-owner'
        if not owner:
            require_check_database(unquote(urlsplit(settings.values['store']['address']).path).removeprefix('/'))
        if args.receipt.exists():
            raise ValueError('The receipt already exists; retain and inspect it before retrying.')
        # Validate destination before connecting or mutating.
        receipt_parent = args.receipt.resolve()
        if any(receipt_parent.is_relative_to(Path(plan[key])) for key in ('sourceRoot', 'specificationsRoot')) or receipt_parent.is_relative_to(Path(plan['specificationsRoot']).parent):
            raise ValueError('Keep receipts outside the source and artifact corpus.')
        with store_connection(Credentials(settings, InvocationPolicy('justify'))) as connection:
            replies = (apply_owner(connection, settings, plan, owner_database=args.owner_store)
                       if owner else apply_disposable(connection, settings, plan))
        write_private(args.receipt, {'planSha256': args.plan_sha256, 'justifications': replies}, plan)
        print(json.dumps({'imported': len(replies), 'receipt': str(args.receipt)}))
        return 0
    except (MycelError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
