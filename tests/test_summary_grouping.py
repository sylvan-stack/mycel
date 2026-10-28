"""Offline grouping profile and estimated-level proofs."""

import unittest
from hashlib import sha256

import numpy as np

from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._source_refs import SourceAddress
from mycel._summary_grouping import SummaryNode
from mycel._summary_request import SummarySection


def node(number, vector=(1.0, 0.0), *, path=None, position=None, root="artifact", text=None):
    place = SourceAddress("fixture", root, path or f"{number:04}.md", f"Section{number}")
    position = number if position is None else position
    section = None
    if text is not None:
        raw = text.encode()
        chunk = ResolvedChunk(str(number), 1, place.name, "document", raw, sha256(raw).hexdigest())
        section = SummarySection(SelectionMember(place, chunk), position)
    return SummaryNode(str(number), place, position, vector, section)


class _Mixture:
    def __init__(self, matrix, components, bic, probabilities=None, *, converged=True):
        self.n_components = components
        self.matrix = matrix
        self.score = bic
        self.probabilities = probabilities
        self.converged_ = converged

    def fit(self, matrix):
        self.matrix = matrix
        return self

    def bic(self, matrix):
        return self.score

    def predict_proba(self, matrix):
        if self.probabilities is not None:
            return self.probabilities
        values = np.zeros((len(matrix), self.n_components))
        values[:, 0] = 1
        return values


class SummaryGroupingTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_zero_one_two_and_multipart_means_keep_canonical_members
#     def test_zero_one_two_and_multipart_means_keep_canonical_members(self):
#         self.assertEqual(group_summary_nodes(()), ())
#         first = node(1, path="same.md", position=10)
#         later = node(2, path="same.md", position=70)
#         self.assertEqual(group_summary_nodes((first,)), ((first,),))
#         self.assertEqual(group_summary_nodes((later, first)), ((first, later),))
#         self.assertEqual(mean_vector(((1, 5), (3, 1))), (2, 3))
#         self.assertEqual(mean_vector(((1e308,), (1e308,))), (1e308,))
#         self.assertEqual(GROUPING_PROFILE, "mycel-summary-v1")
#         self.assertEqual(set(numerical_versions()), {"numpy", "scipy", "scikit-learn"})
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_zero_one_two_and_multipart_means_keep_canonical_members

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_real_pca_mixture_is_repeatable_and_input_order_independent
#     def test_real_pca_mixture_is_repeatable_and_input_order_independent(self):
#         nodes = tuple(node(number, tuple((40.0 if column == number // 8 else 0.0)
#                     + ((number % 8) - 3.5) * (column + 1) / 100
#                     for column in range(12))) for number in range(24))
#         first = group_summary_nodes(nodes)
#         self.assertEqual(first, group_summary_nodes(tuple(reversed(nodes))))
#         self.assertEqual(first, group_summary_nodes(nodes))
#         self.assertEqual(len(first), 3)
#         self.assertEqual({member.key for group in first for member in group}, {member.key for member in nodes})
#         self.assertEqual({frozenset(member.key for member in group) for group in first},
#                          {frozenset(str(number) for number in range(start, start + 8)) for start in (0, 8, 16)})
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_real_pca_mixture_is_repeatable_and_input_order_independent

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_uncached_real_numerical_fit_starts_no_child_and_restores_openmp_environment
#     def test_uncached_real_numerical_fit_starts_no_child_and_restores_openmp_environment(self):
#         import joblib.externals.loky.backend.context as cpu_context
#         nodes = tuple(node(number, (number / 10, 1.0)) for number in range(11))
#         attempted = []
#
#         def refuse_child(*args, **kwargs):
#             attempted.append(args)
#             raise AssertionError("numerical planning must not start a child process")
#
#         for ambient in (None, "7"):
#             with self.subTest(ambient=ambient), patch.dict(os.environ), \
#                     patch.object(cpu_context, "physical_cores_cache", None), \
#                     patch("subprocess.Popen", side_effect=refuse_child):
#                 if ambient is None:
#                     os.environ.pop("OMP_NUM_THREADS", None)
#                 else:
#                     os.environ["OMP_NUM_THREADS"] = ambient
#                 self.assertTrue(group_summary_nodes(nodes))
#                 self.assertEqual(os.environ.get("OMP_NUM_THREADS"), ambient)
#                 self.assertIsNone(cpu_context.physical_cores_cache)
#         self.assertEqual(attempted, [])
#         # The caller's setting also survives a refused numerical fit.
#         with patch.dict(os.environ, {"OMP_NUM_THREADS": "7"}):
#             def fail_fit(**kwargs):
#                 self.assertEqual(os.environ["OMP_NUM_THREADS"], "1")
#                 raise ValueError("private fit error")
#
#             with patch("sklearn.mixture.GaussianMixture", side_effect=fail_fit), self.assertRaises(MycelError):
#                 group_summary_nodes(nodes)
#             self.assertEqual(os.environ["OMP_NUM_THREADS"], "7")
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_uncached_real_numerical_fit_starts_no_child_and_restores_openmp_environment

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_duplicate_constant_vectors_use_valid_finite_fit_without_warning_output
#     def test_duplicate_constant_vectors_use_valid_finite_fit_without_warning_output(self):
#         nodes = tuple(node(number, (1, 1)) for number in range(11))
#         with warnings.catch_warnings(record=True) as seen:
#             warnings.simplefilter("always")
#             self.assertEqual(group_summary_nodes(nodes), (nodes,))
#         self.assertEqual(seen, [])
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_duplicate_constant_vectors_use_valid_finite_fit_without_warning_output

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_exact_profile_pca_dimensions_candidate_range_and_smaller_bic_tie
#     def test_exact_profile_pca_dimensions_candidate_range_and_smaller_bic_tie(self):
#         nodes = tuple(node(number, tuple(float(number + column) for column in range(12))) for number in range(24))
#         mixtures, reductions = [], []
#
#         def mixture(**kwargs):
#             mixtures.append(kwargs)
#             # Components two and three tie; the earlier, smaller candidate wins.
#             return _Mixture(None, kwargs["n_components"], 4 if kwargs["n_components"] == 1 else 1)
#
#         class Reduction:
#             def __init__(self, **kwargs):
#                 reductions.append(kwargs)
#                 self.dimensions = kwargs["n_components"]
#
#             def fit_transform(self, matrix):
#                 return matrix[:, :self.dimensions]
#
#         with patch("sklearn.decomposition.PCA", Reduction), patch("sklearn.mixture.GaussianMixture", mixture):
#             groups = group_summary_nodes(tuple(reversed(nodes)))
#         self.assertEqual(reductions, [{"n_components": 10, "random_state": 0}])
#         self.assertEqual(mixtures, [{"n_components": count, "covariance_type": "spherical",
#                                     "reg_covar": 1e-4, "random_state": 0} for count in (1, 2, 3)])
#         self.assertEqual(groups, (nodes,))  # The unassigned second component is discarded.
#         # The n-1 cap also limits PCA for a small high-dimensional group.
#         with patch("sklearn.decomposition.PCA", Reduction), patch("sklearn.mixture.GaussianMixture", mixture):
#             group_summary_nodes(nodes[:3])
#         self.assertEqual(reductions[-1], {"n_components": 2, "random_state": 0})
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_exact_profile_pca_dimensions_candidate_range_and_smaller_bic_tie

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_overlap_inclusive_threshold_argmax_tie_and_empty_components
#     def test_overlap_inclusive_threshold_argmax_tie_and_empty_components(self):
#         nodes = tuple(node(number) for number in range(89))
#         probability = np.zeros((89, 11))
#         probability[0, :2] = (0.1, 0.9)
#         probability[1] = 1 / 11  # None meets .10; equal maxima choose component zero.
#         probability[2:, 10] = 1
#         choices = []
#
#         def mixture(**kwargs):
#             components = kwargs["n_components"]
#             choices.append(components)
#             return _Mixture(None, components, 0 if components == 11 else 1,
#                             probability if components == 11 else None)
#
#         with patch("sklearn.mixture.GaussianMixture", mixture):
#             groups = group_summary_nodes(nodes)
#         self.assertEqual(choices, list(range(1, 13)))
#         self.assertEqual(groups, ((nodes[0], nodes[1]), (nodes[0],), nodes[2:]))
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_overlap_inclusive_threshold_argmax_tie_and_empty_components

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_candidate_component_cap_is_150
#     def test_candidate_component_cap_is_150(self):
#         nodes = tuple(node(number) for number in range(1201))
#         calls = []
#
#         def mixture(**kwargs):
#             calls.append(kwargs["n_components"])
#             return _Mixture(None, kwargs["n_components"], kwargs["n_components"])
#
#         with patch("sklearn.mixture.GaussianMixture", mixture):
#             self.assertEqual(group_summary_nodes(nodes), (nodes,))
#         self.assertEqual(calls, list(range(1, 151)))
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_candidate_component_cap_is_150

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_invalid_vectors_and_fit_failure_are_reported_without_fallback
#     def test_invalid_vectors_and_fit_failure_are_reported_without_fallback(self):
#         for value in ((math.inf,), (math.nan,), (), (True,), ("1",)):
#             with self.assertRaises(MycelError) as caught:
#                 node(1, value)
#             self.assertEqual(caught.exception.code, "invalid_input")
#         for parts in ((), ((1,), (1, 2)), ((math.nan,),)):
#             with self.assertRaises(MycelError):
#                 mean_vector(parts)
#         for nodes in ((node(1), node(1)), (node(1), node(2, (1,))),
#                       (node(1), replace(node(2), place=SourceAddress("other", "artifact", "a.md", "One")))):
#             with self.assertRaises(MycelError):
#                 group_summary_nodes(nodes)
#         for failure in (ValueError("private fitting data"), ArithmeticError("private numbers")):
#             with patch("sklearn.mixture.GaussianMixture", side_effect=failure), self.assertRaises(MycelError) as caught:
#                 group_summary_nodes(tuple(node(number) for number in range(3)))
#             self.assertEqual(caught.exception.code, "refused")
#             self.assertEqual(caught.exception.message, "Summary grouping failed: numerical_fit.")
#         for score, converged in ((math.nan, True), (1, False)):
#             with patch("sklearn.mixture.GaussianMixture", return_value=_Mixture(None, 1, score, converged=converged)):
#                 with self.assertRaises(MycelError):
#                     group_summary_nodes(tuple(node(number) for number in range(3)))
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_invalid_vectors_and_fit_failure_are_reported_without_fallback

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_top_target_singleton_promotion_and_no_summary_stop
#     def test_top_target_singleton_promotion_and_no_summary_stop(self):
#         nodes = tuple(node(number) for number in range(11))
#         with patch("mycel._summary_grouping.group_summary_nodes") as grouping:
#             self.assertEqual(plan_summary_levels(nodes[:10]).levels, ())
#             grouping.assert_not_called()
#         with patch("mycel._summary_grouping.group_summary_nodes", return_value=(nodes[:4], *(tuple((member,)) for member in nodes[4:]))):
#             plan = plan_summary_levels(nodes)
#         self.assertEqual(len(plan.levels), 1)
#         level, = plan.levels
#         self.assertEqual(level.nodes_in, 11)
#         self.assertEqual(level.moved_up, nodes[4:])
#         self.assertEqual(len(level.output_nodes), 8)
#         self.assertEqual(level.groups[0].summary.vector, mean_vector(tuple(member.vector for member in nodes[:4])))
#         self.assertEqual(level.groups[0].summary.place.address, "fixture:@index/summaries#1%2F1")
#         with patch("mycel._summary_grouping.group_summary_nodes", return_value=tuple((member,) for member in nodes)):
#             no_summaries = plan_summary_levels(nodes)
#         self.assertEqual(len(no_summaries.levels), 1)
#         self.assertEqual(no_summaries.requests, 0)
#         self.assertEqual(no_summaries.levels[0].moved_up, nodes)
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_top_target_singleton_promotion_and_no_summary_stop

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_five_level_limit_and_estimated_mean_nodes
#     def test_five_level_limit_and_estimated_mean_nodes(self):
#         nodes = tuple(node(number, (number + 1, -number)) for number in range(11))
#         seen = []
#
#         def split(members, level):
#             seen.append((level, members))
#             return tuple((member,) for member in members)
#
#         with patch("mycel._summary_grouping.group_summary_nodes", side_effect=lambda values: (values,)):
#             plan = plan_summary_levels(nodes, split_group=split)
#         self.assertEqual(len(plan.levels), 5)
#         self.assertEqual(plan.requests, 55)
#         self.assertEqual([level.level for level in plan.levels], [1, 2, 3, 4, 5])
#         self.assertTrue(all(level.nodes_in == 11 for level in plan.levels))
#         self.assertTrue(all(member.section is None for _, members in seen for member in members))
#         self.assertTrue(plan.report()["estimated"])
#         self.assertEqual(plan.report()["groupingProfile"], GROUPING_PROFILE)
#         self.assertEqual(plan.report()["numericalVersions"], numerical_versions())
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_five_level_limit_and_estimated_mean_nodes

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_numbering_sorts_complete_member_lists_after_component_order_and_splitting
#     def test_numbering_sorts_complete_member_lists_after_component_order_and_splitting(self):
#         nodes = tuple(node(number) for number in range(11))
#         # Overlapping groups have component order unrelated to source order.
#         groups = (nodes[4:], nodes[:6])
#
#         def split(members, level):
#             return (members[:2], members[2:])
#
#         with patch("mycel._summary_grouping.group_summary_nodes", return_value=groups):
#             plan = plan_summary_levels(nodes, split_group=split)
#         level, = plan.levels
#         self.assertEqual(tuple(group.members for group in level.groups),
#                          (nodes[:2], nodes[2:6], nodes[4:6], nodes[6:]))
#         self.assertEqual([group.summary.place.name for group in level.groups], ["1/1", "1/2", "1/3", "1/4"])
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_numbering_sorts_complete_member_lists_after_component_order_and_splitting

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_real_request_splits_count_each_part_without_promoting_cut_parts
#     def test_real_request_splits_count_each_part_without_promoting_cut_parts(self):
#         nodes = tuple(node(number, text=f"# Section{number}\n" + "雪🙂" * 12000) for number in range(11))
#         prompts = SummaryPrompts(b"instruction", b"task\n$sections", "fixture")
#
#         def split(members, level):
#             if any(member.section is None for member in members):
#                 return (members,)
#             by_key = {member.section.member.chunk.identifier: member for member in members}
#             return tuple(tuple(by_key[section.member.chunk.identifier] for section in request.sections)
#                          for request in plan_summary_requests(tuple(member.section for member in members), prompts))
#
#         with patch("mycel._summary_grouping.group_summary_nodes", side_effect=lambda values: (values,)):
#             plan = plan_summary_levels(nodes, split_group=split)
#         # Each 24,000-codepoint section needs a separate request after framing.
#         self.assertEqual([len(level.groups) for level in plan.levels], [11, 1])
#         self.assertEqual(plan.requests, 12)
#         self.assertEqual(plan.levels[0].moved_up, ())
#         self.assertEqual(tuple(member for group in plan.levels[0].groups for member in group.members), nodes)
#         self.assertTrue(all(group.summary.section is None for group in plan.levels[0].groups))
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_real_request_splits_count_each_part_without_promoting_cut_parts

# TEST-TIER-DISABLED-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_invalid_split_cannot_omit_duplicate_reorder_or_substitute_members
#     def test_invalid_split_cannot_omit_duplicate_reorder_or_substitute_members(self):
#         nodes = tuple(node(number) for number in range(11))
#         splits = ((), (nodes[:-1],), (nodes, nodes[:1]), (tuple(reversed(nodes)),),
#                   (nodes[5:], nodes[:5]), ((replace(nodes[0], vector=(8, 4)), *nodes[1:]),))
#         for parts in splits:
#             with patch("mycel._summary_grouping.group_summary_nodes", return_value=(nodes,)):
#                 with self.assertRaises(MycelError) as caught:
#                     plan_summary_levels(nodes, split_group=lambda members, level: parts)
#             self.assertEqual(caught.exception.code, "invalid_input")
# TEST-TIER-DISABLED-END tests/test_summary_grouping.py::SummaryGroupingTests.test_invalid_split_cannot_omit_duplicate_reorder_or_substitute_members


if __name__ == "__main__":
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:3
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:5
# import math
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:6
# import os
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:8
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:9
# import warnings
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:9
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:13
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:16
# from mycel._summary_grouping import (GROUPING_PROFILE, SummaryNode,
#     group_summary_nodes, mean_vector, numerical_versions, plan_summary_levels)
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_grouping.py:18
# from mycel._summary_request import (SummaryPrompts, SummarySection,
#     plan_summary_requests)
# TEST-TIER-IMPORTS-END tests/test_summary_grouping.py:18
