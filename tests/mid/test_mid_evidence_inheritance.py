"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_evidence_inheritance as _support
# from test_evidence_inheritance import (
#     InheritanceStoreTests,
#     InheritanceUnitTests,
#     SourceResolver,
#     UUID,
#     _freeze,
#     contextmanager,
#     evidence,
#     fixtures,
#     inherited_inputs,
#     json,
#     patch,
#     replace,
#     sha256,
#     unittest,
#     uuid4,
# )


# class InheritanceUnitTests(_support.InheritanceUnitTests):
# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_old_manifest_and_every_old_snapshot_are_locked_and_revalidated_before_inheritance
#     def test_old_manifest_and_every_old_snapshot_are_locked_and_revalidated_before_inheritance(self):
#         current = inherited_inputs(self.observed)
#         self.prepare(current)
#         manifest_key = ('owner', self.original.manifest.identifier)
#         dep_hash = self.original.manifest.payload['dependant']['hash']
#         for damage in ('kind', 'manifest_metadata', 'snapshot_metadata'):
#             with self.subTest(damage=damage):
#                 execute = self.connection.execute
#                 def race(statement, parameters=()):
#                     if statement == evidence._INHERITANCE_OWNER_SQL:
#                         if damage == 'snapshot_metadata':
#                             raw, metadata = self.connection.snapshots[('owner', dep_hash)]
#                             self.connection.snapshots[('owner', dep_hash)] = (raw, {**metadata, 'bytes': 0})
#                         else:
#                             kind, raw, metadata = self.connection.manifests[manifest_key]
#                             self.connection.manifests[manifest_key] = (
#                                 'verification' if damage == 'kind' else kind, raw,
#                                 {'schema': 99} if damage == 'manifest_metadata' else metadata)
#                     return execute(statement, parameters)
#                 with patch.object(self.connection, 'execute', side_effect=race), self.assertRaises(evidence.EvidenceError) as error:
#                     self.inherit(current)
#                 self.assertEqual(error.exception.status, 'snapshot_corrupt')
#                 self.assertEqual(len(self.connection.manifests), 1)
#                 self.assertEqual(len(self.connection.dependencies), 1)
#         result = self.inherit(current)
#         self.assertEqual(self.writer.read_baseline('owner', result).manifest.payload['members'],
#                          self.original.manifest.payload['members'])
#         sql = [statement for statement, _ in self.connection.sql]
#         self.assertIn(evidence._MANIFEST_LOCK_SQL, sql)
#         self.assertIn(evidence._SNAPSHOT_LOCK_SQL, sql)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_old_manifest_and_every_old_snapshot_are_locked_and_revalidated_before_inheritance

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_complete_prior_owner_reference_graph_and_exact_version_are_required
#     def test_complete_prior_owner_reference_graph_and_exact_version_are_required(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         owners, refs, versions = dict(self.connection.owners), dict(self.connection.refs), dict(self.connection.versions)
#         for kind in ('owner_repository','owner_kind','owner_identity','refs_missing','refs_wrong_ordinal','refs_extra',
#                      'version_identity','version_owner','version_hash','version_bytes','version_comparison'):
#             with self.subTest(kind=kind):
#                 self.connection.owners = dict(owners)
#                 self.connection.refs = dict(refs)
#                 self.connection.versions = dict(versions)
#                 self.damage_prior(kind)
#                 with patch.object(self.writer,'_write',side_effect=AssertionError('corrupt baseline reached writer')):
#                     with self.assertRaises(evidence.EvidenceError) as error:
#                         self.inherit(current)
#                 self.assertEqual(error.exception.status,'snapshot_corrupt')
#                 self.assertEqual((len(self.connection.manifests),len(self.connection.dependencies)),(1,1))
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_complete_prior_owner_reference_graph_and_exact_version_are_required

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_prior_corruption_during_fresh_reread_is_not_inherited
#     def test_prior_corruption_during_fresh_reread_is_not_inherited(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         for kind in ('owner_kind','refs_missing','version_bytes'):
#             with self.subTest(kind=kind):
#                 owners, refs, versions = dict(self.connection.owners), dict(self.connection.refs), dict(self.connection.versions)
#                 def reread():
#                     self.damage_prior(kind)
#                     return current
#                 with self.assertRaises(evidence.EvidenceError) as error:
#                     self.inherit(current,reread=reread)
#                 self.assertEqual(error.exception.status,'snapshot_corrupt')
#                 self.assertEqual(len(self.connection.manifests),1)
#                 self.connection.owners, self.connection.refs, self.connection.versions = owners, refs, versions
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_prior_corruption_during_fresh_reread_is_not_inherited

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_atomic_recheck_detects_owner_refs_and_old_row_races_before_writes
#     def test_atomic_recheck_detects_owner_refs_and_old_row_races_before_writes(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         owners, refs, versions = dict(self.connection.owners), dict(self.connection.refs), dict(self.connection.versions)
#         execute = self.connection.execute
#         for kind in ('owner_kind','owner_identity','refs_missing','version_bytes','version_comparison'):
#             with self.subTest(kind=kind):
#                 self.connection.owners, self.connection.refs, self.connection.versions = dict(owners), dict(refs), dict(versions)
#                 changed = False
#                 def race(statement,parameters=()):
#                     nonlocal changed
#                     if statement == evidence._INHERITANCE_OWNER_SQL and not changed:
#                         changed = True; self.damage_prior(kind)
#                     return execute(statement,parameters)
#                 with patch.object(self.connection,'execute',side_effect=race), patch.object(
#                         self.writer,'_write',side_effect=AssertionError('stale old graph reached writer')):
#                     with self.assertRaises(evidence.EvidenceError) as error:
#                         self.inherit(current)
#                 self.assertTrue(changed)
#                 self.assertEqual(error.exception.status,'changed_since_ingest')
#                 self.assertEqual((len(self.connection.manifests),len(self.connection.dependencies)),(1,1))
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_atomic_recheck_detects_owner_refs_and_old_row_races_before_writes

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_captured_old_comparison_has_no_mutable_alias_during_atomic_recheck
#     def test_captured_old_comparison_has_no_mutable_alias_during_atomic_recheck(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         previous = self.connection.dependencies[self.dependency]
#         row = list(self.connection.versions[previous[1]])
#         row[6] = json.loads(evidence.canonical_json(row[6]))
#         self.connection.versions[previous[1]] = tuple(row)
#         execute = self.connection.execute
#         def race(statement,parameters=()):
#             if statement == evidence._INHERITANCE_OWNER_SQL:
#                 self.connection.versions[previous[1]][6]['body']['hash'] = '0'*64
#             return execute(statement,parameters)
#         with patch.object(self.connection,'execute',side_effect=race):
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 self.inherit(current)
#         self.assertEqual(error.exception.status,'changed_since_ingest')
#         self.assertEqual(len(self.connection.manifests),1)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_captured_old_comparison_has_no_mutable_alias_during_atomic_recheck

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_old_file_rebinding_is_allowed_but_all_integrity_rows_are_locked
#     def test_old_file_rebinding_is_allowed_but_all_integrity_rows_are_locked(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         previous = self.connection.dependencies[self.dependency]
#         row = list(self.connection.versions[previous[1]]); row[3] = uuid4()
#         self.connection.versions[previous[1]] = tuple(row)
#         result = self.inherit(current)
#         self.assertEqual(self.writer.read_baseline('owner',result).manifest.payload['members'],self.original.manifest.payload['members'])
#         statements = [sql for sql,_ in self.connection.sql]
#         for sql in (evidence._INHERITANCE_OWNER_SQL,evidence._INHERITANCE_REFERENCES_SQL,evidence._INHERITANCE_VERSION_SQL):
#             self.assertIn(sql,statements)
#             self.assertIn('NOWAIT',sql)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_old_file_rebinding_is_allowed_but_all_integrity_rows_are_locked

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_invalid_authorization_never_takes_a_snapshot_or_creates_evidence
#     def test_invalid_authorization_never_takes_a_snapshot_or_creates_evidence(self):
#         current = inherited_inputs(self.observed); self.prepare(current)
#         before = len(self.connection.sql)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.writer.inherit_pin(current,lambda:current,previous_dependency=self.dependency,
#                 dependency_id=uuid4(),authorization='owner_confirmation')
#         self.assertEqual(error.exception.status,'invalid_input')
#         self.assertEqual(len(self.connection.sql),before)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_invalid_authorization_never_takes_a_snapshot_or_creates_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_deleted_or_disabled_source_needs_no_live_source_rows_and_preserves_owned_before_text
#     def test_deleted_or_disabled_source_needs_no_live_source_rows_and_preserves_owned_before_text(self):
#         for disabled in (False, True):
#             with self.subTest(disabled=disabled):
#                 current = inherited_inputs(self.observed, disabled=disabled)
#                 self.prepare(current)
#                 def reread():
#                     self.assertEqual(self.connection.guards, ['owner'])
#                     return current
#                 identifier = self.inherit(current, reread=reread)
#                 inherited = self.writer.read_baseline('owner', identifier)
#                 for field in ('members', 'pinnedHash', 'source', 'capturedAt', 'location', 'ref'):
#                     self.assertEqual(inherited.manifest.payload[field], self.original.manifest.payload[field])
#                 self.assertEqual(inherited.manifest.payload['dependantVersion'], '100')
#                 self.assertEqual(inherited.manifest.payload['dependant']['hash'], current.dependant.chunk.snapshot_hash)
#                 self.assertNotEqual(inherited.manifest.payload['dependant'], self.original.manifest.payload['dependant'])
#                 self.assertEqual(current.resolution.state, 'invalid' if disabled else 'unresolved')
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_deleted_or_disabled_source_needs_no_live_source_rows_and_preserves_owned_before_text

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_substantive_body_edit_and_wrong_original_declaration_cannot_inherit
#     def test_substantive_body_edit_and_wrong_original_declaration_cannot_inherit(self):
#         for current in (inherited_inputs(self.observed, body='Different answer.\n'),
#                         inherited_inputs(self.observed)):
#             if current.dependant.chunk.body == b'Exact\tanswer.\n':
#                 resolution = current.catalog.resolve('source:another.md#Source')
#                 current = replace(current, resolution=resolution)
#             self.prepare(current)
#             before = len(self.connection.manifests)
#             with self.assertRaises(evidence.EvidenceError):
#                 self.inherit(current)
#             self.assertEqual(len(self.connection.manifests), before)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_substantive_body_edit_and_wrong_original_declaration_cannot_inherit

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_fresh_observation_and_exact_dependant_binding_are_required_before_inheritance
#     def test_fresh_observation_and_exact_dependant_binding_are_required_before_inheritance(self):
#         current = inherited_inputs(self.observed)
#         self.prepare(current)
#         changed = replace(current, guards={'locationIdentity': 'changed'})
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.inherit(current, reread=lambda: changed)
#         self.assertEqual(error.exception.status, 'changed_since_ingest')
#         self.connection.versions.pop(current.dependant.chunk.version)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.inherit(current)
#         self.assertEqual(error.exception.status, 'changed_since_ingest')
#         self.assertEqual(len(self.connection.manifests), 1)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_fresh_observation_and_exact_dependant_binding_are_required_before_inheritance

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_baseline_must_belong_to_previous_exact_dependant_version
#     def test_baseline_must_belong_to_previous_exact_dependant_version(self):
#         current = inherited_inputs(self.observed)
#         self.prepare(current)
#         old = list(self.connection.dependencies[self.dependency])
#         old[1] += 50
#         self.connection.dependencies[self.dependency] = tuple(old)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.inherit(current)
#         self.assertEqual(error.exception.status, 'snapshot_corrupt')
#         self.assertEqual(len(self.connection.manifests), 1)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_baseline_must_belong_to_previous_exact_dependant_version

# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceUnitTests.test_capture_guard_binds_file_identity_and_aliases_as_well_as_complete_bytes
#     def test_capture_guard_binds_file_identity_and_aliases_as_well_as_complete_bytes(self):
#         source = replace(self.observed.selection.file, identifier=str(uuid4()))
#         catalog = SourceResolver(self.observed.settings, (self.observed.dependant_file, source))
#         resolution = catalog.resolve(self.observed.resolution.declaration)
#         changed = replace(self.observed, catalog=catalog, resolution=resolution, selection=resolution.selection)
#         self.assertNotEqual(changed.identity, self.observed.identity)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             with evidence.checked_input_guard(self.connection, self.observed, lambda: changed):
#                 self.fail('changed file identity admitted')
#         self.assertEqual(error.exception.status, 'changed_since_ingest')
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceUnitTests.test_capture_guard_binds_file_identity_and_aliases_as_well_as_complete_bytes



# class InheritanceStoreTests(_support.InheritanceStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_evidence_inheritance.py::InheritanceStoreTests.test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows
#     def test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             helper = fixtures.EvidenceStoreTests()
#             observed = helper.seed(connection, fixtures.inputs())
#             writer = evidence.EvidenceStore(connection)
#             dependency = uuid4()
#             original_id = helper.pin(writer, observed, dependency=dependency,
#                                     reread=lambda: helper.observe(connection, observed))
#             original = writer.read_baseline('owner', original_id)
#             desired = inherited_inputs(observed)
#             file, chunk = desired.dependant_file, desired.dependant.chunk
#             version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) RETURNING id',
#                       (uuid4(), UUID(file.identifier), file.snapshot_hash, file.source, Jsonb({}))).fetchone()[0]
#             metadata = {'name': chunk.name, 'kind': chunk.kind, 'title': chunk.title,
#                         'span': {'start': chunk.span[0], 'end': chunk.span[1]},
#                         'bodySpan': {'start': chunk.body_span[0], 'end': chunk.body_span[1]}}
#             number = connection.execute('INSERT INTO public.mycel_chunk_versions '
#                     '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
#                     (UUID(chunk.identifier), chunk.snapshot_hash, chunk.source, chunk.source.decode().replace('\0', '\ufffd'),
#                      Jsonb(json.loads(evidence.canonical_json(chunk.comparison))), Jsonb(metadata))).fetchone()[0]
#             connection.execute('DELETE FROM public.mycel_file_locations WHERE kind=%s AND file_version IN '
#                      '(SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', ('disk', UUID(file.identifier)))
#             location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
#                          (uuid4(), version, 'disk', 'disk', Jsonb({}))).fetchone()[0]
#             connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
#                                (uuid4(), number, location, 'disk', 'disk', Jsonb({})))
#             connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
#             def reread():
#                 catalog = SourceResolver.from_store(connection, observed.settings)
#                 dep = catalog.resolve(desired.dependant.place.address, purpose='endpoint').selection
#                 return evidence.InheritanceInputs(observed.settings, dep.members[0], dep.file,
#                          evidence.CaptureLocation('disk'), catalog.resolve(observed.resolution.declaration), catalog)
#             current = reread()
#             previous_owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s',
#                                                 (dependency,)).fetchone()[0]
#             refs = connection.execute('SELECT owner,repository,snapshot_hash,manifest_hash,ordinal '
#                     'FROM public.mycel_evidence_references WHERE owner=%s ORDER BY ordinal',(previous_owner,)).fetchall()
#             before = connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0]
#             connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND ordinal>0',(previous_owner,))
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
#                                    authorization='normalized_equivalent_edit')
#             self.assertEqual(error.exception.status,'snapshot_corrupt')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0],before)
#             for ref in refs[1:]:
#                 connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',ref)
#             connection.execute("UPDATE public.mycel_evidence_owners SET kind='verification' WHERE id=%s",(previous_owner,))
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
#                                    authorization='normalized_equivalent_edit')
#             self.assertEqual(error.exception.status,'snapshot_corrupt')
#             connection.execute("UPDATE public.mycel_evidence_owners SET kind='baseline' WHERE id=%s",(previous_owner,))
#             old_number = int(original.manifest.payload['dependantVersion'])
#             old_version = connection.execute('SELECT snapshot_hash,source_bytes,text,comparison FROM public.mycel_chunk_versions WHERE id=%s',
#                                              (old_number,)).fetchone()
#             wrong = b'# Answer\nDifferent retained version body.\n'
#             connection.execute('UPDATE public.mycel_chunk_versions SET snapshot_hash=%s,source_bytes=%s,text=%s,comparison=%s WHERE id=%s',
#                     (sha256(wrong).hexdigest(),wrong,wrong.decode(),
#                      Jsonb(json.loads(evidence.canonical_json(evidence.document_comparisons('Different retained version body.\n','Answer')))),old_number))
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
#                                    authorization='normalized_equivalent_edit')
#             self.assertEqual(error.exception.status,'snapshot_corrupt')
#             connection.execute('UPDATE public.mycel_chunk_versions SET snapshot_hash=%s,source_bytes=%s,text=%s,comparison=%s WHERE id=%s',
#                                (*old_version[:3],Jsonb(old_version[3]),old_number))
#             for lock_sql, parameters in (
#                     ('SELECT id FROM public.mycel_evidence_owners WHERE id=%s FOR UPDATE', (previous_owner,)),
#                     ('SELECT hash FROM public.mycel_manifests WHERE repository=%s AND hash=%s FOR UPDATE',
#                      ('owner', original_id)),
#                     ('SELECT hash FROM public.mycel_snapshots WHERE repository=%s AND hash=%s FOR UPDATE',
#                      ('owner', original.manifest.payload['dependant']['hash']))):
#                 with self.subTest(lock=lock_sql), self.store_fixture.backend.connection(self.store_fixture.database) as contender:
#                     with contender.transaction():
#                         contender.execute(lock_sql, parameters)
#                         with self.assertRaises(MycelError) as busy:
#                             writer.inherit_pin(current,reread,previous_dependency=dependency,dependency_id=uuid4(),
#                                                authorization='normalized_equivalent_edit')
#                         self.assertEqual(busy.exception.code.value,'busy')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_manifests').fetchone()[0],before)
#             inherited_id = writer.inherit_pin(current, reread, previous_dependency=dependency,
#                             dependency_id=uuid4(), authorization='normalized_equivalent_edit')
#             inherited = writer.read_baseline('owner', inherited_id)
#             self.assertEqual(inherited.manifest.payload['members'], original.manifest.payload['members'])
#             self.assertEqual(inherited.manifest.payload['pinnedHash'], original.manifest.payload['pinnedHash'])
#             self.assertEqual(inherited.manifest.payload['dependantVersion'], str(number))
#             self.assertEqual(current.resolution.state, 'unresolved')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks WHERE repository=%s',
#                                                ('source',)).fetchone()[0], 0)
#             self.assertEqual(writer.read_baseline('owner', original_id), original)
# TEST-TIER-DISABLED-END tests/test_evidence_inheritance.py::InheritanceStoreTests.test_real_new_dependant_version_inherits_deleted_source_with_no_live_source_rows


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_evidence_inheritance.py:11
# from psycopg.types.json import Jsonb
# TEST-TIER-IMPORTS-END tests/test_evidence_inheritance.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_evidence_inheritance.py:14
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_evidence_inheritance.py:14

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
