# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Canonical non-live handler checks; no real credentials or provider calls."""
import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from mycel._evaluation import DriftCase, EvaluationSet
from mycel._settings import load_settings

AT = '2026-10-15T12:00:00+00:00'


def settings(root, *, candidates=2):
    config = root / 'config.toml'
    config.write_text('[repos.fixture]\nenabled=true\nartifact_root=' + json.dumps(str(root)) +
        '\nevaluation="evaluation.toml"\n[drifts]\ncandidates=' + str(candidates) +
        '\nat_once=1\nattempts=2\nseconds=6\nreview_timeout_seconds=2\n')
    return load_settings(path=config, home=root)


def suite(cases):
    return EvaluationSet(Path('/fictional/versioned-evaluation.toml'), 'a' * 64, drifts=tuple(cases))


def cases():
    return (DriftCase('unchanged', 'x = 1', 'x = 1', 'still_supported', current='x = 1', unchanged=True),
        DriftCase('changed', 'x = 1', 'x = 1', 'needs_review', current='x = 2', critical=('operator',)),
        DriftCase('deleted', 'allow()', 'allow()', 'needs_review', source_state='deleted', critical=('deletion',)),
        DriftCase('missing', 'old', 'claim', 'unresolved', current='new', unavailable=('baseline',)),
        DriftCase('context', 'old', 'claim', 'needs_review', current='new', context=('full context\n',)))


class DriftEvaluationTests(unittest.TestCase):
    def setUp(self):
        blocked = ExitStack()
        self.addCleanup(blocked.close)
        for entry in ('mycel._database.store_connection',
                      'mycel._classification_runner.Credentials',
                      'mycel._credentials.run_child',
                      'mycel._voyage._https_request',
                      'http.client.HTTPConnection.request',
                      'socket.create_connection', 'socket.socket.connect',
                      'socket.socket.connect_ex'):
            blocked.enter_context(patch(entry, side_effect=AssertionError('non-live evaluation must not use external services')))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
