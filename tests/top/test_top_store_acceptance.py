"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_store_acceptance as _support
from test_store_acceptance import (
    psycopg,
    sha256,
    store,
    uuid4,
)


class ProductStoreTests(_support.ProductStoreTests):
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
