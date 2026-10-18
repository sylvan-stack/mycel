"""Finite classifier proofs with scripted services and disposable real stores."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import json
import os
import re
import signal
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity
from mycel._classify import classify_arguments
from mycel._classification_payload import ReviewerRequest
from mycel._classification_runner import (ClassifyDependencies, preview_classification,
                                           run_classification)
from mycel._classification_store import ClassificationPreparation, ClassificationStore
from mycel._coverage import proves
from mycel._drift_store import DriftStore
from mycel._errors import MycelError
from mycel._jev import JevFailure, JevOutcome, JevRequest, route_response, validate_response
from mycel._locks import operation_guard, removal_guard
from mycel._reviewer import ReviewerFailure, ReviewerSuccess
from mycel._settings import load_settings

try:
    from . import test_classification_store as fixture_module
    from .test_classification_payload import fixture, reviewed
    from .test_jev import http, response
except ImportError:
    import test_classification_store as fixture_module
    from test_classification_payload import fixture, reviewed
    from test_jev import http, response


AT = fixture_module.AT
NOW = fixture_module.NOW


def outcome(decision, label='needs_review'):
    return route_response(decision, validate_response(http(response(label=label,
        model=decision.payload['models']['jev']['model'])),
                          model=decision.payload['models']['jev']['model']))


class _ScriptedJev:
    def __init__(self, callback):
        self.callback = callback

    def classify(self, decision, *, deadline, before_call, cancelled, on_call):
        before_call()
        if cancelled():
            raise JevFailure('cancelled')
        on_call()
        return self.callback(decision, deadline, cancelled)


class _ScriptedReviewer:
    def __init__(self, callback):
        self.callback = callback

    def classify(self, decision, *, deadline, before_call, cancelled, on_call):
        before_call()
        if cancelled():
            raise ReviewerFailure('cancelled')
        on_call()
        return self.callback(decision, deadline, cancelled)


class _DryStore:
    """Native boundaries are separately checked below; forbid every write seam."""
    def __init__(self, preparation):
        self.preparation = preparation
        self.drifts = self
        self.previews = []

    def list(self, repository):
        source = {'id': 'reason-1', 'dependency': 'edge-1', 'pairHash': 'a' * 64,
                  'active': True, 'source': {'address': 'owner:@code/source.py#governor'},
                  'classification': {'status': 'pending_jev'}}
        return {'drifts': [{'id': 'drift-1', 'chunkId': 'dependant-1', 'version': 'v1',
                           'current': True, 'state': 'open', 'chunk': {'address': 'owner:@code/claim.py#claim'},
                           'sources': [source]}]}

    def preview(self, settings, drift_id, reason_id, *, at):
        self.previews.append((drift_id, reason_id, at))
        return self.preparation

    def prepare(self, *args, **kwargs):
        raise AssertionError('Dry-run must not retain evidence or update work.')

    def session(self, *args, **kwargs):
        raise AssertionError('Dry-run must not allocate a classifier invocation.')


class ClassifyDryRunTests(unittest.TestCase):
    @proves('MYC-14.21')
    def test_exact_bytes_readiness_and_maximum_calls_without_any_execution_or_mutation(self):
        decision = reviewed(fixture()[2])
        preparation = ClassificationPreparation('drift-1', 'reason-1', 'owner', 'a' * 64,
            AT, decision, None, json.dumps({'command': {'executableSha256': 'b' * 64}}).encode(),
            b'{}', 'pending_jev', AT)
        store = _DryStore(preparation)
        options = {'candidates': 100, 'at_once': 2, 'seconds': 300,
                   'jev_timeout_seconds': 10, 'review_timeout_seconds': 120,
                   'attempts': 2, 'max_input_bytes': 24000, 'review_max_input_bytes': 1048576,
                   'review_command': ['/fictional/adapter']}
        settings = SimpleNamespace(values={'drifts': options}, require_valid=lambda **kwargs: None)
        forbidden = lambda *a: self.fail('A dry-run instantiated a provider/credential/command boundary.')
        dependencies = ClassifyDependencies(utc_now=lambda: AT, jev_factory=forbidden,
                                             reviewer_factory=forbidden)
        with patch('mycel._classification_runner.Credentials', side_effect=forbidden), \
                patch('mycel._classification_runner.ReviewCommandIdentity.inspect', side_effect=forbidden):
            reply = run_classification(store, settings, 'owner', dry_run=True, dependencies=dependencies)
        pair = reply['pairs'][0]
        self.assertEqual(reply['maxCalls'], {'jev': 2, 'review': 2})
        self.assertEqual(pair['reviewerReadiness'], 'configured_unverified')
        self.assertEqual(pair['bytes']['jev'], len(JevRequest(decision).body))
        self.assertEqual(pair['bytes']['review'], len(ReviewerRequest(decision, 120000).transmitted_bytes))
        self.assertEqual((reply['workItems'], reply['pairCandidates'], reply['selected']), (1, 1, 1))
        self.assertEqual((reply['jevCalls'], reply['reviewCalls'], reply['status']), (0, 0, 0))
        self.assertEqual(len(store.previews), 1)
        options['max_input_bytes'] = 1
        options['review_max_input_bytes'] = 1
        oversized = run_classification(store, settings, 'owner', dry_run=True, dependencies=dependencies)
        self.assertEqual(oversized['maxCalls'], {'jev': 0, 'review': 0})
        store.preparation = replace(preparation, status='pending_debounce')
        pending = run_classification(store, settings, 'owner', dry_run=True, dependencies=dependencies)
        self.assertEqual(pending['maxCalls'], {'jev': 0, 'review': 0})
        self.assertEqual(pending['pendingDebounce'], 1)

    @proves('MYC-14.21', 'MYC-0.10')
    def test_public_argument_validation_preserves_explicit_positive_cap_and_dry_run(self):
        self.assertEqual(classify_arguments(('--k', '2', '--dry-run')), (2, True))
        self.assertEqual(classify_arguments(()), (None, False))
        for arguments in (('--k',), ('--k', '0'), ('--k', '-1'), ('--k', '1.5'),
                          ('--dry-run', '--dry-run'), ('--live',), ('--k', '2', '--k', '3')):
            with self.subTest(arguments=arguments), self.assertRaises(MycelError):
                classify_arguments(arguments)


class FiniteClassifyStoreTests(fixture_module.ClassificationStoreFixture):
    def setup_three(self, connection):
        (self.fixture.fixture.downstream / 'keep.md').write_bytes(b'# Keep\nIndependent surviving document.\n')
        self.fixture.prepare(connection)
        self.fixture.change(connection)
        self.old_files()
        return self.fixture.one(connection)

    def options(self, **values):
        source = self.base.config.read_text()
        if '[drifts]' not in source:
            source += '\n[drifts]\n'
        prefix, tail = source.rsplit('[drifts]', 1)
        for name, value in values.items():
            line = name + '=' + json.dumps(value)
            if re.search('(?m)^' + name + '=', tail):
                tail = re.sub('(?m)^' + name + '=.*$', line, tail)
            else:
                tail += line + '\n'
        self.base.config.write_text(prefix + '[drifts]' + tail)
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)

    def dependencies(self, callback, **kwargs):
        return ClassifyDependencies(utc_now=lambda: AT,
            jev_factory=lambda *args: _ScriptedJev(callback), **kwargs)

    @proves('MYC-14.8', 'MYC-14.18', 'MYC-13.18', kind='store')
    def test_deterministic_caps_concurrency_live_leases_and_no_pass_locks_during_calls(self):
        with self.base.connect() as connection:
            initial = self.setup_three(connection)
            ordering = []
            for source in initial['sources']:
                prepared = preview_classification(ClassificationStore(connection), self.base.settings,
                    initial['id'], source['id'], at=AT)
                ordering.append((prepared.eligible_at, initial['chunkId'], prepared.input_hash, source['id']))
            expected = [item[3] for item in sorted(ordering)[:2]]
            barrier = threading.Barrier(2)
            calls, active, maximum = [], [0], [0]
            mutex = threading.Lock()

            def classify(decision, deadline, cancelled):
                with mutex:
                    active[0] += 1
                    maximum[0] = max(maximum[0], active[0])
                    calls.append(decision.payload['current']['place']['address'])
                barrier.wait(timeout=10)
                with mutex, self.base.connect() as observer:
                    leases = observer.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                        "WHERE repository='downstream' AND kind='classification_lease'").fetchone()[0]
                    self.assertEqual(leases, 2)
                    with operation_guard(observer, 'downstream', 'pass'):
                        self.assertFalse(cancelled())
                    with self.assertRaises(MycelError) as busy:
                        with removal_guard(observer, 'downstream'):
                            self.fail('A live classifier did not protect repository removal.')
                    self.assertEqual(busy.exception.code, 'busy')
                barrier.wait(timeout=10)
                with mutex:
                    active[0] -= 1
                return outcome(decision)

            reply = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                k=2, dependencies=self.dependencies(classify))
            self.assertEqual((reply['selected'], reply['completed'], reply['needsReview'], reply['status']), (2, 2, 2, 0), reply)
            self.assertEqual((reply['workItems'], reply['pairCandidates'], reply['selectedWorkItems']), (1, 3, 1))
            self.assertEqual(maximum[0], 2)
            self.assertEqual(reply['jevCalls'], 2)
            self.assertEqual([pair['reason'] for pair in reply['pairs']], expected)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                "WHERE kind='classification_lease'").fetchone()[0], 0)
            # Completed exact results consume no new call opportunity.
            again = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                k=3, dependencies=self.dependencies(lambda decision, *a: outcome(decision)))
            self.assertEqual((again['completed'], again['reused'], again['jevCalls']), (3, 2, 1), again)
            stable = self.fixture.one(connection)
            final = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                k=3, dependencies=self.dependencies(lambda *a: self.fail('Completed cache called a provider.')))
            self.assertEqual((final['completed'], final['reused'], final['jevCalls']), (3, 3, 0), final)
            self.assertEqual(self.fixture.one(connection), stable)
            dry = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dry_run=True, dependencies=self.dependencies(lambda *a: self.fail('Dry cache called a provider.')))
            self.assertEqual((dry['completed'], dry['maxCalls']), (3, {'jev': 0, 'review': 0}), dry)

    @proves('MYC-14.8', 'MYC-14.18', 'MYC-13.18', kind='store')
    def test_read_only_dry_run_preserves_all_rows_then_nonblocking_busy_refuses_execution(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            before = self.fixture.state(connection)
            dependencies = self.dependencies(lambda *a: self.fail('Dry-run or busy called a provider.'))
            dry = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                                     dry_run=True, dependencies=dependencies)
            self.assertEqual((dry['selected'], dry['status'], dry['maxCalls']), (1, 0, {'jev': 2, 'review': 0}), dry)
            self.assertEqual(dry['pairs'][0]['bytes']['jev'], len(JevRequest(prepared.decision).body))
            self.assertEqual(self.fixture.state(connection), before)
            with self.base.connect() as blocker, operation_guard(blocker, 'downstream', 'classify'):
                before = self.fixture.state(connection)
                blocked = run_classification(ClassificationStore(connection), self.base.settings,
                                             'downstream', dependencies=dependencies)
                self.assertEqual((blocked['status'], blocked['error']['code'], blocked['jevCalls']), (1, 'busy', 0), blocked)
                self.assertEqual(self.fixture.state(connection), before)

    @proves('MYC-6.3', 'MYC-14.8', 'MYC-14.18', kind='store')
    def test_public_dry_run_reaches_the_store_as_every_command_and_reads_only_its_password(self):
        from io import StringIO
        from mycel._classify import handle_classify
        from mycel._cli import run
        from mycel._credentials import Credentials
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            before = self.fixture.state(connection)
            # The configured check server decides whether the store item is needed.
            expected = ['store'] if connection.pgconn.used_password else []
        purposes, keychain = [], Credentials._keychain
        def recorded(credentials, purpose, **limits):
            purposes.append(purpose)
            return keychain(credentials, purpose, **limits)
        def forbidden(*args, **kwargs):
            raise AssertionError('A dry-run took a model credential, launched an adapter or called a provider.')
        dependencies = self.dependencies(forbidden, reviewer_factory=forbidden)
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                patch.object(Credentials, '_keychain', recorded), \
                patch.object(Credentials, 'jev_key', forbidden), patch.object(Credentials, 'embedding_key', forbidden), \
                patch('mycel._jev._https_request', forbidden), patch('mycel._reviewer.run_resolved_reviewer', forbidden):
            status = run(['classify', '--repo', 'downstream', '--dry-run'], stdout=stdout, stderr=stderr,
                         handlers={'classify': lambda invocation: handle_classify(invocation, dependencies)})
        reply = json.loads(stdout.getvalue())
        self.assertEqual((status, stderr.getvalue()), (0, ''), reply)
        (entry,) = reply['repositories']
        result = entry['result']
        self.assertEqual((result['dryRun'], result['selected'], result['status']), (True, 1, 0), result)
        self.assertEqual(result['maxCalls'], {'jev': 2, 'review': 0})
        self.assertEqual(result['pairs'][0]['bytes']['jev'], len(JevRequest(prepared.decision).body))
        self.assertEqual(purposes, expected)
        with self.base.connect() as connection:
            self.assertEqual(self.fixture.state(connection), before)

    @proves('MYC-13.18', 'MYC-14.18', 'MYC-14.25', kind='store')
    def test_unconfigured_reviewer_keeps_low_confidence_and_insufficient_work_open_without_repinning(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.assertFalse(self.base.settings.values['drifts'].get('review_command'))
            immutable = self.fixture.immutable(connection)
            stale = {tuple(row[:3]) for row in self.fixture.stale(connection)}
            for insufficient in (False, True):
                def classify(decision, deadline, cancelled):
                    value = response(label='insufficient_evidence' if insufficient else 'needs_review',
                        model=decision.payload['models']['jev']['model'])
                    if not insufficient:
                        answer = value['answers']['dependency']
                        answer['probabilities'] = {'needs_review': 0.6, 'insufficient_evidence': 0.2,
                                                   'still_supported': 0.2}
                        answer['confidence'] = 0.4
                    return route_response(decision, validate_response(http(value),
                        model=decision.payload['models']['jev']['model']))
                reply = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                    dependencies=self.dependencies(classify,
                        reviewer_factory=lambda *a: self.fail('An unconfigured reviewer must never instantiate.')))
                self.assertEqual((reply['jevCalls'], reply['reviewCalls'], reply['needsLlmReview'],
                    reply['completed']), (1, 0, 1, 0), reply)
                result = reply['pairs'][0]['classification']
                self.assertEqual(result['reason'], 'reviewer_unconfigured')
                self.assertEqual(result['evidence']['jev']['reason'],
                    'insufficient_evidence' if insufficient else 'jev_low_confidence')
                current = self.fixture.one(connection)
                self.assertEqual(current['state'], 'open')
                self.assertTrue(self.fixture.reason(current)['active'])
                self.assertEqual(self.fixture.immutable(connection), immutable)
                self.assertEqual({tuple(row[:3]) for row in self.fixture.stale(connection)}, stale)

    @proves('MYC-14.8', 'MYC-14.18', 'MYC-13.18', kind='store')
    def test_transient_retries_honor_retry_after_and_terminal_failures_have_exact_stage_caps(self):
        self.write_reviewer()
        with self.base.connect() as connection:
            self.prepare(connection)
            current, waits, attempts = [0.0], [], []
            def wait(event, seconds):
                if threading.current_thread() is threading.main_thread():
                    event.wait(0.001)
                    return
                current[0] += seconds
                waits.append(seconds)
            def transient(decision, deadline, cancelled):
                attempts.append(current[0])
                if len(attempts) == 1:
                    raise JevFailure('rate_limited', retry_after_seconds=1.5)
                return outcome(decision)
            reply = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(transient, monotonic=lambda: current[0], wait=wait))
            self.assertEqual((reply['completed'], reply['jevCalls'], reply['status']), (1, 2, 0), reply)
            self.assertGreaterEqual(attempts[1] - attempts[0], 1.5)
            # Different model policy invalidates the old completed identity.
            self.options(model='jev-1.14.0')
            terminal_calls = []
            def terminal(decision, deadline, cancelled):
                terminal_calls.append(decision.input_hash)
                raise JevFailure('authentication')
            failed = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(terminal))
            self.assertEqual((failed['errors'], failed['jevCalls'], failed['status']), (1, 1, 1), failed)
            self.assertEqual(len(terminal_calls), 1)
            self.assertEqual(self.fixture.reason(self.fixture.one(connection))['classification']['status'], 'error')
            self.options(model='jev-1.15.0')
            current[0] = 0
            reviews = []
            def review(decision, deadline, cancelled):
                reviews.append(current[0])
                if len(reviews) == 1:
                    raise ReviewerFailure('unavailable', retry_after_seconds=0.25)
                return ReviewerSuccess(ReviewerRequest(decision, 120000), 'needs_review',
                    'Complete fixture reviewed independently.', (decision.evidence_locators[0],))
            routed = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(lambda decision, *a: outcome(decision, 'insufficient_evidence'),
                    monotonic=lambda: current[0], wait=wait,
                    reviewer_factory=lambda *a: _ScriptedReviewer(review)))
            self.assertEqual((routed['completed'], routed['jevCalls'], routed['reviewCalls'], routed['status']), (1, 1, 2, 0), routed)
            self.assertGreaterEqual(reviews[1] - reviews[0], 1)
            self.assertEqual([attempt['stage'] for attempt in routed['pairs'][0]['classification']['evidence']['attempts']],
                             ['jev', 'review', 'review'])

    @proves('MYC-14.8', 'MYC-14.18', kind='store')
    def test_deadline_and_sigint_join_attempts_and_preserve_committed_prefix_and_inactive_exclusion(self):
        self.options(at_once=1, seconds=30)
        with self.base.connect() as connection:
            self.setup_three(connection)
            current, calls = [0.0], []
            def classify(decision, deadline, cancelled):
                calls.append(decision.input_hash)
                if len(calls) == 2:
                    current[0] = 31
                    self.assertTrue(cancelled())
                    raise JevFailure('cancelled')
                return outcome(decision)
            reply = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(classify, monotonic=lambda: current[0]))
            self.assertEqual((reply['selected'], reply['completed'], reply['jevCalls'], reply['status']), (3, 1, 2, 1), reply)
            self.assertTrue(reply['incomplete'])
            self.assertFalse(any(thread.name.startswith('mycel-classify') for thread in threading.enumerate()))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                "WHERE kind='classification_lease'").fetchone()[0], 0)
            # Interrupt on the next eligible input; earlier guarded cache stays.
            def interrupt(*args):
                raise KeyboardInterrupt()
            stopped = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(interrupt))
            self.assertEqual(stopped['stopped'], 'interrupted', stopped)
            self.assertTrue(stopped['incomplete'])
            self.assertGreaterEqual(sum(source['classification']['status'] == 'complete'
                for source in self.fixture.one(connection)['sources']), 1)
            self.assertFalse(any(thread.name.startswith('mycel-classify') for thread in threading.enumerate()))
            senders = []
            def repeated_interrupt(decision, deadline, cancelled):
                def send():
                    time.sleep(0.02)
                    os.kill(os.getpid(), signal.SIGINT)
                    time.sleep(0.03)
                    os.kill(os.getpid(), signal.SIGINT)
                sender = threading.Thread(target=send, name='fixture-repeat-sigint')
                senders.append(sender)
                sender.start()
                while not cancelled():
                    time.sleep(0.002)
                # Model cleanup is still live when the repeated signal arrives.
                time.sleep(0.1)
                sender.join()
                raise JevFailure('cancelled')
            previous = signal.signal(signal.SIGINT, signal.default_int_handler)
            try:
                repeated = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                    dependencies=self.dependencies(repeated_interrupt))
            finally:
                signal.signal(signal.SIGINT, previous)
            self.assertEqual(repeated['stopped'], 'interrupted', repeated)
            self.assertTrue(repeated['incomplete'])
            self.assertTrue(senders)
            self.assertFalse(any(sender.is_alive() for sender in senders))
            self.assertFalse(any(thread.name.startswith('mycel-classify') for thread in threading.enumerate()))
            self.fixture.fixture.answer.unlink()
            self.fixture.fixture.publish(connection, 'downstream', collect=False)
            inactive = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                dependencies=self.dependencies(lambda *a: self.fail('Off-disk work called a provider.')))
            self.assertEqual((inactive['selected'], inactive['jevCalls']), (0, 0), inactive)

    @proves('MYC-14.8', 'MYC-14.18', kind='store')
    def test_oversize_review_and_changed_support_policy_with_atomic_activity_rollback(self):
        self.write_reviewer()
        with self.base.connect() as connection:
            self.prepare(connection)
            options = self.base.settings.values['drifts']
            revised = self.base.config.read_text() + 'max_input_bytes=1\n'
            self.base.config.write_text(revised)
            self.base.settings = load_settings(path=self.base.config, home=self.base.base)
            reviews = []
            def review(decision, deadline, cancelled):
                reviews.append(decision.input_hash)
                return ReviewerSuccess(ReviewerRequest(decision, 120000), 'still_supported',
                    'The complete fixture still supports this claim.', (decision.evidence_locators[0],))
            dependencies = self.dependencies(lambda *a: self.fail('Oversized Jev input was transmitted.'),
                reviewer_factory=lambda *a: _ScriptedReviewer(review))
            with MutationActivity(connection, build=37).session() as audit:
                reply = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                                             dependencies=dependencies, activity=audit)
                self.assertEqual((reply['completed'], reply['jevCalls'], reply['reviewCalls'], reply['status']), (1, 0, 1, 0), reply)
                audit.finish('done', counts={('downstream', 'classify'): reply})
            self.assertEqual(DriftStore(connection).list('downstream')['drifts'], [])
            row = connection.execute("SELECT outcome,counts FROM public.mycel_activity "
                "WHERE repository='downstream' AND kind='classify'").fetchone()
            self.assertEqual(row, ('done', reply))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_activity_classifications').fetchone()[0], 2)
            self.base.config.write_text(revised + 'confidence_floor=0.8\n')
            self.base.settings = load_settings(path=self.base.config, home=self.base.base)
            before = self.fixture.state(connection)
            projected = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                                           dry_run=True, dependencies=dependencies)
            self.assertEqual(projected['selected'], 1, projected)
            self.assertTrue(projected['pairs'][0]['wouldReopen'])
            self.assertEqual(self.fixture.state(connection), before)
            # Policy-invalid old support reopens before new review; an audit
            # publication failure rolls back support and its detail together.
            import mycel._activity as activity_module
            original = activity_module._execute
            def fail_detail(current, sql, parameters=None):
                if sql.startswith('INSERT INTO public.mycel_activity_classifications'):
                    sql = sql.replace('mycel_activity_classifications', 'mycel_missing_activity')
                return original(current, sql, parameters)
            with MutationActivity(connection, build=38).session() as audit:
                with patch('mycel._activity._execute', side_effect=fail_detail):
                    rejected = run_classification(ClassificationStore(connection), self.base.settings, 'downstream',
                        dependencies=dependencies, activity=audit)
                self.assertEqual((rejected['selected'], rejected['completed'], rejected['status']), (1, 0, 1), rejected)
                self.assertEqual(len(DriftStore(connection).list('downstream')['drifts']), 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE build=38").fetchone()[0], 0)


    @proves('MYC-14.18', kind='store')
    def test_dry_run_empty_enabled_repository_preserves_rows_sequences_and_all_known_guards(self):
        from contextlib import ExitStack
        from psycopg import sql
        from mycel._classification_runner import _PreviewStore
        from mycel._classify import handle_classify
        from mycel._cli import Invocation
        from mycel._locks import ALLOCATOR_LOCK, LockNamespace, _session_guard, allocate_key

        empty = self.base.base / 'unrelated-empty'
        empty.mkdir()
        original_config = self.base.config.read_text()
        extended_config = original_config + '\n[repos.unrelated_empty]\nenabled=true\nartifact_root=' + json.dumps(str(empty)) + '\n'
        forbidden_calls = []
        def forbidden(*args, **kwargs):
            forbidden_calls.append(True)
            raise AssertionError('Dry-run acquired credentials, launched an executable or called a provider.')
        dependencies = self.dependencies(forbidden, reviewer_factory=forbidden)

        with self.base.connect() as connection, self.base.connect() as observer:
            prepared = self.prepare(connection)
            def inventory():
                sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
                    "WHERE schemaname='public' ORDER BY sequencename").fetchall()
                return self.fixture.state(connection), [(name, connection.execute(
                    sql.SQL('SELECT last_value,is_called FROM public.{}').format(sql.Identifier(name))).fetchone())
                    for (name,) in sequences]
            def dry_run():
                invocation = Invocation('classify', repositories=('downstream',),
                    arguments=('--dry-run',), settings=self.base.settings)
                return handle_classify(invocation, dependencies, _store=(connection, None))
            def repository_reply(result):
                return result.value['repositories'][0]['result']
            with ExitStack() as mocks:
                for target in ('mycel._credentials.Credentials', 'mycel._classification_runner.Credentials',
                               'mycel._jev._https_request', 'mycel._reviewer.run_resolved_reviewer'):
                    mocks.enter_context(patch(target, side_effect=forbidden))
                before = inventory()
                control = dry_run()
                self.assertEqual(control.status, 0, control.value)
                expected = repository_reply(control)
                self.assertEqual((expected['selected'], expected['maxCalls']), (1, {'jev': 2, 'review': 0}))
                self.assertEqual(inventory(), before)

                self.base.config.write_text(extended_config)
                self.base.settings = load_settings(path=self.base.config, home=self.base.base)
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_repository_state "
                    "WHERE repository='unrelated_empty'").fetchone(), (0,))
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_lock_keys "
                    "WHERE identity='unrelated_empty'").fetchone(), (0,))
                assemble = _PreviewStore._assemble
                observed_scopes = []
                def inspect(preview, *args, **kwargs):
                    observed_scopes.append(preview._protected_repositories)
                    self.assertEqual(preview._protected_repositories, ('downstream', 'fixture'))
                    # The excluded empty owner cannot acquire its missing
                    # operation identity while this read snapshot is live.
                    with self.assertRaises(MycelError) as blocked:
                        with operation_guard(observer, 'unrelated_empty', 'pass'):
                            self.fail('An unguarded owner appeared during the preview.')
                    self.assertEqual(blocked.exception.code, 'busy')
                    return assemble(preview, *args, **kwargs)
                before = inventory()
                with patch.object(_PreviewStore, '_assemble', inspect):
                    added = dry_run()
                self.assertEqual(added.status, 0, added.value)
                actual = repository_reply(added)
                self.assertEqual((actual['selected'], actual['maxCalls']), (expected['selected'], expected['maxCalls']))
                self.assertEqual(actual['pairs'][0]['classification']['inputHash'], prepared.input_hash)
                self.assertEqual(actual['pairs'][0]['bytes'], expected['pairs'][0]['bytes'])
                self.assertGreaterEqual(len(observed_scopes), 2)
                self.assertEqual(inventory(), before)

                for guard in (operation_guard(observer, 'downstream', 'pass'),
                              removal_guard(observer, 'downstream'),
                              _session_guard(observer, ALLOCATOR_LOCK, shared=False, message='Fixture allocator busy.')):
                    with guard:
                        before = inventory()
                        busy = dry_run()
                        self.assertEqual(busy.status, 1, busy.value)
                        self.assertEqual(repository_reply(busy)['error']['code'], 'busy')
                        self.assertEqual(inventory(), before)

                # Retained complete results use the same protected scope in
                # inherited check_in_transaction/reuse, without new history.
                self.base.config.write_text(original_config)
                self.base.settings = load_settings(path=self.base.config, home=self.base.base)
                applied = ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='needs_review', at=AT)
                self.assertTrue(applied['applied'], applied)
                self.base.config.write_text(extended_config)
                self.base.settings = load_settings(path=self.base.config, home=self.base.base)
                before = inventory()
                with patch.object(_PreviewStore, '_assemble', inspect):
                    cached = dry_run()
                self.assertEqual(cached.status, 0, cached.value)
                cached_reply = repository_reply(cached)
                self.assertEqual((cached_reply['completed'], cached_reply['reused'], cached_reply['maxCalls']),
                    (1, 1, {'jev': 0, 'review': 0}), cached_reply)
                self.assertEqual(inventory(), before)

                # A partial identity for an unregistered empty owner remains
                # safe: known keys are locked, while its missing key cannot
                # appear until the fixed allocator guard is released.
                allocate_key(observer, LockNamespace.PASS, 'unrelated_empty')
                before = inventory()
                partial = dry_run()
                self.assertEqual(partial.status, 0, partial.value)
                self.assertEqual(repository_reply(partial)['selected'], 1)
                self.assertEqual(inventory(), before)
                self.assertEqual(connection.execute("SELECT namespace FROM public.mycel_lock_keys "
                    "WHERE identity='unrelated_empty'").fetchall(), [('repository.pass',)])

                # A registered/indexed owner must never be excluded merely
                # because its required lock keys are absent or incomplete.
                observer.execute("INSERT INTO public.mycel_repository_state VALUES ('unrelated_empty',NULL,'[]')")
                before = inventory()
                malformed = dry_run()
                self.assertEqual(malformed.status, 1, malformed.value)
                self.assertEqual(repository_reply(malformed)['error']['code'], 'store_format')
                self.assertEqual(inventory(), before)
                self.assertEqual(forbidden_calls, [])
