# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured disposable-store proofs for disk scope and candidate production."""

from mycel._errors import MycelError
from mycel._retrieval_store import StoreCandidates


import unittest
from dataclasses import replace
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._embedding_plan import EmbeddingPart, load_tokenizer, plan_chunk
from mycel._evaluation_store import _hash
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


class RetrievalStoreTests(unittest.TestCase):
    check_kind = "store"

    def connection(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def settings(self, *, shared=(), organization=False):
        loaded = load_settings(path=self.store_fixture.settings_file)
        root = self.store_fixture.root
        repos = {name: {"enabled": name != "disabled", "code_subdirs": [],
                       "code_root": str(root / "work" / name),
                       "artifact_root": str(root / "documents" / name)}
                 for name in ("fixture", "other", "handbook", "disabled")}
        values = {**loaded.values, "repos": repos, "organizations": {
            "team": {"root": str(root / "work"), "artifact_root": str(root / "team-docs")}}
            if organization else {}, "search": {
            **loaded.values["search"], "shared_documents": list(shared)}}
        return replace(loaded, values=_freeze(values))

    def seed(self, connection, *, repository="fixture", path="code.py", root="code",
             source="body\n", name="Symbol", kind="function", corpus=None,
             aliases=(), location_kind="disk", file_id=None, chunk_id=None):
        file_id, chunk_id = file_id or uuid4(), chunk_id or uuid4()
        raw = source.encode()
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (file_id, repository, root, path, corpus or ("documents" if kind == "document" else "code")))
        file_version = connection.execute("INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,'{}') "
            "ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id",
            (uuid4(), file_id, sha256(raw).hexdigest(), raw)).fetchone()[0]
        location = connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,'{}') "
            "ON CONFLICT (file_version,kind,location) DO UPDATE SET metadata=mycel_file_locations.metadata RETURNING id",
            (uuid4(), file_version, location_kind, location_kind)).fetchone()[0]
        for alias_root, alias_path in aliases:
            connection.execute("INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                               (file_id, alias_root, alias_path))
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,'{}') ON CONFLICT DO NOTHING",
                           (chunk_id, repository, file_id, kind))
        metadata = {"name": name, "kind": kind, "span": {"start": 0, "end": len(raw)}}
        version = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
            (chunk_id, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb(metadata))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,'{}')",
                           (uuid4(), version, location, location_kind, location_kind))
        return file_id, chunk_id, version

    def plan(self, connection, chunk_id, version, source="body\n", *, repository="fixture",
             vectors=((1.0, 0.0),), split_lines=False, model="voyage-code-4", plan_failure=None,
             part_failure=None):
        tokenizer = load_tokenizer()
        plan = plan_chunk(repository, str(chunk_id), str(version), source, place_line="code.py — Symbol (function)",
                          kind="code", tokenizer=tokenizer)
        if split_lines:
            offset, parts = 0, []
            for order, line in enumerate(source.splitlines(keepends=True)):
                end = offset + len(line.encode())
                text = plan.place_line + "\n" + line
                submitted, planning = tokenizer.counts(text, "document")
                parts.append(EmbeddingPart(order, offset, end, submitted, planning, line, text))
                offset = end
            plan = replace(plan, parts=tuple(parts))
        identifier = uuid4()
        connection.execute("INSERT INTO public.mycel_embedding_plans VALUES (%s,%s,%s,1024,%s,%s,%s,%s)",
            (identifier, version, model, plan.plan_sha256, plan.place_line, Jsonb(plan.to_dict()),
             None if plan_failure is None else Jsonb(plan_failure)))
        for part, vector in zip(plan.parts, vectors, strict=True):
            connection.execute("INSERT INTO public.mycel_embedding_parts VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (identifier, part.order, part.start_byte, part.end_byte, part.input_text.encode(),
                 part.submitted_tokens, part.planning_tokens,
                 None if part_failure is None else Jsonb(part_failure)))
            if vector is not None:
                expanded = (*vector, *((0.0,) * (1024 - len(vector))))
                connection.execute("INSERT INTO public.mycel_vectors VALUES (%s,%s,%s,1024,%s::vector)",
                    (identifier, part.order, model, "[" + ",".join(map(str, expanded)) + "]"))
        return identifier

    @staticmethod
    def keys(candidates):
        return {candidate.chunk.key for candidate in candidates}

    def contents(self, connection):
        return {table.name: _hash(connection.execute(
            f"SELECT to_jsonb(t) FROM public.{table.name} t ORDER BY to_jsonb(t)::text").fetchall())
                for table in TABLES}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
