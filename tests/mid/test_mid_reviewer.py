"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_reviewer as _support
from test_reviewer import (JevOutcome ,Path ,READ ,SYSTEM_PATH ,WRITE ,context_fixture ,json ,os ,patch ,reviewer ,subprocess ,sys ,time)


class ReviewerExecutionTests(_support.ReviewerExecutionTests):

# TEST-TIER-BEGIN tests/test_reviewer.py::ReviewerExecutionTests.test_inheritable_store_lock_and_credential_descriptors_are_closed
    def test_inheritable_store_lock_and_credential_descriptors_are_closed(self):
        with (self.root / 'credential').open('w+b') as credential, (self.root / 'lock').open('w+b') as lock:
            fds = [credential.fileno(), lock.fileno()]
            for fd in fds:
                os.set_inheritable(fd, True)
            code = READ + f"""closed=[]
for fd in {fds!r}:
 try: os.fstat(fd)
 except OSError: closed.append(fd)
assert closed=={fds!r}
""" + WRITE
            self.call(*self.adapter(code))
            for fd in fds:
                self.assertIsNotNone(os.fstat(fd))
# TEST-TIER-END tests/test_reviewer.py::ReviewerExecutionTests.test_inheritable_store_lock_and_credential_descriptors_are_closed

# TEST-TIER-BEGIN tests/test_reviewer.py::ReviewerExecutionTests.test_large_complete_request_and_concurrent_output_pressure_do_not_deadlock
    def test_large_complete_request_and_concurrent_output_pressure_do_not_deadlock(self):
        captured = self.root / 'request'
        code = """import os,sys
os.write(1,b' '*131072)
os.write(2,b'd'*65536)
""" + READ + f"__import__('pathlib').Path({str(captured)!r}).write_bytes(raw)\n" + WRITE
        client, _ = self.adapter(code)
        decision = context_fixture(client.command, padding=b'# ' + b'x' * 240000 + b'\n')
        outcome = JevOutcome(decision, None, 'needs_llm_review', 'jev_input_too_large')
        handoff = outcome.reviewer_handoff(timeout_ms=5000)
        result = self.call(client, handoff)
        self.assertEqual(captured.read_bytes(), result.request.transmitted_bytes)
        self.assertIn(b'x' * 240000, captured.read_bytes())
        self.assertNotIn(b'jev_input_too_large', captured.read_bytes())
        # Exactly full output caps are accepted, including JSON whitespace;
        # overflow by a single byte is checked separately.
        exact_code = READ + """wire=json.dumps(reply).encode()
os.write(1,b' '*(1048576-len(wire))+wire)
os.write(2,b'd'*65536)
"""
        result = self.call(*self.adapter(exact_code))
        self.assertEqual(result.judgement, 'needs_review')
# TEST-TIER-END tests/test_reviewer.py::ReviewerExecutionTests.test_large_complete_request_and_concurrent_output_pressure_do_not_deadlock


# TEST-TIER-BEGIN tests/test_reviewer.py::ReviewerExecutionTests.test_timeout_and_cancellation_kill_ignoring_descendants_and_reap_child
    def test_timeout_and_cancellation_kill_ignoring_descendants_and_reap_child(self):
        real_spawn = subprocess.Popen
        for cancel in (False, True):
            ready, survived = self.root / f'ready-{cancel}', self.root / f'survived-{cancel}'
            grandchild = f"import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(1.5);pathlib.Path({str(survived)!r}).write_text('survived')"
            code = READ + f"""import pathlib,signal,subprocess
signal.signal(signal.SIGTERM,signal.SIG_IGN)
subprocess.Popen([sys.executable,'-c',{grandchild!r}])
pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))
time.sleep(10)
"""
            client, decision = self.adapter(code, limits=reviewer.ReviewerLimits(.15 if not cancel else 5))
            children = []
            def capture(*args, **kwargs):
                child = real_spawn(*args, **kwargs)
                children.append(child)
                return child
            started = time.monotonic()
            with self.subTest(cancel=cancel), patch('mycel._safeguards.subprocess.Popen', side_effect=capture):
                if cancel:
                    with self.assertRaises(KeyboardInterrupt):
                        self.call(client, decision, cancelled=ready.exists)
                else:
                    with self.assertRaises(reviewer.ReviewerFailure) as raised:
                        self.call(client, decision)
                    self.assertEqual(raised.exception.code, 'timeout')
            self.assertLess(time.monotonic() - started, 2.5)
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode)
            time.sleep(max(0, 1.7 - (time.monotonic() - started)))
            self.assertFalse(survived.exists())
        # Repeat real interrupts during cleanup in a disposable outer process;
        # the owner process never receives these test signals.
        ready = self.root / 'signal-pid'
        survived = self.root / 'signal-survived'
        grandchild = f"import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(1.5);pathlib.Path({str(survived)!r}).write_text('survived')"
        code = READ + f"""import pathlib,signal,subprocess
signal.signal(signal.SIGTERM,signal.SIG_IGN)
subprocess.Popen([sys.executable,'-c',{grandchild!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))
time.sleep(10)
"""
        source = Path(_support.__file__).resolve().parents[1] / 'src'
        tests = Path(_support.__file__).resolve().parent
        driver = f"""import json,os,pathlib,signal,sys,threading,time
sys.path[:0]=[{str(source)!r},{str(tests)!r}]
from mycel import _reviewer as reviewer, _classification_payload as payload
from mycel._safeguards import InvocationPolicy
from test_reviewer import context_fixture
root=pathlib.Path({str(self.root)!r})
ready=pathlib.Path({str(ready)!r})
command=payload.ReviewCommandIdentity.inspect([sys.executable,'-c',{code!r}],'fixture-v1',root)
client=reviewer.ReviewerClient(InvocationPolicy('classify'),command,home=root)
def interrupt():
 while not ready.exists():time.sleep(.005)
 os.kill(os.getpid(),signal.SIGINT)
 time.sleep(.05)
 os.kill(os.getpid(),signal.SIGTERM)
sender=threading.Thread(target=interrupt);sender.start()
interrupted=False
try:client.classify(context_fixture(command),deadline=time.monotonic()+5,before_call=lambda:None)
except KeyboardInterrupt:interrupted=True
sender.join()
pid=int(ready.read_text())
try:os.kill(pid,0);reaped=False
except ProcessLookupError:reaped=True
print(json.dumps({{'interrupted':interrupted,'reaped':reaped}}))
"""
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-c', driver], capture_output=True, timeout=8,
                                env={'HOME': str(self.root), 'PATH': SYSTEM_PATH, 'LC_ALL': 'C'},
                                cwd=self.root, start_new_session=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'interrupted': True, 'reaped': True})
        time.sleep(max(0, 1.7 - (time.monotonic() - started)))
        self.assertFalse(survived.exists())
# TEST-TIER-END tests/test_reviewer.py::ReviewerExecutionTests.test_timeout_and_cancellation_kill_ignoring_descendants_and_reap_child
