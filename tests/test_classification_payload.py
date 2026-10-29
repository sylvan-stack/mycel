# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Supplemental pure checks; native store tests own classifier acceptance claims."""

import unittest
from contextlib import ExitStack
from hashlib import sha256
from unittest.mock import patch

from mycel import _classification_payload as payload
from mycel import _evidence as evidence
from mycel._source_refs import SourceAddress


def fixture(*, current=b'return "admin"\n', capture_time='2026-10-09T00:00:00Z', padding=b''):
    source = SourceAddress('source', 'code', 'access.py', 'permission')
    dependant = SourceAddress('owner', 'code', 'guide.py', 'claim')
    before_bytes, dependant_bytes = b'return "reader"\n', b'readers_may_delete = True\n'
    before = evidence.snapshot(before_bytes, comparison=evidence.exact_comparison(before_bytes, 'code_text'),
              place=source, file_source=padding + before_bytes, span=(len(padding), len(padding) + len(before_bytes)))
    dep = evidence.snapshot(dependant_bytes, comparison=evidence.exact_comparison(dependant_bytes, 'code_text'),
              place=dependant, file_source=padding + dependant_bytes,
              span=(len(padding), len(padding) + len(dependant_bytes)))
    manifest = evidence.BaselineManifest({
        'schema': 1, 'ownerRepository': 'owner', 'dependantId': '00000000-0000-0000-0000-000000000002',
        'dependantVersion': '7', 'dependant': dep.evidence.as_dict(), 'kind': 'declared',
        'ref': source.address, 'source': evidence._place(source), 'selection': 'chunk',
        'members': [{'id': '00000000-0000-0000-0000-000000000001', 'place': evidence._place(source),
                     'evidence': before.evidence.as_dict()}],
        'pinnedHash': before.evidence.comparison.hash, 'selectionComparison': before.evidence.comparison.as_dict(),
        'capturedAt': capture_time, 'location': {'kind': 'disk'}})
    now = evidence.snapshot(current, comparison=evidence.exact_comparison(current, 'code_text'), place=source,
                           file_source=padding + current, span=(len(padding), len(padding) + len(current)))
    before_text, current_text, dep_text = (payload.DecisionText.create(item.evidence, item.source)
                                         for item in (before, now, dep))
    selection = payload.CurrentSelection.create('present', source, 'chunk', (current_text,))
    decision = payload.DecisionPayload.create(baseline=manifest, before=(before_text,), current=selection,
                                             dependant=dep_text)
    return manifest, (before, now, dep), decision


def reviewer_identity():
    return payload.ReviewCommandIdentity({
        'argv': ['/Users/example/.local/bin/mycel-review-adapter', '--config',
                 '/Users/example/.config/reviewer/config.toml'],
        'executableSha256': sha256(b'fictional adapter bytes; not an installed executable\n').hexdigest(),
        'adapterRevision': 'example-adapter-v1', 'protocol': 1,
        'instructionVersion': 'mycel-review-v1', 'environmentVersion': 'mycel-review-env-v1'})


def reviewed(decision):
    value = decision.as_dict()
    value['models']['review'] = reviewer_identity().model_identity('example-provider', 'example-model-2026-10-01')
    return payload.DecisionPayload(value)


def guards(decision, *, changed_at='2026-10-09T00:00:00Z', file_hash='a' * 64):
    return [{'place': decision.payload['current']['place'], 'event': 'file_changed',
             'hash': file_hash, 'changedAt': changed_at}]


class ClassificationPayloadTests(unittest.TestCase):
    def setUp(self):
        # Payload preparation and dry-run command inspection have no model or
        # child-process channel. Fail immediately if any case creates one.
        blocked = ExitStack()
        self.addCleanup(blocked.close)
        for entry in ('mycel._voyage._https_request', 'http.client.HTTPConnection.request',
                      'urllib.request.urlopen', 'socket.create_connection', 'socket.socket.connect',
                      'subprocess.Popen', 'subprocess.run'):
            blocked.enter_context(patch(entry, side_effect=AssertionError('preparation must not call or spawn')))



# Archived complete imports; restore needed names in their original scope, not at this file tail.
