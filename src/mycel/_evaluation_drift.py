"""Non-live canonical fixture evaluation through the finite classifier runner.

Only this invocation's memory changes. Fixture labels never enter a decision,
adapter or cache key. Scripted responses exercise production routing and exact
evidence guards; they are not measurements or provider qualification.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
import sys
import threading
import time
from uuid import NAMESPACE_URL, uuid5

from ._classification_eligibility import classification_eligibility, observe_input
from ._classification_payload import (CurrentSelection, DecisionPayload, DecisionText,
    EvidenceBundle, ReviewCommandIdentity, ReviewerRequest, ancestor_context,
    ENVIRONMENT_VERSION, INSTRUCTION_VERSION, LABELS, PROTOCOL, QUESTION_VERSION, ROUTING_REVISION)
from ._classification_runner import ClassifyDependencies, run_classification
from ._classification_store import ClassificationPreparation
from ._errors import MycelError
from ._evidence import BaselineManifest, EvidenceError, canonical_json, exact_comparison, snapshot
from ._jev import JevFailure, JevResponse, route_response
from ._reviewer import ReviewerFailure, ReviewerSuccess
from ._source_refs import SourceAddress


STANDIN_REVISION = 'mycel-drift-fixture-v1'
STANDIN_PROVIDER = 'mycel-deterministic-stand-in'
STANDIN_MODEL = 'lexical-v1'


def _semantic(case):
    return {'before': case.before, 'current': case.current, 'dependant': case.dependant,
            'sourceState': case.source_state, 'context': list(case.context),
            'unavailable': sorted(case.unavailable)}


def _fingerprint(case):
    return sha256(canonical_json(_semantic(case))).hexdigest()


class _Settings:
    """Keep real validation/current guards; replace only the scripted reviewer."""
    def __init__(self, settings):
        self.original = settings
        self._home = settings._home
        drifts = {**settings.values['drifts'], 'review_command': [sys.executable],
                  'review_revision': STANDIN_REVISION, 'review_provider': STANDIN_PROVIDER,
                  'review_model': STANDIN_MODEL}
        self.values = {**settings.values, 'drifts': drifts}

    def require_valid(self, require_store=True):
        self.original.require_valid(require_store=require_store)

    def require_current(self):
        self.original.require_current()


def _text(raw, place):
    source = raw.encode('utf-8')
    return snapshot(source, comparison=exact_comparison(source, 'code_text'),
                    place=place, file_source=source, span=(0, len(source)))


def _prepare(case, ordinal, repository, settings, command, at):
    semantic = _fingerprint(case)
    identifier = lambda role: str(uuid5(NAMESPACE_URL, 'mycel-evaluation:' + semantic + ':' + role))
    drift_id, reason_id = identifier('drift:' + str(ordinal)), identifier('reason:' + str(ordinal))
    base = dict(repository=repository, drift_id=drift_id, reason_id=reason_id,
                pair_hash=semantic, recorded_at=at, guards_bytes=b'{}', observations_bytes=b'{}')
    if case.unavailable:
        fault = {'baseline': 'baseline_missing', 'dependant': 'insufficient_evidence',
                 'context': 'context_missing'}[case.unavailable[0]]
        return ClassificationPreparation(**base, decision=None, bundle=None,
            status='error', eligible_at=None, fault=fault), (), None
    source = SourceAddress(repository, 'code', '__evaluation__/source.py', 'source')
    dependant = SourceAddress(repository, 'code', '__evaluation__/claim.py', 'claim')
    before, dep = _text(case.before, source), _text(case.dependant, dependant)
    captures = [before, dep]
    manifest = BaselineManifest({'schema': 1, 'ownerRepository': repository,
        'dependantId': identifier('dependant'), 'dependantVersion': '1',
        'dependant': dep.evidence.as_dict(), 'kind': 'declared', 'ref': source.address,
        'source': before.evidence.as_dict()['place'], 'selection': 'chunk',
        'members': [{'id': identifier('source'), 'place': before.evidence.as_dict()['place'],
                     'evidence': before.evidence.as_dict()}],
        'pinnedHash': before.evidence.comparison.hash,
        'selectionComparison': before.evidence.comparison.as_dict(),
        'capturedAt': at, 'location': {'kind': 'disk'}})
    current_text = ()
    if case.source_state == 'present':
        current = _text(case.current, source)
        captures.append(current)
        current_text = (DecisionText.create(current.evidence, current.source),)
    selection = CurrentSelection.create(case.source_state, source, 'chunk', current_text)
    contexts = []
    for index, value in enumerate(case.context):
        captured = _text(value, SourceAddress(repository, 'code', '__evaluation__/context.py',
                                             'context' + str(index).zfill(8)))
        captures.append(captured)
        contexts.append(ancestor_context(DecisionText.create(captured.evidence, captured.source)))
    decision = DecisionPayload.create(baseline=manifest,
        before=(DecisionText.create(before.evidence, before.source),), current=selection,
        dependant=DecisionText.create(dep.evidence, dep.source), context=contexts,
        jev_model=settings.values['drifts']['model'],
        review=command.model_identity(settings.values['drifts']['review_provider'],
                                      settings.values['drifts']['review_model']),
        confidence_floor=settings.values['drifts']['confidence_floor'])
    now = datetime.fromisoformat(at.replace('Z', '+00:00')).astimezone(timezone.utc)
    try:
        changed = (now - timedelta(seconds=settings.values['drifts']['debounce_seconds'] + 1)).isoformat()
    except (OverflowError, ValueError):
        raise MycelError('invalid_input', 'The fixture quiet period exceeds the supported clock range.') from None
    observation = observe_input(source.address, semantic, kind='deleted' if case.source_state == 'deleted' else 'file',
        observed_at=changed, **({'modified_at': changed} if case.source_state == 'present' else {}))
    eligibility = classification_eligibility((observation,), at=at,
        debounce_seconds=settings.values['drifts']['debounce_seconds'])
    guard = {'place': before.evidence.as_dict()['place'], 'changedAt': changed,
             'event': 'deleted' if case.source_state == 'deleted' else 'file_changed'}
    if case.source_state == 'present':
        guard['hash'] = captures[2].evidence.hash
    bundle = EvidenceBundle.create(owner_repository=repository, baseline_id=manifest.identifier,
        decision=decision, evidence=tuple(item.evidence for item in captures), guards=(guard,))
    return ClassificationPreparation(**{**base, 'guards_bytes': canonical_json({'command': command.as_dict()}),
        'observations_bytes': canonical_json([observation])}, decision=decision, bundle=bundle,
        status=eligibility.status, eligible_at=eligibility.eligible_at), tuple(captures), manifest


class FixtureStore:
    """Duck-typed runner store with real canonical guards and memory-only state."""
    def __init__(self, cases, repository, settings, command, *, at, offset=0,
                 clock=None, ledger=None):
        self.drifts = self
        self.repository = repository
        self.preparations, self.captures, self.baselines, self.records = {}, {}, {}, {}
        self.cache, self.leases, self.rows = {}, {}, []
        self.calls, self.active = {}, threading.local()
        self.call_mutex = threading.Lock()
        self.clock = time.monotonic if clock is None else clock
        self.ledger = {} if ledger is None else ledger
        for index, case in enumerate(cases, offset):
            self.ledger[index] = {'started': self.clock(), 'prepared': None, 'store': self}
            prepared, captures, baseline = _prepare(case, index, repository, settings, command, at)
            self.ledger[index]['prepared'] = prepared
            self.preparations[prepared.reason_id] = prepared
            self.captures[prepared.reason_id] = captures
            self.baselines[prepared.reason_id] = baseline
            self.calls[prepared.reason_id] = {'jev': 0, 'review': 0}
            self.rows.append({'id': prepared.drift_id, 'chunkId': str(index), 'version': '1',
                'current': True, 'state': 'open',
                'chunk': {'address': repository + ':@code/__evaluation__/claim.py#claim'},
                'sources': [{'id': prepared.reason_id, 'dependency': prepared.reason_id,
                    'active': True, 'pairHash': prepared.pair_hash,
                    'source': {'address': repository + ':@code/__evaluation__/source.py#source'},
                    'classification': {'status': prepared.status}}]})

    def session(self, repository):
        return nullcontext()

    def reconcile(self, settings, repository, *, at):
        settings.require_current()

    def list(self, repository):
        return {'drifts': self.rows}

    def preview(self, settings, drift_id, reason_id, *, at):
        settings.require_current()
        prepared = self.preparations[reason_id]
        if prepared.drift_id != drift_id:
            raise MycelError('invalid_input', 'The fixture reason belongs to a different work item.')
        return prepared

    prepare = preview

    def check(self, settings, prepared, *, stage, at):
        settings.require_current()
        try:
            current = self.preparations[prepared.reason_id]
            if (current.input_hash != prepared.input_hash
                    or current.pair_hash != prepared.pair_hash):
                return {'allowed': False, 'reason': 'obsolete'}
            if prepared.decision is None:
                return {'allowed': False, 'reason': prepared.fault}
            eligibility = classification_eligibility(json.loads(prepared.observations_bytes), at=at,
                debounce_seconds=settings.values['drifts']['debounce_seconds'])
            if not eligibility.eligible:
                return {'allowed': False, 'reason': 'pending_debounce'}
            DecisionPayload.from_bytes(prepared.decision.canonical_bytes, prepared.input_hash)
            EvidenceBundle.from_bytes(prepared.bundle.canonical_bytes, prepared.bundle.evidence_hash)
            baseline = self.baselines[prepared.reason_id]
            BaselineManifest.from_bytes(baseline.canonical_bytes, baseline.identifier)
            if (prepared.bundle.payload['inputHash'] != prepared.input_hash
                    or prepared.bundle.payload['baseline'] != baseline.identifier):
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            command = ReviewCommandIdentity.inspect(settings.values['drifts']['review_command'],
                settings.values['drifts']['review_revision'], settings._home or '/')
            if json.loads(prepared.guards_bytes)['command'] != command.as_dict():
                return {'allowed': False, 'reason': 'obsolete'}
            for item in self.captures[prepared.reason_id]:
                item.evidence.verify(item.source, textual=True)
            return {'allowed': True}
        except EvidenceError as error:
            return {'allowed': False, 'reason': error.status}

    check_in_transaction = check

    @contextmanager
    def stage(self, settings, prepared, *, stage, at):
        checked = self.check(settings, prepared, stage=stage, at=at)
        previous = getattr(self.active, 'reason', None)
        if checked['allowed']:
            with self.call_mutex:
                self.leases[prepared.input_hash] = self.leases.get(prepared.input_hash, 0) + 1
            self.active.reason = prepared.reason_id
        try:
            yield checked
        finally:
            if checked['allowed']:
                with self.call_mutex:
                    self.leases[prepared.input_hash] -= 1
                self.active.reason = previous

    def reuse(self, settings, prepared, *, at):
        return self.cache.get(prepared.input_hash) if self.check(settings, prepared,
            stage='application', at=at)['allowed'] else None

    def apply(self, settings, prepared, *, judgement, evidence, at):
        checked = self.check(settings, prepared, stage='application', at=at)
        if not checked['allowed']:
            return {'applied': False, 'obsolete': True}
        record = {'status': 'complete', 'judgement': judgement, 'inputHash': prepared.input_hash,
                  'evidence': evidence}
        self.cache[prepared.input_hash] = record
        self.records[prepared.reason_id] = record
        for row in self.rows:
            if row['id'] == prepared.drift_id:
                row['sources'][0]['classification'] = record
                if judgement == 'still_supported':
                    row['sources'][0]['active'], row['state'] = False, 'closed'
        return {'applied': True, 'obsolete': False}

    def record_classification(self, settings, drift_id, reason_id, pair_hash, *, status,
                              evidence, canonical_input_hash, at, _canonical_guard):
        allowed = _canonical_guard()
        self.records[reason_id] = {'status': status, 'inputHash': canonical_input_hash,
                                  'evidence': evidence, 'obsolete': not allowed}
        return {'applied': allowed, 'obsolete': not allowed}


def _judgement(decision):
    """A deliberately simple versioned stand-in, independent of every label."""
    value = decision.payload
    if not value['dependant']['text'].strip():
        return 'insufficient_evidence'
    if value['current']['state'] == 'deleted':
        return 'needs_review'
    tokens = lambda texts: re.findall(r'\w+|[^\w\s]', '\n'.join(texts), flags=re.UNICODE)
    before = tokens([item['text'] for item in value['before']])
    current = tokens([item['text'] for item in value['current']['members']])
    return 'still_supported' if before == current else 'needs_review'


class _Jev:
    def classify(self, decision, *, deadline, before_call, cancelled, on_call):
        before_call()
        if cancelled():
            raise JevFailure('cancelled')
        on_call()
        label = _judgement(decision)
        ambiguous = label == 'needs_review' and decision.payload['current']['state'] != 'deleted'
        probabilities = {name: Decimal('0.2') if ambiguous else Decimal(0)
                         for name in LABELS}
        probabilities[label] = Decimal('0.6') if ambiguous else Decimal(1)
        response = JevResponse(decision.payload['models']['jev']['model'], label, probabilities,
            Decimal('0.4') if ambiguous else Decimal(1), {'input_tokens': 0, 'output_tokens': 0}, False)
        return route_response(decision, response)


class _Reviewer:
    def classify(self, decision, *, deadline, before_call, cancelled, on_call):
        before_call()
        if cancelled():
            raise ReviewerFailure('cancelled')
        on_call()
        return ReviewerSuccess(ReviewerRequest(decision, 1), _judgement(decision),
            'Deterministic non-live fixture stand-in.', (), None)


def _observed_factory(factory, store, stage):
    """Count actual on_call events even if cancellation prevents publication."""
    def create(*args):
        client = factory(*args)
        class Observed:
            def classify(self, decision, **kwargs):
                reason = store.active.reason
                original = kwargs['on_call']
                def called():
                    original()
                    with store.call_mutex:
                        store.calls[reason][stage] += 1
                return client.classify(decision, **{**kwargs, 'on_call': called})
        return Observed()
    return create


def _result(case, entry, record, *, finished, stopped=False):
    """Local fixture lifetime includes assembly and its batch's scheduling wait."""
    prepared = None if entry is None else entry['prepared']
    store = None if entry is None else entry['store']
    record = record or {}
    calls = ({'jev': 0, 'review': 0} if prepared is None else
             store.calls.get(prepared.reason_id, {'jev': 0, 'review': 0}))
    actual = (record.get('judgement', 'unresolved')
              if record.get('status') == 'complete' and not record.get('obsolete') else 'unresolved')
    result = {'id': case.id, 'expect': case.expect, 'actual': actual,
        'correct': actual == case.expect, 'critical': list(case.critical),
        'attempts': sum(calls.values()), 'standinCalls': dict(calls),
        'elapsedMs': 0 if entry is None else max(0.0, (finished - entry['started']) * 1000),
        'usage': None, 'cost': None, 'processed': bool(record),
        'inputBytes': None if prepared is None or prepared.decision is None else len(prepared.decision.canonical_bytes)}
    # No canonical request exists for missing evidence or an unassembled case.
    # Omission preserves that distinction without inventing an input hash.
    if prepared is not None and prepared.input_hash is not None:
        result['inputHash'] = prepared.input_hash
    if prepared is not None:
        row = next((row for row in store.rows if row['id'] == prepared.drift_id), None)
        if row is not None:
            result['lifecycle'] = {'status': record.get('status', 'unprocessed'),
                'active': row['sources'][0]['active'], 'obsolete': bool(record.get('obsolete'))}
    evidence = record.get('evidence', {})
    jev = evidence.get('jev', {})
    if 'jev' in jev:
        result['jev'] = {'judgement': jev['jev']['label'],
            'probabilities': jev['jev']['probabilities'], 'confidence': jev['jev']['confidence'],
            'simulated': True}
    if 'review' in evidence:
        result['review'] = {key: evidence['review'][key] for key in ('provider', 'model', 'judgement')}
        result['review']['simulated'] = True
    if jev.get('reason'):
        result['escalation'] = jev['reason']
    fault = (None if prepared is None else prepared.fault) or record.get('reason')
    if fault:
        result['error'] = {'code': 'internal' if record.get('failed') else 'refused',
                           'message': 'Fixture pipeline outcome: ' + str(fault) + '.'}
    elif stopped and not record:
        result['error'] = {'code': 'refused', 'message': 'The fixture was not processed after cancellation.'}
    return result


def run_drift_evaluation(suite, settings, *, repository, build, live=False,
                         dependencies=None, store_factory=FixtureStore):
    if type(live) is not bool:
        raise MycelError('invalid_input', 'Live Drift evaluation requires an explicit boolean choice.')
    if live:
        from ._evaluation_live import run_live_drift_evaluation
        return run_live_drift_evaluation(suite, settings, repository=repository, build=build,
            dependencies=dependencies, store_factory=store_factory)
    dependencies = dependencies or ClassifyDependencies(
        jev_factory=lambda *_: _Jev(), reviewer_factory=lambda *_: _Reviewer())
    started = dependencies.monotonic()
    settings.require_valid(require_store=False)
    settings.require_current()
    view = _Settings(settings)
    command = ReviewCommandIdentity.inspect(view.values['drifts']['review_command'], STANDIN_REVISION,
                                          view._home or '/')
    results, batches = [], []
    cap = view.values['drifts']['candidates']
    stopped, interrupted = False, False
    ledger = {}
    try:
        for offset in range(0, len(suite.drifts), cap):
            cases = suite.drifts[offset:offset + cap]
            if stopped or dependencies.cancelled():
                stopped = True
                break
            store = store_factory(cases, repository, view, command, at=dependencies.utc_now(),
                offset=offset, clock=dependencies.monotonic, ledger=ledger)
            observed = replace(dependencies,
                jev_factory=_observed_factory(dependencies.jev_factory, store, 'jev'),
                reviewer_factory=_observed_factory(dependencies.reviewer_factory, store, 'review'))
            reply = run_classification(store, view, repository, k=len(cases), dependencies=observed)
            finished = dependencies.monotonic()
            batches.append({'cases': len(cases), 'incomplete': reply['incomplete'],
                'jevStandinCalls': reply['jevCalls'], 'reviewStandinCalls': reply['reviewCalls']})
            stopped = reply['incomplete']
            interrupted |= reply.get('stopped') == 'interrupted'
            pairs = {pair['reason']: pair for pair in reply['pairs']}
            for ordinal, case in enumerate(cases, offset):
                entry = ledger[ordinal]
                pair = pairs.get(entry['prepared'].reason_id)
                results.append(_result(case, entry, None if pair is None else pair['classification'],
                                       finished=finished, stopped=stopped))
            if any(store.leases.values()):
                raise MycelError('internal', 'The fixture runner retained an active evidence lease.')
    except KeyboardInterrupt:
        # No adapter is detached: run_classification joins its own active work.
        # Assembly/between-batch interrupts start no future batch or provider.
        stopped, interrupted = True, True
    finished = dependencies.monotonic()
    for ordinal in range(len(results), len(suite.drifts)):
        entry = ledger.get(ordinal)
        prepared = None if entry is None else entry['prepared']
        record = (None if prepared is None else entry['store'].records.get(prepared.reason_id))
        results.append(_result(suite.drifts[ordinal], entry, record, finished=finished, stopped=stopped))
    if any(any(store.leases.values()) for store in {entry['store'] for entry in ledger.values()}):
        raise MycelError('internal', 'The interrupted fixture runner retained an active evidence lease.')
    settings.require_current()
    routed = [row for row in results if 'escalation' in row]
    critical_miss = lambda row: bool(row['critical']) and row['actual'] == 'still_supported'
    supported = [row for row in results if row['expect'] == 'still_supported']
    count = len(results)
    return {'kind': 'drift', 'evaluationSchema': suite.schema_version, 'repository': repository,
        'file': str(suite.file), 'fileHash': suite.file_hash, 'build': build, 'live': False,
        'pipeline': {'protocol': PROTOCOL, 'model': view.values['drifts']['model'],
            'questionVersion': QUESTION_VERSION, 'choiceOrder': list(LABELS),
            'policyRevision': ROUTING_REVISION,
            'confidenceFloor': view.values['drifts']['confidence_floor'],
            'reviewCommandHash': command.command_hash, 'reviewRevision': STANDIN_REVISION,
            'reviewInstructionVersion': INSTRUCTION_VERSION, 'reviewEnvironmentVersion': ENVIRONMENT_VERSION,
            'reviewer': {'provider': STANDIN_PROVIDER, 'model': STANDIN_MODEL},
            'mode': 'deterministic-stand-ins', 'standinRevision': STANDIN_REVISION},
        'cases': count, 'distinctCases': len({_fingerprint(case) for case in suite.drifts}),
        'criticalCases': sum(bool(case.critical) for case in suite.drifts),
        'criticalMisses': sum(critical_miss(row) for row in results),
        'unchangedCases': sum(case.unchanged for case in suite.drifts), 'routedCases': len(routed),
        'jevUnresolvedOnRouted': sum(row['jev']['judgement'] == 'insufficient_evidence' for row in routed if 'jev' in row),
        'reviewerUnresolvedOnRouted': sum(row.get('review', {}).get('judgement') == 'insufficient_evidence' for row in routed),
        'jevCriticalMissesOnRouted': sum(bool(row['critical']) and row.get('jev', {}).get('judgement') == 'still_supported' for row in routed),
        'reviewerCriticalMissesOnRouted': sum(bool(row['critical']) and row.get('review', {}).get('judgement') == 'still_supported' for row in routed),
        'jevErrorsOnRouted': sum(row.get('jev', {}).get('judgement') != row['expect'] for row in routed),
        'reviewerErrorsOnRouted': sum(row.get('review', {}).get('judgement') != row['expect'] for row in routed),
        'errorRate': sum(not row['correct'] for row in results) / count if count else None,
        'falsePositiveRate': sum(row['actual'] == 'needs_review' for row in supported) / len(supported) if supported else None,
        'elapsedMs': max(0.0, (dependencies.monotonic() - started) * 1000),
        'usage': None, 'cost': None, 'qualified': False,
        'qualificationFailures': ['Non-live deterministic stand-ins do not qualify a provider profile.']
            + (['Stopped or unprocessed cases make this evaluation inconclusive.'] if stopped else []),
        'incomplete': stopped, 'interrupted': interrupted, 'batches': batches, 'results': results}
