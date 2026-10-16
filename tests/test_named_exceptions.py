"""MYC-D37 permits only the prescribed settings data, without scope coupling."""
import ast
import json
from pathlib import Path
import re
import tempfile
import unittest
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._scope import RepositoryLocations
from mycel._settings import load_settings

ROOT=Path(__file__).resolve().parents[1]

class NamedExceptionTests(unittest.TestCase):
    @proves('MYC-0.3','MYC-1.5')
    def test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling(self):
        defaults=json.loads((ROOT/'src/mycel/data/settings-defaults.json').read_text())
        self.assertEqual(defaults['search']['shared_documents'],[{'repo':'mycel','paths':['.']},{'repo':'arbol','paths':['GLOSSARY.md']}])
        self.assertEqual(defaults['scan']['skip_folders'],['.arbol','.arco','.bare','.git','.mypy_cache','.next','.pytest_cache','.ruff_cache','.svelte-kit','.turbo','.venv','__pycache__','build','coverage','dist','node_modules','releases','site-packages','storybook-static','venv'])
        forbidden=re.compile(r'(?i)(?<![a-z])(?:arbol|arco|sylvan|universe|infer|blueprint)(?![a-z])')
        for path in (ROOT/'src/mycel').glob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Constant) and isinstance(node.value,str):
                    self.assertIsNone(forbidden.search(node.value),f'{path.name}:{node.lineno}')

    @proves('MYC-0.3','MYC-1.5')
    def test_shared_defaults_create_no_repository_alias_or_folder_fallback_and_are_overridable(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory); config=home/'config.toml';config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n')
            snapshot=load_settings(path=config,home=home)
            locations=RepositoryLocations(snapshot)
            self.assertEqual(locations.repositories,())
            for name in ('arbol','Arbol','mycel'):
                with self.assertRaises(MycelError) as error: locations.resolve_scope([name])
                self.assertEqual(error.exception.code,'unknown_repository')
            with self.assertRaises(MycelError): locations.resolve_scope(cwd=home)
            config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n[search]\nshared_documents=[]\n[repos.Arbol]\nenabled=true\ncode_root="'+str(home/'project')+'"\n')
            locations=RepositoryLocations(load_settings(path=config,home=home))
            self.assertEqual(locations.snapshot.values['search']['shared_documents'],())
            self.assertEqual([r.name for r in locations.resolve_scope(['Arbol'])],['Arbol'])
            with self.assertRaises(MycelError): locations.resolve_scope(['arbol'])
