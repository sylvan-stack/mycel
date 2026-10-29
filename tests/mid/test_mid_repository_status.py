
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_repository_status.py::RepositoryStatusUnitTests.test_snapshot_methods_refuse_idle_connections_before_reading_inventory
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Snapshot methods refuse idle connections before reading inventory.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_status.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_snapshot_methods_refuse_idle_connections_before_reading_inventory(self):
#         connection = SimpleNamespace(autocommit=True,
#             info=SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE))
#         reports = object.__new__(RepositoryReports)
#         reports.connection = connection
#         writer = object.__new__(EmbeddingStore)
#         writer.connection = connection
#         for action in (reports.names_in_snapshot, lambda: reports.status_in_snapshot('fixture'),
#                        lambda: writer.prepare_in_snapshot('fixture', contexts={}),
#                        lambda: retained_contexts(connection, 'fixture', in_snapshot=True)):
#             with self.subTest(action=action), self.assertRaises(MycelError) as error:
#                 action()
#             self.assertEqual(error.exception.code, 'invalid_input')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_status.py::RepositoryStatusStoreTests.test_public_status_counts_disk_branch_stash_and_provisional_parts_without_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public status counts disk branch stash and provisional parts without writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_status.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_status_counts_disk_branch_stash_and_provisional_parts_without_writes(self):
#         self.base.initialize()
#         branch = self.base.artifact / 'branch.md'
#         branch.write_bytes(b'# Branch\nOnly in the branch.\n')
#         self.base.commit()
#         (self.base.artifact / 'guide.md').write_bytes(b'# Guide\nStashed guide version.\n')
#         (self.base.artifact / 'stash.md').write_bytes(b'# Stash\nOnly in the stash.\n')
#         self.base.git('stash', 'push', '--include-untracked', '--message', 'Fixture stash')
#         branch.unlink()
#         (self.base.artifact / 'guide.md').write_bytes(b'# Guide\nDirty disk guide version.\n')
#         (self.base.artifact / 'disk.md').write_bytes(b'# Disk\nOnly on disk.\n')
#         with self.base.connect() as connection:
#             self.base.apply(connection)
#             connection.execute("UPDATE public.mycel_repository_state SET last_pass_at='2026-10-15T10:00:00Z'")
#             before = self.state(connection)
#             with self.no_work():
#                 status, reply = self.invoke(connection, '--repo', 'fixture')
#             self.assertEqual(status, 0, reply)
#             result = reply['repositories'][0]['result']
#             self.assertEqual(result['documents'], {'onDisk': 2, 'elsewhere': 2})
#             self.assertEqual(result['chunks'], {'onDisk': 2, 'elsewhere': 2, 'stale': 0})
#             self.assertEqual(result['vectors'], {'embedded': 0, 'pending': 6, 'failed': 0, 'deferred': 0, 'ineligible': 0})
#             self.assertEqual(result['parts'], {'embedded': 0, 'pending': 6, 'failed': 0, 'deferred': 0})
#             self.assertEqual(result['lastPass'], '2026-10-15T10:00:00+00:00')
#             self.assertEqual(result['folders'], {'code': str(self.base.code), 'documents': str(self.base.artifact)})
#             self.assertEqual((result['known'], result['enabled']), (True, True))
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_status.py::RepositoryStatusStoreTests.test_all_lists_disabled_orphan_and_enabled_empty_without_requiring_available_folders
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: All lists disabled orphan and enabled empty without requiring available folders.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_status.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_all_lists_disabled_orphan_and_enabled_empty_without_requiring_available_folders(self):
#         self.base.initialize()
#         with self.base.connect() as connection:
#             self.base.apply(connection)
#             # Retained rows belong to their stored name, independently of the
#             # current settings. Both ineligible repositories keep their text.
#             connection.execute("INSERT INTO public.mycel_repository_state VALUES ('orphan',NULL,'{}')")
#             connection.execute("INSERT INTO public.mycel_repository_state VALUES ('disabled',NULL,'{}')")
#             connection.execute("INSERT INTO public.mycel_chunks (id,repository,kind,metadata) "
#                                "SELECT gen_random_uuid(),owner,'summary','{}'::jsonb "
#                                "FROM unnest(ARRAY['disabled','orphan']) owner")
#             connection.execute("INSERT INTO public.mycel_chunk_versions "
#                 "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) "
#                 "SELECT id,encode(sha256('retained'::bytea),'hex'),'retained'::bytea,'retained','{}','{}' "
#                 "FROM public.mycel_chunks WHERE repository IN ('disabled','orphan')")
#             connection.execute("INSERT INTO public.mycel_locations (id,chunk_version,kind,location,metadata) "
#                 "SELECT gen_random_uuid(),v.id,'branch','branch',"
#                 "'{\"kind\":\"summary\",\"path\":\"retained\",\"name\":\"Kept\"}'::jsonb "
#                 "FROM public.mycel_chunk_versions v "
#                 "JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository IN ('disabled','orphan')")
#             self.base.config.write_text(self.base.config.read_text() + '\n[repos.disabled]\nenabled=false\n'
#                 + '\n[repos.empty]\nenabled=true\nartifact_root=' + json.dumps(str(self.base.base / 'unavailable')) + '\n')
#             # A missing configured checkout must not obstruct stored reports.
#             self.base.code.rename(self.base.base / 'moved')
#             before = self.state(connection)
#             with self.no_work():
#                 status, reply = self.invoke(connection, '--all')
#                 named_status, named = self.invoke(connection, '--repo', 'orphan')
#             self.assertEqual((status, named_status), (0, 0), reply)
#             reports = {entry['repository']: entry['result'] for entry in reply['repositories']}
#             self.assertEqual(set(reports), {'fixture', 'disabled', 'orphan', 'empty'})
#             for name, known in (('disabled', True), ('orphan', False)):
#                 current = reports[name]
#                 self.assertEqual((current['known'], current['enabled']), (known, False))
#                 self.assertEqual(current['chunks'], {'onDisk': 0, 'elsewhere': 1, 'stale': 0})
#                 self.assertEqual(current['vectors']['pending'], 0)
#                 self.assertEqual(current['parts']['pending'], 0)
#                 # Missing coverage is not a failure caused by ineligibility.
#                 self.assertEqual(current['vectors']['failed'], 0)
#                 self.assertEqual(current['vectors']['ineligible'], 1)
#             self.assertEqual(reports['fixture']['documents']['onDisk'], 1)
#             self.assertEqual(reports['empty']['chunks']['onDisk'], 0)
#             self.assertNotIn('lastPass', reports['empty'])
#             self.assertEqual(named['repositories'][0]['result'], reports['orphan'])
#             from mycel._capture import capture_repository
#             from mycel._embed import embed
#             from mycel._freshness import Deadline
#             from mycel._ingest import ingest
#             from mycel._scope import RepositoryLocations
#             from mycel._search_store import search_from_store
#             settings = load_settings(path=self.base.config, home=self.base.base)
#             self.assertEqual({repo.name for repo in RepositoryLocations(settings).resolve_scope(all_repositories=True)},
#                              {'fixture', 'empty'})
#             with self.no_work(), patch('mycel._cli.invocation_store', side_effect=AssertionError('Ineligible work opened a store')):
#                 for command, handler in (('ingest', ingest), ('embed', embed)):
#                     output = StringIO()
#                     with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
#                         refused = run([command, '--repo', 'disabled', '--repo', 'orphan'],
#                             handlers={command: handler}, stdout=output, stderr=StringIO())
#                     self.assertEqual(refused, 1, output.getvalue())
#                 for name in ('disabled', 'orphan'):
#                     with self.assertRaises(MycelError):
#                         capture_repository(settings, name)
#                     with self.assertRaises(MycelError):
#                         with EmbeddingStore(connection, settings).session(name):
#                             self.fail('Ineligible embedding session entered')
#                     with self.assertRaises(MycelError):
#                         search_from_store(connection, settings, 'retained', (name,),
#                             deadline=Deadline.after(1), no_fresh=True)
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_status.py::RepositoryStatusStoreTests.test_coverage_counts_whole_current_model_versions_and_failed_pending_parts_apart
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Coverage counts whole current model versions and failed pending parts apart.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_status.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_coverage_counts_whole_current_model_versions_and_failed_pending_parts_apart(self):
#         self.base.initialize(b'# Guide\n' + b'Guide body words. ' * 30 + b'\n')
#         for name in ('complete', 'failed', 'old'):
#             (self.base.artifact / (name + '.md')).write_bytes(('# ' + name + '\n' + 'Body words. ' * 30 + '\n').encode())
#         tokenizer = load_tokenizer()
#         local = replace(tokenizer, catalog=replace(tokenizer.catalog, input_token_cap=40))
#         with self.base.connect() as connection:
#             self.base.apply(connection)
#             contexts, _ = retained_contexts(connection, 'fixture')
#             writer = EmbeddingStore(connection, self.base.settings, tokenizer=local)
#             with writer.session('fixture'):
#                 prepared = writer.prepare('fixture', contexts=contexts, persist=True)
#                 by_name = {value.plan.place_line.split('.md')[0].split('/')[-1]: value for value in prepared.versions}
#                 complete, failed, old, mixed = (by_name[name] for name in ('complete', 'failed', 'old', 'guide'))
#                 self.assertGreaterEqual(len(mixed.parts), 3)
#                 writes, failures = [], []
#                 for value in (complete, failed, old, mixed):
#                     for number, part in enumerate(value.parts):
#                         identity = PartIdentity('fixture', value.version.chunk_id, value.version.version, part.part.order)
#                         if value is complete or value is old or value is mixed and number == 0:
#                             writes.append(VectorWrite(identity, writer.model, writer.dimensions, (0.125,) * writer.dimensions))
#                         elif value is failed or value is mixed and number == 1:
#                             failures.append(PartFailure(identity, 'content', 'Fixture content failure.'))
#                 writer.commit(tuple(writes))
#                 writer.record_failures(tuple(failures))
#             connection.execute("UPDATE public.mycel_embedding_plans SET model='historical-model' WHERE id=%s", (old.id,))
#             connection.execute("UPDATE public.mycel_vectors SET model='historical-model' WHERE plan_id=%s", (old.id,))
#             expected = writer.prepare('fixture', contexts=contexts).counts.to_dict()
#             before = self.state(connection)
#             with self.no_work():
#                 result = RepositoryReports(connection, self.base.settings, tokenizer=local).status('fixture')
#             self.assertEqual(result['vectors'], {**expected['versions'], 'ineligible': 0})
#             self.assertEqual(result['parts'], expected['parts'])
#             self.assertEqual(result['vectors'], {'embedded': 1, 'pending': 2, 'failed': 1, 'deferred': 0, 'ineligible': 0})
#             self.assertGreater(result['parts']['failed'], result['vectors']['failed'])
#             self.assertGreater(result['parts']['pending'], result['vectors']['pending'])
#             self.assertEqual(self.state(connection), before)
#             # Returned vectors waiting behind another pass remain durable
#             # deferred work. Reporting must not drain them or call a provider.
#             with self.base.connect() as passer, writer.session('fixture'):
#                 current = writer.prepare('fixture', contexts=contexts, persist=True)
#                 staged = tuple(VectorWrite(PartIdentity(item.repository, item.chunk_id, item.chunk_version,
#                     item.part_order), writer.model, writer.dimensions, (0.125,) * writer.dimensions)
#                     for batch in current.batches for item in batch.inputs
#                     if item.chunk_version == mixed.version.version)
#                 self.assertTrue(staged)
#                 with operation_guard(passer, 'fixture', 'pass'):
#                     receipt = writer.commit(staged)
#                 self.assertTrue(receipt.deferred)
#                 before = self.state(connection)
#                 with self.no_work():
#                     deferred = RepositoryReports(connection, self.base.settings, tokenizer=local).status('fixture')
#                 self.assertEqual(deferred['vectors'],
#                     {'embedded': 1, 'pending': 1, 'failed': 1, 'deferred': 1, 'ineligible': 0})
#                 self.assertEqual(deferred['parts']['deferred'], len(staged))
#                 self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_repository_status.py::RepositoryStatusStoreTests.test_inventory_provenance_and_last_pass_share_one_repeatable_read_snapshot
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Inventory provenance and last pass share one repeatable read snapshot.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_repository_status.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_inventory_provenance_and_last_pass_share_one_repeatable_read_snapshot(self):
#         self.base.initialize()
#         with self.base.connect() as connection, self.base.connect() as writer:
#             self.base.apply(connection)
#             connection.execute("UPDATE public.mycel_repository_state SET last_pass_at='2026-10-15T10:00:00Z'")
#             original = ProvenanceReports.status_in_snapshot
#             def concurrent_change(reports, repository):
#                 value = original(reports, repository)
#                 writer.execute("UPDATE public.mycel_repository_state SET last_pass_at='2026-10-15T11:00:00Z'")
#                 writer.execute("DELETE FROM public.mycel_locations WHERE kind='disk'")
#                 writer.execute("DELETE FROM public.mycel_file_locations WHERE kind='disk'")
#                 return value
#             with patch.object(ProvenanceReports, 'status_in_snapshot', concurrent_change):
#                 result = RepositoryReports(connection, self.base.settings).status('fixture')
#             self.assertEqual((result['documents']['onDisk'], result['chunks']['onDisk'], result['lastPass']),
#                              (1, 1, '2026-10-15T10:00:00+00:00'))
#             later = RepositoryReports(connection, self.base.settings).status('fixture')
#             self.assertEqual((later['documents']['onDisk'], later['chunks']['onDisk'], later['lastPass']),
#                              (0, 0, '2026-10-15T11:00:00+00:00'))
# LOW-TIER-SOURCE-END
# LOW-TIER-END
