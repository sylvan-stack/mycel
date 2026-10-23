"""D38 inheritance verifies parsed exact files without renewing source pins."""

from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from psycopg.types.json import Jsonb

from mycel import _evidence as evidence
from mycel._code import chunk_code
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._locks import atomic_transaction
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
    @proves('MYC-13.15')
    def test_invalid_pin_options_refuse_before_guard_or_reread(self):
        inputs = fixtures.inputs()
        writer = evidence.EvidenceStore(object())
        valid = dict(dependency_id=uuid4(), kind='declared', declaration=inputs.resolution.declaration,
                     captured_at='2026-10-09T00:00:00Z', authorization='initial_resolution')
        for changed in ({'authorization': 'unknown'}, {'kind': 'unknown'}, {'declaration': 'changed'},
                        {'dependency_id': 'not-a-uuid'}, {'expected_owner': 'not-a-uuid'},
                        {'expected_owner': uuid4()}):
            with self.subTest(options=changed), patch.object(evidence, 'checked_input_guard',
                    side_effect=AssertionError('invalid options reached the guard')), self.assertRaises(evidence.EvidenceError):
                writer.pin(inputs, lambda: self.fail('invalid options reached reread'), **{**valid, **changed})

    @proves('MYC-13.15')
    def test_function_and_method_renames_keep_source_pin_and_exact_new_comparison(self):
        examples = (
            ('# prefix\ndef old(x):\n    return x + 1\n', '# prefix\ndef new(x):\n    return x + 1\n', 'old', 'new', 'answer.py'),
            ('class Box:\n    def old(self, x):\n        return x\n',
             'class Box:\n    def new(self, x):\n        return x\n', 'Box.old', 'Box.new', 'answer.py'),
            ('# préface\r\ndef ancien(é):\r\n    return é + 1\r\n',
             '# préface\r\ndef nouveau(é):\r\n    return é + 1\r\n', 'ancien', 'nouveau', 'answer.py'),
            ('function old(x: number): number { return x + 1; }\n',
             'function newName(x: number): number { return x + 1; }\n', 'old', 'newName', 'answer.ts'),
            ('function old(x) { return x + 1; }\n',
             'function newName(x) { return x + 1; }\n', 'old', 'newName', 'answer.js'),
        )
        for old, new, old_name, new_name, path in examples:
            with self.subTest(name=new_name, path=path):
                previous, current = pair(old, new, old_name, new_name, path=path)
                baseline = fixtures.capture(previous)
                inherited = evidence.inherit_baseline(baseline, current.dependant, current.dependant_file,
                    authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
                for key in ('members', 'source', 'pinnedHash', 'ref', 'location', 'capturedAt'):
                    self.assertEqual(inherited.manifest.payload[key], baseline.manifest.payload[key])
                self.assertNotEqual(inherited.manifest.payload['dependant']['hash'], baseline.manifest.payload['dependant']['hash'])
                self.assertEqual(inherited.manifest.payload['dependant']['comparison'],
                                 current.dependant.chunk.comparison)
                self.assertEqual(inherited.manifest.payload['dependantVersion'], str(current.dependant.chunk.version))

    @proves('MYC-13.15')
    def test_changed_signature_body_comment_or_line_endings_never_inherit(self):
        old = '# prefix\ndef old(x):\n    return x + 1\n'
        changes = ('# prefix\ndef new(y):\n    return x + 1\n',
                   '# prefix\ndef new(x):\n    return x + 2\n',
                   '# changed\ndef new(x):\n    return x + 1\n',
                   '# prefix\r\ndef new(x):\r\n    return x + 1\r\n')
        for new in changes:
            previous, current = pair(old, new)
            with self.subTest(source=new), self.assertRaises(evidence.EvidenceError):
                evidence.inherit_baseline(fixtures.capture(previous), current.dependant, current.dependant_file,
                    authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
        for path, old, new in (
                ('answer.ts', 'function old(x: number): number { return x + 1; }\n',
                 'function newName(x: number): number { return x + 2; }\n'),
                ('answer.js', 'function old(x) { return x + 1; }\n',
                 'function newName(x) { return x + 2; }\n')):
            previous, current = pair(old, new, 'old', 'newName', path=path)
            with self.subTest(path=path), self.assertRaises(evidence.EvidenceError):
                evidence.inherit_baseline(fixtures.capture(previous), current.dependant, current.dependant_file,
                    authorization='recognized_rename', previous_file_source=previous.dependant_file.source)

    @proves('MYC-13.15')
    def test_code_rename_requires_authorization_complete_old_file_and_fresh_parse_spans(self):
        previous, current = pair('# prefix\ndef old(x):\n    return x\n', '# prefix\ndef new(x):\n    return x\n')
        baseline = fixtures.capture(previous)
        for authorization, source in ((None, previous.dependant_file.source),
                ('normalized_equivalent_edit', previous.dependant_file.source),
                ('recognized_rename', None), ('recognized_rename', b'def old(x):\n    return x\n')):
            with self.subTest(authorization=authorization, missing=source is None), self.assertRaises(evidence.EvidenceError):
                evidence.inherit_baseline(baseline, current.dependant, current.dependant_file,
                    authorization=authorization, previous_file_source=source)
        raw = b'def new(x):\n    return x\n'
        forged = replace(current.dependant.chunk, source=raw, snapshot_hash=sha256(raw).hexdigest(),
            span=(len(b'# prefix\n'), len(current.dependant_file.source)),
            comparison=evidence.exact_comparison(raw, 'code_text').as_dict())
        with self.assertRaises(evidence.EvidenceError):
            evidence.inherit_baseline(baseline, replace(current.dependant, chunk=forged), current.dependant_file,
                authorization='recognized_rename', previous_file_source=previous.dependant_file.source)


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

    @proves('MYC-1.34', 'MYC-2.26', 'MYC-16.5', kind='store')
    def test_both_wrappers_preserve_code_rename_pin_with_new_exact_version(self):
        with self.connect() as connection:
            writer, previous, original, old, current = self.prepare(connection,
                '# préface\r\ndef ancien(é):\r\n    return é\r\n', '# préface\r\ndef nouveau(é):\r\n    return é\r\n',
                old_name='ancien', new_name='nouveau')
            baseline = writer.read_baseline('owner', original)
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            catalog = SourceResolver.from_store(connection, current.settings)
            selected = catalog.resolve(current.dependant.place.address, purpose='endpoint').selection
            current = evidence.InheritanceInputs(current.settings, selected.members[0], selected.file,
                current.location, catalog.resolve(current.resolution.declaration), catalog)
            for native in (False, True):
                identifier = uuid4()
                if native:
                    with evidence.checked_input_guard(connection, current, lambda: current) as token, atomic_transaction(connection):
                        inherited = writer.inherit_in_transaction(token, previous_dependency=previous,
                            dependency_id=identifier, authorization='recognized_rename')
                else:
                    inherited = writer.inherit_pin(current, lambda: current, previous_dependency=previous,
                        dependency_id=identifier, authorization='recognized_rename')
                result = writer.read_baseline('owner', inherited)
                self.assertEqual(result.manifest.payload['members'], baseline.manifest.payload['members'])
                self.assertEqual(result.manifest.payload['pinnedHash'], baseline.manifest.payload['pinnedHash'])
                self.assertEqual(result.manifest.payload['dependantVersion'], str(current.dependant.chunk.version))
                self.assertNotEqual(result.manifest.payload['dependant']['hash'], baseline.manifest.payload['dependant']['hash'])

    @proves('MYC-2.26', 'MYC-16.5', kind='store')
    def test_changed_code_refuses_without_writing_or_renewing_owner(self):
        with self.connect() as connection:
            writer, previous, original, _, current = self.prepare(connection, new='def new(x):\n    return x + 1\n')
            before = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone()
            for native in (False, True):
                with self.subTest(native=native), self.assertRaises(evidence.EvidenceError):
                    if native:
                        with evidence.checked_input_guard(connection, current, lambda: current) as token, atomic_transaction(connection):
                            writer.inherit_in_transaction(token, previous_dependency=previous,
                                dependency_id=uuid4(), authorization='recognized_rename')
                    else:
                        writer.inherit_pin(current, lambda: current, previous_dependency=previous,
                            dependency_id=uuid4(), authorization='recognized_rename')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone(), before)
            self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)

    @proves('MYC-16.5', kind='store')
    def test_prior_complete_file_lock_is_nonblocking_and_missing_file_is_not_substituted(self):
        with self.connect() as connection, self.connect() as blocker:
            writer, previous, original, old, current = self.prepare(connection)
            with blocker.transaction():
                blocker.execute('SELECT id FROM public.mycel_file_versions WHERE file_id=%s AND snapshot_hash=%s FOR UPDATE',
                                (old.dependant_file.identifier, old.dependant_file.snapshot_hash))
                with evidence.checked_input_guard(connection, current, lambda: current) as token:
                    with self.assertRaises(MycelError) as error, atomic_transaction(connection):
                        writer.inherit_in_transaction(token, previous_dependency=previous,
                            dependency_id=uuid4(), authorization='recognized_rename')
                self.assertEqual(error.exception.code.value, 'busy')
            connection.execute('DELETE FROM public.mycel_file_versions WHERE file_id=%s AND snapshot_hash=%s',
                               (old.dependant_file.identifier, old.dependant_file.snapshot_hash))
            with self.assertRaises(evidence.EvidenceError) as error:
                writer.inherit_pin(current, lambda: current, previous_dependency=previous,
                    dependency_id=uuid4(), authorization='recognized_rename')
            self.assertEqual(error.exception.status, 'baseline_missing')
            self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)
