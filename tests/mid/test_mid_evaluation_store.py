"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_evaluation_store as _support
# from test_evaluation_store import (
#     EvaluationSet,
#     EvaluationStoreTests,
#     Jsonb,
#     Path,
#     PreparedQueryVector,
#     RetrievalPlace,
#     StoreRetrieval,
#     TABLES,
#     _RecordingConnection,
#     _Vectors,
#     _freeze,
#     _hash,
#     load_settings,
#     pq,
#     replace,
#     run_retrieval_evaluation,
#     search_text,
#     sha256,
#     unittest,
#     uuid4,
# )


# class EvaluationStoreTests(_support.EvaluationStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_query_vectors_precede_one_snapshot_and_all_store_rows_remain_exact
#     def test_query_vectors_precede_one_snapshot_and_all_store_rows_remain_exact(self):
#         with self.connection() as connection:
#             self.seed(connection)
#             before = self.contents(connection)
#             recorded = _RecordingConnection(connection)
#             vectors = _Vectors(recorded, fallback=True)
#             queries = (RetrievalQuery("  Exact  ", ("fixture:guide.md#Exact",)),
#                        RetrievalQuery("how does exact work", ("fixture:guide.md#Exact",), "docs"))
#             calls = []
#
#             def search(current, snapshot, query, prepared, *, k, freshness):
#                 self.assertEqual(vectors.queries, list(queries))
#                 self.assertEqual(current.execute("SELECT current_setting('transaction_read_only'), "
#                     "current_setting('transaction_isolation')").fetchone(), ("on", "repeatable read"))
#                 calls.append((query, prepared, k, freshness))
#                 return RetrievalReply("identifier" if query == queries[0] else "question", False,
#                                       (self.selected(snapshot, "fixture:guide.md#Exact"),))
#
#             report = run_retrieval_evaluation(self.suite(*queries), repository="fixture", build="412",
#                 model="voyage-code-4", query_vectors=vectors,
#                 retrieval=StoreRetrieval(recorded, self.settings(), search=search))
#             self.assertEqual(len(calls), 2)
#             self.assertEqual([call[0] for call in calls], list(queries))
#             self.assertTrue(all(call[2:] == (10, False) for call in calls))
#             self.assertEqual((report["build"], report["model"], report["searchReply"], report["byWordingAlone"]),
#                              ("412", "voyage-code-4", 3, 2))
#             self.assertEqual(self.contents(connection), before)
#             self.assertEqual(sum("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY" in sql
#                                  for sql in recorded.statements), 2)  # checked-store inspection, then evaluation
#             self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"))
#                                  for sql in recorded.statements))
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_query_vectors_precede_one_snapshot_and_all_store_rows_remain_exact

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_exact_header_positions_faults_and_whole_query_denominators
#     def test_exact_header_positions_faults_and_whole_query_denominators(self):
#         with self.connection() as connection:
#             whole = "class Policy:\n def apply(self): pass\n"
#             file_id, _, header = self.seed(connection, path="policy.py", root="code", source=whole,
#                 name="Policy", kind="class", chunk_source="class Policy:\n", span={"start": 0, "end": 14})
#             self.seed(connection, file_id=file_id, path="policy.py", root="code", source=whole,
#                 name="Policy.apply", kind="method", family="Policy", chunk_source=" def apply(self): pass\n",
#                 span={"start": 14, "end": len(whole)})
#             self.seed(connection, path="same.md", source="# Artifact\n", name="Artifact")
#             self.seed(connection, path="same.md", root="code", source="# Checkout\n", name="Checkout", corpus="documents")
#             self.seed(connection, path="first.py", root="code", source="def first(): pass\n", name="First", kind="function")
#             self.seed(connection, path="second.py", root="code", source="def second(): pass\n", name="Second", kind="function")
#             self.seed(connection, path="unreturned.py", root="code", source="def absent(): pass\n", name="Unreturned", kind="function")
#             queries = (RetrievalQuery("Policy", ("fixture:policy.py#Policy", "fixture:@code/policy.py#Policy")),
#                 RetrievalQuery("what is unreturned", ("fixture:unreturned.py#Unreturned",)),
#                 RetrievalQuery("where is policy", ("fixture:policy.py#Policy", "fixture:gone.md#Missing")),
#                 RetrievalQuery("ambiguous", ("fixture:same.md#Checkout",)),
#                 RetrievalQuery("whole", ("fixture:policy.py",)),
#                 RetrievalQuery("family", ("fixture:policy.py#Policy.*",)),
#                 RetrievalQuery("ineligible", ("fixture:@code/same.md#Checkout",), "code"))
#
#             def search(current, snapshot, query, prepared, **options):
#                 return RetrievalReply("identifier" if query.text == "Policy" else "question", True,
#                     (self.selected(snapshot, "fixture:policy.py#Policy.apply"),
#                      self.selected(snapshot, "fixture:first.py#First"),
#                      self.selected(snapshot, "fixture:second.py#Second"),
#                      self.selected(snapshot, "fixture:policy.py#Policy")))
#
#             report = self.measure(connection, queries, search)
#             self.assertEqual(report["recall"], {"at3": 0.0, "at10": 0.5})
#             self.assertEqual(report["byRoute"]["identifier"], {"queries": 1, "at3": 0.0, "at10": 1.0})
#             self.assertEqual(report["byRoute"]["question"]["at3"], 0.0)
#             rows = report["results"]
#             self.assertEqual(rows[0]["expected"][0]["resolved"]["version"], header)
#             self.assertEqual(rows[0]["expected"][0]["position"], 4)
#             self.assertNotIn("position", rows[1]["expected"][0])
#             self.assertTrue(all(not row["included"] for row in rows[2:]))
#             self.assertEqual([row["expected"][-1]["fault"] for row in rows[2:]],
#                 ["not_in_index", "ambiguous", "not_one_chunk", "not_in_index", "ineligible"])
#             self.assertEqual(len(rows[0]["returned"]), 4)
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_exact_header_positions_faults_and_whole_query_denominators

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_current_versions_vectors_and_settings_have_guarded_comparison_fingerprints
#     def test_current_versions_vectors_and_settings_have_guarded_comparison_fingerprints(self):
#         with self.connection() as connection:
#             _, _, version = self.seed(connection)
#             plan = self.vector(connection, version)
#             query = RetrievalQuery("Exact", ("fixture:guide.md#Exact",))
#             def search(current, snapshot, query, prepared, **options):
#                 return RetrievalReply("identifier", True, (self.selected(snapshot, "fixture:guide.md#Exact"),))
#             before = self.measure(connection, (query,), search)
#             self.assertEqual(comparison_failures(before, self.measure(connection, (query,), search)), ())
#             connection.execute("UPDATE public.mycel_vectors SET embedding=%s::vector WHERE plan_id=%s",
#                 ("[" + ",".join(["0", "1"] + ["0"] * 1022) + "]", plan))
#             changed = self.measure(connection, (query,), search)
#             self.assertIn("indexFingerprint", comparison_failures(before, changed))
#             changed_settings = replace(self.settings(), values=_freeze({**self.settings().values,
#                 "search": {**self.settings().values["search"], "shared_documents": [{"repo": "handbook", "paths": ["."]}]}}))
#             changed = self.measure(connection, (query,), search, settings=changed_settings)
#             self.assertIn("settingsHash", comparison_failures(before, changed))
#             connection.execute("UPDATE public.mycel_embedding_parts SET failure=%s WHERE plan_id=%s",
#                                (Jsonb({"kind": "fictional_failed_part"}), plan))
#             self.assertNotEqual(changed["indexFingerprint"], self.measure(connection, (query,), search)["indexFingerprint"])
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_current_versions_vectors_and_settings_have_guarded_comparison_fingerprints

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_concurrent_publication_cannot_mix_resolution_vectors_or_search_versions
#     def test_concurrent_publication_cannot_mix_resolution_vectors_or_search_versions(self):
#         with self.connection() as connection, self.connection() as writer:
#             file_id, chunk_id, version = self.seed(connection, source="# Old\n", name="Old")
#             plan = self.vector(connection, version)
#             old_values = []
#             def search(current, snapshot, query, prepared, **options):
#                 if not old_values:
#                     self.seed(writer, file_id=file_id, chunk_id=chunk_id, source="# New\n", name="New")
#                     writer.execute("DELETE FROM public.mycel_locations WHERE chunk_version=%s", (version,))
#                     writer.execute("DELETE FROM public.mycel_file_locations WHERE file_version IN "
#                         "(SELECT id FROM public.mycel_file_versions WHERE file_id=%s AND source_bytes=%s)", (file_id, b"# Old\n"))
#                     writer.execute("UPDATE public.mycel_vectors SET embedding=%s::vector WHERE plan_id=%s",
#                         ("[" + ",".join(["0", "1"] + ["0"] * 1022) + "]", plan))
#                 old_values.append(current.execute("SELECT source_bytes FROM public.mycel_chunk_versions WHERE id=%s",
#                                                   (version,)).fetchone()[0])
#                 self.assertTrue(current.execute("SELECT embedding::text FROM public.mycel_vectors WHERE plan_id=%s",
#                                                 (plan,)).fetchone()[0].startswith("[1,0,"))
#                 self.assertEqual(snapshot.resolver.resolve("fixture:guide.md#New", purpose="read").fault, "missing_name")
#                 return RetrievalReply("identifier", True, (self.selected(snapshot, "fixture:guide.md#Old"),))
#             queries = (RetrievalQuery("Old", ("fixture:guide.md#Old",)),) * 2
#             report = self.measure(connection, queries, search)
#             self.assertEqual(old_values, [b"# Old\n", b"# Old\n"])
#             self.assertTrue(all(row["expected"][0]["resolved"]["version"] == version for row in report["results"]))
#             with StoreRetrieval(connection, self.settings()).snapshot("fixture") as after:
#                 self.assertEqual(after.resolver.resolve("fixture:guide.md#Old", purpose="read").fault, "missing_name")
#                 self.assertNotEqual(report["indexFingerprint"], after.index_fingerprint)
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_concurrent_publication_cannot_mix_resolution_vectors_or_search_versions

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_shared_artifact_alias_selects_retained_code_primary_without_changing_identity
#     def test_shared_artifact_alias_selects_retained_code_primary_without_changing_identity(self):
#         with self.connection() as connection:
#             source = "# Shared\n# Other\n"
#             file_id, _, _ = self.seed(connection, repository="handbook", root="code",
#                 path="docs/shared.md", name="Shared", source=source, chunk_source="# Shared\n",
#                 span={"start": 0, "end": 9}, aliases=(("artifact", "selected/nested/shared.md"),))
#             self.seed(connection, file_id=file_id, repository="handbook", root="code",
#                 path="docs/shared.md", name="Other", source=source, chunk_source="# Other\n",
#                 span={"start": 9, "end": len(source)})
#             self.seed(connection, repository="handbook", root="code", path="docs/outside.md",
#                 name="Outside", aliases=(("artifact", "outside/shared.md"),))
#             self.seed(connection, repository="disabled", root="code", path="docs/shared.md",
#                 name="Hidden", aliases=(("artifact", "selected/nested/shared.md"),))
#             canonical = "handbook:@code/docs/shared.md#Shared"
#             alias = "handbook:@artifact/selected/nested/shared.md#Shared"
#             query = RetrievalQuery("where is shared", (alias, canonical,
#                 "handbook:@code/docs/shared.md#Other"), "docs")
#             before = self.contents(connection)
#
#             def search(current, snapshot, query, prepared, **options):
#                 return RetrievalReply("question", True, (self.selected(snapshot, alias),))
#
#             # An exact artifact file and its recursive parent must select the
#             # same physical document even though its retained primary is code.
#             for prefix in ("selected/nested/shared.md", "selected"):
#                 with self.subTest(prefix=prefix):
#                     settings = self.settings(shared=({"repo": "handbook", "paths": [prefix]},
#                         {"repo": "disabled", "paths": ["."]}))
#                     with StoreRetrieval(connection, settings).snapshot("fixture") as snapshot:
#                         resolve = lambda ref: snapshot.resolver.resolve(ref, purpose="read").selection.members[0]
#                         member = resolve(alias)
#                         self.assertEqual(member, resolve(canonical))
#                         self.assertEqual(member.place.address, canonical)
#                         self.assertTrue(snapshot.eligible(query, member))
#                         self.assertFalse(snapshot.eligible(replace(query, only="code"), member))
#                         self.assertFalse(snapshot.eligible(query, resolve("handbook:@artifact/outside/shared.md#Outside")))
#                         self.assertEqual(snapshot.resolver.resolve(
#                             "disabled:@artifact/selected/nested/shared.md#Hidden").fault, "disabled_repository")
#                     report = self.measure(connection, (query,), search, settings=settings)
#                     row = report["results"][0]
#                     self.assertTrue(row["included"])
#                     self.assertEqual(row["expected"][0]["resolved"], row["expected"][1]["resolved"])
#                     self.assertEqual([item["position"] for item in row["expected"][:2]], [1, 1])
#                     self.assertEqual(len(row["returned"]), 1)
#                     self.assertEqual(row["returned"][0]["address"], canonical)
#                     # Two aliases of Shared count once; the distinct unreturned
#                     # Other chunk supplies the second denominator member.
#                     self.assertEqual(report["recall"], {"at3": 0.5, "at10": 0.5})
#
#                     def alias_reply(current, snapshot, query, prepared, **options):
#                         place = self.selected(snapshot, alias)
#                         return RetrievalReply("question", True, (replace(place,
#                             address=replace(place.address, root="artifact", path="selected/nested/shared.md")),))
#
#                     with StoreRetrieval(connection, settings, search=alias_reply).snapshot("fixture") as snapshot:
#                         with self.assertRaises(MycelError) as error:
#                             snapshot.search(query, PreparedQueryVector((1.0,)))
#                         self.assertEqual(error.exception.code, "internal")
#             self.assertEqual(self.contents(connection), before)
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_shared_artifact_alias_selects_retained_code_primary_without_changing_identity

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_result_scope_uses_stored_corpus_and_only_selected_enabled_shared_documents
#     def test_result_scope_uses_stored_corpus_and_only_selected_enabled_shared_documents(self):
#         with self.connection() as connection:
#             self.seed(connection, root="code", path="docs/checkout.md", name="Checkout")
#             self.seed(connection, repository="handbook", path="selected/one.md", name="Selected")
#             self.seed(connection, repository="handbook", path="outside.md", name="Outside")
#             self.seed(connection, repository="disabled", path="selected/one.md", name="Hidden")
#             self.seed(connection, path="branch.md", name="Branch", location_kind="branch")
#             settings = self.settings(shared=({"repo": "handbook", "paths": ["selected"]},
#                                              {"repo": "disabled", "paths": ["."]}))
#             with StoreRetrieval(connection, settings).snapshot("fixture") as snapshot:
#                 resolve = lambda ref: snapshot.resolver.resolve(ref, purpose="read").selection.members[0]
#                 query = RetrievalQuery("docs", ("fixture:docs/checkout.md#Checkout",), "docs")
#                 self.assertTrue(snapshot.eligible(query, resolve("fixture:docs/checkout.md#Checkout")))
#                 self.assertFalse(snapshot.eligible(replace(query, only="code"), resolve("fixture:docs/checkout.md#Checkout")))
#                 self.assertTrue(snapshot.eligible(query, resolve("handbook:selected/one.md#Selected")))
#                 self.assertFalse(snapshot.eligible(query, resolve("handbook:outside.md#Outside")))
#                 self.assertEqual(snapshot.resolver.resolve("disabled:selected/one.md#Hidden").fault, "disabled_repository")
#                 self.assertEqual(snapshot.resolver.resolve("fixture:branch.md#Branch").fault, "missing_file")
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_result_scope_uses_stored_corpus_and_only_selected_enabled_shared_documents

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_read_handoff_rejects_missing_guards_and_expired_snapshot_and_store_blocks_writes
#     def test_read_handoff_rejects_missing_guards_and_expired_snapshot_and_store_blocks_writes(self):
#         with self.connection() as connection:
#             self.seed(connection)
#             for context in (atomic_transaction, snapshot_transaction):
#                 with context(connection):
#                     with self.assertRaises(MycelError):
#                         SourceResolver.from_read_transaction(connection, self.settings())
#             with structure_guard(connection), atomic_transaction(connection):
#                 with self.assertRaises(MycelError):
#                     SourceResolver.from_read_transaction(connection, self.settings())
#             before = self.contents(connection)
#             with StoreRetrieval(connection, self.settings()).snapshot("fixture") as snapshot:
#                 self.assertEqual(snapshot.resolver.resolve("fixture:guide.md#Exact").state, "resolved")
#                 # A nested savepoint contains the deliberately rejected write;
#                 # the adapter itself never opens one or allocates lock keys.
#                 with self.assertRaises(Exception) as error:
#                     with connection.transaction():
#                         connection.execute("DELETE FROM public.mycel_chunk_versions")
#                 self.assertEqual(error.exception.sqlstate, "25006")
#             self.assertEqual(self.contents(connection), before)
#             with self.assertRaises(MycelError):
#                 snapshot.search(RetrievalQuery("Exact", ("fixture:guide.md#Exact",)), PreparedQueryVector((1.0,)))
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_read_handoff_rejects_missing_guards_and_expired_snapshot_and_store_blocks_writes

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_store.py::EvaluationStoreTests.test_empty_section_reports_actual_index_and_null_shares_without_search
#     def test_empty_section_reports_actual_index_and_null_shares_without_search(self):
#         with self.connection() as connection:
#             self.seed(connection)
#             before = self.contents(connection)
#             report = run_retrieval_evaluation(self.suite(), repository="fixture", build="412",
#                 model="voyage-code-4", query_vectors=_Vectors(connection),
#                 retrieval=StoreRetrieval(connection, self.settings()))
#             self.assertIsNotNone(report["indexGeneration"])
#             self.assertEqual(len(report["indexFingerprint"]), 64)
#             self.assertEqual(report["recall"], {"at3": None, "at10": None})
#             self.assertEqual(report["results"], [])
#             self.assertEqual(self.contents(connection), before)
# TEST-TIER-DISABLED-END tests/test_evaluation_store.py::EvaluationStoreTests.test_empty_section_reports_actual_index_and_null_shares_without_search


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_store.py:16
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_evaluation_store.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_store.py:17
# from mycel._evaluation import (EvaluationSet, PreparedQueryVector, RetrievalPlace,
#     RetrievalQuery, RetrievalReply, comparison_failures, run_retrieval_evaluation)
# TEST-TIER-IMPORTS-END tests/test_evaluation_store.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_store.py:20
# from mycel._locks import atomic_transaction, snapshot_transaction, structure_guard
# TEST-TIER-IMPORTS-END tests/test_evaluation_store.py:20

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_store.py:21
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_evaluation_store.py:21

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
