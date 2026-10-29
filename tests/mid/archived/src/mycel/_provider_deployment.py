"""Exact retained provider-profile deployment gate; no automatic Build coupling.

This consumes one explicit measured component report. It never calls a model,
retunes settings or reconstructs an OnDemandProofs object from retained JSON.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation

from ._coverage import CheckResult, OnDemandProofs, run_on_demand_checks


import json
import math
import re
import stat
from decimal import InvalidOperation
from hashlib import sha256
from pathlib import Path

from ._classification_payload import LABELS, ReviewCommandIdentity
from ._errors import MycelError
from ._evidence import EvidenceError
from ._jev import JevFailure
from ._provider_qualification import (
    QUALIFICATION_REVISION,
    _jev_response_from_report,
    classification_diagnostics,
    profile_fingerprint,
    qualify_profile,
    semantic_fingerprint,
)


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _require(condition):
    if not condition:
        raise MycelError('refused', 'The retained report does not qualify this exact configured provider pipeline for deployment.')


def require_qualification(report, suite, expected_pipeline):
    """Pure content verification; the caller retains actual-run provenance.

    A profile-qualified report can survive an unrelated Build change when all
    semantic component identities still match. It proves no automatic Build or
    same-Build requirement acceptance and is never an input to run_checks.
    """
    try:
        _require(type(report) is dict and type(expected_pipeline) is dict)
        _require(report['kind'] == 'drift' and report['reportVersion'] == 2
            and report['qualificationRevision'] == QUALIFICATION_REVISION
            and report['evaluationSchema'] == suite.schema_version and report['live'] is True
            and report['providerExecution'] == 'production-defaults'
            and report['pipeline']['mode'] == 'configured-live-providers'
            and report['qualified'] is True and report['qualificationFailures'] == []
            and report['incomplete'] is False and report['interrupted'] is False)
        _require(isinstance(report['build'], str) and bool(report['build'])
            and isinstance(report['recordedAt'], str) and bool(report['recordedAt']))
        _require(_bytes(report['pipeline']) == _bytes(expected_pipeline)
            and report['profileFingerprint'] == profile_fingerprint(expected_pipeline))
        _require(report['fileHash'] == suite.file_hash and report['file'] == str(suite.file)
            and type(report['cases']) is int and report['cases'] == len(suite.drifts)
            and len(report['results']) == len(suite.drifts))
        _require(re.fullmatch('[0-9a-f]{64}', report['reportFingerprint']) is not None
            and sha256(_bytes({key: value for key, value in report.items()
                               if key != 'reportFingerprint'})).hexdigest() == report['reportFingerprint'])
        for case, row in zip(suite.drifts, report['results'], strict=True):
            _require(row['id'] == case.id and row['expect'] == case.expect
                and row['critical'] == list(case.critical)
                and row['semanticHash'] == semantic_fingerprint(case)
                and row['profileFingerprint'] == report['profileFingerprint']
                and row['processed'] is True and type(row['attempts']) is int and row['attempts'] >= 0
                and row['actual'] in (*LABELS, 'unresolved')
                and type(row['correct']) is bool and row['correct'] == (row['actual'] == case.expect))
            _require('inputHash' not in row or re.fullmatch('[0-9a-f]{64}', row['inputHash']) is not None)
            _require(set(row['providerCalls']) == {'jev', 'review'}
                and all(type(v) is int and v >= 0 for v in row['providerCalls'].values())
                and sum(row['providerCalls'].values()) == row['attempts'])
            jev = row.get('jev')
            if jev is not None:
                response = _jev_response_from_report(jev, row['stageUsage']['jev'])
                _require(response.model == expected_pipeline['model'] and jev['provider'] == 'typesafe')
            review = row.get('review')
            if review is not None:
                _require(type(review['protocol']) is int and review['protocol'] == 1
                    and review['judgement'] in LABELS
                    and review['identitySources'] == {
                        'returnedFields': ['protocol', 'inputHash', 'provider', 'model', 'adapterRevision', 'commandHash'],
                        'instructionVersion': 'canonical-request',
                        'environmentVersion': 'retained-command-identity'})
            # A complete final categorical result must be the actual selected
            # stage, never a separately edited correctness/count field.
            if not case.unavailable:
                selected_stage = review if review is not None else jev
                _require(selected_stage is not None and row['actual'] == selected_stage['judgement'])
            _require(type(row['elapsedMs']) in {int, float} and math.isfinite(row['elapsedMs'])
                and row['elapsedMs'] >= 0)
            cost = row['cost']
            _require(cost is None or type(cost) is dict and set(cost) == {'amount', 'currency'}
                and type(cost['amount']) in {int, float} and math.isfinite(cost['amount'])
                and cost['amount'] >= 0 and isinstance(cost['currency'], str) and bool(cost['currency']))
        _require(sum(batch['cases'] for batch in report['batches']) == report['cases']
            and all(batch['incomplete'] is False for batch in report['batches'])
            and sum(batch['jevCalls'] for batch in report['batches']) == sum(row['providerCalls']['jev'] for row in report['results'])
            and sum(batch['reviewCalls'] for batch in report['batches']) == sum(row['providerCalls']['review'] for row in report['results']))
        qualification = qualify_profile(suite.drifts, report['results'], expected_pipeline,
            real_provider_execution=True, incomplete=False)
        _require(qualification['qualified'])
        _require(all(_bytes(report[key]) == _bytes(value) for key, value in qualification.items()))
        diagnostics = classification_diagnostics(suite.drifts, report['results'])
        _require(_bytes(report['diagnostics']) == _bytes(diagnostics))
        for key in ('errorRate', 'falsePositiveRate', 'meaningfulMisses', 'unnecessaryWork',
                    'stillSupportedPrecision', 'escalationRate'):
            _require(_bytes(report[key]) == _bytes(diagnostics['overall'][key]))
        _require(report['routedCases'] == sum('escalation' in row for row in report['results']))
        _require(type(report['elapsedMs']) in {int, float} and math.isfinite(report['elapsedMs']) and report['elapsedMs'] >= 0)
        cost = report['cost']
        _require(cost is None or type(cost) is dict and set(cost) == {'amount', 'currency'}
            and type(cost['amount']) in {int, float} and math.isfinite(cost['amount'])
            and cost['amount'] >= 0 and isinstance(cost['currency'], str) and bool(cost['currency']))
        # Ensure every retained value is serializable finite data, not a live
        # object or a fabricated conversion into requirement acceptance.
        retained = json.loads(_bytes(report))
        return {'schema': 'mycel-provider-deployment-qualification-v1', 'qualified': True,
            'pipeline': json.loads(_bytes(expected_pipeline)), 'profileFingerprint': report['profileFingerprint'],
            'evaluationFileHash': suite.file_hash, 'reportFingerprint': report['reportFingerprint'],
            'evaluatedBuild': report['build'], 'reportRecordedAt': report['recordedAt'],
            'quality': diagnostics, 'reviewerComparison': {key: qualification[key] for key in
                ('commonRoutedCases', 'jevErrorsOnRouted', 'reviewerErrorsOnRouted',
                 'jevCriticalMissesOnRouted', 'reviewerCriticalMissesOnRouted',
                 'jevUnresolvedOnRouted', 'reviewerUnresolvedOnRouted')},
            'usage': retained['usage'], 'cost': retained['cost'], 'elapsedMs': retained['elapsedMs'],
            'report': retained, 'componentProvenanceOnly': True,
            'sameBuildOnDemandProof': False, 'automaticWorkingBuildQualification': False,
            'modelCallsMadeByConsumer': 0, 'settingsOrPinsChanged': False}
    except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation, JevFailure):
        raise MycelError('refused', 'The retained provider qualification report is invalid or incomplete.') from None


def prepare_deployment(settings, suite, report_path, *, expected_report_sha256):
    """Explicit development-tool seam; reads the reviewed report, writes nothing.

    The caller retains the returned whole record beside the actual146 operation
    receipt. No new settings key, public command or automatic gate is introduced.
    """
    from ._evaluation_live import _pipeline
    settings.require_valid(require_store=False)
    settings.require_current()
    options = settings.values['drifts']
    _require(bool(options.get('review_command')))
    try:
        command = ReviewCommandIdentity.inspect(options['review_command'], options['review_revision'], settings._home or '/')
    except EvidenceError:
        raise MycelError('refused', 'The configured provider deployment reviewer identity is unavailable.') from None
    _require(command.available)
    try:
        path = Path(report_path)
        _require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode))
        raw = path.read_bytes()
        _require(sha256(raw).hexdigest() == expected_report_sha256)
        def object_pairs(pairs):
            value = {}
            for key, member in pairs:
                if key in value: raise ValueError('duplicate member')
                value[key] = member
            return value
        report = json.loads(raw, object_pairs_hook=object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))
        record = require_qualification(report, suite, _pipeline(settings, command))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise MycelError('refused', 'The exact reviewed provider qualification report could not be read.') from None
    settings.require_current()
    try:
        _require(command == ReviewCommandIdentity.inspect(options['review_command'], options['review_revision'], settings._home or '/'))
    except EvidenceError:
        raise MycelError('refused', 'The configured provider deployment reviewer identity changed during preparation.') from None
    try:
        _require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode) and path.read_bytes() == raw)
    except OSError:
        raise MycelError('refused', 'The exact reviewed provider qualification report changed during preparation.') from None
    return {**record, 'retainedReport': {'path': str(path.resolve()), 'sha256': sha256(raw).hexdigest()}}


def run_provider_deployment_checks(settings, suite, provider_proofs, reports, *, repository, build,
                                   implementation_identity, live=False):
    """Consume an explicitly completed146 group without another provider call.

    The trusted same-process group caller passes the original OnDemandProofs
    and reports objects directly from run_provider_checks. This API never
    invokes that producer, reconstructs a proof or loads a report file. A plain
    report dictionary has no independent object-origin authentication; the
    caller retains genuine operation provenance, not a self-comparison claim.
    Both separately executed proof objects remain available to the caller.
    Automatic Build discovery never calls this helper.
    """
    if live is not True:
        raise MycelError('refused', 'Provider deployment checks require explicit live selection.')
    if (not isinstance(implementation_identity, str) or not implementation_identity
            or not isinstance(build, str) or not build
            or not isinstance(repository, str) or not repository):
        raise MycelError('invalid_input', 'Provider deployment checks require an immutable Build identity.')
    import unittest

    from ._coverage import run_on_demand_checks
    expected_checks = (
        ('mycel._provider_checks.run_provider_checks.<locals>.ProviderAcceptance.test_fixed_embedding_compatibility',
         'live', ('MYC-13.9',)),
        ('mycel._provider_checks.run_provider_checks.<locals>.ProviderAcceptance.test_configured_drift_live_pipeline',
         'live', ('MYC-13.19',)),
        ('mycel._provider_checks.run_provider_checks.<locals>.ProviderAcceptance.test_same_run_finite_profile_qualification',
         'eval', ('MYC-13.20',)))

    class ProviderDeploymentAcceptance(unittest.TestCase):
        pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
        def test_same_run_provider_qualification_required_for_deployment(self):
            self.assertIs(type(provider_proofs), OnDemandProofs)
            self.assertEqual(provider_proofs.implementation_identity, implementation_identity)
            self.assertEqual(len(provider_proofs.checks), len(expected_checks))
            for check, expected in zip(provider_proofs.checks, expected_checks, strict=True):
                self.assertIs(type(check), CheckResult)
                self.assertEqual((check.name, check.kind, check.requirements), expected)
                self.assertEqual(check.status, 'passed', 'The same provider group did not complete successfully.')
            self.assertIs(type(reports), dict)
            actual_drift_report = reports.get('drift')
            embedding = reports.get('embedding')
            self.assertIsInstance(embedding, dict)
            self.assertIs(embedding.get('passed'), True)
            self.assertIs(embedding.get('live'), True)
            self.assertEqual(embedding.get('providerExecution'), 'production-defaults')
            self.assertEqual(embedding.get('build'), build)
            self.assertIsInstance(actual_drift_report, dict)
            self.assertEqual(actual_drift_report.get('build'), build)
            self.assertEqual(actual_drift_report.get('repository'), repository)
            settings.require_valid(require_store=False)
            settings.require_current()
            options = settings.values['drifts']
            _require(bool(options.get('review_command')))
            command = ReviewCommandIdentity.inspect(options['review_command'],
                options['review_revision'], settings._home or '/')
            _require(command.available)
            from ._evaluation_live import _pipeline
            record = require_qualification(actual_drift_report, suite, _pipeline(settings, command))
            settings.require_current()
            _require(command == ReviewCommandIdentity.inspect(options['review_command'],
                options['review_revision'], settings._home or '/'))
            # This record is provenance only. Only the executor below creates
            # this consumer's actual live proof, including when it fails.
            reports['deployment'] = {**record, 'sameProcessProviderGroupConsumed': True,
                'reportObjectOrigin': 'trusted-same-process-group-caller',
                'implementationIdentity': implementation_identity,
                'providerCheckNames': [row.name for row in provider_proofs.checks],
                'additionalProviderCallsByConsumer': 0}

    consumer_proofs = run_on_demand_checks(((ProviderDeploymentAcceptance(
        'test_same_run_provider_qualification_required_for_deployment'), 'live', ('MYC-14.22',)),),
        implementation_identity=implementation_identity)
    # Never reconstruct or concatenate proof rows into a manufactured object.
    # run_checks already accepts this sequence of independently executed proofs.
    return (provider_proofs, consumer_proofs), reports

# Archived complete imports; restore needed names in their original scope, not at this file tail.
