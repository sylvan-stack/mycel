# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Inheritance keeps owned before-text even when the current source is absent."""

import json
import unittest
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from unittest.mock import patch
from uuid import UUID, uuid4

from mycel import _evidence as evidence
from mycel._resolver import SourceResolver
from mycel._settings import _freeze

try:
    from . import test_evidence as fixtures
except ImportError:
    import test_evidence as fixtures


def inherited_inputs(previous, *, disabled=False, body='Exact\tanswer.\n'):
    dep = fixtures.document('owner', 'answer.md', '# Renamed\n' + body, version=100,
                            identifier=previous.dependant.chunk.identifier)
    settings = previous.settings
    if disabled:
        settings = replace(settings, values=_freeze({'repos': {'owner': {'enabled': True},
                            'source': {'enabled': False}}, 'store': {}}))
    catalog = SourceResolver(settings, (dep,))
    resolution = catalog.resolve(previous.resolution.declaration)
    return evidence.InheritanceInputs(settings, fixtures.member(dep), dep, evidence.CaptureLocation('disk'),
                                      resolution, catalog, {'locationIdentity': 'disk'})


class InheritanceUnitTests(unittest.TestCase):
    def setUp(self):
        self.observed = fixtures.inputs()
        self.connection = fixtures.EvidenceConnection(self.observed)
        self.writer = evidence.EvidenceStore(self.connection)
        for target, context in (('checked_store', self.checked), ('operation_guard', self.operation),
                                ('read_snapshot', self.read)):
            patcher = patch.object(evidence, target, context)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.dependency = uuid4()
        baseline_id = self.writer.pin(self.observed, lambda: self.observed,
                       dependency_id=self.dependency, kind='declared', declaration=self.observed.resolution.declaration,
                       captured_at='2026-10-09T00:00:00Z', authorization='initial_resolution')
        self.original = self.writer.read_baseline('owner', baseline_id)

    @contextmanager
    def checked(self, connection):
        yield

    @contextmanager
    def operation(self, connection, repository, operation):
        connection.guards.append(repository)
        try:
            yield
        finally:
            connection.guards.remove(repository)

    @contextmanager
    def read(self, connection):
        yield

    def prepare(self, current):
        file, chunk = current.dependant_file, current.dependant.chunk
        self.connection.files[(file.identifier, file.snapshot_hash)] = (file.repository, file.source)
        self.connection.versions[chunk.version] = (chunk.version, UUID(chunk.identifier), file.repository,
                                      UUID(file.identifier), chunk.snapshot_hash, chunk.source, dict(chunk.comparison))
        self.connection.files.pop((self.observed.selection.file.identifier, self.observed.selection.file.snapshot_hash), None)
        self.connection.versions.pop(self.observed.selection.members[0].chunk.version, None)

    def inherit(self, current, *, reread=None):
        return self.writer.inherit_pin(current, reread or (lambda: current), previous_dependency=self.dependency,
                         dependency_id=uuid4(), authorization='normalized_equivalent_edit')


    def damage_prior(self, kind):
        previous = self.connection.dependencies[self.dependency]
        if kind.startswith('owner_'):
            key = next(key for key,value in self.connection.owners.items() if value == previous[5])
            value = self.connection.owners.pop(key)
            position = {'owner_repository':0,'owner_kind':1,'owner_identity':2}[kind]
            fields = list(key); fields[position] = 'incorrect'
            self.connection.owners[tuple(fields)] = value
        elif kind.startswith('refs_'):
            key = (previous[5],previous[0]); refs = list(self.connection.refs[key])
            if kind == 'refs_missing': refs = refs[:1]
            elif kind == 'refs_wrong_ordinal': refs[1] = (99,*refs[1][1:])
            elif kind == 'refs_extra': refs.append((len(refs),refs[1][1],None))
            self.connection.refs[key] = refs
        else:
            row = list(self.connection.versions[previous[1]])
            if kind == 'version_identity': row[1] = uuid4()
            elif kind == 'version_owner': row[2] = 'source'
            elif kind == 'version_hash': row[4] = '0'*64
            elif kind == 'version_bytes':
                row[5] = b'# Answer\nDifferent retained version body.\n'
                row[4] = sha256(row[5]).hexdigest()
                row[6] = dict(evidence.document_comparisons('Different retained version body.\n','Answer'))
            elif kind == 'version_comparison':
                row[6] = json.loads(evidence.canonical_json(row[6]))
                row[6]['body']['hash'] = '0'*64
            self.connection.versions[previous[1]] = tuple(row)


class InheritanceStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
