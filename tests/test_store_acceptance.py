"""Product-store acceptance requires a real per-check disposable database."""

from contextlib import contextmanager
from hashlib import sha256
import io
import json
import socket
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg

from mycel._cli import run
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._settings import load_settings
from mycel import _store as store


class RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **kwargs)

    def transaction(self, *args, **kwargs):
        return self.connection.transaction(*args, **kwargs)


class ProductStoreTests(unittest.TestCase):
    check_kind = "store"

    def connection(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def error(self, code, action):
        with self.assertRaises(MycelError) as error:
            action()
        self.assertEqual(error.exception.code.value, code)

    @proves("MYC-0.4", "MYC-6.1", "MYC-6.5", "MYC-6.19", kind="store")
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

    @proves("MYC-0.8", "MYC-6.5", kind="store")
    def test_compatible_init_and_read_guards_issue_no_ddl(self):
        with self.connection() as connection:
            recorded = RecordingConnection(connection)
            result = store.initialize_store(recorded, dimensions=1024)
            self.assertFalse(result.changed)
            with store.checked_store(recorded) as inspection:
                self.assertEqual(inspection.state, "current")
            self.assertFalse(any(statement.lstrip().upper().startswith(
                ("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE")) for statement in recorded.statements))

    @proves("MYC-0.8", "MYC-6.7", "MYC-6.17", kind="store")
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

    @proves("MYC-6.6", "MYC-6.19", kind="store")
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

    @proves("MYC-6.8", "MYC-6.19", kind="store")
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

    @proves("MYC-6.5", "MYC-6.19", kind="store")
    def test_exact_utf8_nul_bytes_projection_and_hash_guards_roundtrip(self):
        samples = ("before\0after 雪", "\0\0\0", "literal \\000 \\0", "\x10\x01\xa0\0\x10\x01", "\uf00b\0\U000f000b", "")
        with self.connection() as connection:
            # Repeated suffix lookaheads made even modest dense NUL input
            # quadratic. Exact full input must survive a finite SQL deadline.
            with connection.transaction():
                connection.execute("SET LOCAL statement_timeout = '2000ms'")
                dense = b'\0' * 100_000
                try:
                    projection = connection.execute('SELECT ' + store._TEXT_PROJECTION_SQL
                            + ' FROM (SELECT %s::bytea AS source_bytes) s', (dense,)).fetchone()[0]
                except psycopg.Error as exc:
                    self.fail('Dense NUL projection failed: ' + type(exc).__name__ + ':' + str(exc.sqlstate))
                self.assertEqual(projection, '\ufffd' * len(dense))
            self.assertEqual(connection.execute('SELECT current_database()').fetchone()[0], self.store_fixture.database)
            connection.execute("INSERT INTO public.mycel_repository_state VALUES ('fixture',NULL,'{}')")
            for text in samples:
                raw, chunk = text.encode(), uuid4()
                connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,'fixture',NULL,'code','{}')", (chunk,))
                version = connection.execute("INSERT INTO public.mycel_chunk_versions "
                    "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}','{}') RETURNING id",
                    (chunk,sha256(raw).hexdigest(),raw,store.search_text(raw))).fetchone()[0]
                self.assertEqual(connection.execute("SELECT source_bytes,text,snapshot_hash FROM public.mycel_chunk_versions WHERE id=%s",
                    (version,)).fetchone(), (raw,text.replace('\0','\ufffd'),sha256(raw).hexdigest()))
                for statement, parameters in (("UPDATE public.mycel_chunk_versions SET snapshot_hash=%s WHERE id=%s",('0'*64,version)),
                    ("UPDATE public.mycel_chunk_versions SET source_bytes=%s WHERE id=%s",(raw+b'changed',version)),
                    ("UPDATE public.mycel_chunk_versions SET text=%s WHERE id=%s",('wrong projection',version))):
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        with connection.transaction():
                            connection.execute(statement,parameters)
                self.assertEqual(connection.execute("SELECT source_bytes FROM public.mycel_chunk_versions WHERE id=%s",(version,)).fetchone(),(raw,))

    @proves("MYC-6.3", kind="store")
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


class EmptyProductStoreTests(unittest.TestCase):
    check_kind = "store"

    initialize_store = staticmethod(lambda backend, settings_file: None)

    @proves("MYC-0.8", "MYC-6.5", "MYC-6.7", kind="store")
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


if __name__ == "__main__":
    unittest.main()
