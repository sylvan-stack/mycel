"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_pin_observation as _support
from test_pin_observation import (
    CompletedChild,
    DiskCatalogConnection,
    EvidenceConnection,
    MycelError,
    Path,
    PinObservationStoreTests,
    PinObservationTests,
    ResolvedChunk,
    ResolvedFile,
    Rows,
    SourceAddress,
    SourceResolver,
    _freeze,
    capture_repository,
    chunk_code,
    contextmanager,
    document,
    evidence,
    evidence_checks,
    json,
    load_settings,
    member,
    no_checkout,
    observation,
    patch,
    replace,
    resolver,
    sha256,
    tempfile,
    unittest,
    uuid4,
)


class PinObservationTests(_support.PinObservationTests):
# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_fresh_disk_and_sql_observations_supply_real_callback_inside_pin_locks
    def test_fresh_disk_and_sql_observations_supply_real_callback_inside_pin_locks(self):
        adapter = self.adapter()
        expected = adapter.observe()
        self.assertIs(expected.settings,self.settings)
        self.assertEqual(expected.resolution.declaration,adapter.declaration)
        self.assertEqual(len(expected.guards['files']),2)
        observed = adapter.reread()
        self.assertEqual(observed.identity,expected.identity)
        self.assertIsNot(observed.catalog,expected.catalog)
        self.assertIsNot(observed.dependant_file,expected.dependant_file)
        original = adapter.reread
        def checked_reread():
            self.assertEqual(self.connection.guards,['owner','source'])
            return original()
        identifier = self.writer.pin(expected,checked_reread,dependency_id=uuid4(),kind='declared',
            declaration=adapter.declaration,captured_at='2026-10-09T00:00:00Z',authorization='initial_resolution')
        self.assertEqual(self.writer.read_baseline('owner',identifier).manifest.payload['dependantVersion'],'1')
        self.assertEqual(self.capture_calls,['owner','source']*3)
        self.assertEqual(sum(sql == resolver._CATALOG_SQL for sql,_ in self.connection.sql),3)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_fresh_disk_and_sql_observations_supply_real_callback_inside_pin_locks

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_changed_source_even_normalized_equal_never_pins_stale_exact_text
    def test_changed_source_even_normalized_equal_never_pins_stale_exact_text(self):
        adapter = self.adapter()
        expected = adapter.observe()
        (self.source_artifact/'source.md').write_text('# Source\nComplete\nsource.\n')
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_changed_source_even_normalized_equal_never_pins_stale_exact_text

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_frontmatter_and_other_dependant_sections_are_complete_file_guards
    def test_frontmatter_and_other_dependant_sections_are_complete_file_guards(self):
        for selected in ('source','owner'):
            with self.subTest(selected=selected):
                adapter = self.adapter()
                expected = adapter.observe()
                path = self.source_artifact/'source.md' if selected == 'source' else self.owner_root/'answer.md'
                original = path.read_bytes()
                path.write_bytes(b'---\nrole: authored\n---\n' + original)
                self.assert_refused_without_write(adapter,expected)
                path.write_bytes(original)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_frontmatter_and_other_dependant_sections_are_complete_file_guards

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_deleted_required_disk_file_never_substitutes_stored_or_branch_text
    def test_deleted_required_disk_file_never_substitutes_stored_or_branch_text(self):
        adapter = self.adapter()
        expected = adapter.observe()
        (self.source_artifact/'source.md').unlink()
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_deleted_required_disk_file_never_substitutes_stored_or_branch_text

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_unindexed_new_file_collision_invalidates_original_legacy_declaration
    def test_unindexed_new_file_collision_invalidates_original_legacy_declaration(self):
        adapter = self.adapter()
        expected = adapter.observe()
        (self.source_code/'source.md').write_text('# Source\nUnindexed collision\n')
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_unindexed_new_file_collision_invalidates_original_legacy_declaration

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_collision_after_scan_but_before_observation_finishes_is_detected
    def test_new_collision_after_scan_but_before_observation_finishes_is_detected(self):
        adapter = self.adapter()
        expected = adapter.observe()
        original = self.capture
        def create_collision_after_capture(snapshot, repository, **kwargs):
            result = original(snapshot,repository,**kwargs)
            if repository.name == 'source':
                (self.source_code/'source.md').write_text('# Source\nNew late collision\n')
            return result
        with patch.object(observation,'capture_repository',create_collision_after_capture):
            self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_collision_after_scan_but_before_observation_finishes_is_detected

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_qualified_source_remains_valid_when_a_different_file_shares_bare_path
    def test_qualified_source_remains_valid_when_a_different_file_shares_bare_path(self):
        adapter = self.adapter(declaration='source:@artifact/source.md#Source')
        expected = adapter.observe()
        (self.source_code/'source.md').write_text('# Source\nDifferent file\n')
        self.assertEqual(adapter.reread().identity,expected.identity)
        self.pin(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_qualified_source_remains_valid_when_a_different_file_shares_bare_path

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_gitignore_exclusion_refuses_before_baseline_write
    def test_new_gitignore_exclusion_refuses_before_baseline_write(self):
        adapter = self.adapter()
        expected = adapter.observe()
        (self.source_artifact/'.gitignore').write_text('source.md\n')
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_gitignore_exclusion_refuses_before_baseline_write

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_alias_and_same_byte_root_rebinding_are_detected_after_observation
    def test_alias_and_same_byte_root_rebinding_are_detected_after_observation(self):
        self.source_code.rmdir()
        self.source_code.symlink_to(self.source_artifact,target_is_directory=True)
        source_file = next(file for file in self.connection.catalog_files.values() if file.repository == 'source')
        source_file = replace(source_file,aliases=(source_file.primary,SourceAddress('source','code','source.md')))
        self.connection.catalog_files[source_file.identifier] = source_file
        adapter = self.adapter()
        expected = adapter.observe()
        other = self.home/'other-source'
        other.mkdir()
        (other/'source.md').write_bytes(self.source_text.encode())
        self.source_code.unlink()
        self.source_code.symlink_to(other,target_is_directory=True)
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_alias_and_same_byte_root_rebinding_are_detected_after_observation

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_required_symlink_never_reads_outside_capture_roots
    def test_new_required_symlink_never_reads_outside_capture_roots(self):
        adapter = self.adapter()
        expected = adapter.observe()
        path = self.source_artifact/'source.md'
        outside = self.home/'outside.md'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_required_symlink_never_reads_outside_capture_roots

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_indexed_exact_version_invalidates_old_guard_even_with_same_bytes
    def test_new_indexed_exact_version_invalidates_old_guard_even_with_same_bytes(self):
        adapter = self.adapter()
        expected = adapter.observe()
        source_file = next(file for file in self.connection.catalog_files.values() if file.repository == 'source')
        updated = replace(source_file,chunks=(replace(source_file.chunks[0],version=12),))
        self.connection.catalog_files[source_file.identifier] = updated
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_indexed_exact_version_invalidates_old_guard_even_with_same_bytes

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_exact_body_and_full_file_spans_must_match_current_parser_projection
    def test_exact_body_and_full_file_spans_must_match_current_parser_projection(self):
        adapter = self.adapter()
        expected = adapter.observe()
        source_file = next(file for file in self.connection.catalog_files.values() if file.repository == 'source')
        bad_chunk = replace(source_file.chunks[0],body_span=(0,len(source_file.chunks[0].source)))
        self.connection.catalog_files[source_file.identifier] = replace(source_file,chunks=(bad_chunk,))
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_exact_body_and_full_file_spans_must_match_current_parser_projection

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_exact_nul_document_and_non_utf8_file_selection_remain_complete_bytes
    def test_exact_nul_document_and_non_utf8_file_selection_remain_complete_bytes(self):
        source_file = next(file for file in self.connection.catalog_files.values() if file.repository == 'source')
        raw = '# Source\nExact\x00body.\n'
        (self.source_artifact/'source.md').write_bytes(raw.encode())
        nul_file = document('source','source.md',raw,version=11)
        self.connection.catalog_files[source_file.identifier] = nul_file
        adapter = self.adapter()
        expected = adapter.observe()
        self.assertEqual(expected.selection.members[0].chunk.source,raw.encode())
        self.assertIn(b'\x00',expected.selection.members[0].chunk.body)
        self.assertEqual(adapter.reread().identity,expected.identity)
        binary = b'\xff\x00complete original bytes'
        (self.source_artifact/'source.md').write_bytes(binary)
        binary_file = replace(nul_file,source=binary,snapshot_hash=sha256(binary).hexdigest(),chunks=())
        self.connection.catalog_files[source_file.identifier] = binary_file
        whole = self.adapter(declaration='source:source.md')
        expected = whole.observe()
        self.assertEqual(expected.selection.kind,'file')
        self.assertEqual(expected.selection.file.source,binary)
        self.assertEqual(whole.reread().identity,expected.identity)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_exact_nul_document_and_non_utf8_file_selection_remain_complete_bytes

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_one_invocation_settings_snapshot_is_reused_without_reloading_changed_settings_file
    def test_one_invocation_settings_snapshot_is_reused_without_reloading_changed_settings_file(self):
        adapter = self.adapter()
        expected = adapter.observe()
        self.settings_path.write_text('[repos.source]\nenabled=false\n')
        with patch('mycel._settings.load_settings',side_effect=AssertionError('Settings must not be reloaded')):
            observed = adapter.reread()
        self.assertIs(observed.settings,self.settings)
        self.assertEqual(observed.identity,expected.identity)
        self.pin(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_one_invocation_settings_snapshot_is_reused_without_reloading_changed_settings_file

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_non_disk_and_invalid_or_ineligible_references_refuse_before_store_read
    def test_non_disk_and_invalid_or_ineligible_references_refuse_before_store_read(self):
        for kwargs in ({'kind':'branch'},{'kind':'stash'},{'kind':'generated'},
                       {'declaration':'not a ref'},{'declaration':'disabled:path#Name'},
                       {'declaration':'unregistered:path#Name'},{'declaration':'source:@index/summaries'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(evidence.EvidenceError):
                self.adapter(**kwargs).observe()
        self.assertFalse(self.connection.sql)
        self.assertFalse(self.capture_calls)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_non_disk_and_invalid_or_ineligible_references_refuse_before_store_read

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_cancellation_refuses_before_read_and_releases_guard_without_write
    def test_cancellation_refuses_before_read_and_releases_guard_without_write(self):
        with self.assertRaises(KeyboardInterrupt):
            self.adapter(cancelled=lambda:True).observe()
        adapter = self.adapter()
        expected = adapter.observe()
        cancelled = self.adapter(cancelled=lambda:True)
        with self.assertRaises(KeyboardInterrupt):
            self.pin(cancelled,expected)
        self.assertFalse(self.connection.guards)
        self.assertFalse(self.connection.snapshots)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_cancellation_refuses_before_read_and_releases_guard_without_write

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_cancellation_after_last_required_read_prevents_pin_and_releases_locks
    def test_cancellation_after_last_required_read_prevents_pin_and_releases_locks(self):
        state = {'cancelled':False}
        adapter = self.adapter(cancelled=lambda:state['cancelled'])
        expected = adapter.observe()
        original = observation._read_alias
        def cancel_after_source_read(repository,address,source,cancelled):
            result = original(repository,address,source,cancelled)
            if address.repository == 'source':
                state['cancelled'] = True
            return result
        with patch.object(observation,'_read_alias',cancel_after_source_read), self.assertRaises(KeyboardInterrupt):
            self.pin(adapter,expected)
        self.assertFalse(self.connection.snapshots)
        self.assertFalse(self.connection.dependencies)
        self.assertFalse(self.connection.guards)
        self.assertNotIn('begin',self.connection.events)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_cancellation_after_last_required_read_prevents_pin_and_releases_locks

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_complete_class_family_cannot_omit_a_current_method_from_membership
    def test_complete_class_family_cannot_omit_a_current_method_from_membership(self):
        raw = 'class Policy:\n def a(self): pass\n def z(self): pass\n'
        (self.source_code/'policy.py').write_text(raw)
        primary = SourceAddress('source','code','policy.py')
        parsed = chunk_code('policy.py',raw)
        chunks = tuple(ResolvedChunk(str(uuid4()),20+number,chunk.symbol,chunk.kind,chunk.text.encode(),
                sha256(chunk.text.encode()).hexdigest(),(chunk.byte_start,chunk.byte_end),None,
                'Policy' if chunk.symbol.startswith('Policy.') else None,
                evidence.exact_comparison(chunk.text.encode(),'code_text').as_dict()) for number,chunk in enumerate(parsed))
        code_file = ResolvedFile(str(uuid4()),'source',primary,(primary,),raw.encode(),sha256(raw.encode()).hexdigest(),chunks)
        self.connection.catalog_files[code_file.identifier] = code_file
        adapter = self.adapter(declaration='source:@code/policy.py#Policy')
        expected = adapter.observe()
        self.assertEqual(len(expected.selection.members),3)
        omitted = replace(code_file,chunks=tuple(replace(chunk,family=None) if chunk.name == 'Policy.z' else chunk
                                                for chunk in code_file.chunks))
        self.connection.catalog_files[code_file.identifier] = omitted
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_complete_class_family_cannot_omit_a_current_method_from_membership

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_nested_class_source_includes_inner_methods_and_parent_continuations_remain_single
    def test_nested_class_source_includes_inner_methods_and_parent_continuations_remain_single(self):
        raw = 'class Policy:\n class Inner:\n  def a(self): pass\n  field = 1\n'
        (self.source_code/'nested.py').write_text(raw)
        primary = SourceAddress('source','code','nested.py')
        parsed = chunk_code('nested.py',raw)
        chunks = []
        for number,chunk in enumerate(parsed):
            family = None if '.' not in chunk.symbol else chunk.symbol.rsplit('.',1)[0]
            chunks.append(ResolvedChunk(str(uuid4()),30+number,chunk.symbol,chunk.kind,chunk.text.encode(),
                sha256(chunk.text.encode()).hexdigest(),(chunk.byte_start,chunk.byte_end),None,family,
                evidence.exact_comparison(chunk.text.encode(),'code_text').as_dict()))
        file = ResolvedFile(str(uuid4()),'source',primary,(primary,),raw.encode(),sha256(raw.encode()).hexdigest(),tuple(chunks))
        self.connection.catalog_files[file.identifier] = file
        inner = self.adapter(declaration='source:@code/nested.py#Policy.Inner').observe()
        self.assertEqual(inner.selection.kind,'family')
        self.assertEqual({member.chunk.name for member in inner.selection.members},
                         {'Policy.Inner','Policy.Inner.a','Policy.Inner.<end>'})
        continuation = self.adapter(declaration='source:@code/nested.py#Policy.Inner.<end>').observe()
        self.assertEqual((continuation.selection.kind,len(continuation.selection.members)),('chunk',1))
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_nested_class_source_includes_inner_methods_and_parent_continuations_remain_single

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_deleted_source_inheritance_checks_only_dependant_and_keeps_owned_original_source
    def test_deleted_source_inheritance_checks_only_dependant_and_keeps_owned_original_source(self):
        adapter = self.adapter()
        expected = adapter.observe()
        dependency = uuid4()
        identifier = self.writer.pin(expected,adapter.reread,dependency_id=dependency,kind='declared',
            declaration=adapter.declaration,captured_at='2026-10-09T00:00:00Z',authorization='initial_resolution')
        old = self.writer.read_baseline('owner',identifier)
        self.install_current_dependant(deleted_source=True)
        inherited_adapter = self.adapter(dependant_ref='owner:answer.md#Renamed')
        inherited = inherited_adapter.observe_inheritance()
        self.assertEqual((inherited.resolution.state,inherited.resolution.fault),('unresolved','missing_file'))
        self.assertEqual(inherited.repositories,('owner',))
        self.assertEqual(len(inherited.guards['files']),1)
        calls_before = len(self.capture_calls)
        new_id = self.writer.inherit_pin(inherited,inherited_adapter.reread_inheritance,
            previous_dependency=dependency,dependency_id=uuid4(),authorization='recognized_rename')
        self.assertEqual(self.capture_calls[calls_before:],['owner'])
        new = self.writer.read_baseline('owner',new_id)
        self.assertEqual(new.manifest.payload['members'],old.manifest.payload['members'])
        self.assertEqual(new.manifest.payload['pinnedHash'],old.manifest.payload['pinnedHash'])
        self.assertEqual(new.manifest.payload['dependantVersion'],'2')
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_deleted_source_inheritance_checks_only_dependant_and_keeps_owned_original_source

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_changed_dependant_during_deleted_source_inheritance_writes_nothing_new
    def test_changed_dependant_during_deleted_source_inheritance_writes_nothing_new(self):
        adapter = self.adapter()
        expected = adapter.observe()
        dependency = uuid4()
        self.writer.pin(expected,adapter.reread,dependency_id=dependency,kind='declared',
            declaration=adapter.declaration,captured_at='2026-10-09T00:00:00Z',authorization='initial_resolution')
        self.install_current_dependant(deleted_source=True)
        inherited_adapter = self.adapter(dependant_ref='owner:answer.md#Renamed')
        inherited = inherited_adapter.observe_inheritance()
        before = (len(self.connection.snapshots),len(self.connection.manifests),len(self.connection.dependencies))
        (self.owner_root/'answer.md').write_text('# Renamed\nChanged after observation\n')
        with self.assertRaises(evidence.EvidenceError) as error:
            self.writer.inherit_pin(inherited,inherited_adapter.reread_inheritance,
                previous_dependency=dependency,dependency_id=uuid4(),authorization='recognized_rename')
        self.assertEqual(error.exception.status,'changed_since_ingest')
        self.assertEqual((len(self.connection.snapshots),len(self.connection.manifests),len(self.connection.dependencies)),before)
        self.assertFalse(self.connection.guards)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_changed_dependant_during_deleted_source_inheritance_writes_nothing_new

# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_inheritance_observes_disabled_or_invalid_source_fault_without_source_capture
    def test_inheritance_observes_disabled_or_invalid_source_fault_without_source_capture(self):
        values = dict(self.settings.values)
        repositories = {name:dict(repo) for name,repo in self.settings.values['repos'].items()}
        repositories['source']['enabled'] = False
        values['repos'] = repositories
        self.settings = replace(self.settings,values=_freeze(values))
        for declaration, fault in (('source:source.md#Source','disabled_repository'), ('bad declaration','invalid_ref')):
            with self.subTest(declaration=declaration):
                adapter = self.adapter(declaration=declaration)
                inherited = adapter.observe_inheritance()
                self.assertEqual((inherited.resolution.state,inherited.resolution.fault),('invalid',fault))
                self.assertEqual(inherited.repositories,('owner',))
                self.assertEqual(len(inherited.guards['files']),1)
        self.assertEqual(self.capture_calls,['owner','owner'])
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_inheritance_observes_disabled_or_invalid_source_fault_without_source_capture



class PinObservationStoreTests(_support.PinObservationStoreTests):
# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationStoreTests.test_real_disk_callback_pins_exact_inputs_and_changed_full_file_writes_no_new_baseline
    def test_real_disk_callback_pins_exact_inputs_and_changed_full_file_writes_no_new_baseline(self):
        # The gate supplies its real disposable backend/default product init.
        # No credential, provider or simulated SQL boundary participates here.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            owner_root, source_root = home/'owner', home/'source'
            owner_root.mkdir()
            source_root.mkdir()
            owner_source = '# Answer\r\nComplete answer.\r\n'
            source_source = '# Source\r\nComplete source.\r\n'
            (owner_root/'answer.md').write_bytes(owner_source.encode())
            source_path = source_root/'source.md'
            source_path.write_bytes(source_source.encode())
            settings_path = home/'settings.toml'
            settings_path.write_text('[store]\naddress="postgresql://fixture@localhost/mycel_check_observation"\n'
                f'[repos.owner]\nenabled=true\nartifact_root={json.dumps(str(owner_root))}\n'
                f'[repos.source]\nenabled=true\nartifact_root={json.dumps(str(source_root))}\n')
            snapshot = load_settings(path=settings_path,home=home)
            dep = document('owner','answer.md',owner_source,version=1)
            src = document('source','source.md',source_source,version=11)
            catalog = SourceResolver(snapshot,(dep,src))
            resolution = catalog.resolve('source:source.md#Source')
            seed = evidence.PinInputs(snapshot,member(dep),dep,resolution.selection,
                                      evidence.CaptureLocation('disk'),resolution,catalog)
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                helper = evidence_checks.EvidenceStoreTests()
                helper.seed(connection,seed)
                adapter = observation.DiskPinObservation(connection,snapshot,'owner:answer.md#Answer','source:source.md#Source')
                expected = adapter.observe()
                writer = evidence.EvidenceStore(connection)
                identifier = writer.pin(expected,adapter.reread,dependency_id=uuid4(),kind='declared',
                    declaration=adapter.declaration,captured_at='2026-10-09T00:00:00Z',authorization='initial_resolution')
                baseline = writer.read_baseline('owner',identifier)
                self.assertEqual(baseline.manifest.payload['dependant']['hash'],sha256(owner_source.encode()).hexdigest())
                self.assertEqual(baseline.manifest.payload['members'][0]['evidence']['hash'],sha256(source_source.encode()).hexdigest())
                counts_sql = 'SELECT (SELECT count(*) FROM public.mycel_snapshots),'
                counts_sql += '(SELECT count(*) FROM public.mycel_manifests),(SELECT count(*) FROM public.mycel_evidence_owners),'
                counts_sql += '(SELECT count(*) FROM public.mycel_evidence_references),(SELECT count(*) FROM public.mycel_dependencies)'
                before = connection.execute(counts_sql).fetchone()
                # The selected section stays exact; the complete file changed.
                source_path.write_bytes(b'---\nrole: authored\n---\n' + source_source.encode())
                with self.assertRaises(evidence.EvidenceError) as error:
                    writer.pin(expected,adapter.reread,dependency_id=uuid4(),kind='declared',
                        declaration=adapter.declaration,captured_at='2026-10-09T00:01:00Z',authorization='initial_resolution')
                self.assertEqual(error.exception.status,'changed_since_ingest')
                self.assertIn('source:@artifact/source.md',error.exception.addresses)
                self.assertEqual(connection.execute(counts_sql).fetchone(),before)
                self.assertEqual(writer.read_baseline('owner',identifier),baseline)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationStoreTests.test_real_disk_callback_pins_exact_inputs_and_changed_full_file_writes_no_new_baseline
