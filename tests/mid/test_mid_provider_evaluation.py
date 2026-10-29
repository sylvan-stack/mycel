"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_provider_evaluation as _support
from test_provider_evaluation import (
    AT,
    CRITICAL_CATEGORIES,
    ClassifyDependencies,
    CredentialUnavailable,
    Decimal,
    DriftCase,
    EvaluationSet,
    FIXED_QUERY,
    FIXED_TEXT,
    FixtureStore,
    InvocationPolicy,
    JevResponse,
    MycelError,
    Path,
    ProviderEvaluationTests,
    ProviderFailure,
    QUALIFICATION_REVISION,
    SimpleNamespace,
    _Jev,
    _Reviewer,
    artificial_outcomes,
    classification_diagnostics,
    json,
    load_settings,
    model_call_allowed,
    patch,
    pipeline,
    profile_fingerprint,
    qualify_profile,
    replace,
    retained_jev,
    run_drift_evaluation,
    run_embedding_live_check,
    semantic_fingerprint,
    settings,
    suite,
    sys,
    tempfile,
    unittest,
)


class ProviderEvaluationTests(_support.ProviderEvaluationTests):
# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_live_embedding_requires_explicit_choice_before_settings_tokenizer_or_credentials
    def test_live_embedding_requires_explicit_choice_before_settings_tokenizer_or_credentials(self):
        with patch('mycel._embedding_live.load_tokenizer', side_effect=AssertionError('tokenizer')), \
                patch('mycel._embedding_live.Credentials', side_effect=AssertionError('credential')):
            for flag in (False, None, 1, 'true'):
                with self.subTest(flag=flag), self.assertRaises(MycelError):
                    run_embedding_live_check(None, build='fixture', live=flag)
        self.assertTrue(model_call_allowed(InvocationPolicy('check', action='embedding', live=True), 'embedding'))
        self.assertFalse(model_call_allowed(InvocationPolicy('check', action='embedding'), 'embedding'))
        self.assertFalse(model_call_allowed(InvocationPolicy('evaluate', kind='drift'), 'jev'))
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_live_embedding_requires_explicit_choice_before_settings_tokenizer_or_credentials

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_embedding_fixed_inputs_separate_submitted_planning_usage_and_stop_on_mismatch
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_embedding_fixed_inputs_separate_submitted_planning_usage_and_stop_on_mismatch

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_embedding_compatibility_failures_stop_before_query
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_embedding_compatibility_failures_stop_before_query

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_missing_reviewer_or_key_stops_before_any_paid_case_and_preserves_settings
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_missing_reviewer_or_key_stops_before_any_paid_case_and_preserves_settings

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_live_standins_use_actual_configured_identity_canonical_runner_and_no_store
    def test_live_standins_use_actual_configured_identity_canonical_runner_and_no_store(self):
        policies, stores = [], []
        def store(*args, **kwargs):
            value = FixtureStore(*args, **kwargs); stores.append(value); return value
        def jev(selected, policy):
            policies.append(policy)
            class ReportedConfidenceJev(_Jev):
                def classify(self, decision, **options):
                    outcome = super().classify(decision, **options)
                    if outcome.response.confidence == Decimal('0.4'):
                        outcome = replace(outcome, response=replace(outcome.response,
                            reported_confidence=Decimal('0.39')))
                    return outcome
            return ReportedConfidenceJev()
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
            self.assertEqual((report['reportVersion'], report['qualificationRevision']),
                (2, 'mycel-drift-qualification-v2'))
            self.assertEqual(report['results'][0]['jev']['judgement'], 'needs_review')
            self.assertEqual((report['results'][0]['jev']['confidence'],
                report['results'][0]['jev']['reportedConfidence']), (0.4, 0.39))
            self.assertEqual(report['results'][0]['jev']['confidenceComparison'],
                {'matches': False, 'reportedMinusCanonical': -0.01})
            self.assertEqual(Decimal(report['results'][0]['jev']['exactDecimals']['confidence']), Decimal('0.4'))
            self.assertEqual(Decimal(report['results'][0]['jev']['exactDecimals']['reportedConfidence']), Decimal('0.39'))
            self.assertEqual(report['results'][0]['jevOnlyOutcome'], 'unresolved')
            self.assertEqual(report['results'][1]['jevOnlyOutcome'], 'needs_review')
            self.assertEqual((report['jevErrorsOnRouted'], report['reviewerErrorsOnRouted'],
                report['jevUnresolvedOnRouted'], report['reviewerUnresolvedOnRouted']), (0, 0, 1, 0))
            self.assertEqual(before, loaded.file.read_bytes())
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_live_standins_use_actual_configured_identity_canonical_runner_and_no_store

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_coverage_floors_are_distinct_semantics_and_conflicting_labels_cannot_qualify
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_coverage_floors_are_distinct_semantics_and_conflicting_labels_cannot_qualify

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_zero_critical_suppression_and_common_subset_strict_improvement_are_required
    def test_zero_critical_suppression_and_common_subset_strict_improvement_are_required(self):
        cases, rows, identity = artificial_outcomes()
        for change in ('critical', 'no-routed', 'no-improvement', 'identity', 'environment', 'incomplete'):
            selected = json.loads(json.dumps(rows))
            if change == 'critical': selected[1]['actual'] = 'still_supported'
            if change == 'no-routed': selected[0].pop('escalation')
            if change == 'no-improvement':
                selected[0]['jev'].update(judgement='insufficient_evidence',
                    probabilities={'still_supported': 0.2, 'needs_review': 0.2, 'insufficient_evidence': 0.6})
                selected[0]['escalation'] = 'insufficient_evidence'
                selected[0]['review']['judgement'] = 'insufficient_evidence'
                selected[0]['actual'] = 'insufficient_evidence'
                selected[0]['jev'] = retained_jev(selected[0]['jev'])
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_zero_critical_suppression_and_common_subset_strict_improvement_are_required

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_correct_tentative_labels_can_leave_jev_only_policy_unresolved
    def test_correct_tentative_labels_can_leave_jev_only_policy_unresolved(self):
        cases, rows, identity = artificial_outcomes()
        for label, probabilities, confidence, reason in (
                ('needs_review', {'still_supported': 0.2, 'needs_review': 0.6, 'insufficient_evidence': 0.2},
                 0.4, 'jev_low_confidence'),
                ('needs_review', {'still_supported': 0.5, 'needs_review': 0.5, 'insufficient_evidence': 0.0},
                 0.25, 'jev_tied'),
                ('insufficient_evidence', {'still_supported': 0.0, 'needs_review': 0.0, 'insufficient_evidence': 1.0},
                 1.0, 'insufficient_evidence')):
            selected = json.loads(json.dumps(rows))
            selected[0]['jev'].update(judgement=label, probabilities=probabilities, confidence=confidence)
            selected[0]['jev'] = retained_jev(selected[0]['jev'])
            selected[0]['escalation'] = reason
            with self.subTest(reason=reason):
                report = qualify_profile(cases, selected, identity, real_provider_execution=True)
                self.assertTrue(report['qualified'], report['qualificationFailures'])
                self.assertEqual(report['jevErrorsOnRouted'], int(label != cases[0].expect))
                self.assertEqual((report['jevCriticalMissesOnRouted'], report['reviewerErrorsOnRouted'],
                    report['jevUnresolvedOnRouted'], report['reviewerUnresolvedOnRouted']), (0, 0, 1, 0))
                self.assertEqual(selected[0]['jev']['judgement'], label)
        # Policy resolution does not allow a reviewer to add a wrong label.
        selected = json.loads(json.dumps(rows))
        selected[0].pop('escalation'); review = selected[0].pop('review')
        selected[0]['jev'].update(judgement='needs_review',
            probabilities={'still_supported': 0.0, 'needs_review': 1.0, 'insufficient_evidence': 0.0}, confidence=1.0)
        selected[0]['jevOnlyOutcome'] = 'needs_review'
        selected[0]['jev'] = retained_jev(selected[0]['jev'])
        selected[50]['escalation'] = 'jev_low_confidence'
        selected[50]['jev'].update(probabilities={'still_supported': 0.6, 'needs_review': 0.2,
            'insufficient_evidence': 0.2}, confidence=0.4)
        selected[50]['jevOnlyOutcome'] = 'unresolved'
        selected[50]['jev'] = retained_jev(selected[50]['jev'])
        selected[50]['review'] = {**review, 'inputHash': selected[50]['inputHash'], 'judgement': 'needs_review'}
        selected[50]['actual'] = 'needs_review'
        report = qualify_profile(cases, selected, identity, real_provider_execution=True)
        self.assertFalse(report['qualified'])
        self.assertEqual((report['jevErrorsOnRouted'], report['reviewerErrorsOnRouted'],
            report['jevUnresolvedOnRouted'], report['reviewerUnresolvedOnRouted']), (0, 1, 1, 0))
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_correct_tentative_labels_can_leave_jev_only_policy_unresolved

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_missing_or_inconsistent_jev_only_baselines_cannot_qualify
    def test_missing_or_inconsistent_jev_only_baselines_cannot_qualify(self):
        cases, rows, identity = artificial_outcomes()
        for change in ('missing', 'false-complete', 'false-abstention', 'old-identity'):
            selected = json.loads(json.dumps(rows)); chosen = dict(identity)
            if change == 'missing': selected[0].pop('jevOnlyOutcome')
            if change == 'false-complete': selected[0]['jevOnlyOutcome'] = 'still_supported'
            if change == 'false-abstention': selected[1]['jevOnlyOutcome'] = 'unresolved'
            if change == 'old-identity': chosen.pop('qualificationRevision')
            with self.subTest(change=change):
                report = qualify_profile(cases, selected, chosen, real_provider_execution=True)
                self.assertFalse(report['qualified'])
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_missing_or_inconsistent_jev_only_baselines_cannot_qualify

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_unavailable_evidence_requires_unresolved_and_zero_calls_even_with_other_good_metrics
    def test_unavailable_evidence_requires_unresolved_and_zero_calls_even_with_other_good_metrics(self):
        cases, rows, identity = artificial_outcomes()
        cases[-1] = replace(cases[-1], expect='unresolved', unavailable=('baseline',))
        rows[-1] = {**rows[-1], 'actual': 'unresolved', 'attempts': 0}
        rows[-1].pop('jev'); rows[-1].pop('inputHash')
        rows[-1]['semanticHash'] = semantic_fingerprint(cases[-1])
        self.assertTrue(qualify_profile(cases, rows, identity, real_provider_execution=True)['qualified'])
        rows[-1]['attempts'] = 1
        self.assertFalse(qualify_profile(cases, rows, identity, real_provider_execution=True)['qualified'])
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_unavailable_evidence_requires_unresolved_and_zero_calls_even_with_other_good_metrics

# TEST-TIER-BEGIN tests/test_provider_evaluation.py::ProviderEvaluationTests.test_profile_identity_changes_require_a_new_versioned_profile_report
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
# TEST-TIER-END tests/test_provider_evaluation.py::ProviderEvaluationTests.test_profile_identity_changes_require_a_new_versioned_profile_report
