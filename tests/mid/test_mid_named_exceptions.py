"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_named_exceptions as _support
# from test_named_exceptions import (
#     NamedExceptionTests,
#     Path,
#     ROOT,
#     unittest,
# )


# class NamedExceptionTests(_support.NamedExceptionTests):
# TEST-TIER-DISABLED-BEGIN tests/test_named_exceptions.py::NamedExceptionTests.test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling
#     def test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling(self):
#         forbidden=re.compile(r'(?i)(?<![a-z])(?:arbol|arco|sylvan|universe|infer|blueprint)(?![a-z])')
#         for path in (ROOT/'src/mycel').glob('*.py'):
#             tree=ast.parse(path.read_text())
#             for node in ast.walk(tree):
#                 if isinstance(node,ast.Constant) and isinstance(node.value,str):
#                     self.assertIsNone(forbidden.search(node.value),f'{path.name}:{node.lineno}')
# TEST-TIER-DISABLED-END tests/test_named_exceptions.py::NamedExceptionTests.test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling

# TEST-TIER-DISABLED-BEGIN tests/test_named_exceptions.py::NamedExceptionTests.test_shared_defaults_create_no_repository_alias_or_folder_fallback_and_are_overridable
#     def test_shared_defaults_create_no_repository_alias_or_folder_fallback_and_are_overridable(self):
#         with tempfile.TemporaryDirectory() as directory:
#             home=Path(directory); config=home/'config.toml';config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n')
#             snapshot=load_settings(path=config,home=home)
#             locations=RepositoryLocations(snapshot)
#             self.assertEqual(locations.repositories,())
#             for name in ('arbol','Arbol','mycel'):
#                 with self.assertRaises(MycelError) as error: locations.resolve_scope([name])
#                 self.assertEqual(error.exception.code,'unknown_repository')
#             with self.assertRaises(MycelError): locations.resolve_scope(cwd=home)
#             config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n[search]\nshared_documents=[]\n[repos.Arbol]\nenabled=true\ncode_root="'+str(home/'project')+'"\n')
#             locations=RepositoryLocations(load_settings(path=config,home=home))
#             self.assertEqual(locations.snapshot.values['search']['shared_documents'],())
#             self.assertEqual([r.name for r in locations.resolve_scope(['Arbol'])],['Arbol'])
#             with self.assertRaises(MycelError): locations.resolve_scope(['arbol'])
# TEST-TIER-DISABLED-END tests/test_named_exceptions.py::NamedExceptionTests.test_shared_defaults_create_no_repository_alias_or_folder_fallback_and_are_overridable


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:2
# import ast
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:4
# import re
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:5
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:7
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:8
# from mycel._scope import RepositoryLocations
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_named_exceptions.py:9
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_named_exceptions.py:9

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
