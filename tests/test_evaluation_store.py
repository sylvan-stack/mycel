# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real disposable-store evaluation inputs with controlled search replies.

These checks prove the measurement/snapshot handoff. The named stand-in places
are not a semantic-ranking evaluation or evidence for MYC-4.25.
"""

import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg import pq
from psycopg.types.json import Jsonb

from mycel._evaluation import (
    EvaluationSet,
    PreparedQueryVector,
    RetrievalPlace,
    run_retrieval_evaluation,
)
from mycel._evaluation_store import StoreRetrieval, _hash
from mycel._settings import _freeze, load_settings
from mycel._store import TABLES, search_text


class _RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.statements = []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **kwargs)


class _Vectors:
    def __init__(self, connection, *, fallback=False):
        self.connection = connection
        self.queries = []
        self.fallback = fallback

    def prepare(self, query):
        if self.connection.info.transaction_status != pq.TransactionStatus.IDLE:
            raise AssertionError("query vectors must precede the index transaction")
        self.queries.append(query)
        if self.fallback:
            return PreparedQueryVector(None, "fictional_missing_key")
        return PreparedQueryVector((1.0,) + (0.0,) * 1023)


class EvaluationStoreTests(unittest.TestCase):
    check_kind = "store"

    def connection(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def settings(self, *, shared=()):
        loaded = load_settings(path=self.store_fixture.settings_file)
        values = {**loaded.values, "repos": {
            "fixture": {"enabled": True}, "handbook": {"enabled": True},
            "disabled": {"enabled": False}}, "search": {
            **loaded.values["search"], "shared_documents": list(shared)}}
        return replace(loaded, values=_freeze(values))

    def seed(self, connection, *, repository="fixture", path="guide.md", root="artifact",
             source="# Exact\n", name="Exact", kind="document", title=None,
             family=None, file_id=None, chunk_id=None, chunk_source=None, span=None,
             corpus=None, aliases=(), location_kind="disk"):
        file_id, chunk_id = file_id or uuid4(), chunk_id or uuid4()
        source_bytes = source.encode()
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (file_id, repository, root, path, corpus or ("documents" if kind == "document" else "code")))
        file_version = connection.execute("INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,'{}') "
            "ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id",
            (uuid4(), file_id, sha256(source_bytes).hexdigest(), source_bytes)).fetchone()[0]
        location = connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (file_version,kind,location) DO UPDATE SET metadata=mycel_file_locations.metadata RETURNING id",
            (uuid4(), file_version, location_kind, location_kind,
             Jsonb({'corpus': corpus or ('documents' if kind == 'document' else 'code')}))).fetchone()[0]
        for alias_root, alias_path in aliases:
            connection.execute("INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                               (file_id, alias_root, alias_path))
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,'{}') ON CONFLICT DO NOTHING",
                           (chunk_id, repository, file_id, kind))
        raw = source_bytes if chunk_source is None else chunk_source.encode()
        metadata = {"name": name, "kind": kind, "title": title, "family": family,
                    "span": span or {"start": 0, "end": len(source_bytes)}}
        version = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
            (chunk_id, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb(metadata))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,'{}')",
                           (uuid4(), version, location, location_kind, location_kind))
        return file_id, chunk_id, version

    def vector(self, connection, version):
        plan = uuid4()
        connection.execute("INSERT INTO public.mycel_embedding_plans VALUES "
            "(%s,%s,'voyage-code-4',1024,'fictional-plan','guide.md — Exact (document)','{}',NULL)", (plan, version))
        connection.execute("INSERT INTO public.mycel_embedding_parts VALUES (%s,0,0,7,%s,2,2,NULL)", (plan, b"# Exact"))
        connection.execute("INSERT INTO public.mycel_vectors VALUES (%s,0,'voyage-code-4',1024,%s::vector)",
                           (plan, "[" + ",".join(["1"] + ["0"] * 1023) + "]"))
        return plan

    def suite(self, *queries):
        return EvaluationSet(Path("/fictional/evaluation.toml"), sha256(b"fictional set").hexdigest(), tuple(queries))

    def measure(self, connection, queries, search, *, settings=None, fallback=False):
        return run_retrieval_evaluation(self.suite(*queries), repository="fixture", build="412",
            model="voyage-code-4", query_vectors=_Vectors(connection, fallback=fallback),
            retrieval=StoreRetrieval(connection, settings or self.settings(), search=search))

    def selected(self, snapshot, address):
        member = snapshot.resolver.resolve(address, purpose="read").selection.members[0]
        return RetrievalPlace(member.chunk.identifier, member.chunk.version, member.place)

    def contents(self, connection):
        # Compare exact complete row values, not only table counts. The adapter
        # must neither create lock-key rows nor touch activity/model caches.
        return {table.name: _hash(connection.execute(
            f"SELECT to_jsonb(t) FROM public.{table.name} t ORDER BY to_jsonb(t)::text").fetchall())
                for table in TABLES}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
