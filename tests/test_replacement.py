# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Disposable filesystem/finite-catalog rehearsals, never an owner cutover or PG proof."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import tempfile
from contextlib import redirect_stdout
from unittest.mock import patch

from mycel_build._core import BuildError
from mycel_build.__main__ import main

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mycel_build._replacement import replacement_plan, validate_replacement_report

AT = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)
STAMP = AT.isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


def binding(path):
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


class Fixture:
    """Synthetic operator evidence and catalog, with actual private file effects."""
    def __init__(self, root):
        self.root = root
        self.old = root / 'old/mycel'; self.old.parent.mkdir(); self.old.write_bytes(b'fixture Mycel 1 runtime\n')
        self.link = root / 'old/better-grep'; self.link.symlink_to('mycel')
        self.new = root / 'new/mycel'
        self.corpus = root / 'source/document.md'; self.corpus.parent.mkdir(); self.corpus.write_bytes(b'Keep exact source evidence.\n')
        self.unrelated = root / 'unrelated.bin'; self.unrelated.write_bytes(b'Keep unrelated bytes.\n')
        self.shell = root / '.shellrc'; self.shell.write_text("export KEEP=one\nalias mycel='old/mycel'\nalias better-grep='old/better-grep'\n# retained tail\n")
        self.basis = write(root / 'evidence/legacy-release-observation.json', {'fixtureOnly': True,
            'fact': 'Disposable Mycel 1 release-file and source-table ownership observation; no owner inventory.'})
        self.table = {'schema': 'legacy', 'name': 'kn_nodes', 'kind': 'table', 'oid': 100,
                      'definitionSha256': sha(b'fixture table definition')}
        self.index = {'schema': 'legacy', 'name': 'kn_nodes_pkey', 'kind': 'index', 'oid': 101,
                      'definitionSha256': sha(b'fixture index definition')}
        self.other = {'schema': 'legacy', 'name': 'kn_unrelated', 'kind': 'table', 'oid': 102,
                      'definitionSha256': sha(b'unrelated table definition')}
        self.catalog = {'schemaVersion': 1, 'observedAt': STAMP, 'database': 'fixture-server/old-shared',
                        'objects': [self.table, self.index, self.other], 'dependencies': [
                            {'owner': {'schema': 'legacy', 'name': 'kn_nodes'},
                             'dependent': {'schema': 'legacy', 'name': 'kn_nodes_pkey'}, 'automatic': True}]}
        self.catalog_binding = write(root / 'evidence/catalog-before.json', self.catalog)
        files = []
        for name, path, kind in [('runtime', self.old, 'file'), ('grep-link', self.link, 'symlink')]:
            row = {'id': name, 'path': str(path), 'role': 'runtime', 'kind': kind,
                   'sha256': sha(path.read_bytes()) if kind == 'file' else sha(b'mycel'),
                   'ownership': None, 'uncertainty': None}
            row['ownership'] = self.evidence(name, {k: row[k] for k in ('path', 'role', 'kind', 'sha256')})
            files.append(row)
        for name, path, role in [('source', self.corpus, 'document_corpus'), ('unrelated', self.unrelated, 'unrelated')]:
            files.append({'id': name, 'path': str(path), 'role': role, 'kind': 'file',
                          'sha256': sha(path.read_bytes()), 'ownership': None, 'uncertainty': None})
        aliases = []
        for name, definition in [('mycel', "alias mycel='old/mycel'"), ('better-grep', "alias better-grep='old/better-grep'")]:
            row = {'id': name, 'name': name, 'sourceFile': str(self.shell), 'definition': definition,
                   'sourceSha256': sha(self.shell.read_bytes()), 'ownership': None, 'uncertainty': None}
            row['ownership'] = self.evidence('alias-' + name, {k: row[k] for k in ('name', 'sourceFile', 'definition', 'sourceSha256')})
            aliases.append(row)
        table = {k: self.table[k] for k in ('schema', 'name', 'oid', 'definitionSha256')}
        table.update(ownedDependents=[{'schema': 'legacy', 'name': 'kn_nodes_pkey'}], uncertainty=None,
                     ownership=self.evidence('table', {'database': self.catalog['database'], 'table': self.table,
                                                      'ownedDependents': [self.index]}))
        self.inventory = {'schemaVersion': 1, 'observedAt': STAMP,
            'oldDatabase': {'identity': self.catalog['database'], 'catalog': self.catalog_binding},
            'newDatabase': 'fixture-server/new-private', 'previousCommand': str(self.old),
            'newCommand': str(self.new), 'files': files, 'aliases': aliases, 'tables': [table],
            'paidOperationsRequested': False}
        self.inventory_path = root / 'inventory.json'; self.save()
        self.sequence = 0

    def evidence(self, name, subject):
        return write(self.root / ('evidence/' + name + '.json'), {'schemaVersion': 1, 'observedAt': STAMP,
            'product': 'mycel1', 'subject': subject,
            'basis': [{'artifact': self.basis, 'locator': 'fixture fact', 'finding': 'Exact disposable object matches the retained observation.'}]})

    def save(self):
        write(self.inventory_path, self.inventory)

    def compile(self):
        self.save(); result = replacement_plan(self.inventory_path, now=AT)
        self.plan, self.report = result['plan'], result['report']
        self.plan_path = self.root / 'plan.json'; write(self.plan_path, self.plan)
        self.plan_sha = sha(self.plan_path.read_bytes())
        return result

    def validate(self):
        path = self.root / 'report.json'; write(path, self.report)
        return validate_replacement_report(self.plan_path, path, expected_plan_sha256=self.plan_sha, now=AT)

    def catalog_after(self):
        return {**self.catalog, 'objects': [self.other], 'dependencies': []}

    def observe(self, step, status, facts):
        self.sequence += 1
        receipt = write(self.root / f'evidence/step-{self.sequence}.json', {'schemaVersion': 1,
            'planSha256': self.plan['sha256'], 'step': step, 'status': status, 'observedAt': STAMP, 'facts': facts})
        next(row for row in self.report['steps'] if row['id'] == step).update(status=status, verification=receipt)

    def action(self, step):
        """Finite rehearsal effects; this executor is test-owned and not a PG driver."""
        if step == 'inventory_review':
            return {'inventorySha256': self.plan['inventory']['sha256'], 'uncertainObjects': [], 'reviewedBasis': self.plan['ownershipEvidence']}
        if step == 'qualification_and_launcher':
            self.new.parent.mkdir(exist_ok=True); self.new.write_bytes(b'fixture Mycel 2 launcher')
            working = write(self.root / 'evidence/working-build-fixture.json', {'status': 'working', 'automaticQualification': True,
                'fixtureOnly': True, 'notPinnedDistributionQualification': True})
            return {'workingBuild': working, 'launcher': str(self.new)}
        if step == 'new_private_store':
            return {'database': self.plan['newDatabase'], 'initExitCode': 0, 'localIngestExitCode': 0,
                    'nonpaidChecksExitCode': 0, 'copiedVersion1State': []}
        if step == 'command_cutover':
            return {'command': str(self.new), 'database': self.plan['newDatabase'], 'infoExitCode': 0, 'cutoverCommitted': True}
        if step.startswith('remove_file:'):
            target = next(x for x in self.plan['files'] if step == 'remove_file:' + x['id'])
            Path(target['path']).unlink()
            return {'path': target['path'], 'beforeSha256': target['sha256'], 'after': 'absent'}
        if step.startswith('remove_alias:'):
            target = self.plan['aliases'][0]; definitions = set(target['definitions'])
            self.shell.write_text(''.join(line for line in self.shell.read_text().splitlines(True) if line.rstrip('\r\n') not in definitions))
            return {'sourceFile': str(self.shell), 'beforeSha256': target['sourceSha256'], 'editCommitted': True}
        if step == 'remove_old_tables':
            # A finite catalog transaction removes only the exact target+owned index.
            after = write(self.root / 'evidence/catalog-after.json', self.catalog_after())
            return {'removedTables': [{'schema': 'legacy', 'name': 'kn_nodes'}], 'restrict': True,
                    'transactionCommitted': True, 'catalogAfter': after}
        if step == 'verify_survivors':
            return {'catalogAfter': write(self.root / 'evidence/catalog-final.json', self.catalog_after()),
                    'unrelatedObjectsVerified': True, 'sourceCorporaVerified': True}
        raise AssertionError('The unit fixture cannot execute another operation.')


class ReplacementTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
