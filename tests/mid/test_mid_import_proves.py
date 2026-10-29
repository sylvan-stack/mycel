"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_import_proves as _support
# from test_import_proves import (
#     ImportPlanTests,
#     OTHER,
#     Path,
#     ProvenImportStoreTests,
#     REQ,
#     ROOT,
#     SOURCE,
#     SPEC,
#     WHEN,
#     importlib,
#     migration,
#     spec,
#     subprocess,
#     tempfile,
#     unittest,
# )


# class ImportPlanTests(_support.ImportPlanTests):
# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ImportPlanTests.test_literal_planning_never_imports_and_preserves_defining_symbol_and_kinds
#     def test_literal_planning_never_imports_and_preserves_defining_symbol_and_kinds(self):
#         plan = self.plan()
#         self.assertEqual(len(plan['declarations']), 1)
#         self.assertEqual(plan['declarations'][0]['kind'], 'store')
#         self.assertEqual(len(plan['pairs']), 2)
#         self.assertEqual(plan['pairs'][0]['chunk'], 'fixture:@code/tests/test_proof.py#Proof.test_value')
#         self.assertEqual(plan['pairs'][0]['origin'], format_entity_uri('req', REQ, 'keep the value', 'fixture'))
#         migration.validate_plan(plan)
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ImportPlanTests.test_literal_planning_never_imports_and_preserves_defining_symbol_and_kinds

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ImportPlanTests.test_unknown_dynamic_duplicate_and_unnormalized_inputs_refuse_before_store_work
#     def test_unknown_dynamic_duplicate_and_unnormalized_inputs_refuse_before_store_work(self):
#         for raw in (SOURCE.replace("'MYC-1.1'", "'MYC-1.3'"),
#                     SOURCE.replace("'MYC-1.1'", 'choose_requirement()'),
#                     SOURCE.replace("'MYC-1.2'", "'MYC-1.1'"),
#                     SOURCE.replace("kind='store'", "kind='live'")):
#             with self.subTest(raw=raw):
#                 self.test.write_text(raw)
#                 with self.assertRaises(ValueError):
#                     self.plan()
#         self.test.write_text(SOURCE)
#         (self.specs / '01-fixture.md').write_text(SPEC.replace(' <!-- ' + REQ + ' -->', ''))
#         with self.assertRaisesRegex(ValueError, 'Normalize'):
#             self.plan()
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ImportPlanTests.test_unknown_dynamic_duplicate_and_unnormalized_inputs_refuse_before_store_work

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ImportPlanTests.test_complete_input_and_plan_changes_refuse_and_private_outputs_cannot_enter_corpora
#     def test_complete_input_and_plan_changes_refuse_and_private_outputs_cannot_enter_corpora(self):
#         plan = self.plan()
#         (self.root / 'new.py').write_text('NEW = 1\n')
#         with self.assertRaises(MycelError):
#             migration.validate_plan(plan)
#         (self.root / 'new.py').unlink()
#         plan['pairs'][0]['chunk'] = 'fixture:@code/unrelated.py#value'
#         with self.assertRaises(MycelError):
#             migration.validate_plan(plan)
#         for path in (self.root / 'result.json', self.specs.parent / 'result.json'):
#             with self.assertRaises(ValueError):
#                 migration.write_private(path, {}, self.plan())
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ImportPlanTests.test_complete_input_and_plan_changes_refuse_and_private_outputs_cannot_enter_corpora

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ImportPlanTests.test_owner_target_is_refused_before_opening_a_connection
#     def test_owner_target_is_refused_before_opening_a_connection(self):
#         from mycel._settings import load_settings
#         config = self.base / 'config.toml'
#         config.write_text('[store]\naddress="postgresql://fixture@localhost:55432/mycel"\n')
#         settings = load_settings(path=config)
#         with self.assertRaisesRegex(ValueError, 'mycel_check_'):
#             migration.apply_disposable(None, settings, self.plan())
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ImportPlanTests.test_owner_target_is_refused_before_opening_a_connection

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ImportPlanTests.test_owner_import_requires_the_named_database_and_the_indexed_clone
#     def test_owner_import_requires_the_named_database_and_the_indexed_clone(self):
#         from mycel._settings import load_settings
#         other = self.base / 'other'
#         other.mkdir()
#
#         def settings(database, code_root):
#             config = self.base / f'{database}-{code_root.name}.toml'
#             config.write_text(f'[store]\naddress="postgresql://fixture@localhost:55432/{database}"\n'
#                               f'[repos.fixture]\nenabled=true\ncode_root="{code_root}"\n'
#                               f'artifact_root="{self.specs.parent}"\n')
#             return load_settings(path=config)
#         for values, owner, message in ((settings('mycel', self.root), 'other', '--owner-store'),
#                                        (settings('mycel_check_x1', self.root), 'mycel_check_x1', 'apply-disposable'),
#                                        (settings('mycel', other), 'mycel', 'indexed code root')):
#             with self.subTest(message), self.assertRaisesRegex(ValueError, message):
#                 migration.apply_owner(None, values, self.plan(), owner_database=owner)
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ImportPlanTests.test_owner_import_requires_the_named_database_and_the_indexed_clone



# class ProvenImportStoreTests(_support.ProvenImportStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_imports_every_uuid_pair_as_proven_with_one_complete_check_verification
#     def test_imports_every_uuid_pair_as_proven_with_one_complete_check_verification(self):
#         with self.base.connect() as connection:
#             replies = migration.apply_disposable(connection, self.settings, self.plan)
#             self.assertEqual(len(replies), 2)
#             self.assertEqual(replies[0]['verification'], replies[1]['verification'])
#             self.assertEqual(replies[0]['verification']['how'], 'check')
#             self.assertEqual(len(replies[0]['verification']['sources']), 2)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (1,))
#             for reply in replies:
#                 self.assertEqual(reply['link']['method'], 'proven')
#                 self.assertEqual(reply['link']['confidence'], 'proven')
#                 self.assertEqual(reply['link']['confidenceScore'], 0.8)
#                 self.assertEqual(reply['link']['who'], 'fixture-owner')
#             links = connection.execute("SELECT state FROM public.mycel_dependencies WHERE kind='asserted'").fetchall()
#             self.assertEqual({row[0]['originId'] for row in links}, {REQ, OTHER})
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_imports_every_uuid_pair_as_proven_with_one_complete_check_verification

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_late_input_edit_rolls_back_all_links_verifications_and_evidence
#     def test_late_input_edit_rolls_back_all_links_verifications_and_evidence(self):
#         original = migration.validate_plan
#         calls = []
#         def changed(plan):
#             calls.append(True)
#             if len(calls) == 3:
#                 self.source.write_text(self.source.read_text() + '\n# late edit\n')
#             return original(plan)
#         with self.base.connect() as connection:
#             before = connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()
#             with patch.object(migration, 'validate_plan', side_effect=changed), self.assertRaises(MycelError):
#                 migration.apply_disposable(connection, self.settings, self.plan)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='asserted'").fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), before)
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_late_input_edit_rolls_back_all_links_verifications_and_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_one_batch_captures_each_repository_once_and_compares_once_at_its_end
#     def test_one_batch_captures_each_repository_once_and_compares_once_at_its_end(self):
#         from mycel import _dependency_inputs
#         captures = []
#         capture = _dependency_inputs.capture_repository
#         def counted(settings, repository, *arguments, **options):
#             captures.append(repository)
#             return capture(settings, repository, *arguments, **options)
#         with self.base.connect() as connection, \
#                 patch.object(_dependency_inputs, 'capture_repository', side_effect=counted):
#             self.assertEqual(len(migration.apply_disposable(connection, self.settings, self.plan)), 2)
#         self.assertEqual(captures, ['fixture', 'fixture'])
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_one_batch_captures_each_repository_once_and_compares_once_at_its_end

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_one_batch_syncs_derived_drift_once_and_reuses_its_catalogs
#     def test_one_batch_syncs_derived_drift_once_and_reuses_its_catalogs(self):
#         from mycel import _drift_store, _resolver
#         syncs, reads = [], []
#         sync = _drift_store.DriftStore.sync_in_transaction
#         def counted_sync(store, *arguments, **options):
#             syncs.append((options.get('captures') is not None, options.get('catalogs') is not None,
#                           options.get('closure')))
#             return sync(store, *arguments, **options)
#         read = _resolver.SourceResolver.from_store.__func__
#         def counted_read(cls, *arguments, **options):
#             reads.append((options.get('kind', 'disk'), options.get('location')))
#             return read(cls, *arguments, **options)
#         with self.base.connect() as connection, \
#                 patch.object(_drift_store.DriftStore, 'sync_in_transaction', counted_sync), \
#                 patch.object(_resolver.SourceResolver, 'from_store', classmethod(counted_read)):
#             self.assertEqual(len(migration.apply_disposable(connection, self.settings, self.plan)), 2)
#         # One sync for both derived pairs, then the verification's own confirmation sync.
#         self.assertEqual([(captures, catalogs) for captures, catalogs, _ in syncs], [(True, True), (True, True)])
#         self.assertIsNone(syncs[0][2])
#         self.assertIsNotNone(syncs[1][2])
#         # Each catalog is read once per kind, location and guard set, not once per pair.
#         self.assertLessEqual(len(reads), 5, reads)
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_one_batch_syncs_derived_drift_once_and_reuses_its_catalogs

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_an_edit_between_pairs_refuses_the_whole_batch
#     def test_an_edit_between_pairs_refuses_the_whole_batch(self):
#         from mycel import _derive
#         derive = _derive.DeriveStore.apply_in_transaction
#         def edited(store, *arguments, **options):
#             reply = derive(store, *arguments, **options)
#             self.source.write_text(self.source.read_text() + '\n# edited mid-batch\n')
#             return reply
#         with self.base.connect() as connection:
#             with patch.object(_derive.DeriveStore, 'apply_in_transaction', edited), self.assertRaises(MycelError):
#                 migration.apply_disposable(connection, self.settings, self.plan)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='asserted'").fetchone(), (0,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (0,))
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_an_edit_between_pairs_refuses_the_whole_batch

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_import_refuses_to_replace_a_newer_human_statement
#     def test_import_refuses_to_replace_a_newer_human_statement(self):
#         from mycel._justify import JustifyStore
#         pairs = [(row['chunk'], row['origin']) for row in self.plan['pairs']]
#         with self.base.connect() as connection:
#             stated = JustifyStore(connection).apply(self.settings, *pairs[1], by='maintainer')
#             before = connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()
#             with self.assertRaisesRegex(MycelError, 'replace an existing'):
#                 migration.apply_disposable(connection, self.settings, self.plan)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), before)
#             link, = connection.execute("SELECT state->'originLink' FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
#             self.assertEqual(link, stated['link'])
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_import_refuses_to_replace_a_newer_human_statement

# TEST-TIER-DISABLED-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_replay_preserves_a_reviewed_score_and_its_verification_history
#     def test_replay_preserves_a_reviewed_score_and_its_verification_history(self):
#         from psycopg.types.json import Jsonb
#         with self.base.connect() as connection:
#             migration.apply_disposable(connection, self.settings, self.plan)
#             identifier, state = connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE kind='asserted' ORDER BY id LIMIT 1").fetchone()
#             state['originLink'].update(confidenceScore=0.4, confidence='candidate',
#                 review={'who': 'reviewer', 'when': WHEN, 'outcome': 'nonconforming'})
#             connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s', (Jsonb(state), identifier))
#             before = connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()
#             with self.assertRaisesRegex(MycelError, 'replace an existing'):
#                 migration.apply_disposable(connection, self.settings, self.plan)
#             self.assertEqual(connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0], state)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), before)
# TEST-TIER-DISABLED-END tests/test_import_proves.py::ProvenImportStoreTests.test_replay_preserves_a_reviewed_score_and_its_verification_history


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_import_proves.py:3
# import json
# TEST-TIER-IMPORTS-END tests/test_import_proves.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_import_proves.py:8
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_import_proves.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_import_proves.py:10
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_import_proves.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_import_proves.py:11
# from mycel._source_refs import format_entity_uri
# TEST-TIER-IMPORTS-END tests/test_import_proves.py:11

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
