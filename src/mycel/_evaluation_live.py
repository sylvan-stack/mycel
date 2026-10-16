"""Explicit configured provider evaluation on exact memory-only fixtures.

This module never opens a corpus store or changes settings, pins or caches.
The real adapters are created only by the explicitly selected live branch.
Injected service stand-ins exercise routing but cannot qualify a provider.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

from ._classification_payload import (ENVIRONMENT_VERSION, INSTRUCTION_VERSION, LABELS,
    PROTOCOL, QUESTION_VERSION, ROUTING_REVISION, ReviewCommandIdentity)
from ._classification_runner import ClassifyDependencies, _jev, run_classification
from ._credentials import Credentials, CredentialUnavailable
from ._errors import MycelError
from ._evidence import EvidenceError
from ._provider_qualification import classification_diagnostics, profile_fingerprint, qualify_profile
from ._safeguards import InvocationPolicy


def _pipeline(settings, command):
    options = settings.values['drifts']
    reviewer = ({'provider': options['review_provider'], 'model': options['review_model']}
                if options.get('review_provider') and options.get('review_model') else None)
    return {'protocol': PROTOCOL, 'model': options['model'], 'questionVersion': QUESTION_VERSION,
        'choiceOrder': list(LABELS), 'policyRevision': ROUTING_REVISION,
        'confidenceFloor': options['confidence_floor'],
        'reviewCommandHash': None if command is None else command.command_hash,
        'reviewRevision': options.get('review_revision'),
        'reviewInstructionVersion': INSTRUCTION_VERSION, 'reviewEnvironmentVersion': ENVIRONMENT_VERSION,
        'reviewer': reviewer, 'mode': 'configured-live-providers'}


def _live_result(case, entry, record, *, finished, profile, stopped=False):
    from ._evaluation_drift import _fingerprint, _result
    row = _result(case, entry, record, finished=finished, stopped=stopped)
    row['providerCalls'] = row.pop('standinCalls')
    row['semanticHash'] = _fingerprint(case)
    row['profileFingerprint'] = profile
    record = record or {}
    evidence = record.get('evidence', {})
    outcome = evidence.get('jev', {})
    stages = {'jev': None, 'review': None}
    if 'jev' in outcome:
        source = outcome['jev']
        row['jev'] = {'provider': 'typesafe', 'model': source['model'],
            'judgement': source['label'], 'probabilities': source['probabilities'],
            'confidence': source['confidence']}
        stages['jev'] = source.get('usage')
    if 'review' in evidence:
        source = evidence['review']
        returned = ('protocol', 'inputHash', 'provider', 'model', 'adapterRevision', 'commandHash')
        prepared = entry['prepared']
        requested = prepared.decision.payload['models']['review']
        command = json.loads(prepared.guards_bytes)['command']
        row['review'] = {**{key: source[key] for key in returned},
            'judgement': source['judgement'],
            'instructionVersion': requested['instructionVersion'],
            'environmentVersion': command['environmentVersion'],
            'identitySources': {'returnedFields': list(returned),
                'instructionVersion': 'canonical-request',
                'environmentVersion': 'retained-command-identity'}}
        stages['review'] = source.get('usage')
    row['reused'] = bool(record.get('reused'))
    row['attemptRecords'] = [] if row['reused'] else evidence.get('attempts', [])
    row['stageUsage'] = stages
    # A failed/retried request can have unreported usage. Do not turn known
    # successful-stage usage into a fabricated total for the complete case.
    row['usage'] = stages if row['attempts'] and all(
        stages[stage] is not None and row['providerCalls'][stage] == 1
        for stage in ('jev', 'review') if row['providerCalls'][stage]) else None
    row['cost'] = None
    return row


def run_live_drift_evaluation(suite, settings, *, repository, build,
                              dependencies=None, store_factory=None):
    """Called only from evaluate's validated --kind drift --live dispatch."""
    from ._evaluation_drift import FixtureStore, _fingerprint, _observed_factory
    real = dependencies is None and (store_factory is None or store_factory is FixtureStore)
    dependencies = dependencies or ClassifyDependencies()
    store_factory = FixtureStore if store_factory is None else store_factory
    started = dependencies.monotonic()
    settings.require_valid(require_store=False)
    settings.require_current()
    options, command, preflight = settings.values['drifts'], None, []
    if not options.get('review_command'):
        preflight.append('The configured reviewer is unavailable; no provider case was sent.')
    else:
        try:
            command = ReviewCommandIdentity.inspect(options['review_command'],
                options['review_revision'], settings._home or '/')
            if not command.available:
                preflight.append('The configured reviewer executable is unavailable; no provider case was sent.')
        except EvidenceError:
            preflight.append('The configured reviewer identity is unavailable; no provider case was sent.')
    pipeline = _pipeline(settings, command)
    policy = InvocationPolicy('evaluate', kind='drift', live=True)
    # No call is useful when the requested comparison cannot use the configured
    # reviewer. Acquire one memory-only Jev credential only after that check.
    if real and not preflight and any(not case.unavailable for case in suite.drifts):
        credentials = Credentials(settings, policy, home=settings._home)
        try:
            credentials.require_jev_key(timeout_seconds=min(10.0, options['seconds']),
                cancelled=dependencies.cancelled)
        except CredentialUnavailable:
            preflight.append('The Jev credential is unavailable; no provider case was sent.')
        else:
            dependencies = replace(dependencies,
                jev_factory=lambda selected, intent: _jev(selected, intent, credentials=credentials))
    results, batches, ledger = [], [], {}
    stopped, interrupted = False, False
    profile = profile_fingerprint(pipeline)
    try:
        if not preflight:
            for offset in range(0, len(suite.drifts), options['candidates']):
                if stopped or dependencies.cancelled():
                    stopped = True
                    break
                cases = suite.drifts[offset:offset + options['candidates']]
                store = store_factory(cases, repository, settings, command, at=dependencies.utc_now(),
                    offset=offset, clock=dependencies.monotonic, ledger=ledger)
                observed = replace(dependencies,
                    jev_factory=_observed_factory(dependencies.jev_factory, store, 'jev'),
                    reviewer_factory=_observed_factory(dependencies.reviewer_factory, store, 'review'))
                reply = run_classification(store, settings, repository, k=len(cases),
                    dependencies=observed, policy=policy)
                finished = dependencies.monotonic()
                batches.append({'cases': len(cases), 'incomplete': reply['incomplete'],
                    'jevCalls': reply['jevCalls'], 'reviewCalls': reply['reviewCalls']})
                stopped = reply['incomplete']
                interrupted |= reply.get('stopped') == 'interrupted'
                pairs = {pair['reason']: pair for pair in reply['pairs']}
                for ordinal, case in enumerate(cases, offset):
                    entry = ledger[ordinal]
                    pair = pairs.get(entry['prepared'].reason_id)
                    results.append(_live_result(case, entry, None if pair is None else pair['classification'],
                        finished=finished, stopped=stopped, profile=profile))
                if any(store.leases.values()):
                    raise MycelError('internal', 'Live evaluation retained an active fixture lease.')
    except KeyboardInterrupt:
        stopped, interrupted = True, True
    finished = dependencies.monotonic()
    for ordinal in range(len(results), len(suite.drifts)):
        case = suite.drifts[ordinal]
        entry = ledger.get(ordinal)
        prepared = None if entry is None else entry['prepared']
        record = None if prepared is None else entry['store'].records.get(prepared.reason_id)
        row = _live_result(case, entry, record, finished=finished, stopped=stopped, profile=profile)
        if preflight:
            # Missing required evidence is still a local unresolved no-call
            # fixture; complete evidence remains explicitly unprocessed.
            row['processed'] = bool(case.unavailable)
            row['error'] = {'code': 'refused', 'message': ('Required fixture evidence is unavailable.'
                if case.unavailable else preflight[0])}
        results.append(row)
    if any(any(entry['store'].leases.values()) for entry in ledger.values()):
        raise MycelError('internal', 'Live evaluation retained an active interrupted fixture lease.')
    try:
        settings.require_current()
    except MycelError:
        preflight.append('The effective configuration changed during evaluation; no profile can qualify.')
    if command is not None and command != ReviewCommandIdentity.inspect(
            options['review_command'], options['review_revision'], settings._home or '/'):
        preflight.append('The configured reviewer executable identity changed during evaluation.')
    qualification = qualify_profile(suite.drifts, results, pipeline,
        real_provider_execution=real and not preflight, incomplete=stopped)
    qualification['qualificationFailures'].extend(preflight)
    qualification['qualified'] = not qualification['qualificationFailures']
    diagnostics = classification_diagnostics(suite.drifts, results)
    count = len(results)
    supported = [row for row in results if row['expect'] == 'still_supported']
    report = {'kind': 'drift', 'evaluationSchema': suite.schema_version, 'reportVersion': 1,
        'repository': repository, 'file': str(suite.file), 'fileHash': suite.file_hash,
        'build': build, 'live': True, 'recordedAt': dependencies.utc_now(), 'pipeline': pipeline,
        'providerExecution': 'production-defaults' if real else 'service-stand-ins',
        'cases': count, **qualification, 'diagnostics': diagnostics,
        'meaningfulMisses': diagnostics['overall']['meaningfulMisses'],
        'unnecessaryWork': diagnostics['overall']['unnecessaryWork'],
        'stillSupportedPrecision': diagnostics['overall']['stillSupportedPrecision'],
        'escalationRate': diagnostics['overall']['escalationRate'],
        'routedCases': sum('escalation' in row for row in results),
        'errorRate': sum(not row['correct'] for row in results) / count if count else None,
        'falsePositiveRate': sum(row['actual'] == 'needs_review' for row in supported) / len(supported) if supported else None,
        'elapsedMs': max(0.0, (finished - started) * 1000), 'usage': None, 'cost': None,
        'incomplete': stopped, 'interrupted': interrupted, 'batches': batches, 'results': results}
    report['reportFingerprint'] = sha256(json.dumps(report, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    return report
