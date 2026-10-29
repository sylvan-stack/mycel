
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_initial_source_ingest.py::InitialSourceIngestStoreTests.test_initial_unindexed_sources_remain_visible_without_broadening_scope_and_source_pass_retries
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Initial unindexed sources remain visible without broadening scope and source pass retries.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_initial_source_ingest.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_initial_unindexed_sources_remain_visible_without_broadening_scope_and_source_pass_retries(self):
#         self.invoke('init')
#         source_bytes = {path: path.read_bytes() for path in
#                         (self.fixture.fixture.source, *self.fixture.extra)}
#         dependant_bytes = self.fixture.fixture.answer.read_bytes()
#         reply = self.invoke('ingest', '--repo', 'downstream')
#         self.assertEqual(set(reply['repositories']), {'downstream'})
#         with self.base.connect() as connection:
#             rows = self.dependencies(connection)
#             self.assertEqual(len(rows), 3)
#             self.assertTrue(all(row[6] is None and row[7] is None for row in rows))
#             self.assertEqual({row[5]['sourceState'] for row in rows}, {'unresolved'})
#             self.assertEqual({row[5]['resolution']['fault'] for row in rows}, {'missing_file'})
#             self.assertEqual(connection.execute(
#                 "SELECT count(*) FROM public.mycel_files WHERE repository='fixture'").fetchone()[0], 0)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
#         self.invoke('ingest', '--repo', 'fixture')
#         with self.base.connect() as connection:
#             rows = self.dependencies(connection)
#             self.assertEqual(len(rows), 3)
#             self.assertTrue(all(row[6] is not None and row[7] is not None for row in rows))
#             self.assertEqual({row[5]['resolution']['state'] for row in rows}, {'resolved'})
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 3)
#         self.assertEqual(self.fixture.fixture.answer.read_bytes(), dependant_bytes)
#         self.assertEqual({path: path.read_bytes() for path in source_bytes}, source_bytes)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_initial_source_ingest.py::InitialSourceIngestStoreTests.test_empty_store_all_processes_downstream_before_sources_and_captures_new_baselines
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Empty store all processes downstream before sources and captures new baselines.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_initial_source_ingest.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_empty_store_all_processes_downstream_before_sources_and_captures_new_baselines(self):
#         self.invoke('init')
#         reply = self.invoke('ingest', '--all')
#         self.assertEqual(list(reply['repositories']), ['downstream', 'fixture'])
#         self.assertTrue(all(value['ran'] for value in reply['repositories'].values()))
#         with self.base.connect() as connection:
#             rows = self.dependencies(connection)
#             self.assertEqual(len(rows), 3)
#             self.assertTrue(all(row[6] is not None and row[7] is not None for row in rows))
#             self.assertEqual({row[5]['resolution']['state'] for row in rows}, {'resolved'})
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 3)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_initial_source_ingest.py::InitialSourceIngestStoreTests.test_changed_initial_unindexed_source_does_not_stop_the_dependant_pass_and_stays_unresolved
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Changed initial unindexed source does not stop the dependant pass and stays unresolved.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_initial_source_ingest.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_initial_unindexed_source_does_not_stop_the_dependant_pass_and_stays_unresolved(self):
#         # Since 20 October 2026 a pass publishes the capture it read and takes
#         # another repository's sources from the index (MYC-1.37): a change to
#         # the unindexed source's disk neither stops nor broadens the pass.
#         self.invoke('init')
#         source = self.fixture.fixture.source
#         source.write_bytes(source.read_bytes() + b'Changed before the dependant pass.\n')
#         reply = self.invoke('ingest', '--repo', 'downstream')
#         self.assertEqual(set(reply['repositories']), {'downstream'})
#         self.assertNotIn('changedDuringPass', reply['repositories']['downstream'])
#         with self.base.connect() as connection:
#             self.assertEqual(connection.execute(
#                 "SELECT count(*) FROM public.mycel_files WHERE repository='downstream'").fetchone()[0], 1)
#             self.assertEqual(connection.execute(
#                 "SELECT count(*) FROM public.mycel_files WHERE repository='fixture'").fetchone()[0], 0)
#             rows = self.dependencies(connection)
#             self.assertEqual(len(rows), 3)
#             self.assertTrue(all(row[6] is None and row[7] is None for row in rows))
#             self.assertEqual({row[5]['sourceState'] for row in rows}, {'unresolved'})
#             self.assertEqual({row[5]['resolution']['fault'] for row in rows}, {'missing_file'})
#         self.invoke('ingest', '--repo', 'fixture')
#         with self.base.connect() as connection:
#             self.assertEqual({row[5]['resolution']['state'] for row in self.dependencies(connection)}, {'resolved'})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_initial_source_ingest.py::InitialSourceIngestStoreTests.test_resolved_uningested_source_change_preserves_existing_pins_and_the_pass_completes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Resolved uningested source change preserves existing pins and the pass completes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_initial_source_ingest.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_resolved_uningested_source_change_preserves_existing_pins_and_the_pass_completes(self):
#         self.invoke('init')
#         self.invoke('ingest', '--repo', 'fixture')
#         self.invoke('ingest', '--repo', 'downstream')
#         with self.base.connect() as connection:
#             before = self.dependencies(connection)
#             pins = [(row[0], row[6], row[7]) for row in before]
#         source = self.fixture.fixture.source
#         source.write_bytes(source.read_bytes() + b'Changed before the source ingest.\n')
#         # The source's disk is its own pass's business: the dependant's pass
#         # completes against the indexed source and changes no pin.
#         reply = self.invoke('ingest', '--repo', 'downstream')
#         self.assertFalse(reply['repositories']['downstream']['files']['changed'])
#         self.assertNotIn('changedDuringPass', reply['repositories']['downstream'])
#         with self.base.connect() as connection:
#             self.assertEqual([(row[0], row[6], row[7]) for row in self.dependencies(connection)], pins)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
