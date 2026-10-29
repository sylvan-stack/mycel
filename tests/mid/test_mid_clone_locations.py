"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_clone_locations as _support
from test_clone_locations import (
    CloneScopeTests,
    CloneStoreTests,
    MycelError,
    Path,
    RepositoryLocations,
    json,
    load_settings,
    os,
    patch,
    replace,
    tempfile,
    unittest,
)


class CloneScopeTests(_support.CloneScopeTests):
# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneScopeTests.test_listed_clone_wins_over_organization_and_selects_only_its_checkout
    def test_listed_clone_wins_over_organization_and_selects_only_its_checkout(self):
        settings = self.settings(readonly=self.readonly)
        with patch('subprocess.Popen', side_effect=AssertionError('Scope must not call Git')):
            locations = RepositoryLocations(settings, cwd=self.clone)
            selected, = locations.resolve_scope()
            self.assertEqual((selected.name,selected.code.path,selected.documents.path),
                             ('fixture',self.clone,self.documents))
            self.assertEqual(selected.location,str(self.clone))
            self.assertEqual(selected.readonly_root,self.readonly)
            primary, = locations.resolve_scope(cwd=self.primary)
            self.assertIsNone(primary.location)
            self.assertEqual(primary.code.path,self.primary)
            explicit, = locations.resolve_scope(['fixture'], cwd=self.readonly)
            self.assertEqual(explicit.code.path,self.readonly)
            self.assertEqual(RepositoryLocations(settings,cwd=self.base).named('fixture')[0].code.path,self.primary)
            self.assertEqual(settings.values['repos']['fixture']['code_root'],str(self.primary))
# TEST-TIER-END tests/test_clone_locations.py::CloneScopeTests.test_listed_clone_wins_over_organization_and_selects_only_its_checkout

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneScopeTests.test_clone_paths_are_typed_and_home_expanded_and_baseline_must_be_listed
    def test_clone_paths_are_typed_and_home_expanded_and_baseline_must_be_listed(self):
        for clones in ('a folder', ['relative/folder'], [False], [None]):
            with self.subTest(clones=clones):
                self.assertFalse(self.settings(clones=clones).valid)
        settings = self.settings(clones=['~/blue/fixture'],readonly='~/blue/fixture')
        self.assertTrue(settings.valid)
        repository, = RepositoryLocations(settings,cwd=self.clone).named('fixture')
        self.assertEqual(repository.code.path,self.clone)
        repository.require_folders()
        bad = self.settings(readonly=self.base/'unlisted')
        with self.assertRaises(MycelError):
            RepositoryLocations(bad).named('fixture')[0].require_folders()
# TEST-TIER-END tests/test_clone_locations.py::CloneScopeTests.test_clone_paths_are_typed_and_home_expanded_and_baseline_must_be_listed

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneScopeTests.test_symlink_alias_names_one_location_and_unknown_folders_register_nothing
    def test_symlink_alias_names_one_location_and_unknown_folders_register_nothing(self):
        alias=self.base/'alias';alias.symlink_to(self.clone,target_is_directory=True)
        settings=self.settings(clones=[str(self.clone),str(alias)])
        locations=RepositoryLocations(settings,cwd=alias)
        repository,=locations.resolve_scope()
        self.assertEqual(len(repository.clones),1)
        self.assertEqual(repository.location,str(self.clone))
        self.assertEqual(repository.code.path,self.clone)
        unlisted=self.base/'unlisted'/'fixture';unlisted.mkdir(parents=True)
        # The containing organization can still be selected, but no new
        # repository or checkout is inferred from an unlisted basename.
        scope=locations.resolve_scope(cwd=unlisted)
        self.assertEqual([item.name for item in scope],['fixture'])
        self.assertEqual(scope[0].code.path,self.primary)
# TEST-TIER-END tests/test_clone_locations.py::CloneScopeTests.test_symlink_alias_names_one_location_and_unknown_folders_register_nothing

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneScopeTests.test_unresolvable_clone_remains_a_local_repository_fault
    def test_unresolvable_clone_remains_a_local_repository_fault(self):
        left=self.base/'loop-a';right=self.base/'loop-b'
        left.symlink_to(right);right.symlink_to(left)
        settings=self.settings(clones=[str(left)])
        locations=RepositoryLocations(settings)
        repository,=locations.named('fixture')
        with self.assertRaises(MycelError):
            repository.require_folders()
        self.assertIn('fault',repository.report())
# TEST-TIER-END tests/test_clone_locations.py::CloneScopeTests.test_unresolvable_clone_remains_a_local_repository_fault



class CloneStoreTests(_support.CloneStoreTests):
# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneStoreTests.test_clones_share_identity_and_exact_versions_and_keep_each_others_locations
    def test_clones_share_identity_and_exact_versions_and_keep_each_others_locations(self):
        self.ingest(self.primary)
        with self.base.connect() as connection:
            original=self.member(connection,self.primary)
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            same=self.member(connection,self.secondary)
            self.assertEqual((same.identifier,same.version),(original.identifier,original.version))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions '
                'WHERE chunk_id=%s',(same.identifier,)).fetchone(),(1,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_locations l "
                "JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version WHERE v.chunk_id=%s AND l.kind='disk'",
                (same.identifier,)).fetchone(),(2,))
        (self.clone/'value.py').write_text('def value():\n    return 2\n')
        self.ingest(self.secondary)
        self.ingest(self.primary)
        with self.base.connect() as connection:
            primary=self.member(connection,self.primary);secondary=self.member(connection,self.secondary)
            self.assertEqual(primary.identifier,secondary.identifier)
            self.assertEqual(primary.version,original.version)
            self.assertNotEqual(primary.version,secondary.version)
            self.assertIn(b'return 2',secondary.source)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions '
                'WHERE chunk_id=%s',(same.identifier,)).fetchone(),(2,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_locations l "
                "JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version WHERE v.chunk_id=%s AND l.kind='disk'",
                (same.identifier,)).fetchone(),(2,))
# TEST-TIER-END tests/test_clone_locations.py::CloneStoreTests.test_clones_share_identity_and_exact_versions_and_keep_each_others_locations

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneStoreTests.test_two_public_passes_capture_concurrently_and_publish_both_clones
    def test_two_public_passes_capture_concurrently_and_publish_both_clones(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier,Event
        from mycel._located_reconciliation import LocatedCaptureStore
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        self.ingest(self.primary);self.ingest(self.secondary)
        self.source.write_text('def value():\n    return 10\n')
        (self.clone/'value.py').write_text('def value():\n    return 20\n')
        simultaneous=Barrier(2);primary_captured=Event();primary_done=Event()
        original=LocatedCaptureStore.capture
        def capture(store,settings,repository):
            manifest=original(store,settings,repository)
            if settings._cwd==self.base.code:
                primary_captured.set()
            simultaneous.wait(timeout=20)
            if settings._cwd==self.clone:
                self.assertTrue(primary_done.wait(timeout=20))
            return manifest
        def run(settings):
            try:
                return ingest(Invocation('ingest',repositories=('fixture',),settings=settings))
            finally:
                if settings._cwd==self.base.code:primary_done.set()
        with patch('mycel._build_identity.current_build',return_value=1), \
                patch.object(LocatedCaptureStore,'capture',capture), ThreadPoolExecutor(2) as pool:
            first=pool.submit(run,self.primary)
            # The allocator deliberately refuses peers without waiting. Start
            # the second invocation after those short guards are released;
            # both captures must still finish before either can publish.
            self.assertTrue(primary_captured.wait(timeout=20))
            second=pool.submit(run,self.secondary)
            results=(first.result(timeout=30),second.result(timeout=30))
        self.assertTrue(all(result.status==0 for result in results),[r.value for r in results])
        with self.base.connect() as connection:
            self.assertIn(b'return 10',self.member(connection,self.primary).source)
            self.assertIn(b'return 20',self.member(connection,self.secondary).source)
# TEST-TIER-END tests/test_clone_locations.py::CloneStoreTests.test_two_public_passes_capture_concurrently_and_publish_both_clones

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneStoreTests.test_location_reservations_are_distinct_and_both_exclude_removal
    def test_location_reservations_are_distinct_and_both_exclude_removal(self):
        from mycel._locks import location_guard,removal_guard
        from mycel._store import checked_store
        with self.base.connect() as first,self.base.connect() as second,self.base.connect() as third:
            with checked_store(first),checked_store(second),checked_store(third), \
                    location_guard(first,'fixture',RepositoryLocations(self.primary).named('fixture')[0].disk_location), \
                    location_guard(second,'fixture',RepositoryLocations(self.secondary).named('fixture')[0].disk_location):
                with self.assertRaises(MycelError) as blocked:
                    with removal_guard(third,'fixture'):pass
                self.assertEqual(blocked.exception.code,'busy')
                with self.assertRaises(MycelError) as duplicate:
                    with location_guard(third,'fixture','disk'):pass
                self.assertEqual(duplicate.exception.code,'busy')
# TEST-TIER-END tests/test_clone_locations.py::CloneStoreTests.test_location_reservations_are_distinct_and_both_exclude_removal

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneStoreTests.test_capture_cannot_be_published_as_a_different_clone
    def test_capture_cannot_be_published_as_a_different_clone(self):
        from mycel._capture import capture_repository
        from mycel._located_reconciliation import LocatedCaptureStore
        self.ingest(self.primary)
        manifest=capture_repository(self.primary,'fixture')
        with self.base.connect() as connection:
            before=self.base.state(connection)
            with self.assertRaises(MycelError) as refusal:
                LocatedCaptureStore(connection).apply(self.secondary,manifest,publish_capture=True)
            self.assertEqual(refusal.exception.code,'invalid_input')
            self.assertEqual(self.base.state(connection),before)
# TEST-TIER-END tests/test_clone_locations.py::CloneStoreTests.test_capture_cannot_be_published_as_a_different_clone
