"""Independent local protocol adapters; no provider or credential access."""

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mycel import _classification_payload as payload
from mycel import _evidence as evidence
from mycel import _reviewer as reviewer
from mycel._classification_runner import ClassifyDependencies, _Runner
from mycel._errors import MycelError
from mycel._jev import JevOutcome
from mycel._safeguards import CompletedChild, InvocationPolicy, SYSTEM_PATH
from mycel._source_refs import SourceAddress


IDENTITY = ('protocol', 'inputHash', 'provider', 'model', 'adapterRevision', 'commandHash')
READ = """import json,os,sys,time
raw=sys.stdin.buffer.read()
request=json.loads(raw)
reply={key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
reply.update(judgement='needs_review',rationale='The changed permission contradicts the claim.',
             evidence=[request['payload']['current']['locator']])
"""
WRITE = "sys.stdout.write(json.dumps(reply));sys.stdout.flush()\n"


def context_fixture(command, *, padding=b'', absent=None):
    """Construct complete pinned/current governor and exact ancestor evidence."""
    dependant = SourceAddress('owner', 'code', 'guide.py', 'claim')
    dep_raw = b'readers_may_delete = True\n'
    dep = evidence.snapshot(dep_raw, comparison=evidence.exact_comparison(dep_raw, 'code_text'), place=dependant,
                            file_source=dep_raw, span=(0, len(dep_raw)))

    def pair(source, old, new):
        before = evidence.snapshot(old, comparison=evidence.exact_comparison(old, 'code_text'), place=source,
                                   file_source=old, span=(0, len(old)))
        now = evidence.snapshot(new, comparison=evidence.exact_comparison(new, 'code_text'), place=source,
                                file_source=new, span=(0, len(new)))
        baseline = evidence.BaselineManifest({'schema': 1, 'ownerRepository': 'owner',
            'dependantId': '00000000-0000-0000-0000-000000000002', 'dependantVersion': '7',
            'dependant': dep.evidence.as_dict(), 'kind': 'declared', 'ref': source.address,
            'source': evidence._place(source), 'selection': 'chunk',
            'members': [{'place': evidence._place(source), 'evidence': before.evidence.as_dict()}],
            'pinnedHash': before.evidence.comparison.hash,
            'selectionComparison': before.evidence.comparison.as_dict(),
            'capturedAt': '2026-10-09T00:00:00Z', 'location': {'kind': 'disk'}})
        before_text, now_text = (payload.DecisionText.create(item.evidence, item.source) for item in (before, now))
        return baseline, before_text, payload.CurrentSelection.create('present', source, 'chunk', (now_text,))

    source = SourceAddress('source', 'code', 'access.py', 'permission')
    baseline, before, current = pair(source, b'return "reader"\n', b'return "admin"\n' + padding)
    governor, governor_before, governor_current = pair(SourceAddress('source', 'code', 'limits.py', 'limits'),
                                                     b'backup_limit = 7\n', b'backup_limit = 2\n')
    ancestor_raw = b'# Backup policy\n\nBackups must remain available.\n'
    ancestor = evidence.snapshot(ancestor_raw, comparison=evidence.exact_comparison(ancestor_raw, 'code_text'),
                                place=SourceAddress('owner', 'code', 'guide.py', 'policy'),
                                file_source=ancestor_raw, span=(0, len(ancestor_raw)))
    context = [payload.ancestor_context(payload.DecisionText.create(ancestor.evidence, ancestor_raw)),
               payload.governor_context(governor, (governor_before,), governor_current, 'stale')]
    if absent:
        current = payload.CurrentSelection.create(absent, source, 'chunk')
    return payload.DecisionPayload.create(baseline=baseline, before=(before,), current=current,
        dependant=payload.DecisionText.create(dep.evidence, dep_raw), context=context,
        review=command.model_identity('fixture-provider', 'fixture-model-2026-10-01'))


def success(request, **changes):
    value = {key: request.payload[key] for key in IDENTITY}
    value.update(judgement='still_supported', rationale='  Supplied evidence establishes support.  ',
                 evidence=[request.decision.evidence_locators[0]], usage={'inputTokens': 12, 'outputTokens': 3})
    value.update(changes)
    return value


def failure(request, code='connection', **changes):
    value = {key: request.payload[key] for key in IDENTITY}
    value['error'] = {'code': code, 'message': 'fixture-secret provider error; never persist this'}
    value['error'].update(changes)
    return value


def completed(value, exit=0):
    raw = json.dumps(value).encode() if not isinstance(value, bytes) else value
    return CompletedChild(exit, raw, b'fixture-secret stderr', .125)


class ReviewerProtocolTests(unittest.TestCase):
    def setUp(self):
        command = payload.ReviewCommandIdentity.inspect([sys.executable, '-c', 'pass'], 'fixture-v1', Path.home())
        self.decision = context_fixture(command)
        self.request = payload.ReviewerRequest(self.decision, 1000)

    def test_success_strict_identity_judgement_evidence_and_usage(self):
        for judgement in payload.LABELS:
            reply = reviewer.validate_response(completed(success(self.request, judgement=judgement)), self.request)
            self.assertEqual(reply.judgement, judgement)
            self.assertEqual(reply.rationale, 'Supplied evidence establishes support.')
            self.assertEqual(reply.evidence, (self.decision.evidence_locators[0],))
            self.assertEqual(dict(reply.usage), {'inputTokens': 12, 'outputTokens': 3})
            self.assertNotIn('stderr', reply.as_dict())
            with self.assertRaises(TypeError):
                reply.usage['inputTokens'] = 1
        for change in ({'protocol': True}, {'protocol': '1'}, {'protocol': 1.0},
                       *({key: 'wrong'} for key in IDENTITY[1:]), {'judgement': 'support'},
                       {'rationale': ' \t\n'}, {'rationale': '\ud800'}, {'rationale': False},
                       {'evidence': []}, {'evidence': [self.decision.evidence_locators[0]] * 2},
                       {'evidence': ['https://outside.invalid/evidence']}, {'evidence': [True]},
                       {'usage': None}, {'usage': {'inputTokens': True}}, {'usage': {'outputTokens': -1}},
                       {'usage': {'inputTokens': 1.0}}, {'usage': {'other': 1}}, {'unknown': 0}):
            with self.subTest(change=change), self.assertRaises(reviewer.ReviewerFailure) as raised:
                reviewer.validate_response(completed(success(self.request, **change)), self.request)
            self.assertEqual(raised.exception.code, 'protocol')
            self.assertFalse(raised.exception.retryable)

    def test_failure_codes_delays_exit_and_safe_diagnostics(self):
        codes = ('authentication', 'connection', 'timeout', 'rate_limited', 'unavailable', 'input_too_large',
                 'invalid_request', 'provider_result_invalid', 'unsupported_protocol', 'internal')
        for code in codes:
            for with_delay in (False, True):
                transient = code in {'connection', 'timeout', 'rate_limited', 'unavailable'}
                with self.subTest(code=code, delay=with_delay), self.assertRaises(reviewer.ReviewerFailure) as raised:
                    reviewer.validate_response(completed(failure(self.request, code,
                        **({'retryAfterSeconds': 0.25} if with_delay else {})), 1), self.request)
                error = raised.exception
                self.assertEqual(error.code, code if transient or not with_delay else 'protocol')
                self.assertEqual(error.retryable, transient)
                self.assertNotIn('fixture-secret', str(error))
                self.assertNotIn('fixture-secret', json.dumps(error.as_dict()))
                self.assertEqual(error.as_dict()['exit'], 1)
        for delay in (None, True, -1, float('inf'), float('nan'), '1', 10**1000):
            with self.subTest(delay=delay), self.assertRaises(reviewer.ReviewerFailure) as raised:
                reviewer.validate_response(completed(failure(self.request, retryAfterSeconds=delay), 1), self.request)
            self.assertEqual(raised.exception.code, 'protocol')
        for value, exit in ((success(self.request), 1), (failure(self.request), 0),
                            (failure(self.request), 2), (success(self.request), -signal.SIGTERM)):
            with self.subTest(exit=exit), self.assertRaises(reviewer.ReviewerFailure) as raised:
                reviewer.validate_response(completed(value, exit), self.request)
            self.assertFalse(raised.exception.retryable)
        for update in ({'code': 'invented'}, {'message': ''}, {'message': '\ud800'}, {'unknown': 0}):
            value = failure(self.request)
            value['error'].update(update)
            with self.subTest(update=update), self.assertRaises(reviewer.ReviewerFailure):
                reviewer.validate_response(completed(value, 1), self.request)
        for missing in IDENTITY:
            value = failure(self.request)
            del value[missing]
            with self.subTest(missing=missing), self.assertRaises(reviewer.ReviewerFailure):
                reviewer.validate_response(completed(value, 1), self.request)

    def test_json_rejects_duplicate_keys_bom_nonfinite_trailing_and_unknown_shapes(self):
        raw = json.dumps(success(self.request)).encode()
        accepted = reviewer.validate_response(completed(b' \t\r\n' + raw + b'\r\n '), self.request)
        self.assertEqual(accepted.judgement, 'still_supported')
        malformed = (b'\xef\xbb\xbf' + raw, b'\xff' + raw, b'```json\n' + raw + b'\n```',
            raw + b'{}', raw + b'garbage', b'\x0b' + raw, b'[]', b'null', b'"object"',
            raw.replace(b'"protocol": 1', b'"protocol": 1,"protocol": 1'),
            raw.replace(b'"inputTokens": 12', b'"inputTokens": 12,"inputTokens": 12'),
            raw.replace(b'"inputTokens": 12', b'"inputTokens": NaN'),
            raw.replace(b'"inputTokens": 12', b'"inputTokens": Infinity'), b'[' * 2000 + b']' * 2000)
        for invalid in malformed:
            with self.subTest(raw=invalid[:25]), self.assertRaises(reviewer.ReviewerFailure) as raised:
                reviewer.validate_response(completed(invalid), self.request)
            self.assertEqual(raised.exception.code, 'protocol')
        mixed = success(self.request)
        mixed['error'] = failure(self.request)['error']
        for exit in (0, 1):
            with self.subTest(exit=exit), self.assertRaises(reviewer.ReviewerFailure):
                reviewer.validate_response(completed(mixed, exit), self.request)

    def test_documented_complete_examples_validate_hash_wire_contract_and_replies(self):
        documentation = (Path(__file__).resolve().parents[1] / 'docs/reviewer.md').read_text()
        def block(heading):
            match = re.search(r'### ' + heading + r'\n.*?```json\n(.*?)\n```', documentation, re.S)
            self.assertIsNotNone(match)
            return json.loads(match.group(1))
        documented = block('Request')
        decision = payload.DecisionPayload(documented['payload'])
        request = payload.ReviewerRequest(decision, documented['budget']['timeoutMs'])
        self.assertEqual(json.loads(request.canonical_bytes), documented)
        self.assertEqual(sha256(decision.canonical_bytes).hexdigest(), documented['inputHash'])
        self.assertEqual(decision.payload['criteria'], payload.CRITERIA)
        self.assertEqual(set(item['role'] for item in decision.payload['context']), {'governor', 'ancestor'})
        governor = next(item for item in decision.payload['context'] if item['role'] == 'governor')
        self.assertTrue(governor['baseline']['members'])
        self.assertTrue(governor['before'][0]['text'])
        self.assertTrue(governor['current']['members'][0]['text'])
        self.assertEqual(governor['freshness'], 'stale')
        self.assertEqual(documented['evidenceLocators'], list(decision.evidence_locators))
        self.assertEqual(len(request.transmitted_bytes), 11055)
        self.assertEqual(decision.input_hash, 'e997d8d538baba0fdf63a3e2cb6422d14fb68f4391b7d2ab5c9498984db6bcc9')
        self.assertIn('11055', documentation)
        self.assertEqual(request.transmitted_bytes, request.canonical_bytes + b'\n')
        result = reviewer.validate_response(completed(block('Success')), request)
        self.assertEqual(result.judgement, 'needs_review')
        self.assertTrue(set(result.evidence) <= set(decision.evidence_locators))
        with self.assertRaises(reviewer.ReviewerFailure) as raised:
            reviewer.validate_response(completed(block('Failure'), 1), request)
        self.assertTrue(raised.exception.retryable)


class ReviewerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='reviewer-unit-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def adapter(self, code=READ + WRITE, *, args=(), limits=None):
        command = payload.ReviewCommandIdentity.inspect([sys.executable, '-c', code, *args], 'fixture-v1', self.root)
        client = reviewer.ReviewerClient(InvocationPolicy('classify'), command, home=self.root, limits=limits)
        return client, context_fixture(command)

    def call(self, client, decision, **kwargs):
        return client.classify(decision, deadline=kwargs.pop('deadline', time.monotonic() + 5),
            before_call=kwargs.pop('before_call', lambda: None), **kwargs)

    def test_exact_request_eof_independent_context_and_literal_resolved_argv(self):
        captured = self.root / 'request'
        observed = self.root / 'observed'
        args = ('$HOME/config', '~/prompt', '*.json', '; touch injected', '{inputHash}')
        code = READ + f"""import pathlib
pathlib.Path({str(captured)!r}).write_bytes(raw)
pathlib.Path({str(observed)!r}).write_text(json.dumps({{'argv':sys.argv[1:],'cwd':os.getcwd(),
 'entries':os.listdir('.'),'mode':__import__('stat').S_IMODE(os.stat('.').st_mode),
 'group':os.getpgrp(),'pid':os.getpid(),'tty':[os.isatty(fd) for fd in (0,1,2)],'env':dict(os.environ)}}))
assert raw.endswith(b'\\n') and not raw.endswith(b'\\n\\n')
assert request['budget']['maxProviderCalls']==1
assert request['budget']['maxOutputBytes']==1048576
assert len(request['payload']['context'])==2
assert all(key not in request for key in ('probabilities','confidence','reason','jev'))
""" + WRITE
        client, decision = self.adapter(code, args=args)
        parent_secrets = {'MYCEL_STORE_PASSWORD': 'fixture-secret-store', 'VOYAGE_API_KEY': 'fixture-secret-voyage',
                          'JEV_API_KEY': 'fixture-secret-jev', 'PYTHONPATH': '/untrusted', 'PATH': '/untrusted'}
        real_spawn = subprocess.Popen
        with patch.dict(os.environ, parent_secrets), patch('mycel._safeguards.subprocess.Popen', wraps=real_spawn) as spawn:
            with patch('mycel._credentials.Credentials.require_jev_key', side_effect=AssertionError('no credentials')), \
                    patch('mycel._credentials.Credentials.require_embedding_key', side_effect=AssertionError('no credentials')):
                result = self.call(client, decision)
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(spawn.call_args.args[0], tuple(client.command.payload['argv']))
        self.assertEqual(captured.read_bytes(), result.request.transmitted_bytes)
        data = json.loads(observed.read_text())
        self.assertEqual(data['argv'], list(args))
        self.assertEqual(data['entries'], [])
        self.assertEqual(data['mode'], 0o700)
        self.assertEqual(data['group'], data['pid'])
        self.assertNotEqual(data['group'], os.getpgrp())
        self.assertEqual(data['tty'], [False] * 3)
        expected_environment = {'HOME': str(self.root.resolve()), 'PATH': SYSTEM_PATH,
            'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8', 'TMPDIR': data['cwd']}
        self.assertEqual(spawn.call_args.kwargs['env'], expected_environment)
        # CoreFoundation may add its own encoding marker during Python startup
        # on Darwin. It is absent from the environment supplied to exec.
        child_environment = {key: value for key, value in data['env'].items()
                             if key != '__CF_USER_TEXT_ENCODING'}
        self.assertEqual(child_environment, expected_environment)
        self.assertFalse(Path(data['cwd']).exists())
        self.assertEqual(result.request.decision, decision)
        self.assertEqual(result.request.decision.payload['context'], decision.payload['context'])

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

    def test_full_transmitted_byte_budget_counts_lf_and_never_truncates_or_spawns(self):
        client, decision = self.adapter()
        wire_size = len(payload.ReviewerRequest(decision, 1000).transmitted_bytes)
        limits = reviewer.ReviewerLimits(1, wire_size - 1)
        client.limits = limits
        with patch('mycel._reviewer.time.monotonic', return_value=100), \
                patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision)
        self.assertEqual(raised.exception.code, 'review_input_too_large')
        spawn.assert_not_called()
        client.limits = reviewer.ReviewerLimits(1, wire_size)
        result = self.call(client, decision)
        self.assertLessEqual(len(result.request.transmitted_bytes), wire_size)
        for state in ('deleted', 'away'):
            result = self.call(client, context_fixture(client.command, absent=state))
            self.assertEqual(result.request.decision.payload['current']['state'], state)
            self.assertTrue(result.request.decision.payload['before'][0]['text'])

    def test_dry_run_report_paths_and_unavailable_command_launch_nothing(self):
        client, decision = self.adapter()
        for policy in (InvocationPolicy('classify', dry_run=True), InvocationPolicy('read'),
                       InvocationPolicy('drifts'), InvocationPolicy('evaluate', kind='drift')):
            client.policy = policy
            with self.subTest(policy=policy), patch('mycel._safeguards.subprocess.Popen') as spawn, \
                    self.assertRaises(MycelError):
                self.call(client, decision)
            spawn.assert_not_called()
        command = payload.ReviewCommandIdentity.inspect([str(self.root / 'absent')], 'fixture-v1', self.root)
        client = reviewer.ReviewerClient(InvocationPolicy('classify'), command, home=self.root)
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, context_fixture(command))
        self.assertEqual(raised.exception.code, 'review_command_unavailable')
        spawn.assert_not_called()

    def test_changed_executable_or_frozen_configuration_is_refused_at_fresh_launch_guard(self):
        adapter = self.root / 'adapter'
        adapter.write_text('#!/bin/sh\nexit 1\n')
        adapter.chmod(0o700)
        command = payload.ReviewCommandIdentity.inspect([str(adapter)], 'fixture-v1', self.root)
        client = reviewer.ReviewerClient(InvocationPolicy('classify'), command, home=self.root)
        def edit():
            adapter.write_text('#!/bin/sh\nexit 0\n')
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, context_fixture(command), before_call=edit)
        self.assertEqual(raised.exception.code, 'obsolete')
        spawn.assert_not_called()
        client, decision = self.adapter()
        def obsolete():
            raise reviewer.ReviewerFailure('obsolete')
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure):
            self.call(client, decision, before_call=obsolete)
        spawn.assert_not_called()
        client, decision = self.adapter()
        replacement, _ = self.adapter(READ + "reply['judgement']='still_supported'\n" + WRITE)
        def switch_configuration():
            client.command = replacement.command
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision, before_call=switch_configuration)
        self.assertEqual(raised.exception.code, 'obsolete')
        spawn.assert_not_called()

    def test_under_millisecond_or_exhausted_prelaunch_budget_never_spawns(self):
        for invalid in (0, -1, True, float('inf'), float('nan'), 10**1000):
            with self.subTest(timeout=invalid), self.assertRaises(MycelError):
                reviewer.ReviewerLimits(invalid)
        for invalid in (0, -1, True, 1.5):
            with self.subTest(input_limit=invalid), self.assertRaises(MycelError):
                reviewer.ReviewerLimits(1, invalid)
        client, decision = self.adapter(limits=reviewer.ReviewerLimits(.0009))
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision)
        self.assertEqual(raised.exception.code, 'timeout')
        spawn.assert_not_called()
        client.limits = reviewer.ReviewerLimits(.03)
        with patch('mycel._safeguards.subprocess.Popen') as spawn, self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision, before_call=lambda: time.sleep(.04))
        self.assertEqual(raised.exception.code, 'timeout')
        spawn.assert_not_called()

    def test_valid_object_followed_by_hang_or_wrong_exit_is_never_success(self):
        for tail, expected in (('time.sleep(10)\n', 'timeout'), ('sys.exit(1)\n', 'protocol'),
                               ('sys.exit(2)\n', 'transport'), ('os.kill(os.getpid(),15)\n', 'transport')):
            client, decision = self.adapter(READ + WRITE + tail, limits=reviewer.ReviewerLimits(.12))
            with self.subTest(tail=tail), self.assertRaises(reviewer.ReviewerFailure) as raised:
                self.call(client, decision)
            self.assertEqual(raised.exception.code, expected)

    def test_incomplete_request_cannot_accept_a_premature_valid_reply(self):
        # An adversarial adapter knows the expected reply but closes stdin before
        # the request is transmitted. A large full request keeps writes pending.
        # Preserve the argv-bound identity while arranging the known reply in a
        # separate absolute file: no shell, placeholders or environment channel.
        response_file = self.root / 'response'
        code = f"import os,sys;os.close(0);sys.stdout.buffer.write(open({str(response_file)!r},'rb').read());sys.stdout.flush()"
        client, _ = self.adapter(code)
        decision = context_fixture(client.command, padding=b'x' * 250000)
        response_file.write_text(json.dumps(success(payload.ReviewerRequest(decision, 5000))))
        with self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision)
        self.assertEqual(raised.exception.code, 'input_incomplete')
        self.assertFalse(raised.exception.retryable)

    def test_output_overflow_kills_and_reaps_before_another_attempt(self):
        real_spawn = subprocess.Popen
        for stream, size in ((1, 1048577), (2, 65537)):
            survived = self.root / f'overflow-survived-{stream}'
            grandchild = f"import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(1.5);pathlib.Path({str(survived)!r}).write_text('survived')"
            code = READ + f"""import signal,subprocess
signal.signal(signal.SIGTERM,signal.SIG_IGN)
subprocess.Popen([sys.executable,'-c',{grandchild!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.write({stream},b'fixture-secret'+b'x'*{size});time.sleep(10)
"""
            client, decision = self.adapter(code)
            children = []
            def spawn(*args, **kwargs):
                child = real_spawn(*args, **kwargs)
                children.append(child)
                return child
            started = time.monotonic()
            with self.subTest(stream=stream), patch('mycel._safeguards.subprocess.Popen', side_effect=spawn), \
                    self.assertRaises(reviewer.ReviewerFailure) as raised:
                self.call(client, decision)
            self.assertEqual(raised.exception.code, 'stdout_limit' if stream == 1 else 'stderr_limit')
            self.assertNotIn('fixture-secret', json.dumps(raised.exception.as_dict()))
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode)
            self.assertTrue(all(pipe.closed for pipe in (children[0].stdin, children[0].stdout, children[0].stderr)))
            time.sleep(max(0, 1.7 - (time.monotonic() - started)))
            self.assertFalse(survived.exists())

    def test_typed_transient_failure_is_exposed_once_without_adapter_or_parent_retry(self):
        count = self.root / 'calls'
        code = READ + f"""__import__('pathlib').Path({str(count)!r}).write_text('one')
reply={{key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}}
reply['error']={{'code':'rate_limited','message':'fixture-secret adapter diagnostic','retryAfterSeconds':.125}}
""" + WRITE + 'sys.exit(1)\n'
        client, decision = self.adapter(code)
        with patch('mycel._safeguards.subprocess.Popen', wraps=subprocess.Popen) as spawn, \
                self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision)
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(count.read_text(), 'one')
        self.assertEqual(raised.exception.code, 'rate_limited')
        self.assertEqual(raised.exception.retry_after_seconds, .125)
        self.assertTrue(raised.exception.retryable)
        self.assertNotIn('fixture-secret', json.dumps(raised.exception.as_dict()))

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
        source = Path(__file__).resolve().parents[1] / 'src'
        tests = Path(__file__).resolve().parent
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

    def test_successful_parent_cannot_leave_a_live_descendant_behind(self):
        survived = self.root / 'survived'
        grandchild = f"import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(1.5);pathlib.Path({str(survived)!r}).write_text('survived')"
        code = READ + f"import subprocess;subprocess.Popen([sys.executable,'-c',{grandchild!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n" + WRITE
        client, decision = self.adapter(code)
        started = time.monotonic()
        self.call(client, decision)
        time.sleep(max(0, 1.7 - (time.monotonic() - started)))
        self.assertFalse(survived.exists())

    def test_invocation_deadline_bounds_guard_spawn_drain_validation_and_budget(self):
        client, decision = self.adapter(limits=reviewer.ReviewerLimits(3))
        result = self.call(client, decision, deadline=time.monotonic() + .4)
        self.assertGreater(result.request.timeout_ms, 0)
        self.assertLessEqual(result.request.timeout_ms, 400)
        self.assertEqual(result.request.payload['budget']['maxProviderCalls'], 1)
        # Validation also spends the same attempt budget; completed process
        # output cannot authorize a late result.
        real_validate = reviewer.validate_response
        def slow_validate(*args):
            time.sleep(.1)
            return real_validate(*args)
        with patch('mycel._reviewer.validate_response', side_effect=slow_validate), \
                self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, decision, deadline=time.monotonic() + .08)
        self.assertEqual(raised.exception.code, 'timeout')

    def test_real_typed_adapter_exhaustion_counts_attempts_and_waits_after_reaping(self):
        # Only store lease/guard observations use an in-memory seam. The finite
        # parent, ReviewerClient, process launcher and wire parser are genuine.
        count = self.root / 'retry-count'
        code = READ + f"""import pathlib
counter=pathlib.Path({str(count)!r})
attempt=int(counter.read_text())+1 if counter.exists() else 1
counter.write_text(str(attempt))
reply={{key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}}
reply['error']={{'code':'rate_limited','message':'fictional transient','retryAfterSeconds':1.25}}
sys.stdout.write(json.dumps(reply));sys.stdout.flush();sys.exit(1)
"""
        client, decision = self.adapter(code)
        clock, waits, children = [0.0], [], []
        lease = {'active': 0, 'entered': 0, 'closed': 0, 'guards': 0}
        real_spawn = subprocess.Popen

        @contextmanager
        def stage(*_args, **_kwargs):
            lease['active'] += 1
            lease['entered'] += 1
            try:
                yield {'allowed': True}
            finally:
                lease['active'] -= 1
                lease['closed'] += 1

        def guard(*_args, **_kwargs):
            self.assertEqual(lease['active'], 1)
            lease['guards'] += 1
            return {'allowed': True}

        def wait(_event, seconds):
            self.assertEqual(lease['active'], 0)
            self.assertEqual(lease['entered'], lease['closed'])
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[-1].returncode)
            self.assertTrue(all(pipe.closed for pipe in
                                (children[-1].stdin, children[-1].stdout, children[-1].stderr)))
            waits.append(seconds)
            clock[0] += seconds

        def spawn(*args, **kwargs):
            child = real_spawn(*args, **kwargs)
            children.append(child)
            return child

        store = SimpleNamespace(stage=stage, check=guard)
        settings = SimpleNamespace(values={'drifts': {'attempts': 2, 'review_timeout_seconds': 5}})
        expires = time.monotonic() + 5
        deadline = SimpleNamespace(expires_at=expires, remaining=lambda: expires-time.monotonic(),
                                   cancelled=lambda: False)
        dependencies = ClassifyDependencies(monotonic=lambda: clock[0], wait=wait)
        reply = {'reviewCalls': 0}
        runner = _Runner(store, settings, reply, dependencies, deadline)
        attempts = []
        with patch('mycel._safeguards.subprocess.Popen', side_effect=spawn), \
                patch('mycel._classification_runner.Credentials', side_effect=AssertionError('no credentials')), \
                patch('mycel._database._native_connect', side_effect=AssertionError('no database')), \
                self.assertRaises(reviewer.ReviewerFailure) as raised:
            runner.attempt(SimpleNamespace(decision=decision), 'review', client, attempts)
        self.assertEqual(raised.exception.code, 'rate_limited')
        self.assertEqual((count.read_text(), reply['reviewCalls'], len(children)), ('2', 2, 2))
        self.assertEqual([row['attempt'] for row in attempts], [1, 2])
        self.assertEqual([row['status'] for row in attempts], ['error', 'error'])
        self.assertTrue(all(row['failure']['code'] == 'rate_limited' for row in attempts))
        self.assertEqual((lease['active'], lease['entered'], lease['closed'], lease['guards']), (0, 2, 2, 2))
        self.assertAlmostEqual(sum(waits), 1.25)
        self.assertTrue(all(child.returncode is not None for child in children))

    def test_each_failure_path_removes_its_private_cwd_after_child_cleanup(self):
        real_spawn = subprocess.Popen
        tails = {
            'typed': "reply={key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')};reply['error']={'code':'authentication','message':'fixture failure'};sys.stdout.write(json.dumps(reply));sys.exit(1)\n",
            'protocol': "sys.stdout.write('{');sys.stdout.flush()\n",
            'timeout': 'time.sleep(10)\n',
            'overflow': "os.write(1,b'x'*1048577);time.sleep(10)\n",
            'cancelled': 'time.sleep(10)\n',
        }
        for name, tail in tails.items():
            observed = self.root / f'failed-cwd-{name}'
            code = READ + f"__import__('pathlib').Path({str(observed)!r}).write_text(os.getcwd())\n" + tail
            client, decision = self.adapter(code, limits=reviewer.ReviewerLimits(.3 if name == 'timeout' else 5))
            children = []

            def spawn(*args, **kwargs):
                child = real_spawn(*args, **kwargs)
                children.append(child)
                return child

            with self.subTest(failure=name), patch('mycel._safeguards.subprocess.Popen', side_effect=spawn):
                if name == 'cancelled':
                    with self.assertRaises(KeyboardInterrupt):
                        self.call(client, decision, cancelled=observed.exists)
                else:
                    with self.assertRaises(reviewer.ReviewerFailure) as raised:
                        self.call(client, decision)
                    expected = {'typed': 'authentication', 'protocol': 'protocol',
                                'timeout': 'timeout', 'overflow': 'stdout_limit'}[name]
                    self.assertEqual(raised.exception.code, expected)
            self.assertTrue(observed.is_file())
            self.assertFalse(Path(observed.read_text()).exists())
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].returncode)
            self.assertTrue(all(pipe.closed for pipe in
                                (children[0].stdin, children[0].stdout, children[0].stderr)))

    def test_real_executable_malformed_json_and_failure_exit_zero_never_succeed(self):
        variants = {
            'bom': "wire=b'\\xef\\xbb\\xbf'+wire\n",
            'duplicate': "wire=wire.replace(b'\"protocol\": 1',b'\"protocol\": 1,\"protocol\": 1',1)\n",
            'nonfinite': "reply['usage']={'inputTokens':float('nan')};wire=json.dumps(reply).encode()\n",
            'trailing': "wire+=b'{}'\n",
            'identity': "reply['inputHash']='0'*64;wire=json.dumps(reply).encode()\n",
            'failure-exit-zero': "reply={key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')};reply['error']={'code':'connection','message':'fixture failure'};wire=json.dumps(reply).encode()\n",
        }
        for name, change in variants.items():
            code = READ + 'wire=json.dumps(reply).encode()\n' + change + 'sys.stdout.buffer.write(wire);sys.stdout.flush()\n'
            client, decision = self.adapter(code)
            with self.subTest(response=name), \
                    patch('mycel._safeguards.subprocess.Popen', wraps=subprocess.Popen) as spawn, \
                    self.assertRaises(reviewer.ReviewerFailure) as raised:
                self.call(client, decision)
            self.assertEqual(raised.exception.code, 'protocol')
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(spawn.call_count, 1)

    def test_revision_and_executable_changes_independently_refuse_prior_review_inputs(self):
        executable = self.root / 'revision-adapter'
        executable.write_text('#!' + sys.executable + '\n' + READ + WRITE)
        executable.chmod(0o700)
        argv = [str(executable)]
        original = payload.ReviewCommandIdentity.inspect(argv, 'adapter-v1', self.root)
        original_decision = context_fixture(original)
        revised = payload.ReviewCommandIdentity.inspect(argv, 'adapter-v2', self.root)
        self.assertEqual(original.payload['argv'], revised.payload['argv'])
        self.assertEqual(original.payload['executableSha256'], revised.payload['executableSha256'])
        self.assertNotEqual(original.command_hash, revised.command_hash)
        revised_decision = context_fixture(revised)
        self.assertNotEqual(original_decision.input_hash, revised_decision.input_hash)
        client = reviewer.ReviewerClient(InvocationPolicy('classify'), revised, home=self.root)
        # A malformed retained identity with the current command hash still
        # cannot bypass the independent adapter-revision comparison.
        mixed = original_decision.as_dict()
        mixed['models']['review']['commandHash'] = revised.command_hash
        with patch('mycel._safeguards.subprocess.Popen') as spawn:
            for decision in (original_decision, payload.DecisionPayload(mixed)):
                with self.assertRaises(reviewer.ReviewerFailure) as raised:
                    self.call(client, decision)
                self.assertEqual(raised.exception.code, 'obsolete')
            spawn.assert_not_called()
        self.assertEqual(self.call(client, revised_decision).judgement, 'needs_review')
        executable.write_text(executable.read_text() + '# changed executable bytes\n')
        replacement = payload.ReviewCommandIdentity.inspect(argv, 'adapter-v2', self.root)
        self.assertEqual(revised.payload['argv'], replacement.payload['argv'])
        self.assertEqual(revised.payload['adapterRevision'], replacement.payload['adapterRevision'])
        self.assertNotEqual(revised.payload['executableSha256'], replacement.payload['executableSha256'])
        replacement_decision = context_fixture(replacement)
        self.assertNotEqual(revised_decision.input_hash, replacement_decision.input_hash)
        with patch('mycel._safeguards.subprocess.Popen') as spawn, \
                self.assertRaises(reviewer.ReviewerFailure) as raised:
            self.call(client, revised_decision)
        self.assertEqual(raised.exception.code, 'obsolete')
        spawn.assert_not_called()
        replacement_client = reviewer.ReviewerClient(InvocationPolicy('classify'), replacement, home=self.root)
        self.assertEqual(self.call(replacement_client, replacement_decision).judgement, 'needs_review')


if __name__ == '__main__':
    unittest.main()
