"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evaluation_drift as _support
from test_evaluation_drift import (ClassifyDependencies ,DriftCase ,Path ,evaluation ,load_settings ,settings ,suite ,tempfile)


class DriftEvaluationTests(_support.DriftEvaluationTests):


# TEST-TIER-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_oversized_input_routes_or_refuses_without_truncating_any_context
    def test_complete_oversized_input_routes_or_refuses_without_truncating_any_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            loaded = settings(root)
            loaded.file.write_text(loaded.file.read_text() + 'max_input_bytes=1\n')
            loaded = load_settings(path=loaded.file, home=root)
            text = 'unchanged full caller ' * 200 + 'EXACT END\n'
            selected = DriftCase('large', 'old', 'claim', 'needs_review', current='new', context=(text,))
            captured = []
            class Reviewer(evaluation._Reviewer):
                def classify(self, decision, **kwargs):
                    captured.append(decision)
                    return super().classify(decision, **kwargs)
            report = evaluation.run_drift_evaluation(suite((selected,)), loaded,
                repository='fixture', build='development', dependencies=ClassifyDependencies(
                    jev_factory=lambda *_: self.fail('An oversized Jev request must not launch.'),
                    reviewer_factory=lambda *_: Reviewer()))
            row = report['results'][0]
            self.assertEqual(row['standinCalls'], {'jev': 0, 'review': 1})
            self.assertEqual(row['escalation'], 'jev_input_too_large')
            self.assertEqual(captured[0].payload['context'][0]['evidence']['text'], text)
            self.assertEqual(row['inputBytes'], len(captured[0].canonical_bytes))
            loaded.file.write_text(loaded.file.read_text() + 'review_max_input_bytes=1\n')
            loaded = load_settings(path=loaded.file, home=root)
            refused = evaluation.run_drift_evaluation(suite((selected,)), loaded,
                repository='fixture', build='development', dependencies=ClassifyDependencies(
                    jev_factory=lambda *_: self.fail('oversized Jev'),
                    reviewer_factory=lambda *_: self.fail('oversized reviewer')))
            self.assertEqual(refused['results'][0]['standinCalls'], {'jev': 0, 'review': 0})
            self.assertEqual(refused['results'][0]['actual'], 'unresolved')
            self.assertIn('review_input_too_large', refused['results'][0]['error']['message'])
# TEST-TIER-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_oversized_input_routes_or_refuses_without_truncating_any_context
