"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_declared_refs as _support
from test_declared_refs import (FileAlias ,Jsonb ,MycelError ,SourceResolver ,bind_disk_file ,replace ,seed_document ,sha256 ,uuid4)


class PhysicalBindingStoreTests(_support.PhysicalBindingStoreTests):


# TEST-TIER-BEGIN tests/test_declared_refs.py::PhysicalBindingStoreTests.test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path
    def test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path(self):
        code, artifact, snapshot = self.setup_disk()
        with self.store_fixture.backend.connection(self.store_fixture.database) as c:
            captured = self.captured(artifact/'old.md', (FileAlias('artifact', 'old.md'),))
            binding = bind_disk_file(c, snapshot, 'fixture', captured)
            # Seed a located chunk against the bound file without another file.
            raw = captured.source
            identifier = uuid4()
            c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
                      (identifier, 'fixture', binding.identifier, 'document', Jsonb({})))
            metadata = {'name': 'Exact', 'kind': 'document', 'title': 'Exact', 'span': {'start': 0, 'end': len(raw)}}
            version = c.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
                                'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                                (identifier, sha256(raw).hexdigest(), raw, raw.decode(), Jsonb({}), Jsonb(metadata))).fetchone()[0]
            c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                      (uuid4(), version, binding.location, 'disk', 'disk', Jsonb({})))
            branch_location = uuid4()
            c.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                      (branch_location, binding.version, 'branch', 'main', Jsonb({'root': 'artifact', 'auditTag': 'retained'})))
            c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                      (uuid4(), version, branch_location, 'branch', 'main', Jsonb({})))
            (artifact/'old.md').rename(artifact/'new.md')
            moved = replace(captured, primary=FileAlias('artifact', 'new.md'), aliases=(FileAlias('artifact', 'new.md'),))
            with self.assertRaises(MycelError):
                bind_disk_file(c, snapshot, 'fixture', moved)
            updated = bind_disk_file(c, snapshot, 'fixture', moved, recognized_move=binding.identifier)
            self.assertEqual((updated.identifier, updated.version, updated.location), (binding.identifier, binding.version, binding.location))
            resolver = SourceResolver.from_store(c, snapshot)
            followed = resolver.resolve_retained('fixture:old.md#Exact', str(identifier))
            self.assertEqual(followed.selection.place.address, 'fixture:@artifact/new.md#Exact')
            self.assertEqual(followed.declaration, 'fixture:old.md#Exact')
            self.assertEqual(followed.selection.members[0].chunk.version, version)
            branch = SourceResolver.from_store(c, snapshot, kind='branch', location='main')
            self.assertEqual(branch.resolve('fixture:old.md#Exact').selection.members[0].chunk.identifier, str(identifier))
            self.assertEqual(branch.resolve('fixture:new.md#Exact').fault, 'missing_file')
            self.assertEqual(c.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s',
                (branch_location,)).fetchone()[0]['auditTag'], 'retained')
            seed_document(c, 'fixture', 'old.md', '# Different\n')
            reused = SourceResolver.from_store(c, snapshot).resolve_retained('fixture:old.md#Exact', str(identifier))
            self.assertEqual(reused.fault, 'missing_name')
            self.assertIsNone(reused.selection)
# TEST-TIER-END tests/test_declared_refs.py::PhysicalBindingStoreTests.test_recognized_move_keeps_file_and_chunk_identity_and_never_overrides_reused_path
