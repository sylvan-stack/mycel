"""Configured disposable-store proofs for disk scope and candidate production."""

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

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_disabled_and_selected_shared_documents_use_origin_and_artifact_aliases
#     def test_disabled_and_selected_shared_documents_use_origin_and_artifact_aliases(self):
#         with self.connection() as connection:
#             own_code = self.seed(connection, path="mine.py", source="scope\n")[1:]
#             own_doc = self.seed(connection, path="checkout.md", kind="document", source="scope\n")[1:]
#             shared = self.seed(connection, repository="handbook", path="docs/shared.md", kind="document",
#                 source="scope\n", aliases=(("artifact", "selected/nested/shared.md"),))[1:]
#             self.seed(connection, repository="handbook", root="artifact", path="selectedness/outside.md",
#                       kind="document", source="scope\n")
#             self.seed(connection, repository="handbook", root="artifact", path="selected/code.py", source="scope\n")
#             self.seed(connection, repository="disabled", root="artifact", path="selected/hidden.md",
#                       kind="document", source="scope\n")
#             for prefix in ("selected/nested/shared.md", "selected"):
#                 settings = self.settings(shared=({"repo": "handbook", "paths": [prefix]},
#                                                  {"repo": "disabled", "paths": ["."]}))
#                 with StoreCandidates(connection, settings).snapshot(("fixture",)) as snapshot:
#                     all_reply = snapshot.candidates("scope")[0]
#                     self.assertEqual(self.keys(all_reply.wording), {(str(i), v) for i, v in (own_code, own_doc, shared)})
#                     documents = snapshot.candidates("scope", only="docs")[0]
#                     self.assertEqual(self.keys(documents.wording), {(str(i), v) for i, v in (own_doc, shared)})
#                     code = snapshot.candidates("scope", only="code")[0]
#                     self.assertEqual(self.keys(code.wording), {(str(own_code[0]), own_code[1])})
#                     self.assertTrue(all(chunk.repository != "disabled" for chunk in snapshot.chunks))
#                     retained = next(chunk for chunk in documents.chunks if chunk.repository == "handbook")
#                     self.assertEqual(retained.place.address, "handbook:@code/docs/shared.md#Symbol")
#                     self.assertEqual(retained.origin, "documents")
#                 with self.assertRaises(MycelError):
#                     with StoreCandidates(connection, settings).snapshot(("disabled",)):
#                         self.fail("a disabled direct scope must refuse")
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_disabled_and_selected_shared_documents_use_origin_and_artifact_aliases

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_complete_body_name_and_path_find_partial_failed_and_unembedded_versions
#     def test_complete_body_name_and_path_find_partial_failed_and_unembedded_versions(self):
#         with self.connection() as connection:
#             long_source = "ordinary words\n" * 100 + "tailneedle\n"
#             _, body_id, body_version = self.seed(connection, path="long.py", source=long_source, name="Long")
#             _, name_id, name_version = self.seed(connection, path="named.py", name="NameNeedle")
#             _, path_id, path_version = self.seed(connection, path="folder/pathneedle.py", name="PathOnly")
#             _, failed_id, failed_version = self.seed(connection, path="failed.py", source="failedneedle\n")
#             self.plan(connection, body_id, body_version, long_source, split_lines=True,
#                       vectors=((1.0, 0.0),) + (None,) * 100)
#             self.plan(connection, name_id, name_version, plan_failure={"kind": "planning"})
#             self.plan(connection, failed_id, failed_version, "failedneedle\n", vectors=(None,),
#                       part_failure={"kind": "content"})
#             with StoreCandidates(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 for query, expected in (("tailneedle", (body_id, body_version)),
#                                         ("NameNeedle", (name_id, name_version)),
#                                         ("pathneedle", (path_id, path_version)),
#                                         ("failedneedle", (failed_id, failed_version))):
#                     with self.subTest(query=query):
#                         reply = snapshot.candidates(query, (1.0,) + (0.0,) * 1023)[0]
#                         self.assertEqual(self.keys(reply.wording), {(str(expected[0]), expected[1])})
#                         self.assertEqual(reply.meaning, ())
#                         self.assertEqual(reply.without_vector, 4)
#                 self.assertEqual(next(chunk.text for chunk in snapshot.chunks if chunk.identifier == str(body_id)),
#                                  long_source)
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_complete_body_name_and_path_find_partial_failed_and_unembedded_versions

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_complete_current_model_parts_collapse_before_each_candidate_limit
#     def test_complete_current_model_parts_collapse_before_each_candidate_limit(self):
#         with self.connection() as connection:
#             source = "manyparts\n" * 30
#             _, long_id, long_version = self.seed(connection, path="000-long.py", source=source)
#             self.plan(connection, long_id, long_version, source, split_lines=True,
#                       vectors=((1.0, 0.0),) * 29 + ((0.0, 1.0),))
#             eligible = {(str(long_id), long_version)}
#             for index in range(24):
#                 _, chunk_id, version = self.seed(connection, path=f"candidate-{index:02}.py", source="manyparts\n")
#                 self.plan(connection, chunk_id, version, "manyparts\n", vectors=((0.8, 0.6),))
#                 eligible.add((str(chunk_id), version))
#             _, historic_id, historic_version = self.seed(connection, path="historical.py", source="manyparts\n")
#             self.plan(connection, historic_id, historic_version, "manyparts\n", model="historical-model")
#             with StoreCandidates(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 query = (1.0,) + (0.0,) * 1023
#                 reply = snapshot.candidates("manyparts", query, k=1)[0]
#                 self.assertEqual(len(reply.meaning), 20)
#                 self.assertEqual(len(self.keys(reply.meaning)), 20)
#                 self.assertEqual(reply.meaning[0].chunk.key, (str(long_id), long_version))
#                 self.assertAlmostEqual(reply.meaning[0].score, 1.0)
#                 self.assertEqual(len(reply.wording), 20)
#                 larger = snapshot.candidates("manyparts", query, k=25)[0]
#                 self.assertEqual(self.keys(larger.meaning), eligible)
#                 self.assertEqual(len(larger.meaning), 25)
#                 self.assertEqual(larger.without_vector, 1)
#                 self.assertNotIn((str(historic_id), historic_version), self.keys(larger.meaning))
#             settings = self.settings()
#             selected_dimensions = replace(settings, values=_freeze({**settings.values,
#                 "embedding": {**settings.values["embedding"], "dimensions": 512}}))
#             with StoreCandidates(connection, selected_dimensions).snapshot(("fixture",)) as snapshot:
#                 reply = snapshot.candidates("manyparts", (1.0,) + (0.0,) * 511, k=25)[0]
#                 self.assertEqual(reply.meaning, ())
#                 self.assertEqual(len(reply.wording), 25)
#                 self.assertEqual(reply.without_vector, 26)
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_complete_current_model_parts_collapse_before_each_candidate_limit

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_branch_stash_and_replaced_disk_versions_never_enter_candidates
#     def test_branch_stash_and_replaced_disk_versions_never_enter_candidates(self):
#         with self.connection() as connection:
#             file_id, chunk_id, old = self.seed(connection, source="oldneedle\n", name="Old")
#             connection.execute("UPDATE public.mycel_locations SET kind='branch',location='old' WHERE chunk_version=%s", (old,))
#             connection.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old'")
#             _, _, current = self.seed(connection, file_id=file_id, chunk_id=chunk_id,
#                                       source="currentneedle\n", name="Current")
#             self.seed(connection, path="branch.py", source="branchneedle\n", location_kind="branch")
#             self.seed(connection, path="stash.py", source="stashneedle\n", location_kind="stash")
#             with StoreCandidates(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 reply = snapshot.candidates("currentneedle")[0]
#                 self.assertEqual(self.keys(reply.wording), {(str(chunk_id), current)})
#                 self.assertEqual(tuple(chunk.key for chunk in reply.chunks), ((str(chunk_id), current),))
#                 for query in ("oldneedle", "branchneedle", "stashneedle"):
#                     self.assertEqual(snapshot.candidates(query)[0].wording, ())
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_branch_stash_and_replaced_disk_versions_never_enter_candidates

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_organization_members_keep_separate_candidate_lists_and_limits
#     def test_organization_members_keep_separate_candidate_lists_and_limits(self):
#         with self.connection() as connection:
#             for repository, count in (("fixture", 25), ("other", 24), ("disabled", 30)):
#                 for index in range(count):
#                     self.seed(connection, repository=repository, path=f"chunk-{index:02}.py", source="memberneedle\n")
#             settings = self.settings(organization=True)
#             with StoreCandidates(connection, settings).snapshot(("team",)) as snapshot:
#                 replies = snapshot.candidates("memberneedle", k=25)
#                 self.assertEqual(tuple(reply.repository for reply in replies), ("fixture", "handbook", "other"))
#                 self.assertEqual(tuple(len(reply.wording) for reply in replies), (25, 0, 24))
#                 for reply in replies:
#                     self.assertTrue(all(candidate.chunk.repository == reply.repository for candidate in reply.wording))
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_organization_members_keep_separate_candidate_lists_and_limits

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_deleted_planned_parts_and_failed_vectors_do_not_become_complete
#     def test_deleted_planned_parts_and_failed_vectors_do_not_become_complete(self):
#         with self.connection() as connection:
#             _, chunk_id, version = self.seed(connection, source="firstneedle\nsecondneedle\n")
#             identifier = self.plan(connection, chunk_id, version, "firstneedle\nsecondneedle\n", split_lines=True,
#                                    vectors=((1.0, 0.0), (0.0, 1.0)))
#             connection.execute("DELETE FROM public.mycel_vectors WHERE plan_id=%s AND part_order=1", (identifier,))
#             connection.execute("DELETE FROM public.mycel_embedding_parts WHERE plan_id=%s AND part_order=1", (identifier,))
#             _, failed_id, failed_version = self.seed(connection, path="failed.py", source="failedneedle\n")
#             self.plan(connection, failed_id, failed_version, "failedneedle\n", part_failure={"kind": "content"})
#             with StoreCandidates(connection, self.settings()).snapshot(("fixture",)) as snapshot:
#                 reply = snapshot.candidates("secondneedle", (1.0,) + (0.0,) * 1023)[0]
#                 self.assertEqual(self.keys(reply.wording), {(str(chunk_id), version)})
#                 self.assertEqual(reply.meaning, ())
#                 self.assertEqual(reply.without_vector, 2)
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_deleted_planned_parts_and_failed_vectors_do_not_become_complete

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval_store.py::RetrievalStoreTests.test_snapshot_keeps_text_places_vectors_together_and_changes_no_store_rows
#     def test_snapshot_keeps_text_places_vectors_together_and_changes_no_store_rows(self):
#         with self.connection() as connection, self.connection() as writer:
#             file_id, chunk_id, version = self.seed(connection, source="oldneedle\n", name="Old")
#             plan = self.plan(connection, chunk_id, version, "oldneedle\n")
#             recorded = _RecordingConnection(connection)
#             before = self.contents(connection)
#             with StoreCandidates(recorded, self.settings()).snapshot(("fixture",)) as snapshot:
#                 self.assertEqual(connection.execute("SELECT current_setting('transaction_read_only'), "
#                     "current_setting('transaction_isolation')").fetchone(), ("on", "repeatable read"))
#                 old_reply = snapshot.candidates("oldneedle", (1.0,) + (0.0,) * 1023)[0]
#                 self.assertEqual(self.keys(old_reply.meaning), {(str(chunk_id), version)})
#                 self.assertEqual(self.contents(connection), before)
#                 writer.execute("UPDATE public.mycel_locations SET kind='branch',location='old' WHERE chunk_version=%s", (version,))
#                 writer.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old'")
#                 self.seed(writer, file_id=file_id, chunk_id=chunk_id, source="newneedle\n", name="New")
#                 writer.execute("UPDATE public.mycel_vectors SET embedding=%s::vector WHERE plan_id=%s",
#                     ("[0,1," + ",".join(["0"] * 1022) + "]", plan))
#                 same = snapshot.candidates("oldneedle", (1.0,) + (0.0,) * 1023)[0]
#                 self.assertEqual(same, old_reply)
#                 self.assertEqual(snapshot.resolver.resolve("fixture:@code/code.py#Old", purpose="read").state, "resolved")
#                 self.assertEqual(snapshot.resolver.resolve("fixture:@code/code.py#New", purpose="read").fault, "missing_name")
#                 with self.assertRaises(Exception) as rejected:
#                     with connection.transaction():
#                         connection.execute("DELETE FROM public.mycel_chunk_versions")
#                 self.assertEqual(rejected.exception.sqlstate, "25006")
#             with self.assertRaises(MycelError):
#                 snapshot.candidates("oldneedle")
#             with StoreCandidates(connection, self.settings()).snapshot(("fixture",)) as after:
#                 self.assertEqual(after.candidates("oldneedle")[0].wording, ())
#                 self.assertEqual(len(after.candidates("newneedle")[0].wording), 1)
#                 self.assertEqual(after.candidates("newneedle")[0].without_vector, 1)
#             self.assertFalse(any(statement.lstrip().upper().startswith(
#                 ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")) for statement in recorded.statements))
# TEST-TIER-DISABLED-END tests/test_retrieval_store.py::RetrievalStoreTests.test_snapshot_keeps_text_places_vectors_together_and_changes_no_store_rows

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_retrieval_store.py:11
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_retrieval_store.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_retrieval_store.py:13
# from mycel._retrieval_store import StoreCandidates
# TEST-TIER-IMPORTS-END tests/test_retrieval_store.py:13
