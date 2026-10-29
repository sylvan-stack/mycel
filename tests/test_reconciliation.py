# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Dependency decisions only; all SYL-111 store acceptance remains unclaimed."""
from dataclasses import FrozenInstanceError, replace
from itertools import permutations

from mycel._reconciliation import (AssertedRemoval, BaselineFault, DependencyRecord,
    DependencyRequest, GraphEdge, ReconciliationError, plan_dependencies)

import unittest
from hashlib import sha256
from pathlib import Path

from mycel._code import chunk_code
from mycel._evidence import (
    CaptureLocation,
    capture_baseline,
    document_comparisons,
    exact_comparison,
)
from mycel._markdown import split_markdown
from mycel._reconciliation import DependencyRecord, plan_dependencies
from mycel._resolver import ResolvedChunk, ResolvedFile, SelectionMember, SourceResolver
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress


def settings(*, enabled=True, registered=True):
    repos = {'owner': {'enabled': True}}
    if registered:
        repos['source'] = {'enabled': enabled}
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({'repos': repos, 'store': {}}), True, True)


def document(repo, path, text, *, version=1, identifier=None):
    parsed = split_markdown(text)
    place = SourceAddress(repo, 'artifact', path)
    chunks = tuple(ResolvedChunk(identifier or f'{repo}:{path}:{index}', version + index,
        chunk.name, 'document', chunk.text.encode(), chunk.snapshot_hash,
        (chunk.span.byte_start, chunk.span.byte_end), chunk.title, None,
        document_comparisons(chunk.body, chunk.title or ''), chunk.body.encode(),
        (len(chunk.text.encode()) - len(chunk.body.encode()), len(chunk.text.encode())))
        for index, chunk in enumerate(parsed.chunks))
    return ResolvedFile(f'file:{repo}:{path}', repo, place, (place,), parsed.source, parsed.file_hash, chunks)


def code(text):
    raw = text.encode()
    place = SourceAddress('source', 'code', 'code.py')
    chunks = []
    for index, item in enumerate(chunk_code('code.py', text)):
        start = raw.find(item.text.encode())
        chunks.append(ResolvedChunk('code:' + item.symbol, index + 1, item.symbol, item.kind, item.text.encode(),
            sha256(item.text.encode()).hexdigest(), (start, start + len(item.text.encode())), None, item.symbol.rsplit('.', 1)[0] if '.' in item.symbol else item.symbol,
            exact_comparison(item.text.encode(), 'code_text').as_dict()))
    return ResolvedFile('code-file', 'source', place, (place,), raw, sha256(raw).hexdigest(), tuple(chunks))


def member(file, index=0):
    chunk = file.chunks[index]
    return SelectionMember(SourceAddress(file.repository, file.primary.root, file.primary.path, chunk.name), chunk)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.dep = document('owner', 'answer.md', '# Answer\nAnswer body.\n', identifier='answer')
        self.src = document('source', 'source.md', '# Source\nOld source.\n', identifier='source-chunk')
        self.declaration = 'source:source.md#Source'

    def resolver(self, source=None, *, enabled=True, registered=True):
        files = (self.dep,) + (() if source is None else (source,))
        return SourceResolver(settings(enabled=enabled, registered=registered), files)

    def record(self, identifier='declared-link', kind='declared', *, source=None, declaration=None):
        source = self.src if source is None else source
        declaration = self.declaration if declaration is None else declaration
        selected = self.resolver(source).resolve(declaration).selection
        manifest = capture_baseline('owner', member(self.dep), self.dep, selected, kind=kind,
            declaration=declaration, captured_at='2026-10-09T00:00:00Z', location=CaptureLocation('disk')).manifest
        return DependencyRecord(identifier, manifest)

    def plan(self, requests=(), existing=(), *, source=None, **kwargs):
        return plan_dependencies(member(self.dep), self.resolver(source), tuple(requests), tuple(existing),
            pin_version=kwargs.pop('pin_version', self.dep.chunks[0].version), **kwargs)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
