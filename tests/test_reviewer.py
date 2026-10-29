# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Independent local protocol adapters; no provider or credential access."""
from contextlib import contextmanager
from hashlib import sha256
import os
import re
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from mycel._classification_runner import ClassifyDependencies, _Runner
from mycel._errors import MycelError
from mycel._jev import JevOutcome
from mycel._safeguards import CompletedChild, InvocationPolicy, SYSTEM_PATH


import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from mycel import _classification_payload as payload
from mycel import _evidence as evidence
from mycel import _reviewer as reviewer
from mycel._safeguards import CompletedChild, InvocationPolicy
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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
