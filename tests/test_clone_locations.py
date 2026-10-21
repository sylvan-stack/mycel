"""Configured clones share repository identity and retain independent locations."""
from dataclasses import replace
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._scope import RepositoryLocations
from mycel._settings import load_settings


class CloneScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.primary = self.base / 'fixture'
        self.clone = self.base / 'blue' / 'fixture'
        self.readonly = self.base / 'readonly' / 'fixture'
        self.documents = self.base / 'documents'
        for path in (self.primary, self.clone, self.readonly, self.documents):
            path.mkdir(parents=True)
            (path / '.git').mkdir()
        self.config = self.base / 'settings.toml'

    def settings(self, *, clones=None, readonly=None):
        lines = ['[store]', 'address="postgresql://fixture@unreachable.invalid/owner"',
                 '[organizations.stack]', 'root='+json.dumps(str(self.base)),
                 '[repos.fixture]', 'enabled=true', 'code_root='+json.dumps(str(self.primary)),
                 'artifact_root='+json.dumps(str(self.documents)),
                 'code_clones='+json.dumps([str(self.clone),str(self.readonly)] if clones is None else clones)]
        if readonly is not None:
            lines.append('readonly_root='+json.dumps(str(readonly)))
        self.config.write_text('\n'.join(lines)+'\n')
        return load_settings(path=self.config, home=self.base)

    @proves('MYC-5.18','MYC-1.38')
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

    @proves('MYC-5.18')
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

    @proves('MYC-5.18','MYC-1.38')
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

    @proves('MYC-5.18')
    def test_unresolvable_clone_remains_a_local_repository_fault(self):
        left=self.base/'loop-a';right=self.base/'loop-b'
        left.symlink_to(right);right.symlink_to(left)
        settings=self.settings(clones=[str(left)])
        locations=RepositoryLocations(settings)
        repository,=locations.named('fixture')
        with self.assertRaises(MycelError):
            repository.require_folders()
        self.assertIn('fault',repository.report())
