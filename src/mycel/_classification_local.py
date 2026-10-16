"""Bounded local eligibility and exact completed-result reuse, without calls."""
from __future__ import annotations

from ._activity import AppliedMutation, ClassificationReference
from ._classification_store import ClassificationStore
from ._deadline import check_deadline, deadline_guard
from ._drift_store import DriftStore
from ._errors import MycelError
from ._freshness import DeadlineExceeded
from ._source_refs import parse_source_address


def reconcile_local(connection, settings, repository, *, activity=None, at=None):
    """Keep current work local; a completed result still passes the live guard.

    The caller supplies its existing deadline scope and activity invocation.
    Pending observation changes produce no classification activity; actual
    reused applications join their own guarded transaction and reply counts.
    This module imports no provider or process adapter.
    """
    counts = {'checked': True, 'complete': False, 'pairs': 0, 'reused': 0,
              'pendingDebounce': 0, 'pendingJev': 0, 'needsLlmReview': 0, 'unresolved': 0}
    try:
        check_deadline()
        listing = DriftStore(connection).list(repository, closed=True)
        store = ClassificationStore(connection)
        for drift in listing['drifts']:
            for source in drift['sources']:
                if not source['active'] and source.get('closed', {}).get('because') != 'still_supported':
                    continue
                check_deadline()
                prepared = store.prepare(settings, drift['id'], source['id'], at=at, reconcile=True)
                counts['pairs'] += 1
                cached = None if prepared.decision is None else store.reuse(settings, prepared, at=at)
                current = source.get('classification', {})
                already_applied = (current.get('status') == 'complete'
                    and current.get('inputHash') == prepared.input_hash
                    and cached is not None and current.get('judgement') == cached.get('judgement'))
                if cached is not None and not already_applied:
                    def audit(result):
                        if activity is not None:
                            changed = bool(result['applied'])
                            detail = ClassificationReference('snapshot:' + prepared.bundle.evidence_hash,
                                parse_source_address(drift['chunk']['address']), cached['judgement'])
                            activity.record_in_transaction(repository, 'classify', AppliedMutation(
                                changed, {**counts, 'reused': counts['reused'] + int(changed)},
                                classifications=(detail,) if changed else ()))
                    check_deadline()
                    result = store.apply(settings, prepared, judgement=cached['judgement'],
                        evidence=cached.get('evidence', {}), at=at, _audit=audit)
                    counts['reused'] += int(result['applied'])
                elif cached is None:
                    key = {'pending_debounce': 'pendingDebounce', 'pending_jev': 'pendingJev',
                           'needs_llm_review': 'needsLlmReview'}.get(prepared.status, 'unresolved')
                    counts[key] += 1
        check_deadline()
        counts['complete'] = True
    except DeadlineExceeded:
        counts['reason'] = 'time_limit'
    except MycelError as error:
        counts['reason'] = error.code
    return counts


def reconcile_freshness(adapter, result, *, deadline):
    """Consume only the original freshness allowance and checked repositories."""
    checks = {}
    for row in result.repositories:
        if row.status != 'done':
            checks[row.repository] = {'checked': False, 'complete': False, 'reason': 'sources_unchecked'}
            continue
        try:
            with deadline_guard(deadline):
                check = reconcile_local(adapter.connection, adapter.settings, row.repository,
                                        activity=adapter.activity)
        except DeadlineExceeded:
            check = {'checked': False, 'complete': False, 'reason': 'time_limit', 'reused': 0}
        checks[row.repository] = check
        if check['reused']:
            adapter.counts[row.repository, 'classify'] = check
    adapter.classification_checks = checks
    return result
