"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_summary_target_faults as _support
# from test_summary_target_faults import (
#     StringIO,
#     SummaryTargetFaultStoreTests,
#     TABLES,
#     builds,
#     json,
#     os,
#     patch,
#     run,
#     unittest,
# )


# class SummaryTargetFaultStoreTests(_support.SummaryTargetFaultStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_built_summary_source_and_related_faults_keep_occurrences_without_generated_edges
#     def test_real_built_summary_source_and_related_faults_keep_occurrences_without_generated_edges(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             result = self.fixture.build(connection)
#             self.assertEqual(result.status, 0, result.value)
#             summaries = self.fixture.summaries(connection)
#             self.assertEqual(len(summaries), 1)
#             generated = SourceResolver.from_store(connection, self.base.settings).index
#             place = next(place for place, chunk in generated if chunk.kind == 'summary')
#             legacy = f'fixture:summaries#{place.name}'
#             missing = SourceAddress('fixture', 'index', 'summaries', 'missing').address
#             (self.base.artifact / 'guide.md').write_text(
#                 '---\nsources: ' + json.dumps([place.address, legacy, missing]) +
#                 '\n---\n# Guide\n<!-- related:\n' + place.address + '\n' + legacy + '\n-->\nBody.\n')
#             with ExitStack() as stack:
#                 self.prohibit_generation(stack)
#                 self.ingest()
#                 before = self.state(connection)
#                 refs = self.disk_refs()
#                 self.assertEqual(len(refs), 5)
#                 self.assertEqual({row['fault'] for row in refs}, {'generated_text'})
#                 self.assertEqual({row['resolutionFault'] for row in refs}, {'generated_text'})
#                 self.assertEqual([row['parsedRef'] for row in refs].count(place.address), 2)
#                 self.assertEqual([row['parsedRef'] for row in refs].count(legacy), 2)
#                 self.assertEqual({row['kind'] for row in refs if 'kind' in row}, {'related'})
#                 self.assertTrue(all(row['resolvedAddress'] is None for row in refs))
#                 self.assertTrue(all(row['baselineStatus'] == 'baseline_missing' for row in refs))
#                 self.assertEqual(self.state(connection), before)
#                 self.ingest()
#                 self.assertEqual({row['fault'] for row in self.disk_refs()}, {'generated_text'})
#             self.assertEqual(connection.execute(
#                 "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_dependencies d ON d.id=e.dependency "
#                 "WHERE d.kind!='generated' AND e.source_version=ANY(%s)",
#                 ([row[1] for row in summaries],)).fetchall(), [])
#             self.assertEqual(connection.execute(
#                 "SELECT 1 FROM public.mycel_relations WHERE baseline_owner IS NOT NULL").fetchall(), [])
#             self.assertEqual(self.fixture.summaries(connection), summaries)
# TEST-TIER-DISABLED-END tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_built_summary_source_and_related_faults_keep_occurrences_without_generated_edges

# TEST-TIER-DISABLED-BEGIN tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_first_overview_projection_repeat_missing_section_and_recreation_report_generated_text
#     def test_first_overview_projection_repeat_missing_section_and_recreation_report_generated_text(self):
#         file = self.base.code / 'src' / 'work.py'
#         file.parent.mkdir()
#         file.write_text('def work():\n    return 1\n')
#         qualified = 'fixture:@index/overview#src'
#         legacy = 'fixture:overview#src'
#         missing = 'fixture:@index/overview#missing'
#         (self.base.artifact / 'guide.md').write_text(
#             '---\nsources: ' + json.dumps([qualified, legacy, missing]) + '\n---\n# Guide\nBody.\n')
#         with self.base.connect() as connection, ExitStack() as stack:
#             self.prohibit_generation(stack)
#             for repeat in range(2):
#                 self.ingest()
#                 before = self.state(connection)
#                 refs = self.disk_refs()
#                 self.assertEqual({row['parsedRef'] for row in refs}, {qualified, legacy, missing})
#                 self.assertEqual({row['fault'] for row in refs}, {'generated_text'})
#                 self.assertEqual(self.state(connection), before)
#                 self.assertEqual(connection.execute(
#                     "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_chunk_versions v ON v.id=e.source_version "
#                     "JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.kind='overview'").fetchall(), [])
#             # Remove the generated section through a complete pass, then restore
#             # it. A later stored retry may change its raw resolution, but never
#             # creates a generated Source Ref edge or rewrites the declaration.
#             file.unlink()
#             self.ingest('--confirm-empty')
#             self.assertEqual(connection.execute(
#                 "SELECT count(*) FROM public.mycel_chunks WHERE kind='overview'").fetchone(), (0,))
#             file.write_text('def work():\n    return 2\n')
#             self.ingest()
#             self.assertEqual({row['fault'] for row in self.disk_refs()}, {'generated_text'})
#             self.assertEqual(connection.execute(
#                 "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_chunk_versions v ON v.id=e.source_version "
#                 "JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.kind='overview'").fetchall(), [])
# TEST-TIER-DISABLED-END tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_first_overview_projection_repeat_missing_section_and_recreation_report_generated_text

# TEST-TIER-DISABLED-BEGIN tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_built_summary_cannot_be_derive_or_relate_endpoint_or_source_including_legacy_alias
#     def test_real_built_summary_cannot_be_derive_or_relate_endpoint_or_source_including_legacy_alias(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             self.assertEqual(self.fixture.build(connection).status, 0)
#             catalog = SourceResolver.from_store(connection, self.base.settings)
#             place = next(place for place, chunk in catalog.index if chunk.kind == 'summary')
#             physical = 'fixture:@artifact/guide.md#Guide'
#             for store in (DeriveStore(connection), RelateStore(connection)):
#                 for generated in (place.address, f'fixture:summaries#{place.name}'):
#                     for dependant, source in ((physical, generated), (generated, physical)):
#                         for remove in (False, True):
#                             with self.subTest(store=type(store).__name__, dependant=dependant,
#                                               source=source, remove=remove), ExitStack() as stack:
#                                 self.prohibit_generation(stack)
#                                 before = self.state(connection)
#                                 with self.assertRaises(MycelError) as error:
#                                     store.apply(self.base.settings, dependant, source, remove=remove,
#                                                 settings_home=self.base.base)
#                                 self.assertEqual(error.exception.code, 'invalid_input')
#                                 self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_built_summary_cannot_be_derive_or_relate_endpoint_or_source_including_legacy_alias

# TEST-TIER-DISABLED-BEGIN tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_physical_generated_names_keep_root_selection_and_legacy_collision_ambiguity
#     def test_real_physical_generated_names_keep_root_selection_and_legacy_collision_ambiguity(self):
#         with self.base.connect() as connection:
#             self.fixture.prepare(connection)
#             self.assertEqual(self.fixture.build(connection).status, 0)
#             catalog = SourceResolver.from_store(connection, self.base.settings)
#             place = next(place for place, chunk in catalog.index if chunk.kind == 'summary')
#             # The extensionless physical document is stored deliberately by the
#             # existing exact parser fixture, independently of scan extensions.
#             try:
#                 from .test_declared_refs import seed_document
#             except ImportError:
#                 from test_declared_refs import seed_document
#             seed_document(connection, 'fixture', 'summaries', '# Physical\nBody.\n', root='artifact')
#             seed_document(connection, 'fixture', 'summaries', '# Physical\nOther body.\n', root='code')
#             catalog = SourceResolver.from_store(connection, self.base.settings)
#             ambiguous = catalog.resolve('fixture:summaries#Physical')
#             self.assertEqual(ambiguous.fault, 'ambiguous_path')
#             self.assertEqual(set(ambiguous.candidates),
#                 {'fixture:@artifact/summaries', 'fixture:@code/summaries'})
#             for root in ('artifact', 'code'):
#                 physical = catalog.resolve(f'fixture:@{root}/summaries#Physical')
#                 self.assertEqual(physical.state, 'resolved')
#                 self.assertEqual(physical.selection.kind, 'chunk')
#             read = catalog.resolve(f'fixture:summaries#{place.name}', purpose='read')
#             self.assertEqual(read.fault, 'ambiguous_path')
#             self.assertIn(place.address, read.candidates)
#             self.assertEqual(catalog.resolve(place.address).fault, 'generated_text')
#             self.assertEqual(catalog.resolve(place.address, purpose='read').selection.kind, 'index')
#             self.assertEqual(catalog.resolve('fixture:overview#not_present').fault, 'missing_file')
# TEST-TIER-DISABLED-END tests/test_summary_target_faults.py::SummaryTargetFaultStoreTests.test_real_physical_generated_names_keep_root_selection_and_legacy_collision_ambiguity


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:2
# from contextlib import ExitStack
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:10
# from mycel._derive import DeriveStore
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:11
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:12
# from mycel._relate import RelateStore
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:13
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:13

# TEST-TIER-IMPORTS-BEGIN tests/test_summary_target_faults.py:14
# from mycel._source_refs import SourceAddress
# TEST-TIER-IMPORTS-END tests/test_summary_target_faults.py:14

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
