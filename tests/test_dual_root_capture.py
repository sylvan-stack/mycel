"""Configured-store proofs for document origin under both independent roots."""

import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from mycel._capture import LocationId, capture_repository
from mycel._coverage import proves, require_check_database
from mycel._disk_reconciliation import DiskCaptureStore
from mycel._located_reconciliation import LocatedCaptureStore, location_key
from mycel._resolver import SourceResolver
from mycel._settings import load_settings


class DualRootCaptureStoreTests(unittest.TestCase):
    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('This acceptance check requires a configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_dual_root_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.roots = {'code': self.base / 'checkout', 'artifact': self.base / 'artifacts'}
        self.sources = {}
        for name, root in self.roots.items():
            root.mkdir()
            for path in ('README.md', 'docs/guide.md'):
                raw = f'# Overview\n{name} {path} body.\n## Detail\nExact {name} detail.\n'.encode()
                self.write(root, path, raw)
                self.sources[(name, path)] = raw
            for path in ('private/excluded.md', 'nested/build/excluded.md', 'ignored.ignore.md'):
                self.write(root, path, b'# Excluded\nNever indexed.\n')
            self.write(root, '.gitignore', b'*.ignore.md\n')
        self.write(self.roots['code'], 'src/worker.py', b'def work():\n    return 1\n')
        self.write(self.roots['code'], 'outside/excluded.py', b'def excluded():\n    return 2\n')
        self.write(self.roots['artifact'], 'src/excluded.py', b'def excluded():\n    return 3\n')
        config = self.base / 'settings.toml'
        config.write_text('[store]\naddress=' + json.dumps(
            self.store_fixture.backend.address(self.store_fixture.database)) + '\n[repos.fixture]\nenabled=true\n'
            'code_root=' + json.dumps(str(self.roots['code'])) + '\nartifact_root=' +
            json.dumps(str(self.roots['artifact'])) + '\ncode_subdirs=["src"]\n'
            '[scan]\nskip_folders=["private","build"]\n')
        self.settings = load_settings(path=config, home=self.base)

    @staticmethod
    def write(root, path, raw):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def git(self, root, *arguments):
        return subprocess.run(['/usr/bin/git', *arguments], cwd=root, check=True, capture_output=True,
            timeout=10, env={**os.environ, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                'GIT_TERMINAL_PROMPT': '0'}).stdout.decode().strip()

    def assert_documents(self, connection, resolver):
        identities = {}
        for (root, path), raw in self.sources.items():
            address = f'fixture:@{root}/{path}'
            whole = resolver.resolve(address, purpose='read').selection
            self.assertIsNotNone(whole)
            self.assertEqual(whole.place.address, address)
            self.assertEqual(whole.file.primary.address, address)
            self.assertEqual(whole.file.source, raw)
            sections = sorted(whole.file.chunks, key=lambda chunk: chunk.span)
            self.assertEqual([chunk.name for chunk in sections], ['Overview', 'Overview > Detail'])
            self.assertEqual(b''.join(chunk.source for chunk in sections), raw)
            for chunk in whole.file.chunks:
                self.assertEqual(chunk.kind, 'document')
                selected = resolver.resolve(address + '#' + chunk.name, purpose='read').selection
                self.assertIsNotNone(selected)
                self.assertEqual(selected.place.root, root)
                self.assertEqual(selected.place.path, path)
                self.assertEqual(selected.members[0].chunk.source, chunk.source)
            corpus = connection.execute('SELECT corpus FROM public.mycel_files WHERE id=%s',
                                        (whole.file.identifier,)).fetchone()[0]
            self.assertEqual(corpus, 'documents')
            identities[(root, path)] = whole.file.identifier
        for path in ('README.md', 'docs/guide.md'):
            self.assertNotEqual(identities[('code', path)], identities[('artifact', path)])
            ambiguity = resolver.resolve('fixture:' + path)
            self.assertEqual(ambiguity.fault, 'ambiguous_path')
            self.assertEqual(ambiguity.candidates, (f'fixture:@artifact/{path}', f'fixture:@code/{path}'))
        for root in self.roots:
            for path in ('private/excluded.md', 'nested/build/excluded.md', 'ignored.ignore.md'):
                self.assertEqual(resolver.resolve(f'fixture:@{root}/{path}').fault, 'missing_file')
        self.assertEqual(resolver.resolve('fixture:@code/outside/excluded.py').fault, 'missing_file')
        self.assertEqual(resolver.resolve('fixture:@artifact/src/excluded.py').fault, 'missing_file')
        code = resolver.resolve('fixture:@code/src/worker.py#work', purpose='read').selection
        self.assertIsNotNone(code)
        self.assertEqual(code.members[0].chunk.kind, 'function')

    @proves('MYC-1.32', kind='store')
    def test_disk_retains_both_document_roots_split_text_origin_and_exclusions_outside_code_subdirs(self):
        manifest = capture_repository(self.settings, 'fixture')
        expected = {(root, path, 'documents') for root, path in self.sources}
        expected.add(('code', 'src/worker.py', 'code'))
        self.assertEqual({(file.primary.root, file.primary.path, file.corpus)
                          for file in manifest.disk.files}, expected)
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            result = DiskCaptureStore(connection).apply(self.settings, manifest)
            self.assertTrue(result.changed)
            self.assertEqual(len(result.files), 5)
            self.assert_documents(connection, SourceResolver.from_store(connection, self.settings))

    @proves('MYC-1.32', kind='store')
    def test_local_branch_documents_keep_their_independent_root_policy_chunks_and_read_addresses(self):
        for root in self.roots.values():
            self.git(root, 'init', '--initial-branch=fixture-main')
            self.git(root, 'add', '--all')
            self.git(root, 'commit', '--message', 'Dual root fixture')
        manifest = capture_repository(self.settings, 'fixture')
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            result = LocatedCaptureStore(connection).apply(self.settings, manifest)
            self.assertEqual(len(result.files), 10)
            self.assert_documents(connection, SourceResolver.from_store(connection, self.settings))
            disk = SourceResolver.from_store(connection, self.settings)
            for root in self.roots:
                branch = SourceResolver.from_store(connection, self.settings, kind='branch',
                    location=location_key(LocationId('branch', root, 'refs/heads/fixture-main')))
                for path in ('README.md', 'docs/guide.md'):
                    address = f'fixture:@{root}/{path}'
                    saved = branch.resolve(address, purpose='read').selection
                    current = disk.resolve(address, purpose='read').selection
                    self.assertIsNotNone(saved)
                    self.assertEqual(saved.place.address, address)
                    self.assertEqual(saved.file.source, self.sources[(root, path)])
                    self.assertEqual(saved.file.identifier, current.file.identifier)
                    self.assertEqual([(chunk.identifier, chunk.version, chunk.kind, chunk.source)
                                      for chunk in saved.file.chunks],
                                     [(chunk.identifier, chunk.version, chunk.kind, chunk.source)
                                      for chunk in current.file.chunks])
                other = 'artifact' if root == 'code' else 'code'
                self.assertEqual(branch.resolve(f'fixture:@{other}/README.md').fault, 'missing_file')


if __name__ == '__main__':
    unittest.main()
