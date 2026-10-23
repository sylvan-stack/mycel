"""Explicit finite classification; no timers, resident work, or hidden calls.

One connection owns the repository lock until every adapter ends. Short store
boundaries are serialized; HTTP and child process work runs outside that mutex
and outside pass locks/transactions. Every adapter still owns its cleanup.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, nullcontext
from contextvars import copy_context
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time

from ._classification_payload import ReviewCommandIdentity, ReviewerRequest
from ._classification_store import ClassificationPreparation, ClassificationStore
from ._credentials import Credentials
from ._deadline import DeadlineConnection, deadline_guard, deadline_suspended
from ._drift_store import _time, _uuid
from ._errors import MycelError
from ._evidence import EvidenceError, canonical_json
from ._freshness import Deadline
from ._jev import JevClient, JevFailure, JevLimits, JevOutcome, JevRequest
from ._locks import (ALLOCATOR_LOCK, LockNamespace, _session_guard, operation_guard,
                     read_snapshot, structure_guard)
from ._reviewer import ReviewerClient, ReviewerFailure, ReviewerLimits
from ._safeguards import InvocationPolicy, _defer_cleanup_signals
from ._staleness import _eligible
from ._store import checked_store


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _jev(settings, policy, *, credentials=None):
    return JevClient(credentials or Credentials(settings, policy), policy, limits=JevLimits.from_settings(settings))


def _reviewer(settings, policy, command):
    return ReviewerClient(policy, command, home=settings._home,
                          limits=ReviewerLimits.from_settings(settings))


@dataclass(frozen=True)
class ClassifyDependencies:
    """Internal scripted seams. Injected adapters obey deadline/cancellation."""
    monotonic: object = field(default=time.monotonic, repr=False)
    utc_now: object = field(default=_utc_now, repr=False)
    wait: object = field(default=lambda event, seconds: event.wait(seconds), repr=False)
    cancelled: object = field(default=lambda: False, repr=False)
    jev_factory: object = field(default=_jev, repr=False)
    reviewer_factory: object = field(default=_reviewer, repr=False)

    def __post_init__(self):
        if any(not callable(getattr(self, name)) for name in self.__dataclass_fields__):
            raise MycelError('invalid_input', 'Classification dependencies must be callable.')


class _PreviewStore(ClassificationStore):
    """Canonical preparation in a native READ ONLY snapshot, retaining nothing.

    Existing pass/removal identities are read, never allocated. The allocator
    guard keeps missing-key repositories absent while complete known-owner
    guards protect indexed rows. Missing guards on a registered owner refuse
    inspection rather than being repaired or silently skipped.
    """
    @contextmanager
    def _guarded(self, settings):
        settings.require_valid(require_store=False)
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            stack.enter_context(structure_guard(self.connection))
            stack.enter_context(_session_guard(self.connection, ALLOCATOR_LOCK, shared=False,
                message='Another invocation is allocating a store lock identity.'))
            protected, missing = [], []
            for repository in _eligible(settings):
                complete = True
                for namespace, shared in ((LockNamespace.MUTATION, True), (LockNamespace.PASS, False)):
                    row = self.connection.execute('SELECT key FROM public.mycel_lock_keys '
                        'WHERE namespace=%s AND identity=%s', (namespace.value, repository)).fetchone()
                    if row is None:
                        complete = False
                        continue
                    stack.enter_context(_session_guard(self.connection, row[0], shared=shared,
                        message='Another repository operation prevents classification inspection.'))
                (protected if complete else missing).append(repository)
            with read_snapshot(self.connection):
                settings.require_current()
                if missing and self.connection.execute('SELECT repository FROM public.mycel_repository_state '
                        'WHERE repository=ANY(%s) ORDER BY repository', (missing,)).fetchall():
                    raise MycelError('store_format', 'An indexed repository lacks its classification inspection guards.')
                # All repository-owned rows reference repository_state. The
                # allocator prevents a missing guard from being created while
                # this snapshot safely observes an unregistered empty owner.
                self._protected_repositories = tuple(protected)
                try:
                    yield
                    settings.require_current()
                finally:
                    self._protected_repositories = None

    def _assemble(self, settings, row, reason_id, *, at, capture_at=None, previous=None):
        protected = getattr(self, '_protected_repositories', None)
        if protected is None:
            raise MycelError('invalid_input', 'Classification inspection requires its guarded read-only snapshot.')
        return super()._assemble(settings, row, reason_id, at=at, capture_at=capture_at,
            previous=previous, _guarded_repositories=protected)

    def _row(self, drift_id):
        row = self.connection.execute('SELECT id,repository,dependant_version,opened_at,closed_at,state,evidence_owner '
            'FROM public.mycel_drifts WHERE id=%s', (drift_id,)).fetchone()
        if row is None:
            raise EvidenceError('version_removed')
        self.drifts._validate(row)
        return row

    def prepare(self, settings, drift_id, reason_id, *, at=None):
        drift_id, reason_id, at = _uuid(drift_id), _uuid(reason_id), _time(at)
        with self._guarded(settings):
            row = self._row(drift_id)
            try:
                previous = row[5].get('classificationObservations', {})
                prepared, _, _ = self._assemble(settings, row, reason_id, at=at, previous=previous)
                prior = row[5].get('classificationRequests', {}).get(prepared.input_hash)
                if (prior is not None and prior.get('source') == reason_id
                        and prior.get('pairHash') == prepared.pair_hash
                        and canonical_json(prior.get('guards')) == prepared.guards_bytes):
                    prepared, _, _ = self._assemble(settings, row, reason_id, at=at,
                        capture_at=prior['recordedAt'], previous=previous)
                return prepared
            except EvidenceError as error:
                source = next((item for item in row[5]['sources'] if item['id'] == reason_id), None)
                return ClassificationPreparation(str(drift_id), str(reason_id), row[1],
                    '' if source is None else source['pairHash'], at, None, None,
                    b'{}', b'{}', 'error', None, error.status)


def preview_classification(store, settings, drift_id, reason_id, *, at=None):
    """Inspect complete current bytes and eligibility with zero store writes."""
    if isinstance(store, ClassificationStore):
        return _PreviewStore(store.connection).prepare(settings, drift_id, reason_id, at=at)
    return store.preview(settings, drift_id, reason_id, at=at)


def _candidate_key(candidate):
    prepared, drift, source = candidate
    # Unknown change times sort last. With the same known time, pristine
    # unclassified work precedes retry work, then stable semantic identities.
    retry = bool(source['classification'].get('evidence') or
                 source['classification']['status'] in {'error', 'needs_llm_review'})
    return (prepared.eligible_at or '9999', retry, drift['chunkId'],
            prepared.input_hash or source['pairHash'], source['id'])


def _empty(repository, dry_run):
    return {'repository': repository, 'selected': 0, 'selectedWorkItems': 0,
            'workItems': 0, 'pairCandidates': 0, 'completed': 0, 'reused': 0,
            'needsReview': 0, 'pendingDebounce': 0, 'pendingJev': 0,
            'needsLlmReview': 0, 'unresolved': 0, 'errors': 0, 'obsolete': 0,
            'jevCalls': 0, 'reviewCalls': 0, 'incomplete': False,
            'dryRun': dry_run, 'status': 0, 'pairs': []}


def _classification(prepared):
    value = {'status': prepared.status, 'inputHash': prepared.input_hash,
             'eligibleAt': prepared.eligible_at}
    if prepared.fault:
        value['reason'] = prepared.fault
    return value


def _counts(reply):
    for name in ('completed', 'reused', 'needsReview', 'pendingDebounce', 'pendingJev',
                 'needsLlmReview', 'unresolved', 'errors', 'obsolete'):
        reply[name] = 0
    failed = False
    for pair in reply['pairs']:
        record = pair['classification']
        status = record['status']
        if record.get('obsolete'):
            reply['obsolete'] += 1
            reply['unresolved'] += 1
        elif status == 'complete':
            reply['completed'] += 1
            reply['reused'] += int(record.get('reused', False))
            reply['needsReview'] += int(record.get('judgement') == 'needs_review')
            reply['unresolved'] += int(record.get('judgement') == 'insufficient_evidence')
        elif status == 'pending_debounce':
            reply['pendingDebounce'] += 1
        elif status == 'pending_jev':
            reply['pendingJev'] += 1
            reply['unresolved'] += int(record.get('failed', False))
        elif status == 'needs_llm_review':
            reply['needsLlmReview'] += 1
            reply['unresolved'] += 1
        else:
            reply['errors'] += 1
            reply['unresolved'] += 1
        failed |= record.get('failed', False)
    reply['status'] = int(failed or reply['incomplete'])
    return reply


def _bytes(prepared, options):
    if prepared.decision is None:
        return {'jev': None, 'review': None, 'reviewTimeoutMs': None}
    timeout_ms = max(1, math.floor(min(options['review_timeout_seconds'], options['seconds']) * 1000))
    review = (None if prepared.decision.payload['models']['review'] is None else
              len(ReviewerRequest(prepared.decision, timeout_ms).transmitted_bytes))
    return {'jev': len(JevRequest(prepared.decision).body), 'review': review,
            'reviewTimeoutMs': timeout_ms if review is not None else None}


def _readiness(prepared, options):
    if prepared.decision is None:
        return 'evidence_unavailable'
    if not options.get('review_command'):
        return 'reviewer_unconfigured'
    command = json.loads(prepared.guards_bytes).get('command')
    return ('configured_unverified' if command and command.get('executableSha256') is not None
            else 'review_command_unavailable')


def _dry_plan(reply, selected, options):
    jev, review = 0, 0
    for pair, (prepared, _, _) in zip(reply['pairs'], selected, strict=True):
        sizes = _bytes(prepared, options)
        readiness = _readiness(prepared, options)
        pair['bytes'], pair['reviewerReadiness'] = sizes, readiness
        pair['eligible'] = prepared.status == 'pending_jev'
        pair['stageReadiness'] = ('complete_reusable' if pair.get('cacheReusable') else
            'evidence_unavailable' if prepared.decision is None else
            'pending_debounce' if not pair['eligible'] else
            'review_required' if sizes['jev'] > options['max_input_bytes'] else 'jev_ready')
        max_jev = max_review = 0
        if pair['eligible'] and not pair.get('cacheReusable'):
            max_jev = options['attempts'] if sizes['jev'] <= options['max_input_bytes'] else 0
            max_review = (options['attempts'] if readiness == 'configured_unverified'
                          and sizes['review'] <= options['review_max_input_bytes'] else 0)
        pair['maxCalls'] = {'jev': max_jev, 'review': max_review}
        jev += max_jev
        review += max_review
    reply['maxCalls'] = {'jev': jev, 'review': review}
    reply['estimates'] = {'tokens': None, 'cost': None,
                          'reason': 'Token and cost figures require model-owned counts; byte counts are exact.'}
    return _counts(reply)


class _BoundaryFailure(Exception):
    def __init__(self, reason):
        self.reason = reason


class _Runner:
    def __init__(self, store, settings, reply, dependencies, deadline, activity=None, policy=None):
        self.store, self.settings, self.reply = store, settings, reply
        self.dependencies, self.deadline, self.activity = dependencies, deadline, activity
        self.options = settings.values['drifts']
        self.mutex = threading.RLock()
        self.stopped = threading.Event()
        self.policy = policy or InvocationPolicy('classify')

    def cancelled(self):
        return self.stopped.is_set() or self.dependencies.cancelled() or self.deadline.cancelled()

    def ensure(self):
        if self.cancelled():
            raise _BoundaryFailure('cancelled' if self.stopped.is_set() or self.dependencies.cancelled() else 'deadline')

    def guard(self, prepared, stage):
        self.ensure()
        with self.mutex:
            self.ensure()
            checked = self.store.check(self.settings, prepared, stage=stage, at=self.dependencies.utc_now())
        self.ensure()
        if not checked['allowed']:
            raise _BoundaryFailure(checked['reason'])

    @contextmanager
    def leased(self, prepared, stage):
        context = self.store.stage(self.settings, prepared, stage=stage, at=self.dependencies.utc_now())
        with self.mutex:
            self.ensure()
            checked = context.__enter__()
        try:
            if not checked['allowed']:
                raise _BoundaryFailure(checked['reason'])
            yield
        finally:
            # Deadline stops paid work; releasing an already-owned evidence
            # lease is cleanup and must still run after that deadline.
            with self.mutex, deadline_suspended():
                context.__exit__(None, None, None)

    def attempt(self, prepared, stage, client, attempts):
        maximum = self.options['attempts']
        for attempt in range(maximum):
            self.ensure()
            started = self.dependencies.monotonic()
            with self.leased(prepared, stage):
                try:
                    def on_call():
                        with self.mutex:
                            self.ensure()
                            self.reply['jevCalls' if stage == 'jev' else 'reviewCalls'] += 1
                    result = client.classify(prepared.decision, deadline=self.deadline.expires_at,
                        before_call=lambda: self.guard(prepared, stage), cancelled=self.cancelled,
                        on_call=on_call)
                    self.ensure()
                    attempts.append({'stage': stage, 'attempt': attempt + 1, 'status': 'complete',
                        'seconds': max(0.0, self.dependencies.monotonic() - started)})
                    return result
                except (JevFailure, ReviewerFailure) as failure:
                    attempts.append({'stage': stage, 'attempt': attempt + 1, 'status': 'error',
                        'seconds': max(0.0, self.dependencies.monotonic() - started),
                        'failure': failure.as_dict()})
                    if failure.code == 'cancelled':
                        raise _BoundaryFailure('cancelled') from None
                    if not failure.retryable or attempt + 1 >= maximum:
                        raise
                    retry_failure = failure
            # The ended attempt's lease is gone before any retry delay. Each
            # retry obtains a new guard/lease; delays never restart debounce.
            delay = max(2 ** attempt, retry_failure.retry_after_seconds or 0)
            if delay >= min(self.deadline.remaining(), self.options[
                    'jev_timeout_seconds' if stage == 'jev' else 'review_timeout_seconds']):
                raise retry_failure
            until = self.dependencies.monotonic() + delay
            while self.dependencies.monotonic() < until:
                self.ensure()
                self.dependencies.wait(self.stopped, min(0.05, until - self.dependencies.monotonic()))

    def publish(self, prepared, record, *, complete=False):
        self.ensure()
        with self.mutex:
            self.ensure()
            if complete:
                result = self.store.apply(self.settings, prepared, judgement=record['judgement'],
                    evidence=record.get('evidence', {}), at=self.dependencies.utc_now(),
                    **({'_audit': self.audit(prepared, record)} if self.activity is not None else {}))
            else:
                result = self.store.drifts.record_classification(self.settings, prepared.drift_id,
                    prepared.reason_id, prepared.pair_hash, status=record['status'],
                    evidence={**record.get('evidence', {}), **({'reason': record['reason']} if 'reason' in record else {})},
                    canonical_input_hash=prepared.input_hash, at=self.dependencies.utc_now(),
                    _canonical_guard=lambda: self.store.check_in_transaction(self.settings, prepared,
                        stage='application', at=self.dependencies.utc_now())['allowed'],
                    **({'_audit': self.audit(prepared, record)} if self.activity is not None else {}))
            if result['obsolete']:
                record['obsolete'], record['failed'] = True, True
            return record

    def audit(self, prepared, record):
        def attach(result):
            from ._activity import AppliedMutation, ClassificationReference
            from ._source_refs import parse_source_address
            dependant = prepared.decision.payload['dependant']['snapshot']['place']['address']
            references = ((ClassificationReference('snapshot:' + prepared.bundle.evidence_hash,
                parse_source_address(dependant), 'obsolete' if result['obsolete'] else
                    record.get('judgement', record['status'])),)
                if result['applied'] or result['obsolete'] else ())
            current = {**record, **({'obsolete': True, 'failed': True} if result['obsolete'] else {})}
            counts = {**self.reply, 'pairs': [
                {**pair, 'classification': current} if pair['reason'] == prepared.reason_id else pair
                for pair in self.reply['pairs']]}
            self.activity.record_in_transaction(prepared.repository, 'classify',
                AppliedMutation(changed=bool(references), counts=_counts(counts), classifications=references))
        return attach

    def pair(self, selected, pair):
        prepared, _, source = selected
        evidence = {'attempts': []}
        try:
            self.ensure()
            with self.mutex:
                prepared = self.store.prepare(self.settings, prepared.drift_id, prepared.reason_id,
                                              at=self.dependencies.utc_now())
                pair['classification'] = _classification(prepared)
                if prepared.status != 'pending_jev':
                    if prepared.status == 'error':
                        pair['classification']['failed'] = True
                    return
                cached = self.store.reuse(self.settings, prepared, at=self.dependencies.utc_now())
                if cached is not None:
                    current = source['classification']
                    already_applied = (current.get('status') == 'complete'
                        and current.get('inputHash') == prepared.input_hash
                        and current.get('judgement') == cached.get('judgement'))
                    pair['classification'] = ({**cached, 'reused': True} if already_applied else
                        self.publish(prepared, {**cached, 'reused': True}, complete=True))
                    return
            if _bytes(prepared, self.options)['jev'] > self.options['max_input_bytes']:
                outcome = JevOutcome(prepared.decision, None, 'needs_llm_review', 'jev_input_too_large')
            else:
                outcome = self.attempt(prepared, 'jev', self.dependencies.jev_factory(self.settings, self.policy),
                                       evidence['attempts'])
            evidence['jev'] = outcome.as_dict()
            if outcome.status == 'complete':
                pair['classification'] = self.publish(prepared, {'status': 'complete',
                    'inputHash': prepared.input_hash, 'judgement': outcome.judgement, 'evidence': evidence}, complete=True)
                return
            pair['classification'] = self.publish(prepared, {'status': 'needs_llm_review',
                'inputHash': prepared.input_hash, 'reason': outcome.reason, 'evidence': evidence})
            readiness = _readiness(prepared, self.options)
            if readiness != 'configured_unverified':
                pair['classification']['reason'] = readiness
                if readiness == 'review_command_unavailable':
                    pair['classification']['failed'] = True
                return
            if _bytes(prepared, self.options)['review'] > self.options['review_max_input_bytes']:
                raise ReviewerFailure('review_input_too_large')
            command = ReviewCommandIdentity.inspect(self.options['review_command'],
                self.options['review_revision'], self.settings._home or Path.home())
            result = self.attempt(prepared, 'review',
                self.dependencies.reviewer_factory(self.settings, self.policy, command), evidence['attempts'])
            evidence['review'] = result.as_dict()
            pair['classification'] = self.publish(prepared, {'status': 'complete',
                'inputHash': prepared.input_hash, 'judgement': result.judgement, 'evidence': evidence}, complete=True)
        except (JevFailure, ReviewerFailure) as failure:
            record = {'status': 'error', 'inputHash': prepared.input_hash,
                      'reason': failure.code, 'evidence': {**evidence, 'failure': failure.as_dict()}, 'failed': True}
            try:
                pair['classification'] = self.publish(prepared, record)
            except (MycelError, _BoundaryFailure):
                pair['classification'] = record
        except _BoundaryFailure as failure:
            pair['classification'] = {**pair['classification'], 'reason': failure.reason, 'failed': True}
            if failure.reason in {'obsolete', 'changed_since_ingest'}:
                pair['classification']['obsolete'] = True
            if failure.reason in {'deadline', 'cancelled'}:
                with self.mutex:
                    self.reply['incomplete'] = True
        except MycelError as error:
            pair['classification'] = {**pair['classification'], 'failed': True, 'reason': error.code.value}
            if self.deadline.cancelled():
                with self.mutex:
                    self.reply['incomplete'] = True
        except EvidenceError as error:
            pair['classification'] = {**pair['classification'], 'failed': True, 'reason': error.status,
                **({'obsolete': True} if error.status == 'obsolete' else {})}
        except KeyboardInterrupt:
            self.stopped.set()
            with self.mutex:
                self.reply['incomplete'], self.reply['stopped'] = True, 'interrupted'
                pair['classification'] = {**pair['classification'], 'failed': True, 'reason': 'cancelled'}
        except Exception:
            # An unexpected adapter/guard failure ends the finite operation.
            # Its arbitrary exception text is neither printed nor retained.
            self.stopped.set()
            with self.mutex:
                self.reply['incomplete'] = True
                pair['classification'] = {**pair['classification'], 'failed': True, 'reason': 'internal'}


def run_classification(store, settings, repository, *, k=None, dry_run=False,
                       dependencies=None, activity=None, deadline=None, policy=None):
    """Run one finite repository selection and always retain its partial reply."""
    settings.require_valid(require_store=False)
    if (type(dry_run) is not bool or k is not None and (type(k) is not int or k < 1)
            or policy is not None and not isinstance(policy, InvocationPolicy)):
        raise MycelError('invalid_input', 'Classification requires a positive candidate cap and explicit dry-run flag.')
    dependencies = dependencies or ClassifyDependencies()
    options = settings.values['drifts']
    cap = options['candidates'] if k is None else k
    reply = _empty(repository, dry_run)
    deadline = deadline or Deadline.after(options['seconds'], clock=dependencies.monotonic)
    if isinstance(store, ClassificationStore):
        store = ClassificationStore(DeadlineConnection(store.connection))
    lock = (nullcontext() if dry_run else operation_guard(store.connection, repository, 'classify')
            if hasattr(store, 'connection') else store.session(repository))
    try:
        with deadline_guard(deadline), (nullcontext() if dry_run else lock):
            from ._staleness import inactive_policy_links
            inactive = (inactive_policy_links(store.connection, settings)
                        if isinstance(store, ClassificationStore) else frozenset())
            if not dry_run:
                store.drifts.reconcile(settings, repository, at=dependencies.utc_now())
                if isinstance(store, ClassificationStore):
                    # Support for an old semantic policy cannot hide a newly
                    # selected model/routing/command identity. Reopen only the
                    # exact inactive reasons invalidated by current inputs.
                    for drift in store.drifts.list(repository, closed=True)['drifts']:
                        for source in drift['sources']:
                            if source['dependency'] in inactive:
                                continue
                            if (not source['active'] and
                                    source.get('closed', {}).get('because') == 'still_supported'):
                                store.prepare(settings, drift['id'], source['id'],
                                    at=dependencies.utc_now(), reconcile=True)
            drifts = (store.drifts.list(repository, closed=dry_run) if isinstance(store, ClassificationStore)
                      else store.drifts.list(repository))['drifts']
            candidates, seen = [], set()
            for drift in drifts:
                if not drift['current'] or drift['state'] != 'open' and not dry_run:
                    continue
                before_count = len(candidates)
                for source in drift['sources']:
                    if source['dependency'] in inactive:
                        continue
                    inspect_closed_support = (dry_run and not source['active'] and
                        source.get('closed', {}).get('because') == 'still_supported')
                    if not source['active'] and not inspect_closed_support:
                        continue
                    key = (drift['version'], source['dependency'],
                           source['classification'].get('inputHash') or source['pairHash'])
                    if key in seen:
                        continue
                    prepared = preview_classification(store, settings, drift['id'], source['id'], at=dependencies.utc_now())
                    if (inspect_closed_support and prepared.decision is not None
                            and prepared.input_hash == source['classification'].get('inputHash')):
                        continue
                    seen.add(key)
                    candidates.append((prepared, drift, source))
                reply['workItems'] += int(len(candidates) > before_count)
            reply['pairCandidates'] = len(candidates)
            candidates.sort(key=_candidate_key)
            selected = candidates[:cap]
            reply['selected'] = len(selected)
            reply['selectedWorkItems'] = len({drift['id'] for _, drift, _ in selected})
            reply['pairs'] = [{'drift': drift['id'], 'reason': source['id'],
                'dependant': drift['chunk'], 'source': source['source'],
                'classification': _classification(prepared),
                **({'wouldReopen': True} if not source['active'] else {})}
                for prepared, drift, source in selected]
            if dry_run:
                if isinstance(store, ClassificationStore):
                    preview = _PreviewStore(store.connection)
                    for pair, (prepared, _, _) in zip(reply['pairs'], selected, strict=True):
                        if prepared.decision is not None and prepared.status == 'pending_jev':
                            cached = preview.reuse(settings, prepared, at=dependencies.utc_now())
                            if cached is not None:
                                pair['classification'] = {**cached, 'reused': True}
                                pair['cacheReusable'] = True
                return _dry_plan(reply, selected, options)
            runner = _Runner(store, settings, reply, dependencies, deadline, activity, policy)
            # At most at_once tasks are submitted at a time; an executor queue
            # must never become a delayed-work system after expiry/SIGINT.
            with ThreadPoolExecutor(max_workers=options['at_once'], thread_name_prefix='mycel-classify') as executor:
                pending, offset = {}, 0
                try:
                    while pending or offset < len(selected):
                        if runner.cancelled():
                            runner.stopped.set()
                            reply['incomplete'] |= any(prepared.status == 'pending_jev'
                                for prepared, _, _ in selected[offset:]) or bool(pending)
                        while not runner.cancelled() and offset < len(selected) and len(pending) < options['at_once']:
                            context = copy_context()
                            future = executor.submit(context.run, runner.pair, selected[offset], reply['pairs'][offset])
                            pending[future] = offset
                            offset += 1
                        done = [future for future in pending if future.done()]
                        for future in done:
                            future.result()
                            del pending[future]
                        if not pending and (runner.cancelled() or offset == len(selected)):
                            break
                        dependencies.wait(threading.Event() if runner.stopped.is_set() else runner.stopped, 0.01)
                except KeyboardInterrupt:
                    runner.stopped.set()
                    reply['incomplete'], reply['stopped'] = True, 'interrupted'
                finally:
                    with _defer_cleanup_signals():
                        if runner.cancelled():
                            runner.stopped.set()
                        # Adapter cancellation owns socket/process cleanup.
                        # Drain every future even if one carries SIGINT; a
                        # repeated caller interrupt cannot detach live work.
                        for future in pending:
                            try:
                                future.result()
                            except KeyboardInterrupt:
                                runner.stopped.set()
                                reply['incomplete'], reply['stopped'] = True, 'interrupted'
                        executor.shutdown(wait=True, cancel_futures=True)
            return _counts(reply)
    except (MycelError, KeyboardInterrupt) as error:
        reply['error'] = ({'code': 'refused', 'message': 'Classification was stopped by the caller.'}
                          if isinstance(error, KeyboardInterrupt) else error.to_dict()['error'])
        reply['incomplete'] = bool(reply['selected']) or deadline.cancelled()
        if isinstance(error, KeyboardInterrupt):
            reply['stopped'] = 'interrupted'
        _counts(reply)
        reply['status'] = 1
        return reply
