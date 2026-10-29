"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_automatic_qualification as _support
from test_automatic_qualification import (Path ,automatic_contract ,os ,patch ,run_group ,signal ,subprocess ,sys ,tempfile ,time)


class AutomaticQualificationTests(_support.AutomaticQualificationTests):


# TEST-TIER-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group
    def test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'child.pid'
            code = ('import os,signal,subprocess,sys,time;'
                'signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                'p=subprocess.Popen([sys.executable,"-I","-B","-c",'
                '"import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"]);'
                'open(sys.argv[1],"w").write(str(p.pid));time.sleep(60)')
            with self.assertRaises(subprocess.TimeoutExpired):
                run_group([sys.executable, '-I', '-B', '-c', code, str(marker)], timeout=1)
            self.assertTrue(marker.is_file())
            child = int(marker.read_text())
            until = time.monotonic() + 2
            while time.monotonic() < until:
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail('a fixture descendant survived the bounded timeout cleanup')
            actual = subprocess.Popen
            created = []
            def start(*args, **options):
                process = actual(*args, **options)
                created.append(process.pid)
                communicate = process.communicate
                first = True
                repeated = False
                def interrupted(*values, **keywords):
                    nonlocal first, repeated
                    if first:
                        first = False
                        raise KeyboardInterrupt
                    if not repeated:
                        repeated = True
                        os.kill(os.getpid(), signal.SIGINT)
                    return communicate(*values, **keywords)
                process.communicate = interrupted
                return process
            handler = signal.getsignal(signal.SIGINT)
            try:
                with patch('mycel_build._process.subprocess.Popen', side_effect=start), self.assertRaises(KeyboardInterrupt):
                    run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
                self.assertEqual(signal.getsignal(signal.SIGINT), handler)
                self.assertEqual(len(created), 1)
                with self.assertRaises(ProcessLookupError):
                    os.kill(created[0], 0)
            finally:
                for identifier in created:
                    try:
                        os.killpg(identifier, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
# TEST-TIER-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group

# TEST-TIER-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped
    def test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped(self):
        actual = subprocess.Popen
        created = []
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
        def spawn(*args, **options):
            process = actual(*args, **options)
            created.append(process.pid)
            # This is the old donor's uncovered successful-spawn/assignment gap.
            # The caught signal must not escape until the real handle is owned.
            os.kill(os.getpid(), signal.SIGTERM)
            return process
        try:
            with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), \
                    self.assertRaises(KeyboardInterrupt) as error:
                run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
            self.assertEqual(error.exception.signum, signal.SIGTERM)
            state = error.exception.process_state
            self.assertTrue(state['spawnAttempted'])
            self.assertTrue(state['spawnConfirmed'])
            self.assertFalse(state['spawnOutcomeUnconfirmed'])
            self.assertEqual(state['pid'], created[0])
            self.assertTrue(state['processReaped'])
            self.assertTrue(state['processGroupAbsent'])
            with self.assertRaises(ProcessLookupError):
                os.kill(created[0], 0)
            self.assertEqual({number: signal.getsignal(number) for number in before}, before)
        finally:
            for identifier in created:
                try:
                    os.killpg(identifier, signal.SIGKILL)
                except ProcessLookupError:
                    pass
# TEST-TIER-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped

# TEST-TIER-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup
    def test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup(self):
        class Deadline(KeyboardInterrupt):
            pass
        actual = subprocess.Popen
        created, observed = [], []
        def deadline(number, frame):
            observed.append(number)
            raise Deadline()
        def spawn(*args, **options):
            process = actual(*args, **options)
            created.append(process.pid)
            os.kill(os.getpid(), signal.SIGALRM)
            return process
        previous = signal.signal(signal.SIGALRM, deadline)
        try:
            with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), self.assertRaises(Deadline) as error:
                run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
            self.assertEqual(observed, [signal.SIGALRM])
            self.assertTrue(error.exception.process_state['processReaped'])
            self.assertTrue(error.exception.process_state['processGroupAbsent'])
            self.assertIs(signal.getsignal(signal.SIGALRM), deadline)
            with self.assertRaises(ProcessLookupError):
                os.kill(created[0], 0)
        finally:
            signal.signal(signal.SIGALRM, previous)
            for identifier in created:
                try:
                    os.killpg(identifier, signal.SIGKILL)
                except ProcessLookupError:
                    pass
# TEST-TIER-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup


# TEST-TIER-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_diamond_kind_order_matches_real_unittest_discovery
    def test_frozen_diamond_kind_order_matches_real_unittest_discovery(self):
        from mycel._coverage import discover_checks, iter_checks, run_checks
        source = b'\n'.join((
            b'import unittest',
            b'class Root(unittest.TestCase):', b' check_kind = "unit"',
            b' def test_shared(self): self.assertTrue(True)',
            b'class Left(Root): pass', b'class Right(Root):', b' check_kind = "eval"',
            b'class Diamond(Left, Right): pass', b''))
        contract = automatic_contract({'tests/test_c3_fixture.py': source})
        expected = {row['name']: row['kind'] for row in contract['declarations']}
        try:
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / 'test_c3_fixture.py').write_bytes(source)
                actual = {check.id(): getattr(check, 'check_kind', 'unit')
                          for check in iter_checks(discover_checks(directory))}
                # C3 puts Right before Root, so Diamond is eval and never automatic.
                self.assertEqual(actual['test_c3_fixture.Diamond.test_shared'], 'eval')
                self.assertEqual(expected, {name: kind for name, kind in actual.items() if kind in {'unit', 'store'}})
                report = run_checks(discover_checks(directory))
                self.assertTrue(report.passed)
                self.assertEqual(sorted(check.name for check in report.checks), sorted(expected))
        finally:
            sys.modules.pop('test_c3_fixture', None)
# TEST-TIER-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_diamond_kind_order_matches_real_unittest_discovery
