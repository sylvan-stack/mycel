# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Native disposable-store proofs for stored summary reports and dry-runs."""
from contextlib import ExitStack
from dataclasses import replace
import io
import json

from mycel._cli import Invocation, run
from mycel._build_identity import current_build
from mycel._errors import MycelError
from mycel._settings import _freeze
from mycel._summaries import handle_summaries
from mycel._summary_store import (PublishedSummaryState, StoreSummaries, summary_repository,
                                  summary_removal_reply, summary_result_reply)


import unittest
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._source_refs import SourceAddress
from mycel._store import search_text
from mycel._summary_store import PublishedSummaryState

try:
    from . import test_retrieval_store as fixtures
except ImportError:
    import test_retrieval_store as fixtures


class SummaryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.RetrievalStoreTests()
        self.fixture.store_fixture = self.store_fixture

    def connection(self):
        return self.fixture.connection()

    def settings(self, **kwargs):
        return self.fixture.settings(**kwargs)

    def document(self, connection, *, path="note.md", root="artifact", text="section\n", name="Section",
                 embedded=True, vectors=((1.0, 0.0),), model="voyage-code-4", **kwargs):
        result = self.fixture.seed(connection, path=path, root=root, source=text, name=name,
                                   kind="document", **kwargs)
        if embedded:
            self.fixture.plan(connection, result[1], result[2], text, vectors=vectors,
                              model=model, repository=kwargs.get("repository", "fixture"))
        return result

    @staticmethod
    def pin(connection, chunk_id, version, *, path="note.md", root="artifact", name="Section"):
        digest = connection.execute("SELECT snapshot_hash FROM public.mycel_chunk_versions WHERE id=%s",
                                    (version,)).fetchone()[0]
        return {"chunkId": str(chunk_id), "chunkVersion": version, "snapshotHash": digest,
                "place": SourceAddress("fixture", root, path, name).address}

    def summary(self, connection, members, *, level=1, number=1, stale=False,
                chunk_id=None, kind="summary", text="published summary\n"):
        chunk_id = chunk_id or uuid4()
        path = "summaries" if kind == "summary" else "overview"
        name = f"{level}/{number}" if kind == "summary" else f"Overview{number}"
        raw = text.encode()
        connection.execute("INSERT INTO public.mycel_repository_state VALUES ('fixture',NULL,'[]') ON CONFLICT DO NOTHING")
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,'fixture',NULL,%s,'{}')", (chunk_id, kind))
        version = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
            (chunk_id, sha256(raw).hexdigest(), raw, search_text(raw),
             Jsonb({"name": name, "kind": kind, "path": path}))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,'index','index','{}')",
                           (uuid4(), version))
        state = {"schemaVersion": 1, "chunkVersion": version, "level": level,
                 "members": list(members), "set": {"builtAt": "2026-10-08T12:00:00Z",
                    "groupingProfile": "mycel-summary-v1", "build": 26,
                    "numericalVersions": {"numpy": "historical-numpy", "scipy": "historical-scipy",
                                          "scikit-learn": "historical-sklearn"}}}
        if kind == "summary":
            state = PublishedSummaryState.from_dict(state, repository="fixture").to_dict()
        connection.execute("INSERT INTO public.mycel_generated_state VALUES (%s,'fixture',%s,%s)",
                           (chunk_id, kind, Jsonb(state)))
        if stale:
            connection.execute("INSERT INTO public.mycel_stale_reasons VALUES (%s,'fixture',%s,NULL,%s)",
                               (uuid4(), version, Jsonb({"kind": "source_changed"})))
        return chunk_id, version, SourceAddress("fixture", "index", path, name)

    @staticmethod
    def no_effects(stack):
        for target in ("mycel._summary_writer.SummaryWriter", "mycel._embedding_store.EmbeddingStore",
                       "mycel._summaries.SummaryWriter", "mycel._summaries.generate_summary_requests",
                       "mycel._capture.capture_repository"):
            stack.enter_context(patch(target, side_effect=AssertionError("a stored report must do no external work")))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
