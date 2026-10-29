"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_grouping as _support
from test_summary_grouping import (group_summary_nodes ,node)


class SummaryGroupingTests(_support.SummaryGroupingTests):

# TEST-TIER-BEGIN tests/test_summary_grouping.py::SummaryGroupingTests.test_real_pca_mixture_is_repeatable_and_input_order_independent
    def test_real_pca_mixture_is_repeatable_and_input_order_independent(self):
        nodes = tuple(node(number, tuple((40.0 if column == number // 8 else 0.0)
                    + ((number % 8) - 3.5) * (column + 1) / 100
                    for column in range(12))) for number in range(24))
        first = group_summary_nodes(nodes)
        self.assertEqual(first, group_summary_nodes(tuple(reversed(nodes))))
        self.assertEqual(first, group_summary_nodes(nodes))
        self.assertEqual(len(first), 3)
        self.assertEqual({member.key for group in first for member in group}, {member.key for member in nodes})
        self.assertEqual({frozenset(member.key for member in group) for group in first},
                         {frozenset(str(number) for number in range(start, start + 8)) for start in (0, 8, 16)})
# TEST-TIER-END tests/test_summary_grouping.py::SummaryGroupingTests.test_real_pca_mixture_is_repeatable_and_input_order_independent
