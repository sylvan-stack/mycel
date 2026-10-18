"""Service-free provider boundaries and pure finite-corpus arithmetic only.

Artificial outcome rows exercise counts; they are not an evaluation set,
label evidence, measured provider report or live/eval requirement acceptance.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from mycel._classification_runner import ClassifyDependencies
from mycel._coverage import proves
from mycel._credentials import CredentialUnavailable
from mycel._embedding_live import FIXED_QUERY, FIXED_TEXT, run_embedding_live_check
from mycel._errors import MycelError
from mycel._evaluation import DriftCase, EvaluationSet
from mycel._evaluation_drift import FixtureStore, _Jev, _Reviewer, run_drift_evaluation
from mycel._provider_qualification import (CRITICAL_CATEGORIES, classification_diagnostics,
    profile_fingerprint, qualify_profile, semantic_fingerprint)
from mycel._safeguards import InvocationPolicy, model_call_allowed
from mycel._settings import load_settings
from mycel._voyage import ProviderFailure


AT = '2026-10-15T12:00:00+00:00'


def settings(root, *, reviewer=True):
    text = '[store]\naddress="postgresql://fixture@localhost:55432/mycel_fictional"\n[drifts]\ncandidates=2\nat_once=2\nattempts=1\nseconds=5\n'
    if reviewer:
        text += ('review_command=' + json.dumps([sys.executable]) + '\nreview_provider="fixture-provider"\n'
                 'review_model="fixture-model-1"\nreview_revision="fixture-adapter-v1"\n')
    file = root / 'config.toml'; file.write_text(text)
    return load_settings(path=file, home=root)


def suite(cases):
    return EvaluationSet(Path('/fictional/reviewed-evaluation.toml'), 'a' * 64, drifts=tuple(cases))


def pipeline():
    return {'protocol': 1, 'model': 'jev-1.13.0', 'questionVersion': 'mycel-dependency-v1',
        'choiceOrder': ['still_supported', 'needs_review', 'insufficient_evidence'],
        'policyRevision': 'fixture-policy', 'confidenceFloor': 0.7,
        'reviewCommandHash': 'a' * 64, 'reviewRevision': 'adapter-v1',
        'reviewInstructionVersion': 'mycel-review-v1', 'reviewEnvironmentVersion': 'mycel-review-env-v1',
        'reviewer': {'provider': 'fixture-provider', 'model': 'fixture-model'}}


def artificial_outcomes():
    """Arithmetic vectors, never executed semantic fixtures or authored labels."""
    identity = pipeline(); cases, rows = [], []
    for number in range(200):
        critical, unchanged = number < 50, 50 <= number < 100
        expected = 'still_supported' if unchanged else 'needs_review'
        case = DriftCase(str(number), 'before ' + str(number), 'claim ' + str(number), expected, current='after ' + str(number),
            critical=(('negation', 'operator', 'permission', 'deletion')[number % 4],) if critical else (), unchanged=unchanged)
        row = {'semanticHash': semantic_fingerprint(case), 'processed': True, 'attempts': 1,
            'actual': expected, 'profileFingerprint': profile_fingerprint(identity),
            'inputHash': format(number, '064x'), 'jev': {'model': identity['model'], 'judgement': expected}}
        if number == 0:
            row['escalation'] = 'jev_low_confidence'
            row['jev']['judgement'] = 'still_supported'
            row['review'] = {**identity['reviewer'], 'judgement': expected,
                'commandHash': identity['reviewCommandHash'], 'adapterRevision': identity['reviewRevision'],
                'instructionVersion': identity['reviewInstructionVersion'],
                'environmentVersion': identity['reviewEnvironmentVersion'], 'inputHash': row['inputHash']}
        cases.append(case); rows.append(row)
    return cases, rows, identity


class ProviderEvaluationTests(unittest.TestCase):
    @proves('MYC-0.10', 'MYC-13.2')
    def test_live_embedding_requires_explicit_choice_before_settings_tokenizer_or_credentials(self):
        with patch('mycel._embedding_live.load_tokenizer', side_effect=AssertionError('tokenizer')), \
                patch('mycel._embedding_live.Credentials', side_effect=AssertionError('credential')):
            for flag in (False, None, 1, 'true'):
                with self.subTest(flag=flag), self.assertRaises(MycelError):
                    run_embedding_live_check(None, build='fixture', live=flag)
        self.assertTrue(model_call_allowed(InvocationPolicy('check', action='embedding', live=True), 'embedding'))
        self.assertFalse(model_call_allowed(InvocationPolicy('check', action='embedding'), 'embedding'))
        self.assertFalse(model_call_allowed(InvocationPolicy('evaluate', kind='drift'), 'jev'))

    @proves('MYC-0.10', 'MYC-13.7')
    def test_embedding_fixed_inputs_separate_submitted_planning_usage_and_stop_on_mismatch(self):
        catalog = SimpleNamespace(tokenizer_repository='fixture', tokenizer_revision='a' * 40,
            tokenizer_sha256='b' * 64, counting_rule='submitted-exact; planning-prompt-plus-exact-v1')
        tokenizer = SimpleNamespace(catalog=catalog, library_sha256='c' * 64,
            counts=lambda text, kind: (3, 5) if kind == 'document' else (2, 4))
        for document_usage, query_usage in ((3, 2), (1, 1), (9, 7)):
            sent = []
            class Client:
                _requests = 0
                def __init__(self, credentials, policy, **options):
                    self.assertions = options
                    sent.append(('intent', policy, options['attempts']))
                def _request(self, inputs, model, dimensions, kind):
                    self._requests += 1
                    sent.append((kind, inputs, model, dimensions))
                    return SimpleNamespace(vectors=(tuple(0.0 for _ in range(dimensions)),),
                        provider_tokens=document_usage if kind == 'document' else query_usage, requests=1)
            with tempfile.TemporaryDirectory() as temporary:
                loaded = settings(Path(temporary))
                report = run_embedding_live_check(loaded, build='fixture', live=True,
                    _client_factory=Client, _tokenizer=tokenizer)
            self.assertEqual(sent[0], ('intent', InvocationPolicy('check', action='embedding', live=True), 1))
            self.assertEqual(sent[1:], [('document', (FIXED_TEXT,), 'voyage-code-4', 1024),
                ('query', (FIXED_QUERY,), 'voyage-code-4', 1024)])
            self.assertEqual((report['reportVersion'], report['checkRevision']), (2, 'mycel-embedding-live-v2'))
            self.assertFalse(report['passed'])  # Internal stand-ins never prove live acceptance.
            self.assertEqual(report['providerExecution'], 'service-stand-ins')
            self.assertFalse(report['incomplete'])
            self.assertEqual(len(report['results']), 2)
            for row, submitted, planning, provider in zip(report['results'], (3, 2), (5, 4),
                                                         (document_usage, query_usage)):
                self.assertEqual((row['submittedTokens'], row['planningTokens'], row['providerInputTextTokens']),
                    (submitted, planning, provider))
                self.assertEqual(row['usage'], {'inputTextTokens': provider})
                self.assertEqual(row['tokenCountComparison'], {'matches': provider == submitted,
                    'providerMinusSubmitted': provider - submitted})
                self.assertTrue(row['passed'])
                self.assertNotIn('error', row)
                self.assertEqual(row['attempts'], 1)

    @proves('MYC-0.10', 'MYC-13.7')
    def test_embedding_compatibility_failures_stop_before_query(self):
        catalog = SimpleNamespace(tokenizer_repository='fixture', tokenizer_revision='a' * 40,
            tokenizer_sha256='b' * 64, counting_rule='submitted-exact; planning-prompt-plus-exact-v1')
        for failure in ('dimension_mismatch', 'planning_count_mismatch', 'authentication',
                        'missing_model', 'invalid_response', 'cancelled'):
            tokenizer = SimpleNamespace(catalog=catalog, library_sha256='c' * 64,
                counts=lambda text, kind: (3, 2 if failure == 'planning_count_mismatch' else 5))
            sent = []
            class Client:
                _requests = 0
                def __init__(self, credentials, policy, **options):
                    pass
                def _request(self, inputs, model, dimensions, kind):
                    self._requests += 1
                    sent.append(kind)
                    if failure == 'cancelled':
                        raise KeyboardInterrupt()
                    if failure not in {'dimension_mismatch', 'planning_count_mismatch'}:
                        raise ProviderFailure(failure)
                    size = dimensions - 1 if failure == 'dimension_mismatch' else dimensions
                    return SimpleNamespace(vectors=(tuple(0.0 for _ in range(size)),),
                        provider_tokens=1, requests=1)
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                report = run_embedding_live_check(settings(Path(temporary)), build='fixture', live=True,
                    _client_factory=Client, _tokenizer=tokenizer)
                self.assertEqual(sent, ['document'])
                self.assertFalse(report['passed'])
                self.assertTrue(report['incomplete'])
                self.assertEqual(len(report['results']), 1)
                row = report['results'][0]
                self.assertFalse(row['passed'])
                self.assertEqual(row['error']['kind'], failure)
                self.assertEqual(row['attempts'], 1)
                if failure not in {'dimension_mismatch', 'planning_count_mismatch'}:
                    self.assertIsNone(row['providerInputTextTokens'])
                    self.assertIsNone(row['tokenCountComparison'])

    @proves('MYC-0.10', 'MYC-14.12')
    def test_missing_reviewer_or_key_stops_before_any_paid_case_and_preserves_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); loaded = settings(root, reviewer=False)
            before = loaded.file.read_bytes()
            cases = suite([DriftCase('complete', 'old', 'claim', 'needs_review', current='new'),
                           DriftCase('missing', 'old', 'claim', 'unresolved', current='new', unavailable=('baseline',))])
            with patch('mycel._evaluation_live.Credentials', side_effect=AssertionError('credential')):
                report = run_drift_evaluation(cases, loaded, repository='fixture', build='fixture', live=True)
            self.assertFalse(report['qualified']); self.assertEqual(report['batches'], [])
            self.assertEqual([row['attempts'] for row in report['results']], [0, 0])
            self.assertEqual([row['processed'] for row in report['results']], [False, True])
            self.assertEqual(before, loaded.file.read_bytes())
            loaded = settings(root)
            with patch('mycel._evaluation_live.Credentials') as credentials:
                credentials.return_value.require_jev_key.side_effect = CredentialUnavailable()
                report = run_drift_evaluation(cases, loaded, repository='fixture', build='fixture', live=True)
            self.assertFalse(report['qualified']); self.assertEqual(report['batches'], [])
            self.assertTrue(any('credential' in reason for reason in report['qualificationFailures']))

    @proves('MYC-0.10', 'MYC-14.17')
    def test_live_standins_use_actual_configured_identity_canonical_runner_and_no_store(self):
        policies, stores = [], []
        def store(*args, **kwargs):
            value = FixtureStore(*args, **kwargs); stores.append(value); return value
        def jev(selected, policy):
            policies.append(policy); return _Jev()
        def reviewer(selected, policy, command):
            policies.append(policy); return _Reviewer()
        cases = suite([DriftCase('changed', 'x=1', 'x=1', 'needs_review', current='x=2'),
            DriftCase('deleted', 'allow()', 'claim', 'needs_review', source_state='deleted', critical=('deletion',)),
            DriftCase('missing', 'old', 'claim', 'unresolved', current='new', unavailable=('baseline',))])
        with tempfile.TemporaryDirectory() as temporary:
            loaded = settings(Path(temporary)); before = loaded.file.read_bytes()
            with patch('mycel._evaluation_live.Credentials', side_effect=AssertionError('credential')), \
                    patch('mycel._database.store_connection', side_effect=AssertionError('store')):
                report = run_drift_evaluation(cases, loaded, repository='fixture', build='fixture', live=True,
                    dependencies=ClassifyDependencies(utc_now=lambda: AT, jev_factory=jev, reviewer_factory=reviewer),
                    store_factory=store)
            self.assertEqual([row['cases'] for row in report['batches']], [2, 1])
            self.assertTrue(all(policy == InvocationPolicy('evaluate', kind='drift', live=True) for policy in policies))
            self.assertEqual(report['pipeline']['reviewer']['provider'], 'fixture-provider')
            review = report['results'][0]['review']
            self.assertEqual(review['provider'], 'fixture-provider')
            prepared = next(iter(stores[0].preparations.values()))
            actual_returned = stores[0].records[prepared.reason_id]['evidence']['review']
            returned_fields = {'protocol', 'inputHash', 'provider', 'model', 'adapterRevision', 'commandHash'}
            self.assertEqual(set(review['identitySources']['returnedFields']), returned_fields)
            self.assertTrue(all(review[key] == actual_returned[key] for key in returned_fields))
            self.assertNotIn('instructionVersion', actual_returned)
            self.assertNotIn('environmentVersion', actual_returned)
            self.assertEqual(review['instructionVersion'], prepared.decision.payload['models']['review']['instructionVersion'])
            self.assertEqual(review['environmentVersion'], json.loads(prepared.guards_bytes)['command']['environmentVersion'])
            self.assertEqual(review['identitySources']['instructionVersion'], 'canonical-request')
            self.assertEqual(review['identitySources']['environmentVersion'], 'retained-command-identity')
            self.assertEqual(review['instructionVersion'], report['pipeline']['reviewInstructionVersion'])
            self.assertEqual(review['environmentVersion'], report['pipeline']['reviewEnvironmentVersion'])
            self.assertEqual(report['results'][1]['actual'], 'needs_review')
            self.assertEqual(report['results'][2]['attempts'], 0)
            self.assertNotIn('inputHash', report['results'][2])
            self.assertEqual(report['providerExecution'], 'service-stand-ins')
            self.assertFalse(report['qualified']); self.assertEqual(report['cost'], None)
            self.assertEqual(before, loaded.file.read_bytes())

    @proves('MYC-13.15')
    def test_coverage_floors_are_distinct_semantics_and_conflicting_labels_cannot_qualify(self):
        cases, rows, identity = artificial_outcomes()
        self.assertTrue(qualify_profile(cases, rows, identity, real_provider_execution=True)['qualified'])
        duplicate = [dict(row, semanticHash=rows[0]['semanticHash']) for row in rows]
        duplicate_cases = [replace(case, before=cases[0].before, current=cases[0].current,
            dependant=cases[0].dependant) for case in cases]
        report = qualify_profile(duplicate_cases, duplicate, identity, real_provider_execution=True)
        self.assertEqual(report['distinctCases'], 1); self.assertFalse(report['qualified'])
        self.assertTrue(any('conflicting' in reason for reason in report['qualificationFailures']))
        self.assertFalse(qualify_profile(cases, rows, identity, real_provider_execution=False)['qualified'])
        for missing in sorted(CRITICAL_CATEGORIES):
            replacement = next(tag for tag in sorted(CRITICAL_CATEGORIES) if tag != missing)
            selected = [replace(case, critical=tuple(replacement if tag == missing else tag
                for tag in case.critical)) for case in cases]
            with self.subTest(missing=missing):
                report = qualify_profile(selected, rows, identity, real_provider_execution=True)
                self.assertEqual((report['distinctCases'], report['criticalCases'], report['unchangedCases']), (200, 50, 50))
                self.assertFalse(report['qualified'])
                self.assertIn('Critical coverage must include negation, operator, permission and deletion.',
                              report['qualificationFailures'])
                from mycel._provider_checks import run_provider_checks
                with patch('mycel._embedding_live.run_embedding_live_check', side_effect=AssertionError('paid embedding')), \
                        patch('mycel._evaluation_live.run_live_drift_evaluation', side_effect=AssertionError('paid drift')), \
                        self.assertRaises(MycelError):
                    run_provider_checks(None, suite(selected), repository='fixture', build='fixture',
                        implementation_identity='fictional-immutable-test-identity', live=True)

    @proves('MYC-13.15', 'MYC-14.17')
    def test_zero_critical_suppression_and_common_subset_strict_improvement_are_required(self):
        cases, rows, identity = artificial_outcomes()
        for change in ('critical', 'no-routed', 'no-improvement', 'identity', 'environment', 'incomplete'):
            selected = json.loads(json.dumps(rows))
            if change == 'critical': selected[1]['actual'] = 'still_supported'
            if change == 'no-routed': selected[0].pop('escalation')
            if change == 'no-improvement': selected[0]['jev']['judgement'] = 'needs_review'
            if change == 'identity': selected[0]['review']['model'] = 'other-model'
            if change == 'environment': selected[0]['review']['environmentVersion'] = 'other-environment'
            with self.subTest(change=change):
                report = qualify_profile(cases, selected, identity,
                    real_provider_execution=True, incomplete=change == 'incomplete')
                self.assertFalse(report['qualified'])
                if change == 'environment':
                    self.assertEqual((report['distinctCases'], report['criticalCases'], report['unchangedCases']), (200, 50, 50))
                    self.assertEqual(selected[0]['review']['provider'], rows[0]['review']['provider'])
                    self.assertEqual(selected[0]['review']['model'], rows[0]['review']['model'])
                    self.assertEqual(report['qualificationFailures'],
                        ['The configured or returned provider identity is missing or changed.'])

    @proves('MYC-13.15', 'MYC-0.10')
    def test_unavailable_evidence_requires_unresolved_and_zero_calls_even_with_other_good_metrics(self):
        cases, rows, identity = artificial_outcomes()
        cases[-1] = replace(cases[-1], expect='unresolved', unavailable=('baseline',))
        rows[-1] = {**rows[-1], 'actual': 'unresolved', 'attempts': 0}
        rows[-1].pop('jev'); rows[-1].pop('inputHash')
        rows[-1]['semanticHash'] = semantic_fingerprint(cases[-1])
        self.assertTrue(qualify_profile(cases, rows, identity, real_provider_execution=True)['qualified'])
        rows[-1]['attempts'] = 1
        self.assertFalse(qualify_profile(cases, rows, identity, real_provider_execution=True)['qualified'])

    @proves('MYC-13.15')
    def test_profile_identity_changes_require_a_new_versioned_profile_report(self):
        cases, rows, _ = artificial_outcomes()
        diagnostics = classification_diagnostics(cases, rows)
        self.assertEqual(set(diagnostics['byCategory']), set(CRITICAL_CATEGORIES) | {'unchanged_cosmetic', 'other'})
        overall = diagnostics['overall']
        self.assertEqual(overall['denominators']['errorRate'], 200)
        self.assertEqual(overall['denominators']['stillSupportedPrecision'], 50)
        self.assertEqual(overall['stillSupportedPrecision'], 1.0)
        self.assertEqual(overall['meaningfulMisses'], 0)
        self.assertIsNone(classification_diagnostics((), ())['overall']['errorRate'])
        self.assertIsNone(classification_diagnostics((), ())['overall']['stillSupportedPrecision'])
        selected = [dict(row) for row in rows]
        selected[1] = {**selected[1], 'actual': 'still_supported'}
        selected[50] = {**selected[50], 'actual': 'needs_review'}
        changed = classification_diagnostics(cases, selected)
        self.assertEqual((changed['overall']['meaningfulMisses'], changed['overall']['unnecessaryWork']), (1, 1))
        self.assertEqual(changed['byCategory']['operator']['meaningfulMisses'], 1)
        self.assertEqual(changed['byCategory']['unchanged_cosmetic']['unnecessaryWork'], 1)
        self.assertEqual(changed['overall']['denominators']['escalationRate'], 200)
        self.assertEqual(changed['overall']['escalationRate'], 1 / 200)
        identity = pipeline(); before = profile_fingerprint(identity)
        for field, value in (('model', 'jev-1.14.0'), ('confidenceFloor', 0.8),
                             ('reviewRevision', 'adapter-v2'), ('reviewCommandHash', 'b' * 64)):
            self.assertNotEqual(before, profile_fingerprint({**identity, field: value}))
