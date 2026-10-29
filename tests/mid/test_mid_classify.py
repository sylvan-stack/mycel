"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_classify as _support
from test_classify import (AT ,ClassificationStore ,JevFailure ,MycelError ,json ,load_settings ,operation_guard ,os ,outcome ,patch ,preview_classification ,removal_guard ,run_classification ,signal ,threading ,time)


class FiniteClassifyStoreTests(_support.FiniteClassifyStoreTests):
# TEST-TIER-BEGIN tests/test_classify.py::FiniteClassifyStoreTests.test_deterministic_caps_concurrency_live_leases_and_no_pass_locks_during_calls
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
# TEST-TIER-END tests/test_classify.py::FiniteClassifyStoreTests.test_deterministic_caps_concurrency_live_leases_and_no_pass_locks_during_calls


# TEST-TIER-BEGIN tests/test_classify.py::FiniteClassifyStoreTests.test_deadline_and_sigint_join_attempts_and_preserve_committed_prefix_and_inactive_exclusion
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
# TEST-TIER-END tests/test_classify.py::FiniteClassifyStoreTests.test_deadline_and_sigint_join_attempts_and_preserve_committed_prefix_and_inactive_exclusion


# TEST-TIER-BEGIN tests/test_classify.py::FiniteClassifyStoreTests.test_dry_run_empty_enabled_repository_preserves_rows_sequences_and_all_known_guards
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
# TEST-TIER-END tests/test_classify.py::FiniteClassifyStoreTests.test_dry_run_empty_enabled_repository_preserves_rows_sequences_and_all_known_guards
