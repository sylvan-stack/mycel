"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_search_reply as _support
from test_search_reply import (
    Candidate,
    ChunkRequirement,
    DependencyFault,
    FreshnessResult,
    FreshnessScope,
    MycelError,
    RankEntry,
    RepositoryCandidates,
    RepositoryRanking,
    RepositoryStatus,
    RetrievalChunk,
    SearchReplyTests,
    candidates,
    chunk,
    entry,
    freshness,
    json,
    ranking,
    replace,
    search_reply,
    unittest,
)


class SearchReplyTests(_support.SearchReplyTests):
# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_results_and_citations_share_original_source_paths_marks_and_faults
    def test_results_and_citations_share_original_source_paths_marks_and_faults(self):
        method = chunk("method")
        guide = chunk("guide", root="artifact", path="guide.md", name="Contract > Limits",
                      origin="documents", kind="document")
        source = {"repository": "glossary", "root": "artifact", "path": "terms.md",
                  "name": "Term", "address": "glossary:@artifact/terms.md#Term"}
        intermediate = {"repository": "contract", "root": "artifact", "path": "contract.md",
                        "name": "Contract", "address": "contract:@artifact/contract.md#Contract"}
        reason = {"kind": "upstream_stale", "edge": "declared", "source": source,
                  "via": [intermediate]}
        fault = {"chunk": intermediate, "ref": "missing:@artifact/missing.md",
                 "fault": "unknown_repository"}
        metadata = {method.key: {"staleReasons": [reason], "heartwood": True, "faults": [fault]},
                    guide.key: {"staleReasons": [reason], "heartwood": True, "faults": [fault]}}
        reply = search_reply(ranking(entry(method, via=guide, documented=(guide,)), entry(guide)),
            candidates(method, guide), freshness=freshness(method, guide), metadata=metadata)
        first, second = reply["results"]
        annotations = {"stale": True, "staleReasons": [reason], "heartwood": True,
                       "dependencyCheck": {"complete": False, "faults": [fault]}}
        for record in (first, second, first["via"], first["documentedIn"][0]):
            with self.subTest(record=record["address"]):
                self.assertEqual({key: record[key] for key in annotations}, annotations)
        self.assertEqual(first["staleReasons"][0]["source"]["name"], "Term")
        self.assertEqual(first["staleReasons"][0]["via"], [intermediate])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_results_and_citations_share_original_source_paths_marks_and_faults

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_reply_annotations_are_independent_copies_of_each_result_and_citation
    def test_reply_annotations_are_independent_copies_of_each_result_and_citation(self):
        method = chunk("method")
        guide = chunk("guide", root="artifact", path="guide.md", name="Guide", origin="documents")
        reason = {"kind": "upstream_stale", "source": {"name": "Original"},
                  "via": [{"name": "Middle"}]}
        fault = {"ref": "fixture:missing.md", "candidates": [{"name": "Candidate"}]}
        observation = {"staleReasons": (reason,), "faults": (fault,), "lines": {"start": 2, "end": 5}}
        metadata = {method.key: observation, guide.key: observation}
        reply = search_reply(ranking(entry(method, via=guide, documented=(guide,)), entry(guide)),
                             candidates(method, guide), metadata=metadata)
        result = reply["results"][0]
        result["staleReasons"][0]["source"]["name"] = "Changed"
        result["staleReasons"][0]["via"][0]["name"] = "Changed"
        result["dependencyCheck"]["faults"][0]["candidates"][0]["name"] = "Changed"
        result["lines"]["start"] = 99
        for record in (result["via"], result["documentedIn"][0], reply["results"][1]):
            self.assertEqual(record["staleReasons"][0]["source"]["name"], "Original")
            self.assertEqual(record["staleReasons"][0]["via"][0]["name"], "Middle")
            self.assertEqual(record["dependencyCheck"]["faults"][0]["candidates"][0]["name"], "Candidate")
        self.assertEqual(observation["staleReasons"][0]["source"]["name"], "Original")
        self.assertEqual(observation["lines"]["start"], 2)
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_reply_annotations_are_independent_copies_of_each_result_and_citation

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_no_check_or_missing_exact_version_requirement_never_certifies_an_unmarked_chunk
    def test_no_check_or_missing_exact_version_requirement_never_certifies_an_unmarked_chunk(self):
        method, old = chunk("method", version=2), chunk("method", version=1)
        for current in (None, freshness(old)):
            with self.subTest(freshness=current):
                reply = search_reply(ranking(entry(method)), candidates(method), freshness=current)
                self.assertFalse(reply["results"][0]["stale"])
                self.assertFalse(reply["results"][0]["dependencyCheck"]["complete"])
        self.assertFalse(search_reply(ranking(entry(method)), candidates(method))["freshness"]["checked"])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_no_check_or_missing_exact_version_requirement_never_certifies_an_unmarked_chunk

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_pending_upstream_or_reachable_fault_keeps_only_affected_exact_checks_incomplete
    def test_pending_upstream_or_reachable_fault_keeps_only_affected_exact_checks_incomplete(self):
        governed, independent = chunk("governed"), chunk("independent", name="Other.step")
        guide = chunk("guide", root="artifact", path="guide.md", name="Guide", origin="documents")
        current = freshness(governed, independent, guide,
            states=(RepositoryStatus("fixture", "done"), RepositoryStatus("upstream", "pending", "Busy.")),
            finished=False)
        current = replace(current, chunk_requirements=(
            ChunkRequirement("fixture", governed.key, ("fixture", "upstream")),
            ChunkRequirement("fixture", independent.key, ("fixture",)),
            ChunkRequirement("fixture", guide.key, ("fixture", "upstream"))))
        ranked = ranking(entry(governed, via=guide, documented=(guide,)), entry(independent))
        reply = search_reply(ranked, candidates(governed, independent), freshness=current)
        first, second = reply["results"]
        self.assertFalse(first["dependencyCheck"]["complete"])
        self.assertFalse(first["via"]["dependencyCheck"]["complete"])
        self.assertFalse(first["documentedIn"][0]["dependencyCheck"]["complete"])
        self.assertTrue(second["dependencyCheck"]["complete"])
        self.assertFalse(reply["freshness"]["finished"])
        fault = DependencyFault("upstream", "missing:guide.md", "unregistered_repository", guide.key)
        faulty = replace(current, repositories=(RepositoryStatus("fixture", "done"),
            RepositoryStatus("upstream", "done")), finished=True, incomplete_repositories=(),
            faults=(fault,), chunk_requirements=(
                replace(current.chunk_requirements[0], faults=(fault,)), current.chunk_requirements[1],
                replace(current.chunk_requirements[2], faults=(fault,))))
        public = {"chunk": {"repository": "fixture", "root": "artifact", "path": "guide.md",
                            "name": "Guide", "address": guide.place.address},
                  "ref": fault.ref, "fault": "unknown_repository"}
        reply = search_reply(ranked, candidates(governed, independent), freshness=faulty,
                             metadata={governed.key: {"faults": [public]}, guide.key: {"faults": [public]}})
        self.assertTrue(reply["freshness"]["finished"])
        self.assertFalse(reply["results"][0]["stale"])
        self.assertFalse(reply["results"][0]["dependencyCheck"]["complete"])
        self.assertEqual(reply["results"][0]["via"]["dependencyCheck"]["faults"], [public])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_pending_upstream_or_reachable_fault_keeps_only_affected_exact_checks_incomplete

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_no_fresh_overrides_prior_done_statuses_for_results_and_citations
    def test_no_fresh_overrides_prior_done_statuses_for_results_and_citations(self):
        method = chunk("method")
        guide = chunk("guide", root="artifact", path="guide.md", name="Guide", origin="documents")
        reply = search_reply(ranking(entry(method, via=guide, documented=(guide,))), candidates(method),
                             freshness=freshness(method, guide), checked=False, ingested={"fixture": 7})
        self.assertEqual(reply["freshness"], {"checked": False, "finished": False, "ingested": 0,
            "withoutVector": 1, "repositories": [{"repository": "fixture", "state": "pending",
            "ingested": 0, "reason": "Freshness checking was turned off."}]})
        result = reply["results"][0]
        for record in (result, result["via"], result["documentedIn"][0]):
            self.assertFalse(record["stale"])
            self.assertFalse(record["dependencyCheck"]["complete"])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_no_fresh_overrides_prior_done_statuses_for_results_and_citations

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_identifier_and_question_wording_fallbacks_explain_meaning_failure
    def test_identifier_and_question_wording_fallbacks_explain_meaning_failure(self):
        method = chunk("method", text="雪" * 300)
        for route, reason in (("identifier", "No embedding credentials are configured."),
                              ("question", "The embedding provider did not answer.")):
            with self.subTest(route=route):
                reply = search_reply(ranking(entry(method, meaning_rank=None), route=route, meaning=False),
                    candidates(method, meaning=False), meaning_reason=reason)
                self.assertEqual(reply["route"], route)
                self.assertEqual(reply["meaning"], {"used": False, "reason": reason})
                self.assertEqual(reply["candidates"], {"meaning": 0, "wording": 1})
                self.assertEqual(reply["results"][0]["ranks"], {"wording": 2})
                self.assertEqual(reply["results"][0]["preview"], "雪" * 240)
                self.assertEqual(reply["results"][0]["id"], method.identifier)
        missing_reason = search_reply(ranking(entry(method), meaning=False), candidates(method, meaning=False))
        self.assertTrue(missing_reason["meaning"]["reason"])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_identifier_and_question_wording_fallbacks_explain_meaning_failure

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_meaning_participation_and_distinct_candidate_counts_are_explicit
    def test_meaning_participation_and_distinct_candidate_counts_are_explicit(self):
        method, second = chunk("method"), chunk("other", name="Other.step")
        duplicate = Candidate(method, .7)
        arms = candidates(method, second)
        arms = replace(arms, meaning=(*arms.meaning, duplicate), wording=(*arms.wording, duplicate))
        reply = search_reply(ranking(entry(method), without=0), arms,
                             freshness=freshness(method), ingested={"fixture": 2})
        self.assertEqual(reply["schema"], 3)
        self.assertEqual(reply["meaning"], {"used": True})
        self.assertEqual(reply["candidates"], {"meaning": 2, "wording": 2})
        self.assertEqual(reply["results"][0]["ranks"], {"meaning": 1, "wording": 2})
        self.assertTrue(reply["results"][0]["dependencyCheck"]["complete"])
        self.assertEqual(reply["freshness"]["ingested"], 2)
        self.assertEqual(reply["freshness"]["repositories"], [{"repository": "fixture", "state": "done",
                                                               "ingested": 2}])
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_meaning_participation_and_distinct_candidate_counts_are_explicit

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_checkout_and_artifact_markdown_keep_actual_roots_canonical_places_and_stable_ids
    def test_checkout_and_artifact_markdown_keep_actual_roots_canonical_places_and_stable_ids(self):
        checkout = chunk("checkout", root="code", path="README.md", name="Limits > 雪",
                         origin="documents", kind="document")
        artifact = replace(checkout, identifier="artifact", root="artifact")
        metadata = {checkout.key: {"file": "/actual/checkout/README.md", "lines": {"start": 5, "end": 8}},
                    artifact.key: {"file": "/actual/artifact/README.md"}}
        reply = search_reply(ranking(entry(checkout, via=artifact, documented=(artifact,)), entry(artifact)),
                             candidates(checkout, artifact), metadata=metadata)
        first, second = reply["results"]
        expected = "Limits%20%3E%20%E9%9B%AA"
        self.assertEqual((first["id"], first["origin"], first["root"], first["path"], first["address"]),
                         ("checkout", "document", "code", "README.md", f"fixture:@code/README.md#{expected}"))
        self.assertEqual((second["id"], second["origin"], second["root"], second["path"], second["address"]),
                         ("artifact", "document", "artifact", "README.md", f"fixture:@artifact/README.md#{expected}"))
        self.assertEqual(first["file"], "/actual/checkout/README.md")
        self.assertEqual(first["lines"], {"start": 5, "end": 8})
        self.assertNotIn("unreadable", first)
        for citation in (first["via"], first["documentedIn"][0]):
            self.assertEqual(citation["id"], "artifact")
            self.assertEqual(citation["root"], "artifact")
            self.assertEqual(citation["address"], second["address"])
            self.assertEqual(citation["document"], artifact.name)
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_checkout_and_artifact_markdown_keep_actual_roots_canonical_places_and_stable_ids

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_unreadable_results_explain_missing_or_escaping_files_without_inventing_paths
    def test_unreadable_results_explain_missing_or_escaping_files_without_inventing_paths(self):
        member = chunk("method")
        for reason in ("The chunk file cannot be read.",
                       "The chunk file no longer belongs to its configured source root.", None):
            with self.subTest(reason=reason):
                reply = search_reply(ranking(entry(member)), candidates(member),
                                     metadata={member.key: {"unreadable": reason}})
                result = reply["results"][0]
                self.assertNotIn("file", result)
                self.assertTrue(result["unreadable"])
                self.assertEqual(result["root"], "code")
                self.assertEqual(result["path"], member.path)
                if reason is not None:
                    self.assertEqual(result["unreadable"], reason)
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_unreadable_results_explain_missing_or_escaping_files_without_inventing_paths

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_index_only_namespace_is_canonical_and_never_gains_a_file_from_metadata
    def test_index_only_namespace_is_canonical_and_never_gains_a_file_from_metadata(self):
        generated = chunk("unchanged-id", root="index", path="summaries", name="1/7", kind="summary",
                          origin="documents", text="Summary.")
        reply = search_reply(ranking(entry(generated)), candidates(generated),
                             metadata={generated.key: {"file": "/incorrect/summaries"}})
        result = reply["results"][0]
        self.assertEqual((result["id"], result["root"], result["address"]),
                         ("unchanged-id", "index", "fixture:@index/summaries#1%2F7"))
        self.assertNotIn("file", result)
        self.assertIn("generated in the index", result["unreadable"])
        self.assertEqual(json.loads(json.dumps(reply)), reply)
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_index_only_namespace_is_canonical_and_never_gains_a_file_from_metadata

# TEST-TIER-BEGIN tests/test_search_reply.py::SearchReplyTests.test_incompatible_scope_and_invalid_options_are_refused
    def test_incompatible_scope_and_invalid_options_are_refused(self):
        member = chunk("method")
        for options in ({"checked": 1}, {"meaning_reason": ""}, {"meaning_reason": {"kind": "failed"}}):
            with self.subTest(options=options), self.assertRaises(MycelError) as error:
                search_reply(ranking(entry(member)), candidates(member), **options)
            self.assertEqual(error.exception.code, "invalid_input")
        with self.assertRaises(MycelError) as error:
            search_reply(ranking(entry(member)), replace(candidates(member), repository="other"))
        self.assertEqual(error.exception.code, "store_format")
# TEST-TIER-END tests/test_search_reply.py::SearchReplyTests.test_incompatible_scope_and_invalid_options_are_refused
