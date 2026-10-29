# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Finite classifier proofs with scripted services and disposable real stores."""
import json
import re
import unittest

from mycel._classification_runner import ClassifyDependencies
from mycel._jev import JevFailure, route_response, validate_response
from mycel._reviewer import ReviewerFailure
from mycel._settings import load_settings

try:
    from . import test_classification_store as fixture_module
    pass
    from .test_jev import http, response
except ImportError:
    import test_classification_store as fixture_module
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
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class FiniteClassifyStoreTests(fixture_module.ClassificationStoreFixture):
    check_kind = "store"

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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
