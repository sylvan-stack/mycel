"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evidence_inheritance as _support
from test_evidence_inheritance import (Jsonb ,MycelError ,SourceResolver ,UUID ,evidence ,fixtures ,inherited_inputs ,json ,sha256 ,uuid4)


class InheritanceStoreTests(_support.InheritanceStoreTests):
# TEST-TIER-BEGIN tests/test_evidence_inheritance.py::InheritanceStoreTests.test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows
    def test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            helper = fixtures.EvidenceStoreTests()
            observed = helper.seed(connection, fixtures.inputs())
            writer = evidence.EvidenceStore(connection)
            dependency = uuid4()
            original_id = helper.pin(writer, observed, dependency=dependency,
                                    reread=lambda: helper.observe(connection, observed))
            original = writer.read_baseline('owner', original_id)
            desired = inherited_inputs(observed)
            file, chunk = desired.dependant_file, desired.dependant.chunk
            version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) RETURNING id',
                      (uuid4(), UUID(file.identifier), file.snapshot_hash, file.source, Jsonb({}))).fetchone()[0]
            metadata = {'name': chunk.name, 'kind': chunk.kind, 'title': chunk.title,
                        'span': {'start': chunk.span[0], 'end': chunk.span[1]},
                        'bodySpan': {'start': chunk.body_span[0], 'end': chunk.body_span[1]}}
            number = connection.execute('INSERT INTO public.mycel_chunk_versions '
                    '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                    (UUID(chunk.identifier), chunk.snapshot_hash, chunk.source, chunk.source.decode().replace('\0', '\ufffd'),
                     Jsonb(json.loads(evidence.canonical_json(chunk.comparison))), Jsonb(metadata))).fetchone()[0]
            connection.execute('DELETE FROM public.mycel_file_locations WHERE kind=%s AND file_version IN '
                     '(SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', ('disk', UUID(file.identifier)))
            location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
                         (uuid4(), version, 'disk', 'disk', Jsonb({}))).fetchone()[0]
            connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                               (uuid4(), number, location, 'disk', 'disk', Jsonb({})))
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            def reread():
                catalog = SourceResolver.from_store(connection, observed.settings)
                dep = catalog.resolve(desired.dependant.place.address, purpose='endpoint').selection
                return evidence.InheritanceInputs(observed.settings, dep.members[0], dep.file,
                         evidence.CaptureLocation('disk'), catalog.resolve(observed.resolution.declaration), catalog)
            current = reread()
            previous_owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
                                                (dependency,)).fetchone()[0]
            refs = connection.execute('SELECT owner,repository,snapshot_hash,manifest_hash,ordinal '
                    'FROM public.mycel_evidence_references WHERE owner=%s ORDER BY ordinal',(previous_owner,)).fetchall()
            before = connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0]
            connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND ordinal>0',(previous_owner,))
            with self.assertRaises(evidence.EvidenceError) as error:
                writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
                                   authorization='normalized_equivalent_edit')
            self.assertEqual(error.exception.status,'snapshot_corrupt')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0],before)
            for ref in refs[1:]:
                connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',ref)
            connection.execute("UPDATE public.mycel_evidence_owners SET kind='verification' WHERE id=%s",(previous_owner,))
            with self.assertRaises(evidence.EvidenceError) as error:
                writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
                                   authorization='normalized_equivalent_edit')
            self.assertEqual(error.exception.status,'snapshot_corrupt')
            connection.execute("UPDATE public.mycel_evidence_owners SET kind='baseline' WHERE id=%s",(previous_owner,))
            old_number = int(original.manifest.payload['dependantVersion'])
            old_version = connection.execute('SELECT snapshot_hash,source_bytes,text,comparison FROM public.mycel_chunk_versions WHERE id=%s',
                                             (old_number,)).fetchone()
            wrong = b'# Answer\nDifferent retained version body.\n'
            connection.execute('UPDATE public.mycel_chunk_versions SET snapshot_hash=%s,source_bytes=%s,text=%s,comparison=%s WHERE id=%s',
                    (sha256(wrong).hexdigest(),wrong,wrong.decode(),
                     Jsonb(json.loads(evidence.canonical_json(evidence.document_comparisons('Different retained version body.\n','Answer')))),old_number))
            with self.assertRaises(evidence.EvidenceError) as error:
                writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
                                   authorization='normalized_equivalent_edit')
            self.assertEqual(error.exception.status,'snapshot_corrupt')
            connection.execute('UPDATE public.mycel_chunk_versions SET snapshot_hash=%s,source_bytes=%s,text=%s,comparison=%s WHERE id=%s',
                               (*old_version[:3],Jsonb(old_version[3]),old_number))
            for lock_sql, parameters in (
                    ('SELECT id FROM public.mycel_evidence_owners WHERE id=%s FOR UPDATE', (previous_owner,)),
                    ('SELECT hash FROM public.mycel_manifests WHERE repository=%s AND hash=%s FOR UPDATE',
                     ('owner', original_id)),
                    ('SELECT hash FROM public.mycel_snapshots WHERE repository=%s AND hash=%s FOR UPDATE',
                     ('owner', original.manifest.payload['dependant']['hash']))):
                with self.subTest(lock=lock_sql), self.store_fixture.backend.connection(self.store_fixture.database) as contender:
                    with contender.transaction():
                        contender.execute(lock_sql, parameters)
                        with self.assertRaises(MycelError) as busy:
                            writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
                                               authorization='normalized_equivalent_edit')
                        self.assertEqual(busy.exception.code.value,'busy')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0],before)
            inherited_id = writer.inherit_pin(current, reread, previous_dependency=dependency,
                            dependency_id=uuid4(), authorization='normalized_equivalent_edit')
            inherited = writer.read_baseline('owner', inherited_id)
            self.assertEqual(inherited.manifest.payload['members'], original.manifest.payload['members'])
            self.assertEqual(inherited.manifest.payload['pinnedHash'], original.manifest.payload['pinnedHash'])
            self.assertEqual(inherited.manifest.payload['dependantVersion'], str(number))
            self.assertEqual(current.resolution.state, 'unresolved')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks WHERE repository=%s',
                                               ('source',)).fetchone()[0], 0)
            self.assertEqual(writer.read_baseline('owner', original_id), original)
# TEST-TIER-END tests/test_evidence_inheritance.py::InheritanceStoreTests.test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows
