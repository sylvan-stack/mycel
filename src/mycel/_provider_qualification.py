"""Pure finite-corpus provider-profile qualification; no calls or proof loading.

A report is diagnostic data. Its profile identity can accompany deployment
review, but cannot become a same-Build OnDemandProofs object by deserialization.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from ._classification_payload import LABELS
from ._evidence import canonical_json
from ._jev import JevFailure, _distribution, _fraction


QUALIFICATION_REVISION = 'mycel-drift-qualification-v2'
CRITICAL_CATEGORIES = frozenset({'negation', 'operator', 'permission', 'deletion'})


def semantic_fingerprint(case):
    return sha256(canonical_json({'before': case.before, 'current': case.current,
        'dependant': case.dependant, 'sourceState': case.source_state,
        'context': list(case.context), 'unavailable': sorted(case.unavailable)})).hexdigest()


def profile_fingerprint(pipeline):
    """Stable exact configured component identity, independent of Build/date."""
    identity = {key: pipeline.get(key) for key in ('qualificationRevision', 'protocol', 'model', 'questionVersion',
        'choiceOrder', 'policyRevision', 'confidenceFloor', 'reviewCommandHash',
        'reviewRevision', 'reviewInstructionVersion', 'reviewEnvironmentVersion', 'reviewer')}
    identity['confidenceFloor'] = str(identity['confidenceFloor'])
    return sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _jev_only_outcome(jev, pipeline):
    """Verify the retained pre-review outcome against the accepted routing.

    The tentative label remains the basis of label-error and critical-miss
    comparisons. A routed result cannot complete without a reviewer.
    """
    try:
        probabilities = {key: _fraction(Decimal(str(value))) for key, value in jev['probabilities'].items()}
        label = jev['judgement']
        if set(probabilities) != set(LABELS) or label not in LABELS:
            return None
        confidence = _fraction(Decimal(str(jev['confidence'])))
        tied = _distribution(probabilities, confidence, label)
        floor = _fraction(Decimal(str(pipeline['confidenceFloor'])))
        return ('unresolved' if tied or label == 'insufficient_evidence'
            or confidence < floor else label)
    except (KeyError, TypeError, ValueError, InvalidOperation, JevFailure):
        return None


def qualify_profile(cases, results, pipeline, *, real_provider_execution, incomplete=False):
    """Assess actual categorical outcomes without treating confidence as truth.

    Callers supply the semantic fingerprint alongside each result. Duplicates
    remain in diagnostics but count once toward all three coverage floors.
    This pure calculation performs no acceptance operation or persistence.
    """
    failures = []
    if not real_provider_execution:
        failures.append('No real explicitly requested provider pipeline was evaluated.')
    if incomplete or len(results) != len(cases) or any(not row.get('processed') for row in results):
        failures.append('Stopped or unprocessed fixtures make qualification inconclusive.')
    by_semantic = {}
    for case, result in zip(cases, results):
        by_semantic.setdefault(semantic_fingerprint(case), []).append((case, result))
    if any(result.get('semanticHash') != semantic_fingerprint(case) for case, result in zip(cases, results)):
        failures.append('A per-case semantic identity differs from the exact fixture bytes.')
    if any(len({case.expect for case, _ in group}) != 1 for group in by_semantic.values()):
        failures.append('Duplicate semantic fixtures have conflicting ground-truth labels.')
    distinct = len(by_semantic)
    critical = sum(any(case.critical for case, _ in group) for group in by_semantic.values())
    unchanged = sum(any(case.unchanged for case, _ in group) for group in by_semantic.values())
    if distinct < 200:
        failures.append('At least 200 distinct labelled semantic pairs are required.')
    if critical < 50:
        failures.append('At least 50 distinct critical-change pairs are required.')
    if unchanged < 50:
        failures.append('At least 50 distinct unchanged or cosmetic pairs are required.')
    categories = {category for case in cases for category in case.critical}
    if not CRITICAL_CATEGORIES <= categories:
        failures.append('Critical coverage must include negation, operator, permission and deletion.')
    misses = sum(bool(case.critical) and case.expect in {'needs_review', 'unresolved'}
        and result['actual'] == 'still_supported' for case, result in zip(cases, results))
    if misses:
        failures.append('Critical work was incorrectly suppressed as still supported.')
    unavailable_ok = all(result['actual'] == 'unresolved' and result['attempts'] == 0
        and not result.get('jev') and not result.get('review') and 'inputHash' not in result
        for case, result in zip(cases, results) if case.unavailable)
    if not unavailable_ok:
        failures.append('Unavailable evidence did not remain unresolved without calls.')
    if any(not case.unavailable and result.get('error') for case, result in zip(cases, results)):
        failures.append('A complete-evidence fixture failed or could not complete its pipeline.')
    expected_reviewer = pipeline.get('reviewer') or {}
    identities_ok = bool(pipeline.get('qualificationRevision') == QUALIFICATION_REVISION
        and pipeline.get('reviewCommandHash') and pipeline.get('reviewRevision')
        and expected_reviewer.get('provider') and expected_reviewer.get('model'))
    baseline_ok = True
    for result in results:
        jev, review = result.get('jev'), result.get('review')
        if jev is not None:
            identities_ok &= jev.get('model') == pipeline.get('model')
            expected_outcome = _jev_only_outcome(jev, pipeline)
            baseline_ok &= (expected_outcome is not None
                and result.get('jevOnlyOutcome') == expected_outcome
                and (expected_outcome == 'unresolved') == bool(result.get('escalation')))
        if review is not None:
            identities_ok &= (review.get('provider') == expected_reviewer.get('provider')
                and review.get('model') == expected_reviewer.get('model')
                and review.get('commandHash') == pipeline.get('reviewCommandHash')
                and review.get('adapterRevision') == pipeline.get('reviewRevision')
                and review.get('instructionVersion') == pipeline.get('reviewInstructionVersion')
                and review.get('environmentVersion') == pipeline.get('reviewEnvironmentVersion')
                and review.get('inputHash') == result.get('inputHash'))
        identities_ok &= result.get('profileFingerprint') == profile_fingerprint(pipeline)
    if not identities_ok:
        failures.append('The configured or returned provider identity is missing or changed.')
    if not baseline_ok:
        failures.append('The Jev-only baseline is missing or differs from the recorded confidence routing.')
    common = [(case, row) for case, row in zip(cases, results)
              if not case.unavailable and row.get('escalation')
              and row.get('jev', {}).get('judgement') in LABELS
              and row.get('review', {}).get('judgement') in LABELS]
    jev_errors = sum(row['jev']['judgement'] != case.expect for case, row in common)
    review_errors = sum(row['review']['judgement'] != case.expect for case, row in common)
    jev_misses = sum(bool(case.critical) and row['jev']['judgement'] == 'still_supported'
                     for case, row in common)
    review_misses = sum(bool(case.critical) and row['review']['judgement'] == 'still_supported'
                        for case, row in common)
    jev_unresolved = sum(row.get('jevOnlyOutcome') == 'unresolved'
                         for _, row in common)
    review_unresolved = sum(row['review']['judgement'] in {'insufficient_evidence', 'unresolved'}
                            for _, row in common)
    if not common:
        failures.append('No routed adjudicated common Jev and reviewer subset was measured.')
    elif (review_misses > jev_misses or review_errors > jev_errors
          or not (review_errors < jev_errors or review_unresolved < jev_unresolved)):
        failures.append('Reviewer must have no more critical misses or wrong labels and strictly improve wrong or unresolved outcomes on the common routed subset.')
    return {'qualificationRevision': QUALIFICATION_REVISION, 'qualified': not failures,
        'qualificationFailures': failures, 'distinctCases': distinct, 'criticalCases': critical,
        'unchangedCases': unchanged, 'criticalMisses': misses,
        'criticalCategories': {category: sum(any(category in case.critical for case, _ in group)
            for group in by_semantic.values()) for category in sorted(CRITICAL_CATEGORIES)},
        'commonRoutedCases': len(common), 'jevErrorsOnRouted': jev_errors,
        'reviewerErrorsOnRouted': review_errors, 'jevCriticalMissesOnRouted': jev_misses,
        'reviewerCriticalMissesOnRouted': review_misses,
        'jevUnresolvedOnRouted': jev_unresolved, 'reviewerUnresolvedOnRouted': review_unresolved,
        'reviewerComparisonBasis': {'wrongLabels': 'jev-tentative-label',
            'criticalMisses': 'jev-tentative-label', 'unresolved': 'jev-only-confidence-routing'},
        'profileFingerprint': profile_fingerprint(pipeline),
        'profileQualificationIsSameBuildProof': False}



def classification_diagnostics(cases, results):
    """Observed category arithmetic with explicit populations and null shares.

    Category tags overlap; repeated fixtures remain observed diagnostics while
    distinct semantic coverage is separately reported by the qualifier.
    """
    pairs = list(zip(cases, results))
    def metrics(selected):
        count = len(selected)
        meaningful = [(case, row) for case, row in selected if case.expect in {'needs_review', 'unresolved'}]
        supported = [(case, row) for case, row in selected if case.expect == 'still_supported']
        predicted_support = [(case, row) for case, row in selected if row['actual'] == 'still_supported']
        processed_complete = [(case, row) for case, row in selected
            if not case.unavailable and row.get('processed') and row.get('inputHash')]
        misses = sum(row['actual'] == 'still_supported' for _, row in meaningful)
        unnecessary = sum(row['actual'] == 'needs_review' for _, row in supported)
        correct_support = sum(case.expect == 'still_supported' for case, _ in predicted_support)
        routed = sum(bool(row.get('escalation')) for _, row in processed_complete)
        wrong = sum(row['actual'] != case.expect for case, row in selected)
        return {'cases': count, 'processedCases': sum(bool(row.get('processed')) for _, row in selected),
            'distinctCases': len({semantic_fingerprint(case) for case, _ in selected}),
            'meaningfulMisses': misses, 'unresolvedMeaningful': sum(row['actual'] in {'insufficient_evidence', 'unresolved'} for _, row in meaningful),
            'unnecessaryWork': unnecessary, 'wrongLabels': wrong,
            'stillSupportedCorrect': correct_support, 'routedCases': routed,
            'errorRate': wrong / count if count else None,
            'meaningfulMissRate': misses / len(meaningful) if meaningful else None,
            'falsePositiveRate': unnecessary / len(supported) if supported else None,
            'stillSupportedPrecision': correct_support / len(predicted_support) if predicted_support else None,
            'escalationRate': routed / len(processed_complete) if processed_complete else None,
            'denominators': {'errorRate': count, 'meaningfulMissRate': len(meaningful),
                'falsePositiveRate': len(supported), 'stillSupportedPrecision': len(predicted_support),
                'escalationRate': len(processed_complete)}}
    categories = {category: metrics([(case, row) for case, row in pairs if category in case.critical])
                  for category in sorted(CRITICAL_CATEGORIES)}
    categories['unchanged_cosmetic'] = metrics([(case, row) for case, row in pairs if case.unchanged])
    categories['other'] = metrics([(case, row) for case, row in pairs if not case.critical and not case.unchanged])
    return {'basis': {'outcomes': 'all selected fixture observations including repeats and unprocessed rows',
        'meaningful': 'ground truth needs_review or unresolved; a miss is incorrect still_supported',
        'unnecessaryWork': 'needs_review outcome against still_supported ground truth',
        'supportPrecision': 'correct still_supported among every still_supported outcome',
        'escalation': 'routed among processed complete-evidence fixtures with canonical inputHash',
        'categories': 'critical tags may overlap; unchanged_cosmetic and other are additional views'},
        'overall': metrics(pairs), 'byCategory': categories}
