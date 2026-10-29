# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Catalogue/transaction unit checks, not PostgreSQL store acceptance proofs.

The scripted connection proves safe sequencing and refusal paths. Actual table
constraints and BM25/HNSW execution must still pass native disposable-store
checks; no store requirement is claimed by these stand-ins.
"""

import unittest
from contextlib import contextmanager
from copy import deepcopy
from uuid import uuid4

import psycopg

from mycel import _store as store
from mycel._errors import MycelError


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class CatalogueConnection:
    """A SQL-scripted seam: no socket, subprocess, credential or provider."""

    def __init__(self, *, current=False, dimensions=1024):
        self.relations = []
        self.columns = {}
        self.constraints = set()
        self.checks = set()
        self.indexes = {}
        self.extensions = {"plpgsql"}
        self.available = {"plpgsql", "pg_search", "vector"}
        self.metadata = []
        self.vector_count = 0
        self.receipt_count = 0
        self.other_rows = {"text": "exact complete text", "evidence": b"retained bytes",
                           "plan": "original", "failure": "recorded"}
        self.sql = []
        self.transactions = []
        self.in_transaction = False
        self.failure = None
        self.shared_busy = False
        self.exclusive_busy = False
        self.locks = 0
        if current:
            self.install(dimensions)

    def install(self, dimensions):
        self.extensions |= store.REQUIRED_EXTENSIONS
        for table in store.TABLES:
            self.add_table(table.name, dimensions)
        self.constraints = store._expected_constraints()
        self.checks = store._expected_checks()
        self.indexes = {
            store.BM25_INDEX: ("public", store.BM25_INDEX, "public", "mycel_chunk_versions", "bm25",
                               True, True, store._bm25_sql(), ["key_field=id"]),
            store.VECTOR_INDEX: ("public", store.VECTOR_INDEX, "public", "mycel_vectors", "hnsw",
                                 True, True, store._vector_sql(dimensions), None),
        }
        self.metadata = [(True, store.STORE_FORMAT, dimensions, uuid4())]

    def add_table(self, name, dimensions):
        self.relations.append(("public", name, "r"))
        self.columns[name] = store._expected_columns(dimensions)[name]
        table = store._TABLE_MAP[name]
        self.constraints |= {row for row in store._expected_constraints() if row[0] == name}
        self.checks |= {row for row in store._expected_checks() if row[0] == name}
        for column in table.columns:
            if "IDENTITY" in column.extra:
                self.relations.append(("public", name + "_" + column.name + "_seq", "S"))

    @contextmanager
    def transaction(self):
        if self.in_transaction:
            raise AssertionError("nested transaction")
        saved = deepcopy({key: value for key, value in self.__dict__.items()
                          if key not in {"sql", "transactions", "failure"}})
        self.in_transaction = True
        self.transactions.append("begin")
        try:
            yield
        except BaseException:
            self.__dict__.update(saved)
            self.transactions.append("rollback")
            raise
        else:
            self.in_transaction = False
            self.transactions.append("commit")

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if self.failure and self.failure(sql):
            raise psycopg.ProgrammingError("private server target and password must not escape")
        if sql.startswith("SET "):
            self.assert_transaction()
            return Rows()
        if "pg_try_advisory_lock" in sql:
            exclusive = "lock_shared" not in sql
            okay = not (self.exclusive_busy if exclusive else self.shared_busy)
            self.locks += int(okay)
            return Rows([(okay,)])
        if "pg_advisory_unlock" in sql:
            self.locks -= 1
            return Rows([(True,)])
        if "FROM pg_catalog.pg_extension " in sql:
            return Rows([(name,) for name in sorted(self.extensions)])
        if sql == store._RELATIONS_SQL:
            return Rows(self.relations)
        if sql == store._COLUMNS_SQL:
            return Rows(("public", table, name, kind, nullable, identity)
                        for table in params[0] for name, (kind, nullable, identity)
                        in self.columns.get(table, {}).items())
        if sql == store._CONSTRAINTS_SQL:
            return Rows(("public", *row) for row in self.constraints)
        if sql == store._CHECKS_SQL:
            return Rows(("public", *row) for row in self.checks)
        if sql == store._INDEXES_SQL:
            return Rows(self.indexes.values())
        if sql.startswith("SELECT singleton, format"):
            return Rows(self.metadata)
        if sql.startswith("SELECT name FROM pg_catalog.pg_available_extensions"):
            return Rows([(name,) for name in sorted(self.available)])
        if sql.startswith("CREATE EXTENSION"):
            self.assert_transaction()
            self.extensions.add(sql.rsplit(" ", 1)[-1])
            return Rows()
        if sql.startswith("CREATE TABLE public."):
            self.assert_transaction()
            name = sql.split("public.", 1)[1].split(" ", 1)[0]
            dimensions = 2048 if "vector(2048)" in sql else 512 if "vector(512)" in sql else \
                         256 if "vector(256)" in sql else 1024
            self.add_table(name, dimensions)
            return Rows()
        if sql.startswith("CREATE INDEX"):
            self.assert_transaction()
            name = sql.split(" ")[2]
            table, method = ("mycel_vectors", "hnsw") if name == store.VECTOR_INDEX else \
                            ("mycel_chunk_versions", "bm25")
            self.indexes[name] = ("public", name, "public", table, method, True, True, sql, None)
            return Rows()
        if sql.startswith("INSERT INTO public.mycel_store"):
            self.assert_transaction()
            number, dimensions, generation = params
            self.metadata = [(True, number, dimensions, generation)]
            return Rows()
        if sql.startswith("SELECT count(*) FROM public.mycel_vectors"):
            return Rows([(self.vector_count,)])
        if sql.startswith("DELETE FROM public.mycel_vectors"):
            self.assert_transaction()
            self.vector_count = 0
            return Rows()
        if sql == "DELETE FROM public.mycel_embedding_receipts":
            self.assert_transaction()
            self.receipt_count = 0
            return Rows()
        if sql.startswith("DROP INDEX"):
            self.assert_transaction()
            del self.indexes[store.VECTOR_INDEX]
            return Rows()
        if sql.startswith("ALTER TABLE public.mycel_vectors"):
            self.assert_transaction()
            dimensions = int(sql.rsplit("(", 1)[1][:-1])
            self.columns["mycel_vectors"]["embedding"] = (f"vector({dimensions})", False, "")
            return Rows()
        if sql.startswith("UPDATE public.mycel_store SET dimensions"):
            singleton, number, _, generation = self.metadata[0]
            self.metadata[0] = (singleton, number, params[0], generation)
            return Rows()
        if sql.startswith("SELECT index_generation FROM public.mycel_store"):
            return Rows([(row[3],) for row in self.metadata])
        if sql.startswith("UPDATE public.mycel_store SET format"):
            singleton, _, dimensions, generation = self.metadata[0]
            self.metadata[0] = (singleton, params[0], dimensions, generation)
            return Rows()
        raise AssertionError("unexpected statement: " + sql)

    def assert_transaction(self):
        if not self.in_transaction:
            raise AssertionError("mutation outside transaction")

    @property
    def mutations(self):
        return [sql for sql, params in self.sql if sql.startswith(("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE"))]


class StoreUnitTests(unittest.TestCase):

    def setUp(self):
        # A scripted SQL seam must never be mistaken for native acceptance.
        self.assertEqual(getattr(self, "check_kind", "unit"), "unit")

    def error(self, code, operation):
        with self.assertRaises(MycelError) as raised:
            operation()
        self.assertEqual(raised.exception.code.value, code)
        return raised.exception


    @staticmethod
    def enter_checked(connection):
        with store.checked_store(connection):
            pass



# Archived complete imports; restore needed names in their original scope, not at this file tail.
