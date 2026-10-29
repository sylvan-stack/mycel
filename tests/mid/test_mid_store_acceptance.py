"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_store_acceptance as _support
from test_store_acceptance import (
    EmptyProductStoreTests,
    MycelError,
    ProductStoreTests,
    RecordingConnection,
    contextmanager,
    io,
    json,
    load_settings,
    patch,
    psycopg,
    run,
    sha256,
    socket,
    store,
    unittest,
    uuid4,
)


class ProductStoreTests(_support.ProductStoreTests):
# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_product_init_has_both_indexes_only_metadata_and_stable_generation
    def test_product_init_has_both_indexes_only_metadata_and_stable_generation(self):
        with self.connection() as connection:
            first = store.require_store(connection)
            self.assertEqual(first.state, "current")
            self.assertEqual((first.format, first.dimensions), (store.STORE_FORMAT, 1024))
            self.assertIsNotNone(first.index_generation)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_repository_state").fetchone(), (0,))
            for table in store.TABLES:
                if table.name != "mycel_store":
                    self.assertEqual(connection.execute(f"SELECT count(*) FROM public.{table.name}").fetchone(), (0,))
            indexes = {row[0] for row in connection.execute(
                "SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname='public'").fetchall()}
            self.assertTrue({store.BM25_INDEX, store.VECTOR_INDEX}.issubset(indexes))
            same = store.initialize_store(connection, dimensions=1024)
            self.assertFalse(same.changed)
            self.assertEqual(same.after.index_generation, first.index_generation)
        # A second invocation reads persisted identity, rather than memory state.
        out = io.StringIO()
        self.assertEqual(run(["info"], stdout=out, stderr=io.StringIO()), 0)
        diagnostic = json.loads(out.getvalue())["store"]
        self.assertEqual(diagnostic["indexGeneration"], first.index_generation)
        self.assertEqual(diagnostic["location"], self.store_fixture.backend.address(self.store_fixture.database))
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_product_init_has_both_indexes_only_metadata_and_stable_generation

# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_compatible_init_and_read_guards_issue_no_ddl
    def test_compatible_init_and_read_guards_issue_no_ddl(self):
        with self.connection() as connection:
            recorded = RecordingConnection(connection)
            result = store.initialize_store(recorded, dimensions=1024)
            self.assertFalse(result.changed)
            with store.checked_store(recorded) as inspection:
                self.assertEqual(inspection.state, "current")
            self.assertFalse(any(statement.lstrip().upper().startswith(
                ("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE")) for statement in recorded.statements))
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_compatible_init_and_read_guards_issue_no_ddl

# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_newer_and_foreign_stores_refuse_without_reading_foreign_or_v1_tables
    def test_newer_and_foreign_stores_refuse_without_reading_foreign_or_v1_tables(self):
        with self.connection() as connection:
            connection.execute("UPDATE public.mycel_store SET format=%s", (store.STORE_FORMAT + 1,))
            connection.execute("CREATE TABLE public.mycel_future_feature (value text)")
            recorded = RecordingConnection(connection)
            self.error("store_format", lambda: store.initialize_store(recorded, dimensions=1024))
            self.error("store_format", lambda: store.require_store(recorded))
            self.assertEqual(store.inspect_store(recorded).format, store.STORE_FORMAT + 1)
            self.assertFalse(any("FROM public.mycel_future_feature" in statement for statement in recorded.statements))
            connection.execute("DROP TABLE public.mycel_future_feature")
            connection.execute("UPDATE public.mycel_store SET format=%s", (store.STORE_FORMAT,))
            connection.execute("CREATE TABLE public.kn_documents (value text)")
            recorded.statements.clear()
            self.error("refused", lambda: store.initialize_store(recorded, dimensions=1024))
            self.error("store_format", lambda: store.require_store(recorded))
            self.assertFalse(any("FROM public." in statement for statement in recorded.statements))
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_newer_and_foreign_stores_refuse_without_reading_foreign_or_v1_tables

# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_migration_step_rolls_back_ddl_and_format_while_preserving_generation
    def test_migration_step_rolls_back_ddl_and_format_while_preserving_generation(self):
        with self.connection() as connection:
            before = store.require_store(connection)
            def fail(current):
                current.execute("CREATE TABLE public.mycel_migration_probe (value text)")
                current.execute("UPDATE public.mycel_store SET format=%s", (store.STORE_FORMAT + 1,))
                raise RuntimeError("deliberate public fixture migration failure")
            with self.assertRaises(RuntimeError):
                store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 1, before.index_generation,
                               {store.STORE_FORMAT: store.Migration(fail, lambda current: None)})
            self.assertEqual(connection.execute(
                "SELECT to_regclass('public.mycel_migration_probe')").fetchone(), (None,))
            after = store.require_store(connection)
            self.assertEqual((after.format, after.index_generation), (store.STORE_FORMAT, before.index_generation))
            self.error("store_format", lambda: store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 1, before.index_generation, {}))
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_migration_step_rolls_back_ddl_and_format_while_preserving_generation

# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_dimension_change_removes_only_vectors_retaining_complete_text_parts_and_failures
    def test_dimension_change_removes_only_vectors_retaining_complete_text_parts_and_failures(self):
        text, chunk, plan = "Public fixture text with 雪.\n", uuid4(), uuid4()
        with self.connection() as connection:
            before = store.require_store(connection)
            connection.execute("INSERT INTO public.mycel_repository_state (repository, read_locations) VALUES ('fixture','{}')")
            connection.execute("INSERT INTO public.mycel_chunks (id,repository,kind,metadata) VALUES (%s,'fixture','code','{}')", (chunk,))
            version = connection.execute(
                "INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) "
                "VALUES (%s,%s,%s,%s,'{}','{}') RETURNING id", (chunk, sha256(text.encode()).hexdigest(), text.encode(), store.search_text(text.encode()))).fetchone()[0]
            connection.execute("INSERT INTO public.mycel_embedding_plans "
                "(id,chunk_version,model,dimensions,plan_hash,place_line,provenance,failure) "
                "VALUES (%s,%s,'voyage-code-4',1024,'fixture-plan','fixture.py — symbol (function)','{}',"
                "'{\"kind\":\"public-fixture\"}')", (plan, version))
            connection.execute("INSERT INTO public.mycel_embedding_parts "
                "(plan_id,part_order,byte_start,byte_end,input_bytes,submitted_tokens,planning_tokens) "
                "VALUES (%s,0,0,%s,%s,1,1)", (plan, len(text.encode()), text.encode()))
            vector = "[" + ",".join(["1"] + ["0"]*1023) + "]"
            connection.execute("INSERT INTO public.mycel_vectors VALUES (%s,0,'voyage-code-4',1024,%s::vector)", (plan, vector))
            self.error("store_format", lambda: store.require_store(connection, dimensions=2048, operation="embed"))
            self.assertEqual(store.require_store(connection, dimensions=2048, operation="search").dimensions, 1024)
            changed = store.initialize_store(connection, dimensions=2048)
            self.assertEqual(changed.vectors_removed, 1)
            self.assertEqual(changed.after.index_generation, before.index_generation)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT text FROM public.mycel_chunk_versions WHERE id=%s", (version,)).fetchone(), (text,))
            self.assertEqual(connection.execute("SELECT input_bytes FROM public.mycel_embedding_parts WHERE plan_id=%s", (plan,)).fetchone(), (text.encode(),))
            self.assertEqual(connection.execute("SELECT failure->>'kind' FROM public.mycel_embedding_plans WHERE id=%s", (plan,)).fetchone(), ("public-fixture",))
            self.assertEqual(store.require_store(connection, dimensions=2048, operation="embed").dimensions, 2048)
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_dimension_change_removes_only_vectors_retaining_complete_text_parts_and_failures

# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_unreachable_target_refuses_init_but_info_and_plain_grep_remain_available
    def test_unreachable_target_refuses_init_but_info_and_plain_grep_remain_available(self):
        # Reserve a loopback port without listening, so no other server can take
        # it and this target cannot authenticate to an unintended database.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            config = self.store_fixture.root / "unavailable.toml"
            config.write_text('[store]\naddress="postgresql://fixture@127.0.0.1:' + str(port)
                              + '/mycel_check_unavailable?sslmode=disable"\n')
            snapshot = load_settings(path=config)
            with patch("mycel._cli.load_settings", return_value=snapshot):
                out = io.StringIO()
                self.assertEqual(run(["init"], stdout=out, stderr=io.StringIO()), 1)
                self.assertEqual(json.loads(out.getvalue())["error"]["code"], "store_unavailable")
                out = io.StringIO()
                self.assertEqual(run(["info"], stdout=out, stderr=io.StringIO()), 0)
                self.assertEqual(json.loads(out.getvalue())["store"]["state"], "unavailable")
                path = self.store_fixture.root / "grep.txt"
                path.write_text("public needle\n")
                self.assertEqual(run(["grep", "-q", "needle", str(path)], stdout=io.StringIO(), stderr=io.StringIO()), 0)
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_unreachable_target_refuses_init_but_info_and_plain_grep_remain_available



class EmptyProductStoreTests(_support.EmptyProductStoreTests):
# TEST-TIER-BEGIN tests/test_store_acceptance.py::EmptyProductStoreTests.test_empty_store_is_refused_by_read_and_created_only_by_explicit_product_init
    def test_empty_store_is_refused_by_read_and_created_only_by_explicit_product_init(self):
        fixture = self.store_fixture
        with fixture.backend.connection(fixture.database) as connection:
            self.assertEqual(store.inspect_store(connection).state, "empty")
            with self.assertRaises(MycelError) as error:
                store.require_store(connection)
            self.assertEqual(error.exception.code.value, "store_format")
        out = io.StringIO()
        self.assertEqual(run(["init"], stdout=out, stderr=io.StringIO()), 0)
        self.assertTrue(json.loads(out.getvalue())["changed"])
        with fixture.backend.connection(fixture.database) as connection:
            self.assertEqual(store.require_store(connection).state, "current")
# TEST-TIER-END tests/test_store_acceptance.py::EmptyProductStoreTests.test_empty_store_is_refused_by_read_and_created_only_by_explicit_product_init
