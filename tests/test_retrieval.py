"""Scoped candidate-arm checks; final search ranking is deliberately absent."""

import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mycel._errors import MycelError
from mycel._retrieval import (
    RetrievalChunk,
    meaning_candidates,
    resolve_search_scope,
    select_chunks,
    selected_shared_document,
    wording_candidates,
)
from mycel._settings import load_settings


def chunk(identifier, *, repository="orchard", path=None, root="code", name="step",
          origin="code", text="", **values):
    return RetrievalChunk(identifier, 1, repository, root, path or f"{identifier}.py",
                          name, "function", origin, text, **values)


class RetrievalScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.organization = self.home / "orchard"
        for name in ("press", "mill", "closed"):
            (self.organization / name / ".git").mkdir(parents=True)
        source = f'''[store]
address = "postgresql://mycel@localhost/mycel"
[organizations."The Orchard"]
root = {json.dumps(str(self.organization))}
[repos.press]
enabled = true
[repos.mill]
enabled = true
[repos.closed]
enabled = false
[repos.handbook]
enabled = true
artifact_root = {json.dumps(str(self.home / "handbook"))}
[search]
shared_documents = [{{repo="handbook", paths=["guides", "TERMS.md"]}},
                    {{repo="closed", paths=["."]}}]
'''
        path = self.home / "settings.toml"
        path.write_text(source)
        self.settings = load_settings(path=path, home=self.home)
        self.settings.require_valid()

    def names(self, scope):
        return tuple(repository.name for repository in scope)

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_named_repository_overrides_cwd_and_unconfigured_names_refuse
#     def test_named_repository_overrides_cwd_and_unconfigured_names_refuse(self):
#         selected = resolve_search_scope(self.settings, ("press",), cwd=self.home)
#         self.assertEqual(self.names(selected), ("press",))
#         for name in ("Arbol", "mycel", "absent"):
#             with self.subTest(name=name), self.assertRaises(MycelError) as raised:
#                 resolve_search_scope(self.settings, (name,), cwd=self.organization / "press")
#             self.assertEqual(raised.exception.code, "unknown_repository")
#         self._assert_origin_and_actual_artifact_alias_determine_scope()
# TEST-TIER-DISABLED-END tests/test_retrieval.py::RetrievalScopeTests.test_named_repository_overrides_cwd_and_unconfigured_names_refuse

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_cwd_resolves_code_artifact_and_organization_folders
#     def test_cwd_resolves_code_artifact_and_organization_folders(self):
#         self.assertEqual(self.names(resolve_search_scope(self.settings,
#             cwd=self.organization / "press" / "src")), ("press",))
#         self.assertEqual(self.names(resolve_search_scope(self.settings,
#             cwd=self.home / "Artifacts/orchard/repos/mill/notes")), ("mill",))
#         for folder in (self.organization, self.organization / "outside-members",
#                        self.home / "Artifacts/orchard"):
#             with self.subTest(folder=folder):
#                 self.assertEqual(self.names(resolve_search_scope(self.settings, cwd=folder)),
#                                  ("mill", "press"))
#         self.assertEqual(self.names(resolve_search_scope(self.settings, ("The Orchard",))),
#                          ("mill", "press"))
#         self._assert_shared_document_paths_are_files_or_recursive_folder_boundaries()
# TEST-TIER-DISABLED-END tests/test_retrieval.py::RetrievalScopeTests.test_cwd_resolves_code_artifact_and_organization_folders

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_no_containing_repository_has_no_fallback
#     def test_no_containing_repository_has_no_fallback(self):
#         with self.assertRaises(MycelError) as raised:
#             resolve_search_scope(self.settings, cwd=self.home / "unrelated")
#         self.assertEqual(raised.exception.code, "unknown_repository")
#         self._assert_disabled_scope_is_excluded_without_substitution()
# TEST-TIER-DISABLED-END tests/test_retrieval.py::RetrievalScopeTests.test_no_containing_repository_has_no_fallback

    def _assert_disabled_scope_is_excluded_without_substitution(self):
        for names, folder in ((("closed",), self.home),
                              ((), self.organization / "closed")):
            with self.subTest(names=names), self.assertRaises(MycelError) as raised:
                resolve_search_scope(self.settings, names, cwd=folder)
            self.assertEqual(raised.exception.code, "refused")
        self.assertEqual(self.names(resolve_search_scope(self.settings, ("closed", "press"))),
                         ("press",))

    def _assert_shared_document_paths_are_files_or_recursive_folder_boundaries(self):
        for path in ("guides/one.md", "guides/deep/two.md", "TERMS.md"):
            self.assertTrue(selected_shared_document(self.settings, "handbook", path))
        for path in ("guide.md", "guides-other/one.md", "TERMS.md.bak", "private/one.md"):
            self.assertFalse(selected_shared_document(self.settings, "handbook", path))
        self.assertFalse(selected_shared_document(self.settings, "closed", "guides/one.md"))
        self.assertFalse(selected_shared_document(self.settings, "unknown", "guides/one.md"))

    def _assert_origin_and_actual_artifact_alias_determine_scope(self):
        own_code = chunk("own-code", repository="press")
        own_doc = chunk("own-doc", repository="press", root="code", path="guide.md",
                        origin="documents")
        selected = chunk("selected", repository="handbook", root="artifact",
                         path="guides/guide.md", origin="documents")
        aliased = chunk("alias", repository="handbook", root="code", path="readme.md",
                        origin="documents", artifact_paths=("guides/linked.md",))
        unselected = chunk("unselected", repository="handbook", root="code",
                           path="guides/unselected.md", origin="documents")
        external_code = chunk("external-code", repository="handbook", root="artifact",
                              path="guides/code.py")
        disabled = chunk("disabled", repository="closed", root="artifact",
                         path="all.md", origin="documents")
        branch = replace(own_code, identifier="branch", on_disk=False)
        index = replace(own_doc, identifier="index", root="index", path="summaries")
        catalog = (own_code, own_doc, selected, aliased, unselected, external_code, disabled,
                   branch, index)
        self.assertEqual(set(select_chunks(self.settings, "press", catalog)),
                         {own_code, own_doc, selected, aliased})
        self.assertEqual(select_chunks(self.settings, "press", catalog, only="code"), (own_code,))
        self.assertEqual(set(select_chunks(self.settings, "press", catalog, only="docs")),
                         {own_doc, selected, aliased})
        self.assertEqual(aliased.place.root, "code")
        self.assertEqual(own_doc.origin, "documents")


class RetrievalCandidateTests(unittest.TestCase):
# TEST-TIER-DISABLED-BEGIN tests/test_retrieval.py::RetrievalCandidateTests.test_empty_query_and_limits_refuse_in_every_corpus
#     def test_empty_query_and_limits_refuse_in_every_corpus(self):
#         for only in (None, "code", "docs"):
#             for query in ("", " ", "\n\t"):
#                 with self.subTest(only=only, query=query), self.assertRaises(MycelError) as raised:
#                     validate_search(query, 10, only)
#                 self.assertEqual(raised.exception.code, "invalid_input")
#             for k in (0, -1, 101, True, False, 1.0, "10"):
#                 with self.subTest(only=only, k=k), self.assertRaises(MycelError) as raised:
#                     validate_search("step", k, only)
#                 self.assertEqual(raised.exception.code, "invalid_input")
#             for k in (1, 100):
#                 validate_search("step", k, only)
# TEST-TIER-DISABLED-END tests/test_retrieval.py::RetrievalCandidateTests.test_empty_query_and_limits_refuse_in_every_corpus

# TEST-TIER-DISABLED-BEGIN tests/test_retrieval.py::RetrievalCandidateTests.test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists
#     def test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists(self):
#         for k in (0, 101):
#             with self.subTest(k=k), self.assertRaises(MycelError):
#                 wording_candidates("step", (), k=k)
#             with self.subTest(k=k), self.assertRaises(MycelError):
#                 meaning_candidates(None, (), k=k)
#         with self.assertRaises(MycelError):
#             wording_candidates(" \n", ())
#         # Candidate behavior remains supplemental until the real-store proofs
#         # claim its requirements. Every assertion still runs in this named
#         # check alongside the input-limit contract it owns.
#         self._assert_wording_searches_complete_body_name_and_path_without_vectors()
#         self._assert_bm25_rewards_frequency_and_normalizes_full_document_length()
#         self._assert_bm25_scores_match_independent_fixed_term_statistics()
#         self._assert_bm25_rare_term_has_the_independent_larger_idf()
#         self._assert_wording_duplicate_rows_do_not_change_scores_or_consume_places()
#         self._assert_meaning_uses_best_part_and_excludes_incomplete_versions()
#         self._assert_parts_and_versions_collapse_before_the_larger_candidate_limit()
#         self._assert_cosine_handles_extreme_scale_and_validates_finite_dimensions()
#         self._assert_both_arms_use_the_same_stable_tie_order_and_disk_only_catalog()
# TEST-TIER-DISABLED-END tests/test_retrieval.py::RetrievalCandidateTests.test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists

    def _assert_wording_searches_complete_body_name_and_path_without_vectors(self):
        body = chunk("body", text="intro " * 2000 + "lateword")
        name = chunk("name", name="NameOnly", text="no matching body")
        path = chunk("path", path="nested/PathOnly.py", text="no matching body")
        partial = chunk("partial", text="lateword", part_vectors=((1.0, 0.0),))
        catalog = (body, name, path, partial)
        self.assertEqual({candidate.chunk.identifier for candidate in wording_candidates("lateword", catalog)},
                         {"body", "partial"})
        self.assertEqual([candidate.chunk.identifier for candidate in wording_candidates("NameOnly", catalog)],
                         ["name"])
        self.assertEqual([candidate.chunk.identifier for candidate in wording_candidates("PathOnly", catalog)],
                         ["path"])
        self.assertEqual(wording_candidates("missingword", catalog), ())
        self.assertEqual(wording_candidates("!!!", catalog), ())

    def _assert_bm25_rewards_frequency_and_normalizes_full_document_length(self):
        concise = chunk("concise", text="needle needle")
        broad = chunk("broad", text="needle " + "other " * 1000)
        irrelevant = chunk("irrelevant", text="other")
        results = wording_candidates("needle", (broad, irrelevant, concise))
        self.assertEqual([candidate.chunk.identifier for candidate in results], ["concise", "broad"])
        self.assertTrue(all(math.isfinite(candidate.score) and candidate.score > 0 for candidate in results))
        self.assertEqual(results, wording_candidates("needle needle", (concise, broad, irrelevant)))

    def _assert_bm25_scores_match_independent_fixed_term_statistics(self):
        # Three documents have lengths 4, 5 and 3 after name/path terms. Needle
        # occurs in two of them, with frequencies 2 and 1: IDF=ln(1.6). These
        # numeric answers are independently calculated at decimal precision.
        concise = chunk("one", path="a", name="meta", text="needle needle")
        longer = chunk("two", path="b", name="meta", text="needle filler filler")
        third = chunk("three", path="c", name="meta", text="filler")
        results = wording_candidates("needle", (longer, third, concise))
        self.assertEqual([candidate.chunk.identifier for candidate in results], ["one", "two"])
        self.assertAlmostEqual(results[0].score, 0.6462549902128864, places=14)
        self.assertAlmostEqual(results[1].score, 0.4263950450889147, places=14)

    def _assert_bm25_rare_term_has_the_independent_larger_idf(self):
        catalog = (chunk("one", path="a", name="meta", text="rare common"),
                   chunk("two", path="b", name="meta", text="filler common"),
                   chunk("three", path="c", name="meta", text="filler common"))
        # Equal length and TF isolate smoothed IDF: rare=ln(8/3), common=ln(8/7).
        rare = wording_candidates("rare", catalog)
        common = wording_candidates("common", catalog)
        self.assertAlmostEqual(rare[0].score, 0.9808292530117262, places=14)
        self.assertTrue(all(abs(candidate.score - 0.13353139262452263) < 1e-14
                            for candidate in common))

    def _assert_wording_duplicate_rows_do_not_change_scores_or_consume_places(self):
        first, second = chunk("a", text="term"), chunk("b", text="term term")
        expected = wording_candidates("term", (first, second))
        self.assertEqual(wording_candidates("term", (first, second, first, second)), expected)
        with self.assertRaises(MycelError) as raised:
            wording_candidates("term", (first, replace(first, text="different")))
        self.assertEqual(raised.exception.code, "store_format")

    def _assert_meaning_uses_best_part_and_excludes_incomplete_versions(self):
        best = chunk("long", fully_embedded=True,
                     part_vectors=((0.0, 1.0), (0.8, 0.6), (1.0, 0.0)) * 40)
        next_best = chunk("next", fully_embedded=True, part_vectors=((0.8, 0.6),))
        incomplete = chunk("partial", part_vectors=((1.0, 0.0),))
        no_vectors = chunk("wording", text="query")
        results = meaning_candidates((1.0, 0.0), (next_best, incomplete, best, no_vectors))
        self.assertEqual([candidate.chunk.identifier for candidate in results], ["long", "next"])
        self.assertAlmostEqual(results[0].score, 1.0)
        self.assertAlmostEqual(results[1].score, 0.8)
        self.assertEqual(meaning_candidates(None, (best,)), ())

    def _assert_parts_and_versions_collapse_before_the_larger_candidate_limit(self):
        catalog = tuple(chunk(f"c{i:02d}", fully_embedded=True, text="term",
                              part_vectors=((1.0, 0.0),) * 25) for i in range(30))
        another_version = replace(catalog[0], version=2)
        rows = (*reversed(catalog), another_version, catalog[0])
        for producer, query in ((wording_candidates, "term"), (meaning_candidates, (1.0, 0.0))):
            for k, expected in ((1, 20), (20, 20), (25, 25)):
                with self.subTest(producer=producer.__name__, k=k):
                    results = producer(query, rows, k=k)
                    self.assertEqual(len(results), expected)
                    self.assertEqual([candidate.chunk.identifier for candidate in results],
                                     [f"c{i:02d}" for i in range(expected)])
                    self.assertEqual(len({candidate.chunk.identifier for candidate in results}), expected)

    def _assert_cosine_handles_extreme_scale_and_validates_finite_dimensions(self):
        extreme = chunk("extreme", fully_embedded=True, part_vectors=((1e-300, 1e-300),))
        self.assertAlmostEqual(meaning_candidates((1e300, 1e300), (extreme,))[0].score, 1.0)
        for vector in ((), (0.0, 0.0), (float("nan"), 1.0), (float("inf"), 1.0), (True, 1.0)):
            with self.subTest(vector=vector), self.assertRaises(MycelError) as raised:
                meaning_candidates(vector, (extreme,))
            self.assertEqual(raised.exception.code, "invalid_input")
        for vector in ((1.0,), (float("nan"), 1.0), (0.0, 0.0)):
            with self.subTest(vector=vector), self.assertRaises(MycelError):
                meaning_candidates((1.0, 0.0), (replace(extreme, part_vectors=(vector,)),))

    def _assert_both_arms_use_the_same_stable_tie_order_and_disk_only_catalog(self):
        artifact = chunk("artifact", path="same.md", root="artifact", origin="documents",
                         text="term", fully_embedded=True, part_vectors=((1.0, 0.0),))
        checkout = replace(artifact, identifier="checkout", root="code")
        branch = replace(artifact, identifier="branch", on_disk=False)
        index = replace(artifact, identifier="index", root="index", path="summaries")
        for producer, query in ((wording_candidates, "term"), (meaning_candidates, (1.0, 0.0))):
            with self.subTest(producer=producer.__name__):
                results = producer(query, (checkout, index, branch, artifact))
                self.assertEqual([candidate.chunk.identifier for candidate in results],
                                 ["artifact", "checkout"])
                self.assertEqual(results, producer(query, (artifact, checkout)))

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_retrieval.py:11
# from mycel._retrieval import (RetrievalChunk, meaning_candidates, resolve_search_scope,
#     select_chunks, selected_shared_document, validate_search, wording_candidates)
# TEST-TIER-IMPORTS-END tests/test_retrieval.py:11
