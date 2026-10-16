"""Invocation deadlines reach safe child boundaries and leave fallback reads usable."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psycopg import pq

from mycel._coverage import proves
from mycel._deadline import (DeadlineConnection, check_deadline, current_deadline,
    deadline_guard, deadline_seconds, deadline_suspended)
from mycel._freshness import Deadline, DeadlineExceeded
from mycel._safeguards import CompletedChild, run_child, run_git


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Connection:
    def __init__(self, *, in_transaction=False):
        self.info = SimpleNamespace(transaction_status=(pq.TransactionStatus.INTRANS
            if in_transaction else pq.TransactionStatus.IDLE))
        self.closed = False
        self.queries = []

    def execute(self, query, params=None, **kwargs):
        self.queries.append((query, params, kwargs))
        if query == 'SHOW statement_timeout':
            return SimpleNamespace(fetchone=lambda: ('17s',))
        if query == 'fixture failure':
            raise RuntimeError('query failed')
        return SimpleNamespace(fetchall=lambda: [('existing indexed result',)])


class DeadlineBoundaryTests(unittest.TestCase):
    @proves('MYC-4.19', kind='unit')
    def test_one_active_budget_bounds_nested_git_and_child_work_then_restores_current_index_reads(self):
        clock = Clock()
        deadline = Deadline.after(0.5, clock=clock)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch('mycel._safeguards._run_process', return_value=CompletedChild(0, b'', b'', 0)) as run, \
                    patch('mycel._safeguards.shutil.which', return_value='/usr/bin/git'), \
                    deadline_guard(deadline):
                self.assertIs(current_deadline(), deadline)
                run_git(('status', '--short'), cwd=folder, timeout_seconds=10)
                self.assertAlmostEqual(run.call_args.kwargs['timeout_seconds'], 0.5)
                clock.now += 0.4
                run_git(('ls-files', '-z'), cwd=folder, timeout_seconds=10)
                self.assertAlmostEqual(run.call_args.kwargs['timeout_seconds'], 0.1)
                clock.now += 0.1
                with self.assertRaises(DeadlineExceeded):
                    run_git(('status', '--short'), cwd=folder)
                self.assertEqual(run.call_count, 2)
            self.assertIsNone(current_deadline())
            with patch('mycel._safeguards.subprocess.Popen') as spawn:
                with self.assertRaises(DeadlineExceeded), deadline_guard(deadline):
                    run_git(('status', '--short'), cwd=folder)
                spawn.assert_not_called()

        # This is an actual local child whose own ten-second timeout has not
        # elapsed. The active freshness allowance stops and reaps it instead.
        children = []
        launch = subprocess.Popen

        def record_child(*args, **kwargs):
            child = launch(*args, **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with patch('mycel._safeguards.subprocess.Popen', side_effect=record_child):
            with self.assertRaises(DeadlineExceeded), deadline_guard(Deadline.after(0.2)):
                run_child((sys.executable, '-c', 'import time; time.sleep(30)'), timeout_seconds=10)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNone(current_deadline())

        # A caller can now read the index with its regular statement settings.
        # No expired ContextVar survives the failed recursive check.
        raw = Connection()
        indexed = DeadlineConnection(raw).execute('SELECT existing indexed results').fetchall()
        self.assertEqual(indexed, [('existing indexed result',)])
        self.assertEqual(raw.queries, [('SELECT existing indexed results', None, {})])
        self.assertEqual(deadline_seconds(10), 10)

    @proves('MYC-4.19', kind='unit')
    def test_nested_deadline_context_and_cleanup_restore_the_original_allowance(self):
        clock = Clock()
        outer, inner = Deadline.after(0.5, clock=clock), Deadline.after(0.1, clock=clock)
        with deadline_guard(outer):
            with self.assertRaises(RuntimeError), deadline_guard(inner):
                self.assertIs(current_deadline(), inner)
                raise RuntimeError('fixture')
            self.assertIs(current_deadline(), outer)
            clock.now += 0.5
            with self.assertRaises(DeadlineExceeded):
                check_deadline()
            with deadline_suspended():
                self.assertIsNone(current_deadline())
                self.assertEqual(deadline_seconds(10), 10)
            self.assertIs(current_deadline(), outer)
            with self.assertRaises(DeadlineExceeded):
                check_deadline()
        self.assertIsNone(current_deadline())

    @proves('MYC-4.19', kind='unit')
    def test_every_sql_read_uses_remaining_allowance_and_restores_autocommit_settings_on_failure(self):
        clock = Clock()
        raw = Connection()
        bounded = DeadlineConnection(raw)
        deadline = Deadline.after(0.5, clock=clock)
        with deadline_guard(deadline):
            bounded.execute('SELECT existing indexed results')
            first = raw.queries[1]
            self.assertEqual(first[0], "SELECT pg_catalog.set_config('statement_timeout', %s, false)")
            self.assertEqual(first[1], ('500ms',))
            self.assertEqual(raw.queries[-1][1], ('17s',))
            clock.now += 0.4
            with self.assertRaises(RuntimeError):
                bounded.execute('fixture failure')
            self.assertIn(raw.queries[-3][1][0], {'99ms', '100ms'})
            self.assertEqual(raw.queries[-1][1], ('17s',))
            clock.now += 0.1
            before = len(raw.queries)
            with self.assertRaises(DeadlineExceeded):
                bounded.execute('SELECT existing indexed results')
            self.assertEqual(len(raw.queries), before)
        bounded.execute('SELECT existing indexed results')
        self.assertEqual(raw.queries[-1], ('SELECT existing indexed results', None, {}))

        # Timeout setup itself can exhaust the allowance. No product query
        # may start afterward, and an installed session setting must restore.
        for stage in ('SHOW statement_timeout', 'set_config', 'SET LOCAL'):
            with self.subTest(setup_stage=stage):
                clock = Clock()
                raw = Connection(in_transaction=stage == 'SET LOCAL')
                execute = raw.execute

                def slow_setup(query, params=None, **kwargs):
                    reply = execute(query, params, **kwargs)
                    if stage in query:
                        clock.now += 0.2
                    return reply

                raw.execute = slow_setup
                with deadline_guard(Deadline.after(0.1, clock=clock)):
                    with self.assertRaises(DeadlineExceeded):
                        DeadlineConnection(raw).execute('SELECT product work')
                self.assertFalse(any(query == 'SELECT product work' for query, _, _ in raw.queries))
                if stage == 'set_config':
                    self.assertEqual(raw.queries[-1][1], ('17s',))

        clock = Clock()
        raw = Connection()
        execute = raw.execute

        def slow_show(query, params=None, **kwargs):
            reply = execute(query, params, **kwargs)
            if query == 'SHOW statement_timeout':
                clock.now += 0.4
            return reply

        raw.execute = slow_show
        with deadline_guard(Deadline.after(0.5, clock=clock)):
            DeadlineConnection(raw).execute('SELECT remaining work')
        self.assertIn(raw.queries[1][1][0], {'99ms', '100ms'})

    @proves('MYC-4.19', kind='unit')
    def test_transaction_timeout_does_not_take_a_snapshot_before_read_only_is_selected(self):
        raw = Connection(in_transaction=True)
        with deadline_guard(Deadline.after(0.5, clock=Clock())):
            DeadlineConnection(raw).execute('SET TRANSACTION READ ONLY ISOLATION LEVEL REPEATABLE READ')
        self.assertEqual(raw.queries, [
            ("SET LOCAL statement_timeout = '500ms'", None, {}),
            ('SET TRANSACTION READ ONLY ISOLATION LEVEL REPEATABLE READ', None, {}),
        ])


if __name__ == '__main__':
    unittest.main()
