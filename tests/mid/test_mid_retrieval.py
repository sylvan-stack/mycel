"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_retrieval as _support
from test_retrieval import (
    MycelError,
    Path,
    RetrievalCandidateTests,
    RetrievalChunk,
    RetrievalScopeTests,
    chunk,
    json,
    load_settings,
    math,
    meaning_candidates,
    replace,
    resolve_search_scope,
    select_chunks,
    selected_shared_document,
    tempfile,
    unittest,
    validate_search,
    wording_candidates,
)


class RetrievalScopeTests(_support.RetrievalScopeTests):
# TEST-TIER-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_named_repository_overrides_cwd_and_unconfigured_names_refuse
    def test_named_repository_overrides_cwd_and_unconfigured_names_refuse(self):
        selected = resolve_search_scope(self.settings, ("press",), cwd=self.home)
        self.assertEqual(self.names(selected), ("press",))
        for name in ("Arbol", "mycel", "absent"):
            with self.subTest(name=name), self.assertRaises(MycelError) as raised:
                resolve_search_scope(self.settings, (name,), cwd=self.organization / "press")
            self.assertEqual(raised.exception.code, "unknown_repository")
        self._assert_origin_and_actual_artifact_alias_determine_scope()
# TEST-TIER-END tests/test_retrieval.py::RetrievalScopeTests.test_named_repository_overrides_cwd_and_unconfigured_names_refuse

# TEST-TIER-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_cwd_resolves_code_artifact_and_organization_folders
    def test_cwd_resolves_code_artifact_and_organization_folders(self):
        self.assertEqual(self.names(resolve_search_scope(self.settings,
            cwd=self.organization / "press" / "src")), ("press",))
        self.assertEqual(self.names(resolve_search_scope(self.settings,
            cwd=self.home / "Artifacts/orchard/repos/mill/notes")), ("mill",))
        for folder in (self.organization, self.organization / "outside-members",
                       self.home / "Artifacts/orchard"):
            with self.subTest(folder=folder):
                self.assertEqual(self.names(resolve_search_scope(self.settings, cwd=folder)),
                                 ("mill", "press"))
        self.assertEqual(self.names(resolve_search_scope(self.settings, ("The Orchard",))),
                         ("mill", "press"))
        self._assert_shared_document_paths_are_files_or_recursive_folder_boundaries()
# TEST-TIER-END tests/test_retrieval.py::RetrievalScopeTests.test_cwd_resolves_code_artifact_and_organization_folders

# TEST-TIER-BEGIN tests/test_retrieval.py::RetrievalScopeTests.test_no_containing_repository_has_no_fallback
    def test_no_containing_repository_has_no_fallback(self):
        with self.assertRaises(MycelError) as raised:
            resolve_search_scope(self.settings, cwd=self.home / "unrelated")
        self.assertEqual(raised.exception.code, "unknown_repository")
        self._assert_disabled_scope_is_excluded_without_substitution()
# TEST-TIER-END tests/test_retrieval.py::RetrievalScopeTests.test_no_containing_repository_has_no_fallback



class RetrievalCandidateTests(_support.RetrievalCandidateTests):
# TEST-TIER-BEGIN tests/test_retrieval.py::RetrievalCandidateTests.test_empty_query_and_limits_refuse_in_every_corpus
    def test_empty_query_and_limits_refuse_in_every_corpus(self):
        for only in (None, "code", "docs"):
            for query in ("", " ", "\n\t"):
                with self.subTest(only=only, query=query), self.assertRaises(MycelError) as raised:
                    validate_search(query, 10, only)
                self.assertEqual(raised.exception.code, "invalid_input")
            for k in (0, -1, 101, True, False, 1.0, "10"):
                with self.subTest(only=only, k=k), self.assertRaises(MycelError) as raised:
                    validate_search("step", k, only)
                self.assertEqual(raised.exception.code, "invalid_input")
            for k in (1, 100):
                validate_search("step", k, only)
# TEST-TIER-END tests/test_retrieval.py::RetrievalCandidateTests.test_empty_query_and_limits_refuse_in_every_corpus

# TEST-TIER-BEGIN tests/test_retrieval.py::RetrievalCandidateTests.test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists
    def test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists(self):
        for k in (0, 101):
            with self.subTest(k=k), self.assertRaises(MycelError):
                wording_candidates("step", (), k=k)
            with self.subTest(k=k), self.assertRaises(MycelError):
                meaning_candidates(None, (), k=k)
        with self.assertRaises(MycelError):
            wording_candidates(" \n", ())
        # Candidate behavior remains supplemental until the real-store proofs
        # claim its requirements. Every assertion still runs in this named
        # check alongside the input-limit contract it owns.
        self._assert_wording_searches_complete_body_name_and_path_without_vectors()
        self._assert_bm25_rewards_frequency_and_normalizes_full_document_length()
        self._assert_bm25_scores_match_independent_fixed_term_statistics()
        self._assert_bm25_rare_term_has_the_independent_larger_idf()
        self._assert_wording_duplicate_rows_do_not_change_scores_or_consume_places()
        self._assert_meaning_uses_best_part_and_excludes_incomplete_versions()
        self._assert_parts_and_versions_collapse_before_the_larger_candidate_limit()
        self._assert_cosine_handles_extreme_scale_and_validates_finite_dimensions()
        self._assert_both_arms_use_the_same_stable_tie_order_and_disk_only_catalog()
# TEST-TIER-END tests/test_retrieval.py::RetrievalCandidateTests.test_candidate_arms_validate_limits_and_produce_distinct_bounded_lists
