"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_store as _support
# from test_store import (
#     CatalogueConnection,
#     MycelError,
#     Rows,
#     StoreUnitTests,
#     contextmanager,
#     deepcopy,
#     psycopg,
#     store,
#     unittest,
#     uuid4,
# )


# class StoreUnitTests(_support.StoreUnitTests):
# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_search_projection_is_explicit_and_exact_utf8_bytes_remain_authoritative
#     def test_search_projection_is_explicit_and_exact_utf8_bytes_remain_authoritative(self):
#         for text in ('\0before\0雪\0', r'literal \000', '\x10\x01\xa0\0', '\uf00b\0\U000f000b', ''):
#             raw = text.encode()
#             self.assertEqual(store.exact_text(memoryview(raw)),text)
#             self.assertEqual(store.search_text(raw),text.replace('\0','\ufffd'))
#             self.assertEqual(store.exact_bytes(bytearray(raw)),raw)
#         for invalid in ('projected text', 4, None, b'\xff'):
#             with self.assertRaises(MycelError):
#                 store.exact_text(invalid)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_search_projection_is_explicit_and_exact_utf8_bytes_remain_authoritative

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_foreign_and_v1_catalogue_refusals_never_read_or_write_their_tables
#     def test_foreign_and_v1_catalogue_refusals_never_read_or_write_their_tables(self):
#         for relation in (("public", "kn_documents", "r"), ("public", "mycel_unknown", "r"),
#                          ("another", "mycel_store", "r"), ("public", "owner_view", "v"),
#                          ("public", "owner_sequence", "S"), ("public", "mycel_store", "p")):
#             with self.subTest(relation=relation):
#                 connection = CatalogueConnection(current=True)
#                 connection.relations.append(relation)
#                 inspection = store.inspect_store(connection)
#                 self.assertEqual(inspection.state, "foreign")
#                 self.error("refused", lambda: store.initialize_store(connection, dimensions=1024))
#                 self.error("store_format", lambda: store.require_store(connection))
#                 self.assertFalse(connection.mutations)
#                 if relation[1] != "mycel_unknown":
#                     self.assertFalse(any("FROM public." in sql for sql, _ in connection.sql))
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_foreign_and_v1_catalogue_refusals_never_read_or_write_their_tables

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_metadata_lookalike_is_rejected_before_product_data_read
#     def test_metadata_lookalike_is_rejected_before_product_data_read(self):
#         connection = CatalogueConnection()
#         connection.relations = [("public", "mycel_store", "r")]
#         connection.columns = {"mycel_store": {"format": ("text", False, "")}}
#         self.assertEqual(store.inspect_store(connection).state, "damaged")
#         self.error("store_format", lambda: store.initialize_store(connection, dimensions=1024))
#         self.assertFalse(any("FROM public." in sql for sql, _ in connection.sql))
#         self.assertFalse(connection.mutations)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_metadata_lookalike_is_rejected_before_product_data_read

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_empty_store_guard_and_diagnostics_have_no_implicit_bootstrap
#     def test_empty_store_guard_and_diagnostics_have_no_implicit_bootstrap(self):
#         connection = CatalogueConnection()
#         inspection = store.inspect_store(connection)
#         self.assertEqual(inspection.diagnostic(), {"state": "empty", "format": None,
#                                                    "dimensions": None, "indexGeneration": None})
#         self.error("store_format", lambda: store.require_store(connection))
#         self.assertFalse(connection.mutations)
#         self.assertIn("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY", [sql for sql, _ in connection.sql])
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_empty_store_guard_and_diagnostics_have_no_implicit_bootstrap

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_explicit_initialization_creates_both_indexes_and_only_metadata_row
#     def test_explicit_initialization_creates_both_indexes_and_only_metadata_row(self):
#         for dimensions in (256, 512, 1024, 2048):
#             with self.subTest(dimensions=dimensions):
#                 connection = CatalogueConnection()
#                 result = store.initialize_store(connection, dimensions=dimensions)
#                 self.assertTrue(result.changed)
#                 self.assertEqual(result.after.state, "current")
#                 self.assertEqual(result.after.dimensions, dimensions)
#                 self.assertEqual(len(connection.metadata), 1)
#                 self.assertEqual(UUID(result.after.index_generation), connection.metadata[0][3])
#                 inserts = [sql for sql in connection.mutations if sql.startswith("INSERT")]
#                 self.assertEqual(len(inserts), 1)
#                 self.assertTrue(inserts[0].startswith("INSERT INTO public.mycel_store"))
#                 self.assertEqual(set(connection.indexes), {store.BM25_INDEX, store.VECTOR_INDEX})
#                 vector_column = connection.columns["mycel_vectors"]["embedding"][0]
#                 self.assertEqual(vector_column, f"vector({dimensions})")
#                 if dimensions == 2048:
#                     self.assertIn("embedding::halfvec(2048)", connection.indexes[store.VECTOR_INDEX][7])
#                 self.assertEqual(connection.locks, 0)
#                 self.assertEqual(result.reply("configured-password-free-address")["format"], {"before": None, "after": store.STORE_FORMAT})
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_explicit_initialization_creates_both_indexes_and_only_metadata_row

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_missing_extensions_are_named_before_any_ddl_and_transaction_rolls_back
#     def test_missing_extensions_are_named_before_any_ddl_and_transaction_rolls_back(self):
#         for missing in ("pg_search", "vector"):
#             connection = CatalogueConnection()
#             connection.available.remove(missing)
#             error = self.error("refused", lambda: store.initialize_store(connection, dimensions=1024))
#             self.assertIn(missing, str(error))
#             self.assertFalse(connection.mutations)
#             self.assertFalse(connection.relations)
#             self.assertEqual(connection.locks, 0)
#             self.assertIn("rollback", connection.transactions)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_missing_extensions_are_named_before_any_ddl_and_transaction_rolls_back

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_ddl_failure_rolls_back_extensions_schema_and_metadata_without_raw_error
#     def test_ddl_failure_rolls_back_extensions_schema_and_metadata_without_raw_error(self):
#         for stop in ("CREATE TABLE public.mycel_chunks", f"CREATE INDEX {store.BM25_INDEX}",
#                      "INSERT INTO public.mycel_store"):
#             connection = CatalogueConnection()
#             connection.failure = lambda sql: sql.startswith(stop)
#             error = self.error("refused", lambda: store.initialize_store(connection, dimensions=1024))
#             self.assertNotIn("private", str(error))
#             self.assertFalse(connection.relations)
#             self.assertFalse(connection.metadata)
#             self.assertEqual(connection.extensions, {"plpgsql"})
#             self.assertEqual(connection.locks, 0)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_ddl_failure_rolls_back_extensions_schema_and_metadata_without_raw_error

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_newer_format_with_unrecognized_future_relation_is_still_store_format
#     def test_newer_format_with_unrecognized_future_relation_is_still_store_format(self):
#         connection = CatalogueConnection(current=True)
#         singleton, _, dimensions, generation = connection.metadata[0]
#         connection.metadata[0] = (singleton, store.STORE_FORMAT + 1, dimensions, generation)
#         connection.relations.append(("public", "mycel_future_feature", "r"))
#         self.assertEqual(store.inspect_store(connection).state, "newer")
#         self.error("store_format", lambda: store.initialize_store(connection, dimensions=1024))
#         self.assertFalse(connection.mutations)
#         self.assertFalse(any("FROM public.mycel_future_feature" in sql for sql, _ in connection.sql))
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_newer_format_with_unrecognized_future_relation_is_still_store_format

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_noop_init_refuses_exclusive_structure_lock_but_accepts_other_shared_work
#     def test_noop_init_refuses_exclusive_structure_lock_but_accepts_other_shared_work(self):
#         connection = CatalogueConnection(current=True)
#         connection.shared_busy = True
#         self.error("busy", lambda: store.initialize_store(connection, dimensions=1024))
#         self.assertFalse(connection.mutations)
#         connection.shared_busy = False
#         connection.exclusive_busy = True
#         self.assertFalse(store.initialize_store(connection, dimensions=1024).changed)
#         self.assertFalse(connection.mutations)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_noop_init_refuses_exclusive_structure_lock_but_accepts_other_shared_work

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_damaged_metadata_missing_columns_constraints_and_indexes_refuse_noop
#     def test_damaged_metadata_missing_columns_constraints_and_indexes_refuse_noop(self):
#         mutations = (
#             lambda c: c.metadata.clear(),
#             lambda c: c.metadata.append(c.metadata[0]),
#             lambda c: c.columns["mycel_vectors"].update(embedding=("vector(512)", False, "")),
#             lambda c: c.constraints.remove(next(row for row in c.constraints if row[1] == "f")),
#             lambda c: c.checks.remove(next(row for row in c.checks if row[0] == "mycel_snapshots")),
#             lambda c: c.checks.remove(next(row for row in c.checks if row[0] == "mycel_store")),
#             lambda c: c.indexes.pop(store.BM25_INDEX),
#             lambda c: c.indexes.update({store.VECTOR_INDEX: (*c.indexes[store.VECTOR_INDEX][:5], False,
#                                                             *c.indexes[store.VECTOR_INDEX][6:])}),
#             lambda c: c.extensions.remove("vector"),
#             lambda c: c.relations.remove(("public", "mycel_chunks", "r")),
#         )
#         for mutate in mutations:
#             with self.subTest(mutate=mutate):
#                 connection = CatalogueConnection(current=True)
#                 mutate(connection)
#                 self.assertEqual(store.inspect_store(connection).state, "damaged")
#                 self.error("store_format", lambda: store.initialize_store(connection, dimensions=1024))
#                 self.assertFalse(connection.mutations)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_damaged_metadata_missing_columns_constraints_and_indexes_refuse_noop

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_native_metadata_read_failure_is_sanitized_format_fault
#     def test_native_metadata_read_failure_is_sanitized_format_fault(self):
#         connection = CatalogueConnection(current=True)
#         connection.failure = lambda sql: sql.startswith("SELECT singleton, format")
#         error = self.error("store_format", lambda: store.initialize_store(connection, dimensions=1024))
#         self.assertNotIn("private", str(error))
#         self.assertFalse(connection.mutations)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_native_metadata_read_failure_is_sanitized_format_fault

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_dimension_change_preserves_generation_text_parts_failures_and_evidence
#     def test_dimension_change_preserves_generation_text_parts_failures_and_evidence(self):
#         connection = CatalogueConnection(current=True)
#         connection.vector_count = 7
#         connection.receipt_count = 2
#         generation, rows = connection.metadata[0][3], deepcopy(connection.other_rows)
#         result = store.initialize_store(connection, dimensions=2048)
#         self.assertEqual(result.vectors_removed, 7)
#         self.assertEqual(result.before.dimensions, 1024)
#         self.assertEqual(result.after.dimensions, 2048)
#         self.assertEqual(connection.metadata[0][3], generation)
#         self.assertEqual(connection.other_rows, rows)
#         self.assertEqual(connection.vector_count, 0)
#         self.assertEqual(connection.receipt_count, 0)
#         self.assertEqual([sql for sql in connection.mutations if sql.startswith("DELETE")],
#                          ["DELETE FROM public.mycel_vectors", "DELETE FROM public.mycel_embedding_receipts"])
#         self.assertEqual(connection.locks, 0)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_dimension_change_preserves_generation_text_parts_failures_and_evidence

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_failed_dimension_change_rolls_back_vectors_column_and_metadata
#     def test_failed_dimension_change_rolls_back_vectors_column_and_metadata(self):
#         connection = CatalogueConnection(current=True)
#         connection.vector_count = 3
#         connection.receipt_count = 2
#         before = deepcopy((connection.columns, connection.indexes, connection.metadata))
#         connection.failure = lambda sql: sql.startswith(f"CREATE INDEX {store.VECTOR_INDEX}")
#         self.error("refused", lambda: store.initialize_store(connection, dimensions=512))
#         self.assertEqual(connection.vector_count, 3)
#         self.assertEqual(connection.receipt_count, 2)
#         self.assertEqual((connection.columns, connection.indexes, connection.metadata), before)
#         self.assertEqual(connection.locks, 0)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_failed_dimension_change_rolls_back_vectors_column_and_metadata

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_invalid_dimension_is_rejected_before_catalogue_or_lock
#     def test_invalid_dimension_is_rejected_before_catalogue_or_lock(self):
#         for dimensions in (True, 0, 1, 4096, "1024", float("nan")):
#             connection = CatalogueConnection()
#             self.error("settings", lambda: store.initialize_store(connection, dimensions=dimensions))
#             self.assertFalse(connection.sql)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_invalid_dimension_is_rejected_before_catalogue_or_lock

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_structure_lock_never_waits_and_shared_guard_lasts_through_operation
#     def test_structure_lock_never_waits_and_shared_guard_lasts_through_operation(self):
#         connection = CatalogueConnection(current=True)
#         with store.checked_store(connection) as inspection:
#             self.assertEqual(connection.locks, 1)
#             self.assertEqual(inspection.state, "current")
#         self.assertEqual(connection.locks, 0)
#         connection.shared_busy = True
#         self.error("busy", lambda: self.enter_checked(connection))
#         connection.exclusive_busy = True
#         self.error("busy", lambda: store.initialize_store(connection, dimensions=512))
#         self.assertFalse(connection.mutations)
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_structure_lock_never_waits_and_shared_guard_lasts_through_operation

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_explicit_forward_migrations_are_consecutive_atomic_and_preserve_generation
#     def test_explicit_forward_migrations_are_consecutive_atomic_and_preserve_generation(self):
#         connection = CatalogueConnection(current=True)
#         generation = str(connection.metadata[0][3])
#         events = []
#         def step(number):
#             def apply(current):
#                 events.append((number, current.metadata[0][1], current.in_transaction))
#                 current.other_rows[str(number)] = "applied"
#             def validate(current):
#                 self.assertEqual(current.other_rows[str(number)], "applied")
#             return store.Migration(apply, validate)
#         start = store.STORE_FORMAT
#         store._migrate(connection, start, start + 2, generation, {start: step(start), start + 1: step(start + 1)})
#         self.assertEqual(events, [(start, start, True), (start + 1, start + 1, True)])
#         self.assertEqual(connection.metadata[0][1], start + 2)
#         self.assertEqual(str(connection.metadata[0][3]), generation)
#         self.assertEqual(connection.transactions, ["begin", "commit", "begin", "commit"])
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_explicit_forward_migrations_are_consecutive_atomic_and_preserve_generation

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_missing_migration_path_refuses_before_any_partial_change
#     def test_missing_migration_path_refuses_before_any_partial_change(self):
#         connection = CatalogueConnection(current=True)
#         generation = str(connection.metadata[0][3])
#         step = store.Migration(lambda current: self.fail("partial migration"), lambda current: None)
#         self.error("store_format", lambda: store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 2, generation, {store.STORE_FORMAT: step}))
#         self.assertFalse(connection.mutations)
#         self.assertFalse(connection.transactions)
#         self.assertEqual(store.STORE_FORMAT, 5)
#         self.assertEqual(set(store.MIGRATIONS), {1, 2, 3, 4})
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_missing_migration_path_refuses_before_any_partial_change

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_failed_migration_rolls_back_only_failed_step_and_generation_change_refuses
#     def test_failed_migration_rolls_back_only_failed_step_and_generation_change_refuses(self):
#         for change_generation in (False, True):
#             connection = CatalogueConnection(current=True)
#             generation = str(connection.metadata[0][3])
#             first = store.Migration(lambda c: c.other_rows.update(first="complete"), lambda c: None)
#             def broken(c):
#                 c.other_rows["second"] = "partial"
#                 if change_generation:
#                     singleton, number, dimensions, _ = c.metadata[0]
#                     c.metadata[0] = (singleton, number, dimensions, uuid4())
#                 else:
#                     raise RuntimeError("injected migration failure")
#             second = store.Migration(broken, lambda c: None)
#             with self.assertRaises(MycelError if change_generation else RuntimeError):
#                 store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 2, generation,
#                                {store.STORE_FORMAT: first, store.STORE_FORMAT + 1: second})
#             self.assertEqual(connection.metadata[0][1], store.STORE_FORMAT + 1)
#             self.assertEqual(str(connection.metadata[0][3]), generation)
#             self.assertEqual(connection.other_rows["first"], "complete")
#             self.assertNotIn("second", connection.other_rows)
#             self.assertEqual(connection.transactions, ["begin", "commit", "begin", "rollback"])
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_failed_migration_rolls_back_only_failed_step_and_generation_change_refuses

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_search_index_deparse_normalization_accepts_only_equivalent_expressions
#     def test_search_index_deparse_normalization_accepts_only_equivalent_expressions(self):
#         connection = CatalogueConnection(current=True)
#         row = connection.indexes[store.BM25_INDEX]
#         connection.indexes[store.BM25_INDEX] = (*row[:7], row[7].replace("(text::", "((text)::")
#                                                .replace("'id'", "id"), row[8])
#         self.assertEqual(store.inspect_store(connection).state, "current")
#         row = connection.indexes[store.VECTOR_INDEX]
#         connection.indexes[store.VECTOR_INDEX] = (*row[:7], row[7].replace("vector_cosine_ops", "vector_l2_ops"), row[8])
#         self.assertEqual(store.inspect_store(connection).state, "damaged")
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_search_index_deparse_normalization_accepts_only_equivalent_expressions

# TEST-TIER-DISABLED-BEGIN tests/test_store.py::StoreUnitTests.test_foreign_extension_is_rejected_without_reading_product_rows
#     def test_foreign_extension_is_rejected_without_reading_product_rows(self):
#         connection = CatalogueConnection(current=True)
#         connection.extensions.add("other_product")
#         self.assertEqual(store.inspect_store(connection).state, "foreign")
#         self.assertFalse(any("FROM public." in sql for sql, _ in connection.sql))
# TEST-TIER-DISABLED-END tests/test_store.py::StoreUnitTests.test_foreign_extension_is_rejected_without_reading_product_rows


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_store.py:11
# from uuid import UUID, uuid4
# TEST-TIER-IMPORTS-END tests/test_store.py:11

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
