# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured disposable-store proofs for exact reads and bounded freshness."""
import io
import json
from pathlib import Path
from unittest.mock import patch

from mycel._cli import run
from mycel._capture import _Capture
from mycel._errors import MycelError
from mycel._declared_refs import DeclaredRefStore
from mycel._locks import operation_guard
from mycel._read import ReadSelectionError
from mycel._resolver import SourceResolver
from mycel._store import checked_store, search_text
try:
    from . import test_declared_refs as declared_fixtures
except ImportError:
    import test_declared_refs as declared_fixtures


import unittest
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._freshness import Deadline
from mycel._read_store import read_from_store
from mycel._source_refs import SourceAddress
from mycel._store import search_text

try:
    pass
    from . import test_freshness_store as freshness_fixtures
    from . import test_retrieval_store as retrieval_fixtures
except ImportError:
    import test_freshness_store as freshness_fixtures
    import test_retrieval_store as retrieval_fixtures


class ReadStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = retrieval_fixtures.RetrievalStoreTests()
        self.base.store_fixture = self.store_fixture
        self.settings = self.base.settings()

    def connection(self):
        return self.base.connection()

    def read(self, connection, place=None, **options):
        options.setdefault("no_fresh", True)
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.settings, place, **options)

    def seed(self, connection, path, source, members, *, root="code", repository="fixture",
             aliases=(), location_kind="disk"):
        """Persist complete file bytes and independently supplied chunk spans."""
        file_id, file_version, location = uuid4(), uuid4(), uuid4()
        raw = source.encode("utf-8")
        corpus = "documents" if path.endswith(".md") else "code"
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)",
                           (file_id, repository, root, path, corpus))
        connection.execute("INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,'{}')",
                           (file_version, file_id, sha256(raw).hexdigest(), raw))
        connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,'{}')",
                           (location, file_version, location_kind, location_kind))
        for alias_root, alias_path in aliases:
            connection.execute("INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)",
                               (file_id, alias_root, alias_path))
        result = {}
        for name, kind, text, extra in members:
            identifier = uuid4()
            chunk_raw = text.encode("utf-8")
            start = raw.index(chunk_raw)
            metadata = {"name": name, "kind": kind, "span": {"start": start,
                        "end": start + len(chunk_raw)}, **extra}
            connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,'{}')",
                               (identifier, repository, file_id, kind))
            version = connection.execute("INSERT INTO public.mycel_chunk_versions "
                "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
                (identifier, sha256(chunk_raw).hexdigest(), chunk_raw, search_text(chunk_raw),
                 Jsonb(metadata))).fetchone()[0]
            connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,'{}')",
                               (uuid4(), version, location, location_kind, location_kind))
            result[name] = str(identifier), version, text
        return result

    @staticmethod
    def generated(connection, *, kind="summary", name="1/7", text="Stored generated text.\n",
                  repository="fixture"):
        identifier = uuid4()
        path = "summaries" if kind == "summary" else "overview"
        raw = text.encode("utf-8")
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,'{}')",
                           (identifier, repository, kind))
        version = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
            (identifier, sha256(raw).hexdigest(), raw, search_text(raw),
             Jsonb({"name": name, "kind": kind, "path": path}))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,'index','index','{}')",
                           (uuid4(), version))
        return str(identifier), version, SourceAddress(repository, "index", path, name).address


class ReadFreshnessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = freshness_fixtures.FreshnessStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

    def read(self, connection, place="fixture:@artifact/driver.md#Driver", **options):
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.base.settings, place, **options)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
