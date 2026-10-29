
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_named_exceptions.py::NamedExceptionTests.test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Only prescribed names are packaged data and runtime has no product coupling.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_named_exceptions.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_only_prescribed_names_are_packaged_data_and_runtime_has_no_product_coupling(self):
#         forbidden=re.compile(r'(?i)(?<![a-z])(?:arbol|arco|sylvan|universe|infer|blueprint)(?![a-z])')
#         for path in (ROOT/'src/mycel').glob('*.py'):
#             tree=ast.parse(path.read_text())
#             for node in ast.walk(tree):
#                 if isinstance(node,ast.Constant) and isinstance(node.value,str):
#                     self.assertIsNone(forbidden.search(node.value),f'{path.name}:{node.lineno}')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_named_exceptions.py::NamedExceptionTests.test_shared_defaults_create_no_repository_alias_or_folder_fallback_and_are_overridable
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Shared defaults create no repository alias or folder fallback and are overridable.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_named_exceptions.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
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
# LOW-TIER-SOURCE-END
# LOW-TIER-END
