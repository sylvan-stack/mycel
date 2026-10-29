# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""SQL seam checks and separate genuine disposable-store acceptance checks.

Scripted connections declare only the evidence-separation requirement. Store
checks use the gate's real fixture and default product initializer; ordinary
unittest runs must select EmbeddingStoreUnitTests, never substitute a stand-in
for an owned store requirement.
"""
from dataclasses import replace
from uuid import UUID, uuid4

import psycopg
from mycel._credentials import Credentials
from mycel._locks import atomic_transaction, operation_guard
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._voyage import HTTPResult, PartFailure, PartIdentity, VectorWrite, VoyageClient
from fixtures import EmbeddingFixtureFailure, EmbeddingStandIn


import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from psycopg import pq
from psycopg.types.json import Jsonb

from mycel import _embedding_store as store
from mycel._coverage import require_check_database
from mycel._embedding_plan import load_tokenizer
from mycel._errors import MycelError
from mycel._locks import atomic_transaction
from mycel._settings import SettingsSnapshot, load_settings
from mycel._store import require_store, search_text
from mycel._voyage import PartIdentity, VectorWrite


def settings(*, enabled=True, model="voyage-code-4", dimensions=1024, base=None):
    values = dict(base.values) if base is not None else {"store": {"address": "postgresql://fictional/fictional"}}
    values["embedding"] = {"model": model, "dimensions": dimensions}
    values["repos"] = {"fixture": {"enabled": enabled}, "disabled": {"enabled": False}}
    return SettingsSnapshot(Path("/fictional/config.toml"), store._frozen(values), True, True)


class Rows:
    def __init__(self, values=()):
        self.values = list(values)

    def fetchall(self):
        return self.values

    def fetchone(self):
        return self.values[0] if self.values else None


class ScriptedConnection:
    """An explicit SQL seam with rollback, never a product storage adapter."""
    def __init__(self):
        self.autocommit = True
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)
        self.versions, self.plans, self.parts, self.vectors, self.receipts = {}, {}, {}, {}, {}
        self.sql, self.events, self.guards = [], [], []
        self.pass_busy = False

    def seed(self, text, *, repository="fixture", chunk=None):
        version = max(self.versions, default=0) + 1
        self.versions[version] = {"repository": repository, "chunk": chunk or uuid4(), "kind": "document",
                                  "hash": sha256(text.encode()).hexdigest(), "text": text,
                                  "metadata": {}, "chunk_metadata": {}, "locations": 1}
        return version

    def delete_plan(self, identifier):
        self.plans.pop(identifier)
        for key in list(self.parts):
            if key[0] == identifier:
                self.parts.pop(key)
                self.vectors.pop(key, None)

    @contextmanager
    def transaction(self):
        if self.info.transaction_status != pq.TransactionStatus.IDLE:
            raise AssertionError("nested scripted transaction")
        saved = deepcopy((self.versions, self.plans, self.parts, self.vectors, self.receipts))
        self.info.transaction_status = pq.TransactionStatus.INTRANS
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.versions, self.plans, self.parts, self.vectors, self.receipts = saved
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")
        finally:
            self.info.transaction_status = pq.TransactionStatus.IDLE

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if sql.startswith("SET "):
            return Rows()
        if sql == store._VERSIONS_SQL:
            return Rows((v["repository"], v["chunk"], v["kind"], v["chunk_metadata"], number,
                         v["hash"], v["text"].encode(), v["metadata"])
                        for number, v in sorted(self.versions.items(), key=lambda item: (str(item[1]["chunk"]), item[0]))
                        if v["repository"] == params[0] and v["locations"])
        if sql == store._PLANS_SQL:
            repository, model, dimensions = params
            return Rows((p[0], p[1], p[4], p[5], p[6], p[7]) for p in self.plans.values()
                        if p[2:4] == (model, dimensions) and self.versions[p[1]]["repository"] == repository)
        if sql == store._PARTS_SQL:
            model, dimensions, identifiers = params
            return Rows((*p, None if key not in self.vectors or self.vectors[key][:2] != (model, dimensions)
                         else json.dumps(self.vectors[key][2]))
                        for key, p in sorted(self.parts.items(), key=lambda item: (str(item[0][0]), item[0][1]))
                        if key[0] in identifiers)
        if sql == store._RECEIPTS_SQL:
            return Rows((*row[:4],store._payload_bytes(row[4])) for row in self.receipts.values() if row[1:4] == tuple(params))
        if sql == store._RECEIPT_SQL:
            row = self.receipts.get(params[0])
            return Rows(() if row is None else ((*row[:4],store._payload_bytes(row[4])),))
        if sql in {store._RETAINED_SQL, store._RECEIPT_VERSIONS_SQL}:
            identifiers = params[1] if sql == store._RETAINED_SQL else params[0]
            return Rows((number, v["chunk"], v["hash"], v["text"].encode()) +
                        ((v["repository"],) if sql == store._RECEIPT_VERSIONS_SQL else ())
                        for number, v in self.versions.items() if number in identifiers
                        and (sql == store._RECEIPT_VERSIONS_SQL or v["repository"] == params[0]))
        if sql == store._PUBLISHED_PLAN_SQL:
            return Rows((p[0], p[4], p[6], p[7]) for p in self.plans.values() if p[1:4] == tuple(params))
        if sql == store._PUBLISHED_PART_SQL:
            p = self.parts.get(tuple(params))
            return Rows(() if p is None else ((p[2], p[3], p[4], p[5], p[6]),))
        if sql.startswith("DELETE FROM public.mycel_embedding_plans"):
            for identifier in list(self.plans):
                if self.plans[identifier][1:4] == tuple(params):
                    self.delete_plan(identifier)
            return Rows()
        if sql.startswith("INSERT INTO public.mycel_embedding_plans"):
            values = tuple(value.obj if isinstance(value, Jsonb) else value for value in params)
            self.plans[values[0]] = values
            return Rows()
        if sql.startswith("INSERT INTO public.mycel_embedding_parts"):
            self.parts[params[:2]] = (*params, None)
            return Rows()
        if sql.startswith("INSERT INTO public.mycel_embedding_receipts"):
            if "embed" not in self.guards or "pass" in self.guards:
                raise AssertionError("staging must hold embed/removal guards without needing the pass guard")
            self.receipts[params[0]] = (*params[:4], store._receipt_payload(params[4]))
            self.events.append("staged")
            return Rows()
        if sql.startswith("INSERT INTO public.mycel_vectors"):
            self.vectors[params[:2]] = (params[2], params[3], tuple(json.loads(params[4])))
            return Rows()
        if sql.startswith("UPDATE public.mycel_embedding_parts SET failure=NULL"):
            self.parts[params] = (*self.parts[params][:-1], None)
            return Rows()
        if sql.startswith("UPDATE public.mycel_embedding_parts SET failure=%s"):
            key = params[1:3]
            if key not in self.vectors or self.vectors[key][:2] != params[-2:]:
                self.parts[key] = (*self.parts[key][:-1], deepcopy(params[0].obj))
            return Rows()
        if sql.startswith("DELETE FROM public.mycel_embedding_receipts"):
            self.receipts.pop(params[0])
            return Rows()
        if sql.startswith("UPDATE public.mycel_embedding_receipts SET payload=%s"):
            row = self.receipts[params[1]]
            self.receipts[params[1]] = (*row[:4], store._receipt_payload(params[0]))
            return Rows()
        raise AssertionError("unscripted SQL: " + sql)


@contextmanager
def checked(connection, **kwargs):
    yield None


@contextmanager
def guarded(connection, repository, operation):
    if operation == "pass" and connection.pass_busy:
        raise MycelError("busy", "Fictional pass is busy.")
    connection.guards.append(operation)
    try:
        yield
    finally:
        connection.guards.remove(operation)


class EmbeddingStoreUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def setUp(self):
        self.connection = ScriptedConnection()
        self.settings = settings()
        self.contexts = {}
        self.addCleanup(patch.stopall)
        patch.object(store, "checked_store", checked).start()
        patch.object(store, "operation_guard", guarded).start()

    def seed(self, text="exact 雪 é 😀\r\nfinal  ", **kwargs):
        version = self.connection.seed(text, **kwargs)
        self.contexts[version] = store.EmbeddingContext("docs/notes.md › Heading", "document")
        return version

    def writer(self, *, settings_=None, tokenizer=None):
        return store.EmbeddingStore(self.connection, settings_ or self.settings, tokenizer=tokenizer or self.tokenizer)

    def prepare(self, writer, **kwargs):
        return writer.prepare("fixture", contexts=self.contexts, **kwargs)

    @staticmethod
    def writes(prepared):
        return tuple(VectorWrite(PartIdentity(item.repository, item.chunk_id, item.chunk_version, item.part_order),
                                 batch.model, batch.dimensions, (0.125,) * batch.dimensions)
                     for batch in prepared.batches for item in batch.inputs)


class EmbeddingStoreAcceptanceTests(unittest.TestCase):
    """Every owned proof below executes against the real private backend."""
    check_kind = "store"

    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def setUp(self):
        if not hasattr(self, "store_fixture"):
            self.fail("This acceptance check requires the genuine disposable store fixture.")
        self.assertIs(self.store_fixture.backend.real_store, True)
        require_check_database(self.store_fixture.database)
        self.settings = settings(base=load_settings(path=self.store_fixture.settings_file))
        self.contexts = {}

    @contextmanager
    def connect(self):
        fixture = self.store_fixture
        with fixture.backend.connection(fixture.database) as connection:
            self.assertEqual(connection.execute("SELECT pg_catalog.current_database()").fetchone()[0], fixture.database)
            require_store(connection)
            yield connection

    def seed(self, connection, text, *, chunk=None, locations=("disk",), repository="fixture"):
        chunk = chunk or uuid4()
        with atomic_transaction(connection):
            connection.execute("INSERT INTO public.mycel_repository_state (repository,read_locations) VALUES (%s,%s) "
                               "ON CONFLICT (repository) DO NOTHING", (repository, Jsonb({})))
            connection.execute("INSERT INTO public.mycel_chunks (id,repository,kind,metadata) VALUES (%s,%s,'document',%s) "
                               "ON CONFLICT (id) DO NOTHING", (chunk, repository, Jsonb({})))
            version = connection.execute("INSERT INTO public.mycel_chunk_versions "
                "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (chunk, sha256(text.encode()).hexdigest(), text.encode(), search_text(text.encode()), Jsonb({}), Jsonb({}))).fetchone()[0]
            for number, kind in enumerate(locations):
                connection.execute("INSERT INTO public.mycel_locations (id,chunk_version,kind,location,metadata) "
                                   "VALUES (%s,%s,%s,%s,%s)", (uuid4(), version, kind, str(number), Jsonb({})))
        self.contexts[version] = store.EmbeddingContext("docs/雪.md › Heading", "document")
        return chunk, version

    def prepare(self, writer, **kwargs):
        return writer.prepare("fixture", contexts=self.contexts, **kwargs)

    writes = staticmethod(EmbeddingStoreUnitTests.writes)


# Archived complete imports; restore needed names in their original scope, not at this file tail.

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_exact_nul_parts_and_durable_receipt_roundtrip_without_projection
# Reason: Repeats the NUL/receipt round trip in an in-memory SQL emulator; the retained case exercises actual byte storage, a contending connection and restart.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_real_nul_saved_inputs_receipts_and_restart_preserve_exact_bytes
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_nul_parts_and_durable_receipt_roundtrip_without_projection(self):
#         text = '# Heading\n雪\0body literal \\000\0end\n'
#         self.seed(text)
#         writer = self.writer()
#         with writer.session('fixture'):
#             prepared = self.prepare(writer,persist=True)
#             self.assertEqual(prepared.versions[0].plan.text,text)
#             self.assertEqual(b''.join(part.part.text.encode() for part in prepared.versions[0].parts),text.encode())
#             self.assertTrue(all(isinstance(row[4],bytes) for row in self.connection.parts.values()))
#             self.connection.pass_busy = True
#             writer.commit(self.writes(prepared))
#             saved = next(iter(self.connection.receipts.values()))[4]
#             encoded = store._payload_bytes(saved)
#             self.assertIn(b'\\u0000',encoded)
#             self.assertEqual(store._receipt_payload(encoded)['plans'][0]['text'],text)
#             self.assertEqual(self.prepare(writer).counts.deferred_parts,len(prepared.versions[0].parts))
#             self.connection.pass_busy = False
#             writer.drain('fixture')
#             self.assertEqual(self.prepare(writer).counts.embedded_versions,1)
#         self.assertFalse(self.connection.receipts)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_saved_input_and_plan_survive_metadata_only_moves
# Reason: Repeats unchanged-plan assertions after a metadata edit in scripted dictionaries; actual locations, saved spans and vectors are checked together in the retained case.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_exact_version_all_locations_saved_spans_vectors_and_metadata_move_coverage
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_saved_input_and_plan_survive_metadata_only_moves(self):
#         version = self.seed()
#         writer = self.writer()
#         with writer.session("fixture"):
#             before = self.prepare(writer, persist=True)
#             writer.commit(self.writes(before))
#             original = self.prepare(writer)
#             self.contexts[version] = store.EmbeddingContext("moved.md › New metadata", "document")
#             self.connection.versions[version]["metadata"] = {"path": "moved.md"}
#             moved = self.prepare(writer, persist=True)
#         self.assertEqual(moved.versions[0].id, original.versions[0].id)
#         self.assertEqual(moved.versions[0].plan, original.versions[0].plan)
#         self.assertEqual(moved.counts.embedded_versions, 1)
#         self.assertFalse(moved.batches)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_same_exact_version_shared_by_locations_embeds_once_and_changed_text_is_pending
# Reason: The scripted SQL returns one version by construction regardless of its locations count; the retained test creates four actual locations and a changed exact version.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_exact_version_all_locations_saved_spans_vectors_and_metadata_move_coverage
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_same_exact_version_shared_by_locations_embeds_once_and_changed_text_is_pending(self):
#         version = self.seed(location_count=4)
#         writer = self.writer()
#         with writer.session("fixture"):
#             prepared = self.prepare(writer, persist=True)
#             self.assertEqual(len(self.writes(prepared)), 1)
#             writer.commit(self.writes(prepared))
#             self.seed("# Renamed heading\nexact body\n", chunk=self.connection.versions[version]["chunk"])
#             updated = self.prepare(writer, persist=True)
#         self.assertEqual((updated.counts.embedded_versions, updated.counts.pending_versions), (1, 1))
#         self.assertEqual(len(updated.batches[0].inputs), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_busy_pass_stages_before_publication_and_next_session_drains_without_resending
# Reason: Repeats deferred-publication/restart behavior with a boolean busy flag and dictionary receipts; the retained case uses an actual conflicting pass lock and stored receipts.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_busy_pass_durable_batch_is_not_coverage_and_next_session_publishes_without_resend
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_busy_pass_stages_before_publication_and_next_session_drains_without_resending(self):
#         self.seed()
#         writer = self.writer()
#         with writer.session("fixture"):
#             prepared = self.prepare(writer, persist=True)
#             self.connection.pass_busy = True
#             writes = self.writes(prepared)
#             receipt = writer.commit(writes)
#             self.assertEqual(receipt.deferred, tuple(value.part for value in writes))
#             self.assertFalse(receipt.retained)
#             self.assertFalse(self.connection.vectors)
#             self.assertEqual(len(self.connection.receipts), 1)
#             staged = self.prepare(writer)
#             self.assertEqual(staged.counts.deferred_parts, 1)
#             self.assertEqual(staged.counts.embedded_versions, 0)
#             self.assertFalse(staged.batches)
#             self.assertEqual(staged.estimate["deferredParts"], 1)
#         with self.assertRaises(MycelError) as failure:
#             with self.writer().session("fixture"):
#                 self.fail("busy deferred session must stop before sending")
#         self.assertEqual(failure.exception.code, "busy")
#         self.connection.pass_busy = False
#         replacement = self.writer()
#         with replacement.session("fixture"):
#             published = self.prepare(replacement)
#         self.assertEqual(published.counts.embedded_versions, 1)
#         self.assertFalse(published.batches)
#         self.assertFalse(self.connection.receipts)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_row_contention_retains_the_whole_durable_batch
# Reason: Boolean-controlled fake row contention duplicates the actual two-connection row-lock/deferred-batch scenario.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_row_lock_defers_whole_response_and_deleted_versions_alone_are_discarded
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_row_contention_retains_the_whole_durable_batch(self):
#         self.seed(); self.seed("second version")
#         writer = self.writer()
#         with writer.session("fixture"):
#             prepared = self.prepare(writer, persist=True)
#             self.connection.row_busy = True
#             writes = self.writes(prepared)
#             receipt = writer.commit(writes)
#             self.assertEqual(set(receipt.deferred), {value.part for value in writes})
#             self.assertFalse(self.connection.vectors)
#             self.connection.row_busy = False
#             drained = writer.drain("fixture")
#         self.assertEqual(len(drained.retained), 2)
#         self.assertEqual(len(self.connection.vectors), 2)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_deleted_versions_only_are_discarded_and_unlocated_retained_versions_keep_vectors
# Reason: Dictionary deletion and location-count mutation repeat the retained actual deletion and unlocated-version publication case.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_row_lock_defers_whole_response_and_deleted_versions_alone_are_discarded
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deleted_versions_only_are_discarded_and_unlocated_retained_versions_keep_vectors(self):
#         first = self.seed(); second = self.seed("second")
#         writer = self.writer()
#         with writer.session("fixture"):
#             writes = self.writes(self.prepare(writer, persist=True))
#             self.connection.delete_version(first)
#             self.connection.versions[second]["locations"] = 0
#             receipt = writer.commit(writes)
#         self.assertEqual({p.chunk_version for p in receipt.deleted}, {str(first)})
#         self.assertEqual({p.chunk_version for p in receipt.retained}, {str(second)})
#         self.assertEqual(len(self.connection.vectors), 1)
#         self.assertFalse(self.connection.receipts)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_publication_sql_failure_rolls_back_all_vectors_and_keeps_receipt_sanitized
# Reason: The mock transaction restores copied dictionaries; the retained test injects the same second-INSERT failure after a real first INSERT and verifies rollback, sanitization and receipt recovery.
# Source: mycel@f606f26b4895fd0a641c4f9eb9088bf177de42aa:tests/test_embedding_store.py
# Retained evidence at review: EmbeddingStoreAcceptanceTests.test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_publication_sql_failure_rolls_back_all_vectors_and_keeps_receipt_sanitized(self):
#         self.seed(); self.seed("second")
#         writer = self.writer()
#         with writer.session("fixture"):
#             writes = self.writes(self.prepare(writer, persist=True))
#             self.connection.fail_vector_number = 2
#             with self.assertRaises(MycelError) as failure:
#                 writer.commit(writes)
#             self.assertEqual(failure.exception.code, "store_unavailable")
#             self.assertNotIn("private", str(failure.exception))
#             self.assertFalse(self.connection.vectors)
#             self.assertEqual(len(self.connection.receipts), 1)
#             self.connection.fail_vector_number = None
#             writer.drain("fixture")
#         self.assertEqual(len(self.connection.vectors), 2)
#         self.assertFalse(self.connection.receipts)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
