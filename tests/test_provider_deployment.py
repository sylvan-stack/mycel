# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Controlled report-shape fixtures; no real live/eval acceptance is asserted."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile

from mycel._classification_payload import ReviewCommandIdentity
from mycel._coverage import OnDemandProofs
from mycel._errors import MycelError
from mycel._evaluation_drift import _fingerprint, _prepare
from mycel._jev import HTTPResult, route_response, validate_response
from mycel._provider_deployment import prepare_deployment, require_qualification

import json
import sys
import unittest
from hashlib import sha256
from unittest.mock import patch

from mycel._provider_qualification import (
    classification_diagnostics,
    profile_fingerprint,
    qualify_profile,
)

try:
    from . import test_provider_evaluation as controlled
except ImportError:
    import test_provider_evaluation as controlled


def fingerprint(report):
    return sha256(json.dumps({key: value for key, value in report.items() if key != 'reportFingerprint'},
        sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def report_shape(expected=None):
    """Artificial arithmetic rows, never an authored/actual qualification run."""
    cases, rows, pipeline = controlled.artificial_outcomes()
    pipeline = {**(pipeline if expected is None else expected), 'mode': 'configured-live-providers'}
    for case, row in zip(cases, rows):
        row.update(id=case.id, expect=case.expect, critical=list(case.critical), correct=True,
            elapsedMs=1.0, profileFingerprint=profile_fingerprint(pipeline), cost=None,
            providerCalls={'jev': 1, 'review': int('review' in row)}, processed=True)
        row['attempts'] = sum(row['providerCalls'].values())
        label = row['jev']['judgement']
        row['jev'].update(provider='typesafe', model=pipeline['model'],
            probabilities={name: (0.6 if name == label else 0.2) if 'review' in row else float(name == label)
                           for name in ('still_supported', 'needs_review', 'insufficient_evidence')},
            confidence=0.4 if 'review' in row else 1.0)
        row['jev'].update(reportedConfidence=row['jev']['confidence'],
            confidenceComparison={'matches': True, 'reportedMinusCanonical': 0.0})
        row['stageUsage'] = {'jev': {'input_tokens': 2, 'output_tokens': 0},
            'review': {'input_tokens': 3, 'output_tokens': 1} if 'review' in row else None}
        row['jev'] = controlled.retained_jev(row['jev'], row['stageUsage']['jev'])
        if 'review' in row:
            row['review'].update(protocol=1, provider=pipeline['reviewer']['provider'],
                model=pipeline['reviewer']['model'], commandHash=pipeline['reviewCommandHash'],
                adapterRevision=pipeline['reviewRevision'], instructionVersion=pipeline['reviewInstructionVersion'],
                environmentVersion=pipeline['reviewEnvironmentVersion'],
                identitySources={'returnedFields': ['protocol', 'inputHash', 'provider', 'model', 'adapterRevision', 'commandHash'],
                    'instructionVersion': 'canonical-request', 'environmentVersion': 'retained-command-identity'})
    suite = controlled.suite(cases)
    qualification = qualify_profile(cases, rows, pipeline, real_provider_execution=True)
    diagnostics = classification_diagnostics(cases, rows)
    report = {'kind': 'drift', 'evaluationSchema': 1, 'reportVersion': 2,
        'repository': 'fixture', 'file': str(suite.file), 'fileHash': suite.file_hash,
        'build': 'fictional-controlled-shape', 'recordedAt': '2026-10-15T12:00:00+00:00',
        'live': True, 'pipeline': pipeline, 'providerExecution': 'production-defaults',
        'cases': len(cases), **qualification, 'diagnostics': diagnostics,
        **{key: diagnostics['overall'][key] for key in ('errorRate', 'falsePositiveRate',
            'meaningfulMisses', 'unnecessaryWork', 'stillSupportedPrecision', 'escalationRate')},
        'routedCases': 1, 'elapsedMs': 200.0, 'usage': {'fixture_input_tokens': 403},
        'cost': {'amount': 0.01, 'currency': 'fixture-currency'}, 'incomplete': False, 'interrupted': False,
        'batches': [{'cases': 200, 'incomplete': False, 'jevCalls': 200, 'reviewCalls': 1}], 'results': rows}
    report['reportFingerprint'] = fingerprint(report)
    return report, suite, pipeline


class ProviderDeploymentTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class SameRunProviderDeploymentCallerTests(unittest.TestCase):
    """Fictional patched provider reports; no actual live acceptance or quota.

    The original146 check suite and original on-demand executor still run so
    object retention and failed-check behavior are real local control behavior.
    Only provider operations return controlled arithmetic shapes; these unit
    results and their ephemeral live records are never retained as acceptance.
    """
    def fixture(self, root):
        from mycel._classification_payload import ReviewCommandIdentity
        from mycel._evaluation_live import _pipeline
        settings = controlled.settings(root)
        adapter = root / 'fictional-adapter'
        adapter.write_text('#!/bin/sh\nexit 1\n')
        adapter.chmod(0o700)
        settings.file.write_text(settings.file.read_text().replace(
            'review_command=' + json.dumps([sys.executable]),
            'review_command=' + json.dumps([str(adapter)])))
        from mycel._settings import load_settings
        settings = load_settings(path=settings.file, home=root)
        command = ReviewCommandIdentity.inspect(settings.values['drifts']['review_command'],
            settings.values['drifts']['review_revision'], root)
        report, suite, pipeline = report_shape(_pipeline(settings, command))
        report['build'] = 'fictional-unit-build'
        report['reportFingerprint'] = fingerprint(report)
        embedding = {'passed': True, 'live': True, 'providerExecution': 'production-defaults',
                     'build': 'fictional-unit-build'}
        return settings, suite, report, embedding, adapter

    def run_fixture(self, settings, suite, report, embedding, *, after_group=None):
        from contextlib import ExitStack

        from mycel._provider_checks import run_provider_checks as original_producer
        from mycel._provider_deployment import run_provider_deployment_checks
        captured = []
        def producer(*args, **options):
            actual = original_producer(*args, **options)
            captured.append(actual)
            if after_group is not None:
                after_group()
            return actual
        with ExitStack() as stack:
            credential = stack.enter_context(patch('mycel._credentials.Credentials'))
            credential.return_value.require_jev_key.return_value = 'fictional-unused-unit-key'
            embed = stack.enter_context(patch('mycel._embedding_live.run_embedding_live_check', return_value=embedding))
            drift = stack.enter_context(patch('mycel._evaluation_live.run_live_drift_evaluation', return_value=report))
            selected = stack.enter_context(patch('mycel._provider_checks.run_provider_checks', side_effect=producer))
            stack.enter_context(patch('mycel._voyage._https_request', side_effect=AssertionError('no real provider transport')))
            stack.enter_context(patch('mycel._reviewer.run_resolved_reviewer', side_effect=AssertionError('no real reviewer child')))
            original_proofs, original_reports = selected(settings, suite, repository='fixture',
                build='fictional-unit-build', implementation_identity='fictional-immutable-unit-source', live=True)
            proofs, reports = run_provider_deployment_checks(settings, suite, original_proofs, original_reports,
                repository='fixture', build='fictional-unit-build',
                implementation_identity='fictional-immutable-unit-source', live=True)
            counters = {'producer': selected.call_count, 'embedding': embed.call_count, 'drift': drift.call_count}
        return proofs, reports, captured, counters


# Archived complete imports; restore needed names in their original scope, not at this file tail.
