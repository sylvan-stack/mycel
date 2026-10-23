"""Partial configured-store proofs for complete located publication.

Collection, dependency application and public command requirements remain open.
"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._activity import MutationActivity, activity_state
from mycel._capture import LocationId, capture_repository
from mycel._coverage import proves, require_check_database
from mycel._errors import MycelError
from mycel._located_reconciliation import LocatedCaptureStore, location_key
from mycel._resolver import SourceResolver
from mycel._settings import load_settings


class LocatedReconciliationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('This partial acceptance check requires a configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_located_identity_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.code = self.base / 'code'
        self.artifact = self.code / 'docs'
        self.artifact.mkdir(parents=True)
        self.config = self.base / 'settings.toml'
        self.settings = self.configure()

    def configure(self, *, code=None, artifact=None):
        self.config.write_text('[store]\naddress=' + json.dumps(
            self.store_fixture.backend.address(self.store_fixture.database)) + '\n[repos.fixture]\nenabled=true\ncode_root=' +
            json.dumps(str(code or self.code)) + '\nartifact_root=' + json.dumps(str(artifact or self.artifact)) + '\n')
        return load_settings(path=self.config, home=self.base)

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def git(self, *arguments, cwd=None):
        result = subprocess.run(['/usr/bin/git', *arguments], cwd=cwd or self.code, check=True, capture_output=True,
            timeout=10, env={**os.environ, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                'GIT_TERMINAL_PROMPT': '0'})
        return result.stdout.decode().strip()

    def commit(self, *, cwd=None):
        self.git('add', '--all', cwd=cwd)
        self.git('commit', '--message', 'Fixture', cwd=cwd)
        return self.git('rev-parse', 'HEAD', cwd=cwd)

    def initialize(self, raw=b'# Guide\nOriginal body.\n'):
        (self.artifact / 'guide.md').write_bytes(raw)
        self.git('init', '--initial-branch=fixture-main')
        return self.commit()

    def apply(self, connection, *, settings=None, **kwargs):
        selected = settings or self.settings
        return LocatedCaptureStore(connection).apply(selected, capture_repository(selected, 'fixture'), **kwargs)

    def resolve(self, connection, ref='fixture:@artifact/guide.md#Guide', *, identifier=None, settings=None):
        options = {} if identifier is None else {'kind': identifier.kind, 'location': location_key(identifier)}
        return SourceResolver.from_store(connection, settings or self.settings, **options).resolve(ref)

    def state(self, connection):
        tables = ('mycel_repository_state', 'mycel_files', 'mycel_file_aliases', 'mycel_file_versions',
                  'mycel_file_locations', 'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations',
                  'mycel_dependencies', 'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_snapshots')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
                for table in tables}

    def own_pin(self, connection, version, label):
        owner, dependency = uuid4(), uuid4()
        raw = label.encode()
        digest = sha256(raw).hexdigest()
        connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s)',
                           ('fixture', digest, raw, Jsonb({})))
        connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
                           (owner, 'fixture', 'baseline', label))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
                           (owner, 'fixture', digest))
        connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (dependency, 'fixture', version, 'fixture:@artifact/source.md#Source',
             'fixture:@artifact/source.md#Source', 'asserted', Jsonb({'label': label}), owner))
        return str(owner), str(dependency)

    @proves('MYC-1.7', 'MYC-1.31', 'MYC-1.34', kind='store')
    def test_file_reconciliation_reads_only_its_own_retained_chunk_versions(self):
        from mycel import _located_reconciliation as publication
        self.initialize()
        for number in range(3):
            (self.artifact / f'other{number}.md').write_text(f'# Other {number}\nSeparate body.\n')
        self.commit()
        with self.connect() as connection:
            first = self.apply(connection)
            self.assertTrue(first.changed)
            before = self.state(connection)
            known = publication._known
            checked = []
            def only_owned(file_id, old_location, rows):
                self.assertTrue(rows)
                self.assertEqual({str(row[0]) for row in rows}, {file_id},
                                 'One file must not repeatedly fetch every other file in the repository')
                checked.append(file_id)
                return known(file_id, old_location, rows)
            with patch.object(publication, '_known', side_effect=only_owned):
                quiet = self.apply(connection)
            self.assertFalse(quiet.changed)
            self.assertGreaterEqual(len(set(checked)), 4)
            self.assertEqual(self.state(connection), before)
            self.assertEqual({(f.binding.primary.address, f.location): f.chunk_versions for f in quiet.files},
                             {(f.binding.primary.address, f.location): f.chunk_versions for f in first.files})

    @proves('MYC-1.30', 'MYC-1.31', kind='store')
    def test_publish_disk_branches_and_untracked_stash_without_changing_checkout(self):
        self.initialize()
        self.git('branch', 'feature')
        (self.artifact / 'guide.md').write_bytes(b'# Guide\nStashed body.\n')
        (self.artifact / 'untracked.md').write_bytes(b'# Extra\nUntracked stash document.\n')
        self.git('stash', 'push', '--include-untracked', '--message', 'Saved')
        stash = self.git('rev-parse', 'refs/stash')
        head, status = self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')
        before_bytes = (self.artifact / 'guide.md').read_bytes()
        with self.connect() as connection:
            result = self.apply(connection)
            disk = self.resolve(connection).selection
            for ref in ('refs/heads/fixture-main', 'refs/heads/feature'):
                branch = self.resolve(connection, identifier=LocationId('branch', 'code', ref)).selection
                self.assertEqual(branch.file.identifier, disk.file.identifier)
                self.assertEqual(branch.members[0].chunk.identifier, disk.members[0].chunk.identifier)
                self.assertEqual(branch.members[0].chunk.version, disk.members[0].chunk.version)
            saved = self.resolve(connection, identifier=LocationId('stash', 'code', stash)).selection
            self.assertEqual(saved.members[0].chunk.identifier, disk.members[0].chunk.identifier)
            self.assertNotEqual(saved.members[0].chunk.version, disk.members[0].chunk.version)
            self.assertEqual(saved.members[0].chunk.source, b'# Guide\nStashed body.\n')
            self.assertIsNotNone(self.resolve(connection, 'fixture:@artifact/untracked.md#Extra',
                                              identifier=LocationId('stash', 'code', stash)).selection)
            self.assertEqual(self.resolve(connection, 'fixture:@artifact/untracked.md').fault, 'missing_file')
            self.assertEqual([file.location.kind for file in result.files],
                             ['disk', 'branch', 'branch', 'stash', 'stash'])
        self.assertEqual((self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1'),
                          (self.artifact / 'guide.md').read_bytes()), (head, status, before_bytes))

    @proves('MYC-1.31', 'MYC-1.34', kind='store')
    def test_branch_only_file_restores_its_exact_identity_and_own_pin(self):
        self.initialize()
        path = self.artifact / 'guide.md'
        raw = path.read_bytes()
        path.unlink()
        with self.connect() as connection:
            first = self.apply(connection)
            self.assertEqual([file.location.kind for file in first.files], ['branch'])
            original = first.files[0]
            old_pin = self.own_pin(connection, original.chunk_versions[0][1], 'original-version-pin')
            path.write_bytes(b'# Guide\nLater disk body.\n')
            later = self.apply(connection).files[0]
            self.assertEqual(later.binding.identifier, original.binding.identifier)
            self.assertEqual(later.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertNotEqual(later.chunk_versions[0][1], original.chunk_versions[0][1])
            later_pin = self.own_pin(connection, later.chunk_versions[0][1], 'later-version-pin')
            path.write_bytes(raw)
            restored = self.apply(connection).files[0]
            self.assertEqual(restored.chunk_versions, original.chunk_versions)
            self.assertEqual(restored.identity.decisions[0].pin_decision, 'restore_existing')
            records = connection.execute('SELECT dependant_version,baseline_owner,id FROM public.mycel_dependencies ORDER BY dependant_version').fetchall()
            self.assertEqual({version: (str(owner), str(dependency)) for version, owner, dependency in records},
                             {original.chunk_versions[0][1]: old_pin, later.chunk_versions[0][1]: later_pin})

    @proves('MYC-16.2', 'MYC-1.31', 'MYC-1.33', kind='store')
    def test_independent_checkout_anchors_do_not_merge_equal_branch_names_paths_or_bytes(self):
        self.initialize()
        other = self.base / 'artifact-checkout'
        (other / 'docs').mkdir(parents=True)
        (other / 'docs' / 'guide.md').write_bytes(b'# Guide\nOriginal body.\n')
        self.git('init', '--initial-branch=fixture-main', cwd=other)
        self.commit(cwd=other)
        settings = self.configure(artifact=other)
        with self.connect() as connection:
            result = self.apply(connection, settings=settings)
            branches = [file for file in result.files if file.location.kind == 'branch']
            self.assertEqual({file.location.checkout for file in branches}, {'code', 'artifact'})
            self.assertEqual(len({file.binding.identifier for file in branches}), 2)
            for file in branches:
                resolved = self.resolve(connection, file.binding.primary.address + '#Guide',
                                        identifier=file.location, settings=settings).selection
                self.assertEqual(resolved.file.identifier, file.binding.identifier)
            bare = self.resolve(connection, 'fixture:docs/guide.md#Guide', settings=settings)
            self.assertEqual(bare.fault, 'ambiguous_path')

    @proves('MYC-1.31', 'MYC-1.33', kind='store')
    def test_root_retarget_preserves_old_versions_but_creates_new_file_identity(self):
        self.initialize()
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            other = self.base / 'other'
            docs = other / 'docs'
            docs.mkdir(parents=True)
            (docs / 'guide.md').write_bytes(b'# Guide\nOriginal body.\n')
            self.git('init', '--initial-branch=fixture-main', cwd=other)
            self.commit(cwd=other)
            settings = self.configure(code=other, artifact=docs)
            current = self.apply(connection, settings=settings).files[0]
            self.assertNotEqual(current.binding.identifier, original.binding.identifier)
            self.assertNotEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_file_versions').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone()[0], 2)

    @proves('MYC-1.31', 'MYC-1.34', kind='store')
    def test_removed_git_locations_retire_once_without_collecting_their_own_evidence(self):
        self.initialize()
        self.git('branch', 'feature')
        (self.artifact / 'extra.md').write_bytes(b'# Extra\nSaved only.\n')
        self.git('stash', 'push', '--include-untracked', '--message', 'Saved')
        stash = self.git('rev-parse', 'refs/stash')
        with self.connect() as connection:
            first = self.apply(connection)
            extra = next(file for file in first.files if file.binding.primary.path == 'extra.md')
            owner, _ = self.own_pin(connection, extra.chunk_versions[0][1], 'stash-owned-pin')
            self.git('branch', '--delete', 'feature')
            self.git('stash', 'drop', 'stash@{0}')
            changed = self.apply(connection)
            self.assertEqual(len(changed.retired_locations), 3)
            self.assertEqual(self.resolve(connection, 'fixture:@artifact/extra.md#Extra',
                identifier=LocationId('stash', 'code', stash)).fault, 'missing_file')
            self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_chunk_versions WHERE id=%s',
                                                    (extra.chunk_versions[0][1],)).fetchone())
            self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_evidence_owners WHERE id=%s', (owner,)).fetchone())
            before = self.state(connection)
            self.assertFalse(self.apply(connection).changed)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-1.22', 'MYC-1.31', kind='store')
    def test_complete_publication_noop_and_batch_callback_audit_failure_are_atomic(self):
        self.initialize()
        with self.connect() as connection:
            self.apply(connection)
            before = self.state(connection)
            with MutationActivity(connection, build=1).session() as audit:
                self.assertFalse(self.apply(connection, activity=audit).changed)
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity').fetchone()[0], 0)
                self.assertEqual(self.state(connection), before)
                callback = unittest.mock.Mock(side_effect=RuntimeError('no-op callback must not run'))
                self.assertFalse(self.apply(connection, batch_handoff=callback, file_handoff=callback).changed)
                callback.assert_not_called()
                path = self.artifact / 'guide.md'
                path.write_bytes(b'# Renamed\nOriginal body.\n')
                def fail(conn, result):
                    self.assertIs(conn, connection)
                    self.assertEqual(result.files[0].identity.decisions[0].pin_decision, 'inherit_existing')
                    self.assertEqual(self.resolve_in_transaction(conn, result.files[0]), b'# Renamed\nOriginal body.\n')
                    self.assertEqual(len(result.files), 2)
                    raise RuntimeError('prospective batch refused')
                with self.assertRaises(RuntimeError):
                    self.apply(connection, activity=audit, batch_handoff=fail)
                self.assertEqual(self.state(connection), before)
                with patch.object(audit, '_details', side_effect=RuntimeError('audit failed')):
                    with self.assertRaises(RuntimeError):
                        self.apply(connection, activity=audit)
                self.assertEqual(self.state(connection), before)
                result = self.apply(connection, activity=audit)
                entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
                detail = activity_state(connection, entry)
                self.assertEqual(detail['counts'], result.counts)
                self.assertEqual(detail['files'][0]['location'], 'disk')
                audit.finish('done')

    def resolve_in_transaction(self, connection, file):
        return bytes(connection.execute('SELECT v.source_bytes FROM public.mycel_chunk_versions v '
            'JOIN public.mycel_locations l ON l.chunk_version=v.id WHERE l.file_location=%s',
            (file.binding.location,)).fetchone()[0])

    @proves('MYC-1.22', 'MYC-1.31', kind='store')
    def test_concurrent_catalog_change_and_failed_complete_parse_publish_no_partial_rows(self):
        self.initialize()
        with self.connect() as connection:
            self.apply(connection)
            manifest = capture_repository(self.settings, 'fixture')
            expected = None
            from mycel import _located_reconciliation
            def race(settings, repository, **kwargs):
                nonlocal expected
                result = capture_repository(settings, repository, **kwargs)
                with self.connect() as other:
                    other.execute("UPDATE public.mycel_file_locations SET metadata=metadata || %s WHERE kind='disk'",
                                  (Jsonb({'externalObservation': True}),))
                expected = self.state(connection)
                return result
            with patch.object(_located_reconciliation, 'capture_repository', side_effect=race):
                with self.assertRaises(MycelError):
                    LocatedCaptureStore(connection).apply(self.settings, manifest)
            self.assertEqual(self.state(connection), expected)
            before = self.state(connection)
            (self.artifact / 'guide.md').write_bytes(b'# Guide\n\xff undecodable body\n')
            failed = capture_repository(self.settings, 'fixture')
            self.assertFalse(failed.deletion_safe)
            with self.assertRaises(MycelError):
                LocatedCaptureStore(connection).apply(self.settings, failed)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-1.8', 'MYC-1.22', 'MYC-1.31', kind='store')
    def test_changed_local_inventory_incomplete_parse_and_empty_disk_refuse_before_writes(self):
        self.initialize()
        with self.connect() as connection:
            self.apply(connection)
            before = self.state(connection)
            manifest = capture_repository(self.settings, 'fixture')
            with self.assertRaises(MycelError):
                LocatedCaptureStore(connection).apply(self.settings, replace(manifest, complete=False))
            from mycel import _located_reconciliation
            calls = 0
            def changed(settings, repository, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    self.git('branch', 'added-during-publication')
                return capture_repository(settings, repository, **kwargs)
            with patch.object(_located_reconciliation, 'capture_repository', side_effect=changed):
                with self.assertRaises(MycelError):
                    LocatedCaptureStore(connection).apply(self.settings, manifest)
            self.assertEqual(self.state(connection), before)
            self.git('branch', '--delete', 'added-during-publication')
            (self.artifact / 'guide.md').unlink()
            with self.assertRaises(MycelError) as error:
                self.apply(connection)
            self.assertEqual(error.exception.code.value, 'refused')
            self.assertEqual(self.state(connection), before)
            away = self.apply(connection, confirm_empty=True)
            self.assertEqual([file.location.kind for file in away.files], ['branch'])
            self.assertEqual(self.resolve(connection).fault, 'missing_file')

    @proves('MYC-1.19', 'MYC-1.31', 'MYC-1.33', kind='store')
    def test_disk_move_and_reused_original_path_preserve_each_retained_branch_binding(self):
        self.initialize()
        path = self.artifact / 'guide.md'
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            path.rename(self.artifact / 'moved.md')
            path.write_bytes(b'# Other\nA distinct replacement.\n')
            result = self.apply(connection)
            moved = self.resolve(connection, 'fixture:@artifact/moved.md#Guide').selection
            replacement = self.resolve(connection, 'fixture:@artifact/guide.md#Other').selection
            retained = self.resolve(connection, identifier=LocationId('branch', 'code', 'refs/heads/fixture-main')).selection
            self.assertEqual(moved.file.identifier, original.binding.identifier)
            self.assertNotEqual(replacement.file.identifier, original.binding.identifier)
            self.assertEqual(retained.file.identifier, original.binding.identifier)
            self.assertEqual(retained.members[0].chunk.version, original.chunk_versions[0][1])
            self.assertEqual(len(result.files), 3)

    @proves('MYC-16.2', 'MYC-1.19', 'MYC-1.31', 'MYC-1.33', kind='store')
    def test_existing_disk_handoff_upgrades_into_complete_locations_and_checked_git_move(self):
        self.initialize()
        path = self.artifact / 'guide.md'
        from mycel._capture import FileAlias
        from mycel._disk_reconciliation import DiskCaptureStore, GitFileMove
        with self.connect() as connection:
            original = DiskCaptureStore(connection).apply(self.settings, capture_repository(self.settings, 'fixture')).files[0]
            first = self.apply(connection)
            self.assertEqual({file.binding.identifier for file in first.files}, {original.binding.identifier})
            self.assertEqual({file.chunk_versions for file in first.files}, {original.chunk_versions})
            before_commit = self.git('rev-parse', 'HEAD')
            raw = path.read_bytes()
            path.unlink()
            moved = self.artifact / 'moved.md'
            moved.write_bytes(raw)
            after_commit = self.commit()
            move = GitFileMove(original.binding.identifier, original.binding.version, before_commit, after_commit,
                               FileAlias('artifact', 'guide.md'), FileAlias('artifact', 'moved.md'))
            current = self.apply(connection, recognized_moves=(move,)).files[0]
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions, original.chunk_versions)
            branch = self.resolve(connection, 'fixture:@artifact/moved.md#Guide',
                                  identifier=LocationId('branch', 'code', 'refs/heads/fixture-main')).selection
            self.assertEqual(branch.file.identifier, original.binding.identifier)

    @proves('MYC-1.31', 'MYC-1.34', kind='store')
    def test_same_exact_child_text_keeps_located_names_under_distinct_parent_versions(self):
        self.initialize(b'# Parent\nOriginal.\n## Child\nIdentical child.\n')
        self.git('branch', 'old-parent')
        (self.artifact / 'guide.md').write_bytes(b'# Renamed\nOriginal.\n## Child\nIdentical child.\n')
        self.commit()
        with self.connect() as connection:
            self.apply(connection)
            current = self.resolve(connection, 'fixture:@artifact/guide.md#Renamed > Child').selection.members[0].chunk
            old = self.resolve(connection, 'fixture:@artifact/guide.md#Parent > Child',
                               identifier=LocationId('branch', 'code', 'refs/heads/old-parent')).selection.members[0].chunk
            self.assertEqual((current.identifier, current.version, current.source), (old.identifier, old.version, old.source))
            before = self.state(connection)
            self.assertFalse(self.apply(connection).changed)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-16.2', 'MYC-1.19', 'MYC-1.31', 'MYC-1.33', kind='store')
    def test_first_discovery_maps_checked_git_rename_across_disk_and_local_branches(self):
        self.initialize()
        self.git('branch', 'old-place')
        raw = (self.artifact / 'guide.md').read_bytes()
        (self.artifact / 'guide.md').unlink()
        (self.artifact / 'moved.md').write_bytes(raw)
        self.commit()
        head, status = self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')
        with self.connect() as connection:
            result = self.apply(connection)
            self.assertEqual(len({file.binding.identifier for file in result.files}), 1)
            self.assertEqual(len({file.chunk_versions for file in result.files}), 1)
            old = self.resolve(connection, identifier=LocationId('branch', 'code', 'refs/heads/old-place')).selection
            moved = self.resolve(connection, 'fixture:@artifact/moved.md#Guide').selection
            self.assertEqual(old.file.identifier, moved.file.identifier)
            proofs = connection.execute("SELECT metadata->'gitCorrespondence' FROM public.mycel_file_locations "
                "WHERE metadata ? 'gitCorrespondence'").fetchall()
            self.assertEqual(len(proofs), 1)
            self.assertEqual(proofs[0][0][0]['similarity'], 100)
            state = self.state(connection)
            self.assertFalse(self.apply(connection).changed)
            self.assertEqual(self.state(connection), state)
        self.assertEqual((self.git('rev-parse', 'HEAD'), self.git('status', '--porcelain=v1')), (head, status))

    @proves('MYC-16.2', 'MYC-1.19', 'MYC-1.31', 'MYC-1.33', 'MYC-1.34', kind='store')
    def test_committed_inode_changing_move_automatically_preserves_ids_versions_and_own_pin(self):
        self.initialize()
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            pin = self.own_pin(connection, original.chunk_versions[0][1], 'before-automatic-move')
            raw = (self.artifact / 'guide.md').read_bytes()
            (self.artifact / 'moved.md').write_bytes(raw)
            (self.artifact / 'guide.md').unlink()
            self.commit()
            current = self.apply(connection).files[0]
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions, original.chunk_versions)
            self.assertEqual(current.identity.decisions[0].pin_decision, 'restore_existing')
            owned = connection.execute('SELECT baseline_owner,id FROM public.mycel_dependencies').fetchone()
            self.assertEqual(tuple(map(str, owned)), pin)
            metadata = connection.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s',
                                          (current.binding.location,)).fetchone()[0]
            self.assertEqual(metadata['moveEvidence'][-1]['previousVersion'], original.binding.version)
            self.assertEqual(self.resolve(connection).fault, 'missing_file')
            state = self.state(connection)
            self.assertFalse(self.apply(connection).changed)
            self.assertEqual(self.state(connection), state)

    @proves('MYC-16.2', 'MYC-1.19', 'MYC-1.31', 'MYC-1.33', 'MYC-1.34', kind='store')
    def test_renamed_tracked_stash_keeps_disk_identity_and_exact_stash_version(self):
        self.initialize()
        raw = (self.artifact / 'guide.md').read_bytes()
        (self.artifact / 'guide.md').unlink()
        (self.artifact / 'saved.md').write_bytes(raw)
        self.git('add', '--all')
        self.git('stash', 'push', '--message', 'Moved tracked file')
        stash = self.git('rev-parse', 'refs/stash')
        with self.connect() as connection:
            self.apply(connection)
            disk = self.resolve(connection).selection
            saved = self.resolve(connection, 'fixture:@artifact/saved.md#Guide',
                                 identifier=LocationId('stash', 'code', stash)).selection
            self.assertEqual(saved.file.identifier, disk.file.identifier)
            self.assertEqual(saved.members[0].chunk.identifier, disk.members[0].chunk.identifier)
            self.assertEqual(saved.members[0].chunk.version, disk.members[0].chunk.version)

    @proves('MYC-16.2', 'MYC-1.31', 'MYC-1.34', kind='store')
    def test_edited_git_rename_keeps_identity_but_creates_a_distinct_exact_version(self):
        raw = b'# Guide\n' + b'Original complete paragraph.\n' * 20
        self.initialize(raw)
        self.git('branch', 'old-place')
        with self.connect() as connection:
            original = self.apply(connection).files[0]
            pin = self.own_pin(connection, original.chunk_versions[0][1], 'original-rename-pin')
            changed = raw + b'An added exact paragraph.\n'
            (self.artifact / 'moved.md').write_bytes(changed)
            (self.artifact / 'guide.md').unlink()
            self.commit()
            current = self.apply(connection).files[0]
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertNotEqual(current.chunk_versions[0][1], original.chunk_versions[0][1])
            self.assertEqual(current.identity.decisions[0].pin_decision, 'requires_authorized_capture')
            old = self.resolve(connection, identifier=LocationId('branch', 'code', 'refs/heads/old-place')).selection
            self.assertEqual(old.members[0].chunk.version, original.chunk_versions[0][1])
            owned = connection.execute('SELECT baseline_owner,id FROM public.mycel_dependencies').fetchone()
            self.assertEqual(tuple(map(str, owned)), pin)

    @proves('MYC-16.2', 'MYC-1.22', 'MYC-1.31', kind='store')
    def test_git_correspondence_recheck_failure_rolls_back_every_location(self):
        self.initialize()
        self.git('branch', 'old-place')
        (self.artifact / 'guide.md').rename(self.artifact / 'moved.md')
        self.commit()
        from mycel import _located_reconciliation
        calls = 0
        original = _located_reconciliation.build_correspondences
        def changed(inputs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MycelError('invalid_input', 'Rename evidence disappeared before publication.')
            return original(inputs)
        with self.connect() as connection:
            before = self.state(connection)
            with patch.object(_located_reconciliation, 'build_correspondences', side_effect=changed):
                with self.assertRaises(MycelError):
                    self.apply(connection)
            self.assertEqual(calls, 2)
            self.assertEqual(self.state(connection), before)

    @proves('MYC-16.2', 'MYC-1.31', 'MYC-1.33', kind='store')
    def test_copied_paths_and_synthetic_renames_in_unrelated_histories_keep_distinct_ids(self):
        raw = b'# Guide\nExact complete text.\n'
        self.initialize(raw)
        (self.artifact / 'copied.md').write_bytes(raw)
        self.commit()
        self.git('checkout', '--orphan', 'unrelated')
        self.git('rm', '--cached', '-r', 'docs')
        (self.artifact / 'guide.md').unlink()
        (self.artifact / 'copied.md').unlink()
        (self.artifact / 'unrelated.md').write_bytes(raw)
        self.commit()
        with self.connect() as connection:
            self.apply(connection)
            disk = self.resolve(connection, 'fixture:@artifact/unrelated.md#Guide').selection
            branch = LocationId('branch', 'code', 'refs/heads/fixture-main')
            original = self.resolve(connection, identifier=branch).selection
            copied = self.resolve(connection, 'fixture:@artifact/copied.md#Guide', identifier=branch).selection
            self.assertEqual(len({disk.file.identifier, original.file.identifier, copied.file.identifier}), 3)

    @proves('MYC-1.22', 'MYC-1.31', kind='store')
    def test_automatic_disk_move_refuses_a_reused_old_physical_path_without_writing(self):
        self.initialize()
        with self.connect() as connection:
            self.apply(connection)
            raw = (self.artifact / 'guide.md').read_bytes()
            (self.artifact / 'moved.md').write_bytes(raw)
            (self.artifact / 'guide.md').unlink()
            self.commit()
            (self.artifact / 'guide.md').write_bytes(b'# Other\nDistinct replacement at the old place.\n')
            state = self.state(connection)
            with self.assertRaises(MycelError):
                self.apply(connection)
            self.assertEqual(self.state(connection), state)
