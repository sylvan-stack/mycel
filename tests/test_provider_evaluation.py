# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Service-free provider boundaries and pure finite-corpus arithmetic only.

Artificial outcome rows exercise counts; they are not an evaluation set,
label evidence, measured provider report or live/eval requirement acceptance.
"""
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from mycel._evaluation import DriftCase, EvaluationSet
from mycel._jev import JevResponse
from mycel._provider_qualification import (
    QUALIFICATION_REVISION,
    profile_fingerprint,
    semantic_fingerprint,
)
from mycel._settings import load_settings

AT = '2026-10-15T12:00:00+00:00'


def settings(root, *, reviewer=True):
    text = '[store]\naddress="postgresql://fixture@localhost:55432/mycel_fictional"\n[drifts]\ncandidates=2\nat_once=2\nattempts=1\nseconds=5\n'
    if reviewer:
        text += ('review_command=' + json.dumps([sys.executable]) + '\nreview_provider="fixture-provider"\n'
                 'review_model="fixture-model-1"\nreview_revision="fixture-adapter-v1"\n')
    file = root / 'config.toml'; file.write_text(text)
    return load_settings(path=file, home=root)


def suite(cases):
    return EvaluationSet(Path('/fictional/reviewed-evaluation.toml'), 'a' * 64, drifts=tuple(cases))


def pipeline():
    return {'qualificationRevision': QUALIFICATION_REVISION,
        'protocol': 1, 'model': 'jev-1.13.0', 'questionVersion': 'mycel-dependency-v1',
        'choiceOrder': ['still_supported', 'needs_review', 'insufficient_evidence'],
        'policyRevision': 'fixture-policy', 'confidenceFloor': 0.7,
        'reviewCommandHash': 'a' * 64, 'reviewRevision': 'adapter-v1',
        'reviewInstructionVersion': 'mycel-review-v1', 'reviewEnvironmentVersion': 'mycel-review-env-v1',
        'reviewer': {'provider': 'fixture-provider', 'model': 'fixture-model'}}


def retained_jev(jev, usage=None):
    """Complete projections for controlled arithmetic fixtures only."""
    probabilities = {key: Decimal(str(value)) for key, value in jev['probabilities'].items()}
    maximum = max(probabilities.values())
    response = JevResponse(jev['model'], jev['judgement'], probabilities,
        (3 * maximum - 1) / 2, usage or {'input_tokens': 0, 'output_tokens': 0},
        sum(value == maximum for value in probabilities.values()) > 1,
        reported_confidence=Decimal(str(jev.get('reportedConfidence', jev['confidence']))))
    source = response.as_dict()
    return {key: source[key] for key in ('provider', 'model', 'probabilities', 'confidence',
        'reportedConfidence', 'confidenceComparison', 'exactDecimals')} | {'judgement': source['label']}


def artificial_outcomes():
    """Arithmetic vectors, never executed semantic fixtures or authored labels."""
    identity = pipeline(); cases, rows = [], []
    for number in range(200):
        critical, unchanged = number < 50, 50 <= number < 100
        expected = 'still_supported' if unchanged else 'needs_review'
        case = DriftCase(str(number), 'before ' + str(number), 'claim ' + str(number), expected, current='after ' + str(number),
            critical=(('negation', 'operator', 'permission', 'deletion')[number % 4],) if critical else (), unchanged=unchanged)
        row = {'semanticHash': semantic_fingerprint(case), 'processed': True, 'attempts': 1,
            'actual': expected, 'profileFingerprint': profile_fingerprint(identity),
            'inputHash': format(number, '064x'), 'jev': {'model': identity['model'], 'judgement': expected}}
        if number == 0:
            row['escalation'] = 'jev_low_confidence'
            row['jev']['judgement'] = 'still_supported'
            row['review'] = {**identity['reviewer'], 'judgement': expected,
                'commandHash': identity['reviewCommandHash'], 'adapterRevision': identity['reviewRevision'],
                'instructionVersion': identity['reviewInstructionVersion'],
                'environmentVersion': identity['reviewEnvironmentVersion'], 'inputHash': row['inputHash']}
        label = row['jev']['judgement']
        row['jev'].update(probabilities={name: (0.6 if name == label else 0.2) if number == 0
            else float(name == label) for name in identity['choiceOrder']},
            confidence=0.4 if number == 0 else 1.0)
        row['jevOnlyOutcome'] = 'unresolved' if number == 0 else label
        row['stageUsage'] = {'jev': {'input_tokens': 0, 'output_tokens': 0}, 'review': None}
        row['jev'] = retained_jev(row['jev'])
        cases.append(case); rows.append(row)
    return cases, rows, identity


class ProviderEvaluationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
