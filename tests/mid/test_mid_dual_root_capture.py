
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_dual_root_capture.py::DualRootCaptureStoreTests.test_disk_retains_both_document_roots_split_text_origin_and_exclusions_outside_code_subdirs
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Disk retains both document roots split text origin and exclusions outside code subdirs.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dual_root_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_disk_retains_both_document_roots_split_text_origin_and_exclusions_outside_code_subdirs(self):
#         manifest = capture_repository(self.settings, 'fixture')
#         expected = {(root, path, 'documents') for root, path in self.sources}
#         expected.add(('code', 'src/worker.py', 'code'))
#         self.assertEqual({(file.primary.root, file.primary.path, file.corpus)
#                           for file in manifest.disk.files}, expected)
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             result = DiskCaptureStore(connection).apply(self.settings, manifest)
#             self.assertTrue(result.changed)
#             self.assertEqual(len(result.files), 5)
#             self.assert_documents(connection, SourceResolver.from_store(connection, self.settings))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_dual_root_capture.py::DualRootCaptureStoreTests.test_local_branch_documents_keep_their_independent_root_policy_chunks_and_read_addresses
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Local branch documents keep their independent root policy chunks and read addresses.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_dual_root_capture.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_local_branch_documents_keep_their_independent_root_policy_chunks_and_read_addresses(self):
#         for root in self.roots.values():
#             self.git(root, 'init', '--initial-branch=fixture-main')
#             self.git(root, 'add', '--all')
#             self.git(root, 'commit', '--message', 'Dual root fixture')
#         manifest = capture_repository(self.settings, 'fixture')
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             result = LocatedCaptureStore(connection).apply(self.settings, manifest)
#             self.assertEqual(len(result.files), 10)
#             self.assert_documents(connection, SourceResolver.from_store(connection, self.settings))
#             disk = SourceResolver.from_store(connection, self.settings)
#             for root in self.roots:
#                 branch = SourceResolver.from_store(connection, self.settings, kind='branch',
#                     location=location_key(LocationId('branch', root, 'refs/heads/fixture-main')))
#                 for path in ('README.md', 'docs/guide.md'):
#                     address = f'fixture:@{root}/{path}'
#                     saved = branch.resolve(address, purpose='read').selection
#                     current = disk.resolve(address, purpose='read').selection
#                     self.assertIsNotNone(saved)
#                     self.assertEqual(saved.place.address, address)
#                     self.assertEqual(saved.file.source, self.sources[(root, path)])
#                     self.assertEqual(saved.file.identifier, current.file.identifier)
#                     self.assertEqual([(chunk.identifier, chunk.version, chunk.kind, chunk.source)
#                                       for chunk in saved.file.chunks],
#                                      [(chunk.identifier, chunk.version, chunk.kind, chunk.source)
#                                       for chunk in current.file.chunks])
#                 other = 'artifact' if root == 'code' else 'code'
#                 self.assertEqual(branch.resolve(f'fixture:@{other}/README.md').fault, 'missing_file')
# LOW-TIER-SOURCE-END
# LOW-TIER-END
