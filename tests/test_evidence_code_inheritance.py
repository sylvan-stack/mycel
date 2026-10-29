# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""D38 inheritance verifies parsed exact files without renewing source pins."""

import json
import unittest
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from mycel import _evidence as evidence
from mycel._code import chunk_code
from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from mycel._source_refs import SourceAddress

try:
    from . import test_evidence as fixtures
except ImportError:
    import test_evidence as fixtures


def code_file(source, name, *, version=1, identifier=None, path='answer.py'):
    primary = SourceAddress('owner', 'code', path)
    parsed = chunk_code(primary.path, source)
    chunks = tuple(ResolvedChunk(
        identifier if item.symbol == name and identifier is not None else str(uuid5(NAMESPACE_URL, 'code:' + item.symbol)),
        version + number, item.symbol, item.kind, item.text.encode(), sha256(item.text.encode()).hexdigest(),
        (item.byte_start, item.byte_end), family=item.symbol.rsplit('.', 1)[0] if '.' in item.symbol else None,
        comparison=evidence.exact_comparison(item.text.encode(), 'code_text').as_dict())
        for number, item in enumerate(parsed))
    raw = source.encode()
    return ResolvedFile(str(uuid5(NAMESPACE_URL, 'code-file')), 'owner', primary, (primary,),
                        raw, sha256(raw).hexdigest(), chunks)


def observed(file, name, source=None):
    source = source or fixtures.document('source', 'source.md', '# Source\nOriginal source.\n', version=20)
    catalog = SourceResolver(fixtures.settings(), (file, source))
    dependant = catalog.resolve(file.primary.address + '#' + name, purpose='endpoint').selection.members[0]
    resolution = catalog.resolve('source:source.md#Source')
    return evidence.PinInputs(catalog.settings, dependant, file, resolution.selection,
                              evidence.CaptureLocation('disk'), resolution, catalog)


def pair(old, new, old_name='old', new_name='new', *, path='answer.py'):
    previous = observed(code_file(old, old_name, path=path), old_name)
    current_file = code_file(new, new_name, version=100, identifier=previous.dependant.chunk.identifier, path=path)
    current = observed(current_file, new_name)
    return previous, current


class CodeInheritanceUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class CodeInheritanceStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def seed(self, connection, inputs):
        for file in (inputs.dependant_file, inputs.selection.file):
            connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                               (file.repository, Jsonb([])))
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (UUID(file.identifier), file.repository, file.primary.root, file.primary.path,
                 'documents' if file.primary.root == 'artifact' else 'code'))
            connection.execute('DELETE FROM public.mycel_file_locations WHERE file_version IN '
                               '(SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', (file.identifier,))
            version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT(file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
                (uuid4(), file.identifier, file.snapshot_hash, file.source, Jsonb({}))).fetchone()[0]
            location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
                                         (uuid4(), version, 'disk', 'disk', Jsonb({}))).fetchone()[0]
            for chunk in file.chunks:
                connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (chunk.identifier, file.repository, file.identifier, chunk.kind, Jsonb({})))
                metadata = {'name': chunk.name, 'kind': chunk.kind, 'family': chunk.family,
                            'span': {'start': chunk.span[0], 'end': chunk.span[1]}}
                if chunk.kind == 'document':
                    metadata.update({'title': chunk.title, 'bodySpan': {'start': chunk.body_span[0], 'end': chunk.body_span[1]}})
                number = connection.execute('INSERT INTO public.mycel_chunk_versions '
                    '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
                    'ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
                    (chunk.identifier, chunk.snapshot_hash, chunk.source, chunk.source.decode(),
                     Jsonb(json.loads(evidence.canonical_json(chunk.comparison))), Jsonb(metadata))).fetchone()[0]
                connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                                   (uuid4(), number, location, 'disk', 'disk', Jsonb(metadata)))
        catalog = SourceResolver.from_store(connection, inputs.settings)
        selected = catalog.resolve(inputs.dependant.place.address, purpose='endpoint').selection
        resolution = catalog.resolve(inputs.resolution.declaration)
        return evidence.PinInputs(inputs.settings, selected.members[0], selected.file, resolution.selection,
                                  inputs.location, resolution, catalog)

    def prepare(self, connection, old='def old(x):\n    return x\n', new='def new(x):\n    return x\n', *, old_name='old', new_name='new'):
        previous, current = pair(old, new, old_name, new_name)
        previous = self.seed(connection, previous)
        writer, dependency = evidence.EvidenceStore(connection), uuid4()
        baseline = fixtures.EvidenceStoreTests().pin(writer, previous, dependency=dependency)
        current = self.seed(connection, current)
        return writer, dependency, baseline, previous, current


# Archived complete imports; restore needed names in their original scope, not at this file tail.
