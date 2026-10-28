"""Configured real-store proofs for retained declarations and physical bindings."""
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import CapturedFile
from mycel._declared_refs import DeclaredRefStore
from mycel._evidence import canonical_json, document_comparisons
from mycel._markdown import split_markdown
from mycel._settings import SettingsSnapshot, _freeze, load_settings
from mycel._source_refs import read_document_declarations
from mycel._store import search_text


def settings(**enabled):
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({
        'repos': {name: {'enabled': value} for name, value in enabled.items()}, 'store': {}}), True, True)


def seed_document(connection, repository, path, source, *, root='artifact', kind='disk', location='disk',
                  file_id=None, chunk_ids=None):
    parsed = split_markdown(source)
    file_id = file_id or uuid4()
    connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                       (repository, Jsonb([])))
    connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                       (file_id, repository, root, path, 'documents'))
    file_version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
        'ON CONFLICT(file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
        (uuid4(), file_id, parsed.file_hash, parsed.source, Jsonb({}))).fetchone()[0]
    file_location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
        (uuid4(), file_version, kind, location, Jsonb({}))).fetchone()[0]
    ids, versions = [], []
    for index, chunk in enumerate(parsed.chunks):
        chunk_id = chunk_ids[index] if chunk_ids else uuid4()
        ids.append(chunk_id)
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (chunk_id, repository, file_id, 'document', Jsonb({})))
        raw = chunk.text.encode()
        metadata = {'name': chunk.name, 'kind': 'document', 'title': chunk.title,
                    'span': {'start': chunk.span.byte_start, 'end': chunk.span.byte_end},
                    'bodySpan': {'start': len(raw) - len(chunk.body.encode()), 'end': len(raw)}}
        version = connection.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
            'ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
            (chunk_id, chunk.snapshot_hash, raw, search_text(raw), Jsonb(json.loads(canonical_json(document_comparisons(chunk.body, chunk.title or '')))),
             Jsonb(metadata))).fetchone()[0]
        versions.append(version)
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                           (uuid4(), version, file_location, kind, location, Jsonb(metadata)))
    return str(file_location), file_id, tuple(ids), tuple(versions)


def retain(connection, snapshot, location, source):
    return DeclaredRefStore(connection).retain(snapshot, location,
        read_document_declarations(split_markdown(source), file='answer.md'))


class DeclaredRefStoreTests(unittest.TestCase):
    check_kind = "store"

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::DeclaredRefStoreTests.test_every_fault_and_exact_malformed_spelling_survives_reply_and_listing
#     def test_every_fault_and_exact_malformed_spelling_survives_reply_and_listing(self):
#         source = ('---\nsources: ["malformed\\0ref"]\n---\n# Answer\n<!-- sources:\n'
#                   'not a ref\nunknown:path\ndisabled:path\nsource:missing.md\n'
#                   'source:collision.md#Same\nsource:headings.md#Same\n-->\n')
#         snapshot = settings(owner=True, source=True, disabled=False)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             location, _, _, _ = seed_document(c, 'owner', 'answer.md', source)
#             seed_document(c, 'source', 'collision.md', '# Same\n', root='artifact')
#             seed_document(c, 'source', 'collision.md', '# Same\n', root='code')
#             seed_document(c, 'source', 'headings.md', '# One\n## Same\n# Two\n## Same\n')
#             identifiers = retain(c, snapshot, location, source)
#             reply = DeclaredRefStore(c).recheck(snapshot, repository='owner')
#             self.assertEqual((reply.checked, len(reply.faults)), (7, 7))
#             self.assertEqual(len(identifiers), 7)
#             self.assertEqual({ref.fault for ref in reply.faults},
#                 {'not_a_ref', 'unregistered_repository', 'disabled_repository', 'missing_file', 'ambiguous_path', 'ambiguous_name'})
#             self.assertIn('malformed\0ref', {ref.declaration for ref in reply.faults})
#             ambiguity = next(ref for ref in reply.faults if ref.fault == 'ambiguous_path')
#             self.assertEqual(ambiguity.candidates, ('source:@artifact/collision.md', 'source:@code/collision.md'))
#             self.assertEqual(ambiguity.candidate_count, 2)
#             self.assertEqual(DeclaredRefStore(c).list(repository='owner', faults_only=True), reply.refs)
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_ref_faults').fetchone()[0], 7)
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::DeclaredRefStoreTests.test_every_fault_and_exact_malformed_spelling_survives_reply_and_listing

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::DeclaredRefStoreTests.test_origin_target_and_settings_passes_retry_and_deactivate_without_repin
#     def test_origin_target_and_settings_passes_retry_and_deactivate_without_repin(self):
#         source = '# Answer\n<!-- sources:\nsource:guide.md#Source\n-->\n'
#         snapshot = settings(owner=True, source=True)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             location, _, _, versions = seed_document(c, 'owner', 'answer.md', source)
#             identifier = retain(c, snapshot, location, source)[0]
#             first = DeclaredRefStore(c).recheck(snapshot, repository='owner')
#             self.assertEqual(first.refs[0].fault, 'missing_file')
#             self.assertEqual(first.refs[0].source_state, 'unresolved')
#             _, source_file, _, target = seed_document(c, 'source', 'guide.md', '# Source\nComplete source.\n')
#             resolved = DeclaredRefStore(c).recheck(snapshot, repository='source')
#             self.assertEqual((resolved.refs[0].state, resolved.refs[0].baseline_status), ('resolved', 'baseline_missing'))
#             self.assertEqual(c.execute('SELECT source_version FROM public.mycel_edges WHERE dependency=%s', (identifier,)).fetchone()[0], target[0])
#             assertion = uuid4()
#             c.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
#                       (assertion, 'owner', versions[0], 'source:guide.md', 'source:@artifact/guide.md', 'asserted', Jsonb({})))
#             c.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (assertion, target[0]))
#             disabled = DeclaredRefStore(c).recheck(settings(owner=True, source=False), repository='owner')
#             self.assertEqual(disabled.refs[0].fault, 'disabled_repository')
#             self.assertIsNone(c.execute('SELECT 1 FROM public.mycel_edges WHERE dependency=%s', (identifier,)).fetchone())
#             self.assertIsNotNone(c.execute('SELECT 1 FROM public.mycel_edges WHERE dependency=%s', (assertion,)).fetchone())
#             restored = DeclaredRefStore(c).recheck(snapshot, repository='source')
#             self.assertEqual(restored.refs[0].identifier, identifier)
#             self.assertEqual(restored.refs[0].state, 'resolved')
#             self.assertEqual(DeclaredRefStore(c).recheck(snapshot, repository='owner').changed, 0)
#             c.execute('DELETE FROM public.mycel_files WHERE id=%s', (source_file,))
#             missing = DeclaredRefStore(c).recheck(snapshot, repository='source')
#             self.assertEqual((missing.refs[0].fault, missing.refs[0].source_state), ('missing_file', 'source_removed'))
#             self.assertIsNone(c.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0])
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::DeclaredRefStoreTests.test_origin_target_and_settings_passes_retry_and_deactivate_without_repin

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::DeclaredRefStoreTests.test_settings_registration_and_new_colliding_file_recheck_previous_selections
#     def test_settings_registration_and_new_colliding_file_recheck_previous_selections(self):
#         source = '# Answer\n<!-- sources:\nnew:guide.md#Source\n-->\n'
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             location, _, _, _ = seed_document(c, 'owner', 'answer.md', source)
#             retain(c, settings(owner=True), location, source)
#             self.assertEqual(DeclaredRefStore(c).recheck(settings(owner=True), repository='owner').refs[0].fault,
#                              'unregistered_repository')
#             seed_document(c, 'new', 'guide.md', '# Source\n')
#             snapshot = settings(owner=True, new=True)
#             self.assertEqual(DeclaredRefStore(c).recheck(snapshot, repository='new').refs[0].state, 'resolved')
#             seed_document(c, 'new', 'guide.md', '# Other\n', root='code')
#             reply = DeclaredRefStore(c).recheck(snapshot, repository='new')
#             self.assertEqual(reply.refs[0].fault, 'ambiguous_path')
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::DeclaredRefStoreTests.test_settings_registration_and_new_colliding_file_recheck_previous_selections

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::DeclaredRefStoreTests.test_shared_exact_version_has_independent_location_declarations_and_missing_owner_fault
#     def test_shared_exact_version_has_independent_location_declarations_and_missing_owner_fault(self):
#         disk = '---\nsources: ["source:disk.md"]\n---\n# Answer\nSame body.\n'
#         branch = '---\nsources: ["source:branch.md"]\n---\n# Answer\nSame body.\n'
#         snapshot = settings(owner=True, source=True)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             disk_location, file_id, ids, versions = seed_document(c, 'owner', 'answer.md', disk)
#             branch_location, _, _, branch_versions = seed_document(c, 'owner', 'answer.md', branch, file_id=file_id,
#                 chunk_ids=ids, kind='branch', location='main')
#             self.assertEqual(versions, branch_versions)
#             retain(c, snapshot, disk_location, disk)
#             retain(c, snapshot, branch_location, branch)
#             reply = DeclaredRefStore(c).recheck(snapshot, repository='owner')
#             self.assertEqual({ref.declaration for ref in reply.refs}, {'source:disk.md', 'source:branch.md'})
#             self.assertEqual(len({ref.identifier for ref in reply.refs}), 2)
#             c.execute('DELETE FROM public.mycel_file_locations WHERE id=%s', (branch_location,))
#             reply = DeclaredRefStore(c).recheck(snapshot, repository='owner')
#             missing = next(ref for ref in reply.refs if ref.location == branch_location)
#             self.assertEqual(missing.fault, 'owner_location_missing')
#             self.assertEqual(len(DeclaredRefStore(c).list()), 2)
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::DeclaredRefStoreTests.test_shared_exact_version_has_independent_location_declarations_and_missing_owner_fault

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::DeclaredRefStoreTests.test_retention_removes_only_own_declared_record_and_preserves_history_owned_evidence
#     def test_retention_removes_only_own_declared_record_and_preserves_history_owned_evidence(self):
#         source = '# Answer\n<!-- sources:\nsource:guide.md\n-->\n'
#         snapshot = settings(owner=True, source=True)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             location, _, _, versions = seed_document(c, 'owner', 'answer.md', source)
#             identifiers = retain(c, snapshot, location, source)
#             stale, owner, drift, asserted = uuid4(), uuid4(), uuid4(), uuid4()
#             c.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
#                       (owner, 'owner', 'baseline', 'retained-history'))
#             state = Jsonb({'declarationLocation': {'file': location}})
#             c.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
#                       (stale, 'owner', versions[0], 'source:old.md', '', 'declared', state, owner))
#             c.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
#                       (asserted, 'owner', versions[0], 'source:asserted.md', '', 'asserted', state))
#             c.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,%s,clock_timestamp(),NULL,%s,%s)',
#                       (drift, 'owner', versions[0], Jsonb({}), owner))
#             self.assertEqual(retain(c, snapshot, location, source), identifiers)
#             self.assertIsNone(c.execute('SELECT 1 FROM public.mycel_dependencies WHERE id=%s', (stale,)).fetchone())
#             self.assertIsNotNone(c.execute('SELECT 1 FROM public.mycel_dependencies WHERE id=%s', (asserted,)).fetchone())
#             self.assertIsNotNone(c.execute('SELECT 1 FROM public.mycel_evidence_owners WHERE id=%s', (owner,)).fetchone())
#             self.assertIsNotNone(c.execute('SELECT 1 FROM public.mycel_drifts WHERE id=%s', (drift,)).fetchone())
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::DeclaredRefStoreTests.test_retention_removes_only_own_declared_record_and_preserves_history_owned_evidence


class PhysicalBindingStoreTests(unittest.TestCase):
    check_kind = "store"

    def setup_disk(self, *, equal=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        code = base / 'code'
        artifact = code if equal else code / 'docs'
        artifact.mkdir(parents=True)
        config = base / 'settings.toml'
        config.write_text(f'[store]\naddress="postgresql://fixture@localhost/disposable"\n[repos.fixture]\nenabled=true\ncode_root={json.dumps(str(code))}\nartifact_root={json.dumps(str(artifact))}\n')
        return code, artifact, load_settings(path=config, home=base)

    def captured(self, path, aliases, raw=b'# Exact\n'):
        path.write_bytes(raw)
        return CapturedFile(aliases[0], tuple(aliases), 'documents', raw, sha256(raw).hexdigest(), split_markdown(raw))

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::PhysicalBindingStoreTests.test_overlapping_and_equal_roots_use_one_identity_and_stable_primary
#     def test_overlapping_and_equal_roots_use_one_identity_and_stable_primary(self):
#         code, artifact, snapshot = self.setup_disk()
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             captured = self.captured(artifact/'guide.md', (FileAlias('code', 'docs/guide.md'), FileAlias('artifact', 'guide.md')))
#             binding = bind_disk_file(c, snapshot, 'fixture', captured)
#             self.assertEqual(binding.primary.address, 'fixture:@artifact/guide.md')
#             again = bind_disk_file(c, snapshot, 'fixture', replace(captured, primary=captured.aliases[0]))
#             self.assertEqual((again.identifier, again.version, again.primary), (binding.identifier, binding.version, binding.primary))
#             resolver = SourceResolver.from_store(c, snapshot)
#             self.assertEqual(resolver.resolve('fixture:@code/docs/guide.md').selection.file.identifier, binding.identifier)
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 1)
#             nested = artifact/'nested'
#             nested.mkdir()
#             nested_capture = self.captured(nested/'guide.md',
#                 (FileAlias('code', 'docs/nested/guide.md'), FileAlias('artifact', 'nested/guide.md')))
#             retained = bind_disk_file(c, snapshot, 'fixture', nested_capture)
#             reconfigured = replace(snapshot, values=_freeze({**dict(snapshot.values), 'repos': {'fixture': {
#                 **dict(snapshot.values['repos']['fixture']), 'code_root': str(nested)}}}))
#             new_capture = replace(nested_capture, primary=FileAlias('code', 'guide.md'),
#                 aliases=(FileAlias('code', 'guide.md'), FileAlias('artifact', 'nested/guide.md')))
#             preserved = bind_disk_file(c, reconfigured, 'fixture', new_capture)
#             self.assertEqual((preserved.identifier, preserved.primary), (retained.identifier, retained.primary))
#         code, artifact, snapshot = self.setup_disk(equal=True)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             captured = self.captured(artifact/'equal.md', (FileAlias('code', 'equal.md'), FileAlias('artifact', 'equal.md')))
#             binding = bind_disk_file(c, snapshot, 'fixture', captured)
#             self.assertEqual(binding.primary.address, 'fixture:@artifact/equal.md')
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::PhysicalBindingStoreTests.test_overlapping_and_equal_roots_use_one_identity_and_stable_primary

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::PhysicalBindingStoreTests.test_distinct_equal_content_files_stay_distinct_and_atomic_replacement_refuses_safely
#     def test_distinct_equal_content_files_stay_distinct_and_atomic_replacement_refuses_safely(self):
#         code, artifact, snapshot = self.setup_disk()
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             first = bind_disk_file(c, snapshot, 'fixture', self.captured(code/'same.md', (FileAlias('code', 'same.md'),)))
#             second = bind_disk_file(c, snapshot, 'fixture', self.captured(artifact/'same.md', (FileAlias('artifact', 'same.md'),)))
#             self.assertNotEqual(first.identifier, second.identifier)
#             ambiguity = SourceResolver.from_store(c, snapshot).resolve('fixture:same.md')
#             self.assertEqual(ambiguity.candidates, ('fixture:@artifact/same.md', 'fixture:@code/same.md'))
#             replacement = artifact/'temporary.md'
#             replacement.write_bytes(b'# Changed\n')
#             replacement.replace(artifact/'same.md')
#             changed = CapturedFile(FileAlias('artifact', 'same.md'), (FileAlias('artifact', 'same.md'),),
#                                    'documents', b'# Changed\n', sha256(b'# Changed\n').hexdigest(), split_markdown(b'# Changed\n'))
#             with self.assertRaises(MycelError) as error:
#                 bind_disk_file(c, snapshot, 'fixture', changed)
#             self.assertEqual(error.exception.code.value, 'invalid_input')
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 2)
#             self.assertEqual(SourceResolver.from_store(c, snapshot).resolve('fixture:@artifact/same.md').selection.file.source, b'# Exact\n')
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::PhysicalBindingStoreTests.test_distinct_equal_content_files_stay_distinct_and_atomic_replacement_refuses_safely

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::PhysicalBindingStoreTests.test_legacy_global_alias_occupancy_refuses_unproved_identity_replacement
#     def test_legacy_global_alias_occupancy_refuses_unproved_identity_replacement(self):
#         code, artifact, snapshot = self.setup_disk()
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             _, file_id, _, _ = seed_document(c, 'fixture', 'guide.md', '# Old\n')
#             c.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)', (file_id, 'code', 'docs/guide.md'))
#             captured = self.captured(artifact/'guide.md', (FileAlias('code', 'docs/guide.md'),))
#             with self.assertRaises(MycelError) as error:
#                 bind_disk_file(c, snapshot, 'fixture', captured)
#             self.assertEqual(error.exception.code.value, 'invalid_input')
#             self.assertEqual(c.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 1)
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::PhysicalBindingStoreTests.test_legacy_global_alias_occupancy_refuses_unproved_identity_replacement

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::PhysicalBindingStoreTests.test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path
#     def test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path(self):
#         code, artifact, snapshot = self.setup_disk()
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             captured = self.captured(artifact/'old.md', (FileAlias('artifact', 'old.md'),))
#             binding = bind_disk_file(c, snapshot, 'fixture', captured)
#             # Seed a located chunk against the bound file without another file.
#             raw = captured.source
#             identifier = uuid4()
#             c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
#                       (identifier, 'fixture', binding.identifier, 'document', Jsonb({})))
#             metadata = {'name': 'Exact', 'kind': 'document', 'title': 'Exact', 'span': {'start': 0, 'end': len(raw)}}
#             version = c.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
#                                 'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
#                                 (identifier, sha256(raw).hexdigest(), raw, raw.decode(), Jsonb({}), Jsonb(metadata))).fetchone()[0]
#             c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
#                       (uuid4(), version, binding.location, 'disk', 'disk', Jsonb({})))
#             branch_location = uuid4()
#             c.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
#                       (branch_location, binding.version, 'branch', 'main', Jsonb({'root': 'artifact', 'auditTag': 'retained'})))
#             c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
#                       (uuid4(), version, branch_location, 'branch', 'main', Jsonb({})))
#             (artifact/'old.md').rename(artifact/'new.md')
#             moved = replace(captured, primary=FileAlias('artifact', 'new.md'), aliases=(FileAlias('artifact', 'new.md'),))
#             with self.assertRaises(MycelError):
#                 bind_disk_file(c, snapshot, 'fixture', moved)
#             updated = bind_disk_file(c, snapshot, 'fixture', moved, recognized_move=binding.identifier)
#             self.assertEqual((updated.identifier, updated.version, updated.location), (binding.identifier, binding.version, binding.location))
#             resolver = SourceResolver.from_store(c, snapshot)
#             followed = resolver.resolve_retained('fixture:old.md#Exact', str(identifier))
#             self.assertEqual(followed.selection.place.address, 'fixture:@artifact/new.md#Exact')
#             self.assertEqual(followed.declaration, 'fixture:old.md#Exact')
#             self.assertEqual(followed.selection.members[0].chunk.version, version)
#             branch = SourceResolver.from_store(c, snapshot, kind='branch', location='main')
#             self.assertEqual(branch.resolve('fixture:old.md#Exact').selection.members[0].chunk.identifier, str(identifier))
#             self.assertEqual(branch.resolve('fixture:new.md#Exact').fault, 'missing_file')
#             self.assertEqual(c.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s',
#                 (branch_location,)).fetchone()[0]['auditTag'], 'retained')
#             seed_document(c, 'fixture', 'old.md', '# Different\n')
#             reused = SourceResolver.from_store(c, snapshot).resolve_retained('fixture:old.md#Exact', str(identifier))
#             self.assertEqual(reused.fault, 'missing_name')
#             self.assertIsNone(reused.selection)
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::PhysicalBindingStoreTests.test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path


class TypedMutationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setup_disk(self, owner_text, source_text, source_path='source.md'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        owner, source = home/'owner', home/'source'
        owner.mkdir()
        source.mkdir()
        (owner/'answer.md').write_bytes(owner_text.encode())
        (source/source_path).write_bytes(source_text.encode())
        config = home/'settings.toml'
        config.write_text('[store]\naddress="postgresql://fixture@localhost/disposable"\n'
            f'[repos.owner]\nenabled=true\nartifact_root={json.dumps(str(owner))}\n'
            f'[repos.source]\nenabled=true\nartifact_root={json.dumps(str(source))}\n'
            + (f'code_root={json.dumps(str(source))}\n' if source_path.endswith('.py') else ''))
        return load_settings(path=config, home=home), owner, source

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::TypedMutationStoreTests.test_file_pin_uses_current_disk_complete_bytes_and_one_dependant_without_silent_retry_repin
#     def test_file_pin_uses_current_disk_complete_bytes_and_one_dependant_without_silent_retry_repin(self):
#         owner_text = '# Answer\n<!-- sources:\nsource:source.md\n-->\n'
#         source_text = '---\nrole: authored\n---\n# Source\r\nComplete\0source.\r\n'
#         snapshot, owner, source = self.setup_disk(owner_text, source_text)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             location, _, _, _ = seed_document(c, 'owner', 'answer.md', owner_text)
#             seed_document(c, 'source', 'source.md', source_text)
#             identifier = retain(c, snapshot, location, owner_text)[0]
#             DeclaredRefStore(c).recheck(snapshot, repository='owner')
#             observation = DiskPinObservation(c, snapshot, 'owner:answer.md#Answer', 'source:source.md')
#             expected = observation.observe()
#             writer = EvidenceStore(c)
#             manifest = writer.pin(expected, observation.reread, dependency_id=identifier, kind='declared',
#                 declaration='source:source.md', captured_at='2026-10-09T08:00:00Z', authorization='initial_resolution')
#             baseline = writer.read_baseline('owner', manifest)
#             self.assertEqual(DeclaredRefStore(c).list(repository='owner')[0].baseline_status, 'retained')
#             descriptor = SnapshotEvidence.from_record(json.loads(canonical_json(baseline.manifest.payload['members'][0]['evidence'])))
#             self.assertEqual(writer.read_snapshot('owner', descriptor), source_text.encode())
#             owner_before = c.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0]
#             disabled = replace(snapshot, values=_freeze({**dict(snapshot.values), 'repos': {
#                 **dict(snapshot.values['repos']), 'source': {**dict(snapshot.values['repos']['source']), 'enabled': False}}}))
#             reply = DeclaredRefStore(c).recheck(disabled, repository='owner')
#             self.assertEqual((reply.refs[0].fault, reply.refs[0].baseline_status), ('disabled_repository', 'retained'))
#             DeclaredRefStore(c).recheck(snapshot, repository='source')
#             self.assertEqual(c.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0], owner_before)
#             self.assertEqual(writer.read_baseline('owner', manifest), baseline)
#             (source/'source.md').write_bytes(b'# Source\nChanged without ingest.\n')
#             with self.assertRaises(EvidenceError) as error:
#                 writer.pin(expected, observation.reread, dependency_id=uuid4(), kind='asserted',
#                     declaration='source:source.md', captured_at='2026-10-09T08:01:00Z', authorization='initial_resolution')
#             self.assertEqual(error.exception.status, 'changed_since_ingest')
#             with self.assertRaises(EvidenceError):
#                 DiskPinObservation(c, snapshot, 'owner:answer.md', 'source:source.md').observe()
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::TypedMutationStoreTests.test_file_pin_uses_current_disk_complete_bytes_and_one_dependant_without_silent_retry_repin

# TEST-TIER-DISABLED-BEGIN tests/test_declared_refs.py::TypedMutationStoreTests.test_class_pin_has_ordered_membership_and_endpoint_selects_one_header
#     def test_class_pin_has_ordered_membership_and_endpoint_selects_one_header(self):
#         owner_text = '# Answer\nComplete answer.\n'
#         source_text = 'class Policy:\n def z(self): pass\n def a(self): pass\n'
#         snapshot, _, _ = self.setup_disk(owner_text, source_text, 'policy.py')
#         with self.store_fixture.backend.connection(self.store_fixture.database) as c:
#             seed_document(c, 'owner', 'answer.md', owner_text)
#             file_id, file_version, file_location = uuid4(), uuid4(), uuid4()
#             c.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s)', ('source', Jsonb([])))
#             c.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)', (file_id, 'source', 'artifact', 'policy.py', 'code'))
#             c.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)', (file_id, 'code', 'policy.py'))
#             c.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s)',
#                       (file_version, file_id, sha256(source_text.encode()).hexdigest(), source_text.encode(), Jsonb({})))
#             c.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
#                       (file_location, file_version, 'disk', 'disk', Jsonb({})))
#             for chunk in chunk_code('policy.py', source_text):
#                 identifier = uuid4()
#                 raw = chunk.text.encode()
#                 metadata = {'name': chunk.symbol, 'kind': chunk.kind, 'family': chunk.symbol.rpartition('.')[0] or None,
#                             'span': {'start': chunk.byte_start, 'end': chunk.byte_end}}
#                 c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
#                           (identifier, 'source', file_id, chunk.kind, Jsonb({})))
#                 version = c.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
#                     'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
#                     (identifier, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb(exact_comparison(raw, 'code_text').as_dict()), Jsonb(metadata))).fetchone()[0]
#                 c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
#                           (uuid4(), version, file_location, 'disk', 'disk', Jsonb({})))
#             observation = DiskPinObservation(c, snapshot, 'owner:answer.md#Answer', 'source:policy.py#Policy')
#             expected = observation.observe()
#             self.assertEqual([member.place.name for member in expected.selection.members], ['Policy', 'Policy.a', 'Policy.z'])
#             writer = EvidenceStore(c)
#             manifest = writer.pin(expected, observation.reread, dependency_id=uuid4(), kind='asserted',
#                 declaration='source:policy.py#Policy', captured_at='2026-10-09T08:00:00Z', authorization='initial_resolution')
#             baseline = writer.read_baseline('owner', manifest).manifest
#             self.assertEqual(baseline.payload['selection'], 'family')
#             self.assertEqual([member['place']['name'] for member in baseline.payload['members']], ['Policy', 'Policy.a', 'Policy.z'])
#             self.assertEqual([member['evidence']['hash'] for member in baseline.payload['members']],
#                              [member.chunk.snapshot_hash for member in expected.selection.members])
#             resolver = SourceResolver.from_store(c, snapshot)
#             endpoint = resolver.resolve('source:policy.py#Policy', purpose='endpoint')
#             self.assertEqual((endpoint.selection.kind, len(endpoint.selection.members)), ('chunk', 1))
#             self.assertEqual(resolver.resolve('source:policy.py', purpose='endpoint').fault, 'one_chunk_required')
#             self.assertEqual(resolver.resolve('source:@index/summaries', purpose='endpoint').fault, 'ineligible_index')
#             self.assertEqual(resolver.resolve('source:@index/summaries').fault, 'ineligible_index')
#             index_id = uuid4()
#             text = b'# Retained summary\n'
#             c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,%s)',
#                       (index_id, 'source', 'index', Jsonb({})))
#             index_version = c.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
#                 'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
#                 (index_id, sha256(text).hexdigest(), text, text.decode(), Jsonb({}),
#                  Jsonb({'name': '1/7', 'path': 'summaries', 'kind': 'index'}))).fetchone()[0]
#             c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,%s,%s,%s)',
#                       (uuid4(), index_version, 'index', 'index', Jsonb({})))
#             resolver = SourceResolver.from_store(c, snapshot)
#             read = resolver.resolve('source:@index/summaries#1%2F7', purpose='read')
#             self.assertEqual((read.selection.kind, read.selection.members[0].chunk.source), ('index', text))
#             self.assertEqual(resolver.resolve('source:@index/summaries#1%2F7', purpose='endpoint').fault, 'ineligible_index')
# TEST-TIER-DISABLED-END tests/test_declared_refs.py::TypedMutationStoreTests.test_class_pin_has_ordered_membership_and_endpoint_selects_one_header

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:2
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:12
# from mycel._capture import CapturedFile, FileAlias
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:13
# from mycel._code import chunk_code
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:15
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:16
# from mycel._evidence import (EvidenceError, EvidenceStore, SnapshotEvidence, canonical_json,
#                              document_comparisons, exact_comparison)
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:19
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:19
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:20
# from mycel._pin_observation import DiskPinObservation
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:20
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:22
# from mycel._source_bindings import bind_disk_file
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:22
# TEST-TIER-IMPORTS-BEGIN tests/test_declared_refs.py:23
# from mycel._source_refs import SourceAddress, read_document_declarations
# TEST-TIER-IMPORTS-END tests/test_declared_refs.py:23
