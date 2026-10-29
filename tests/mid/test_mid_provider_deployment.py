"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_provider_deployment as _support
from test_provider_deployment import (Decimal ,HTTPResult ,MycelError ,Path ,ReviewCommandIdentity ,_prepare ,controlled ,deepcopy ,fingerprint ,json ,qualify_profile ,report_shape ,require_qualification ,route_response ,tempfile ,validate_response)


class ProviderDeploymentTests(_support.ProviderDeploymentTests):
# TEST-TIER-BEGIN tests/test_provider_deployment.py::ProviderDeploymentTests.test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing
    def test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing(self):
        for maximum, other, confidence in (
                ('0.6666666666666667', '0.16666666666666665', '0.5'),
                ('0.799999999999999999', '0.100000000000000001', '0.7')):
            report, suite, pipeline = report_shape()
            last = other if confidence == '0.5' else '0.1'
            wire = ('{"model":"jev-1.13.0","answers":{"dependency":{"type":"choice",'
                '"choice":"still_supported","probabilities":{"still_supported":' + maximum
                + ',"needs_review":' + other + ',"insufficient_evidence":' + last
                + '},"confidence":' + confidence
                + '}},"usage":{"input_tokens":2,"output_tokens":0}}').encode()
            response = validate_response(HTTPResult(200, wire), model='jev-1.13.0')
            with tempfile.TemporaryDirectory() as temporary:
                settings = controlled.settings(Path(temporary))
                command = ReviewCommandIdentity.inspect(settings.values['drifts']['review_command'],
                    settings.values['drifts']['review_revision'], Path(temporary))
                prepared, _, _ = _prepare(suite.drifts[0], 0, 'fixture', settings, command, controlled.AT)
                outcome = route_response(prepared.decision, response)
            source = response.as_dict()
            row = report['results'][0]
            row['jev'] = {key: source[key] for key in ('provider', 'model', 'probabilities', 'confidence',
                'reportedConfidence', 'confidenceComparison', 'exactDecimals')} | {'judgement': source['label']}
            row['jevOnlyOutcome'] = outcome.as_dict().get('judgement', 'unresolved')
            row['escalation'] = outcome.reason
            report.update(qualify_profile(suite.drifts, report['results'], pipeline, real_provider_execution=True))
            report['reportFingerprint'] = fingerprint(report)
            # Exercise the actual retained JSON boundary, including rounded displays.
            retained = json.loads(json.dumps(report))
            with self.subTest(display=confidence):
                self.assertEqual(retained['results'][0]['jev']['confidence'], float(confidence))
                self.assertLess(Decimal(retained['results'][0]['jev']['exactDecimals']['confidence']), Decimal('0.7'))
                record = require_qualification(retained, suite, pipeline)
                self.assertTrue(record['qualified'])
                self.assertEqual(retained['results'][0]['jevOnlyOutcome'], 'unresolved')
                self.assertEqual((retained['jevUnresolvedOnRouted'], retained['reviewerUnresolvedOnRouted']), (1, 0))
                self.assertEqual(retained['results'][0]['jev']['exactDecimals'], source['exactDecimals'])
            for change in ('missing', 'extra', 'numeric-exact', 'rounded-canonical', 'wrong-delta',
                           'boolean-confidence', 'boolean-probability', 'numeric-matches'):
                changed = deepcopy(retained)
                jev = changed['results'][0]['jev']
                if change == 'missing': jev.pop('exactDecimals')
                if change == 'extra': jev['exactDecimals']['unknown'] = '0'
                if change == 'numeric-exact': jev['exactDecimals']['confidence'] = float(confidence)
                if change == 'rounded-canonical': jev['exactDecimals']['confidence'] = confidence
                if change == 'wrong-delta': jev['exactDecimals']['reportedMinusCanonical'] = '0'
                if change == 'boolean-confidence': changed['results'][1]['jev']['confidence'] = True
                if change == 'boolean-probability': changed['results'][1]['jev']['probabilities']['needs_review'] = True
                if change == 'numeric-matches': jev['confidenceComparison']['matches'] = 0
                changed['reportFingerprint'] = fingerprint(changed)
                with self.subTest(display=confidence, change=change), self.assertRaises(MycelError):
                    require_qualification(changed, suite, pipeline)
# TEST-TIER-END tests/test_provider_deployment.py::ProviderDeploymentTests.test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::ProviderDeploymentTests.test_exact_component_report_retains_quality_cost_and_cannot_be_a_same_build_proof
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Exact component report retains quality cost and cannot be a same build proof.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_component_report_retains_quality_cost_and_cannot_be_a_same_build_proof(self):
#         report, suite, pipeline = report_shape()
#         with patch('mycel._credentials.Credentials', side_effect=AssertionError('credential')), \
#                 patch('mycel._coverage.run_checks', side_effect=AssertionError('automatic gate')):
#             record = require_qualification(report, suite, pipeline)
#         self.assertTrue(record['qualified'])
#         self.assertEqual(record['quality'], report['diagnostics'])
#         self.assertEqual(record['report'], report)
#         self.assertEqual((record['usage'], record['cost'], record['elapsedMs']),
#                          (report['usage'], report['cost'], report['elapsedMs']))
#         self.assertEqual(record['reviewerComparison']['commonRoutedCases'], 1)
#         self.assertFalse(record['sameBuildOnDemandProof'] or record['automaticWorkingBuildQualification'])
#         self.assertNotIsInstance(record, OnDemandProofs)
#         self.assertEqual(record['modelCallsMadeByConsumer'], 0)
#         record['report']['results'].clear()
#         self.assertEqual(len(report['results']), 200)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::ProviderDeploymentTests.test_missing_changed_incomplete_empty_routed_or_failing_reports_refuse_deployment
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Missing changed incomplete empty routed or failing reports refuse deployment.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_changed_incomplete_empty_routed_or_failing_reports_refuse_deployment(self):
#         original, suite, pipeline = report_shape()
#         for change in ('missing', 'old-report', 'old-qualification', 'missing-baseline', 'confidence-diagnostic',
#                        'identity', 'environment', 'request-source', 'incomplete', 'empty-routed',
#                        'critical', 'metric', 'file', 'tamper'):
#             report = deepcopy(original)
#             if change == 'missing': report.pop('reportVersion')
#             if change == 'old-report': report['reportVersion'] = 1
#             if change == 'old-qualification': report['qualificationRevision'] = 'mycel-drift-qualification-v1'
#             if change == 'missing-baseline': report['results'][0].pop('jevOnlyOutcome')
#             if change == 'confidence-diagnostic': report['results'][0]['jev']['confidenceComparison']['matches'] = False
#             if change == 'identity': report['pipeline']['reviewRevision'] = 'other-revision'
#             if change == 'environment': report['results'][0]['review']['environmentVersion'] = 'changed-environment'
#             if change == 'request-source': report['results'][0]['review']['identitySources']['instructionVersion'] = 'adapter-echo'
#             if change == 'incomplete': report['incomplete'] = True
#             if change == 'empty-routed':
#                 row = report['results'][0]
#                 row.pop('escalation'); row.pop('review'); row['providerCalls']['review'] = 0; row['attempts'] = 1
#                 report['batches'][0]['reviewCalls'] = 0; report['routedCases'] = 0
#             if change == 'critical': report['results'][1]['actual'] = 'still_supported'
#             if change == 'metric': report['diagnostics']['overall']['meaningfulMisses'] = 99
#             if change == 'file': report['fileHash'] = 'b' * 64
#             if change != 'tamper': report['reportFingerprint'] = fingerprint(report)
#             else: report['build'] = 'tampered'
#             with self.subTest(change=change), self.assertRaises(MycelError) as raised:
#                 require_qualification(report, suite, pipeline)
#             self.assertEqual(raised.exception.code, 'refused')
#         mutations = {'model': 'jev-9.9.9', 'questionVersion': 'changed-question',
#             'choiceOrder': list(reversed(pipeline['choiceOrder'])), 'policyRevision': 'changed-policy',
#             'confidenceFloor': 0.9, 'reviewCommandHash': 'c' * 64, 'reviewRevision': 'changed-adapter',
#             'reviewInstructionVersion': 'changed-instruction', 'reviewEnvironmentVersion': 'changed-environment',
#             'reviewer': {**pipeline['reviewer'], 'provider': 'changed-provider'}}
#         for member, value in mutations.items():
#             report = deepcopy(original); report['pipeline'][member] = value
#             report['reportFingerprint'] = fingerprint(report)
#             with self.subTest(pipeline_member=member), self.assertRaises(MycelError) as raised:
#                 require_qualification(report, suite, pipeline)
#             self.assertEqual(raised.exception.code, 'refused')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::ProviderDeploymentTests.test_explicit_development_seam_binds_reviewed_report_and_current_command_without_calls_or_writes
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Explicit development seam binds reviewed report and current command without calls or writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_explicit_development_seam_binds_reviewed_report_and_current_command_without_calls_or_writes(self):
#         from mycel._classification_payload import ReviewCommandIdentity
#         from mycel._evaluation_live import _pipeline
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary); settings = controlled.settings(root)
#             options = settings.values['drifts']
#             command = ReviewCommandIdentity.inspect(options['review_command'], options['review_revision'], root)
#             report, suite, pipeline = report_shape(_pipeline(settings, command))
#             path = root / 'actual-shape-only.json'; path.write_text(json.dumps(report))
#             expected = sha256(path.read_bytes()).hexdigest()
#             before = {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in root.iterdir()}
#             with patch('mycel._credentials.Credentials', side_effect=AssertionError('credential')), \
#                     patch('mycel._reviewer.run_resolved_reviewer', side_effect=AssertionError('reviewer')):
#                 record = prepare_deployment(settings, suite, path, expected_report_sha256=expected)
#             self.assertEqual(record['retainedReport'], {'path': str(path.resolve()), 'sha256': expected})
#             self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in root.iterdir()}, before)
#             path.write_text(path.read_text() + ' ')
#             with self.assertRaises(MycelError):
#                 prepare_deployment(settings, suite, path, expected_report_sha256=expected)
#             path.write_text(json.dumps(report))
#             linked = root / 'linked-report.json'; linked.symlink_to(path)
#             with self.assertRaises(MycelError) as raised:
#                 prepare_deployment(settings, suite, linked, expected_report_sha256=expected)
#             self.assertEqual(raised.exception.code, 'refused')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::SameRunProviderDeploymentCallerTests.test_deployment_caller_requires_explicit_live_before_provider_operation
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Deployment caller requires explicit live before provider operation.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deployment_caller_requires_explicit_live_before_provider_operation(self):
#         from mycel._provider_deployment import run_provider_deployment_checks
#         with patch('mycel._provider_checks.run_provider_checks', side_effect=AssertionError('provider group')) as producer, \
#                 patch('mycel._credentials.Credentials', side_effect=AssertionError('credential')):
#             for choice in (False, None, 1, 'true'):
#                 with self.subTest(choice=choice), self.assertRaises(MycelError):
#                     run_provider_deployment_checks(None, None, None, None, repository='fixture', build='fictional-unit-build',
#                         implementation_identity='fictional-immutable-unit-source', live=choice)
#             producer.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::SameRunProviderDeploymentCallerTests.test_deployment_caller_consumes_one_same_process_group_and_returns_original_proof_objects
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Deployment caller consumes one same process group and returns original proof objects.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deployment_caller_consumes_one_same_process_group_and_returns_original_proof_objects(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             settings, suite, report, embedding, _ = self.fixture(Path(temporary))
#             proofs, reports, captured, calls = self.run_fixture(settings, suite, report, embedding)
#             self.assertEqual(calls, {'producer': 1, 'embedding': 1, 'drift': 1})
#             self.assertIs(proofs[0], captured[0][0])
#             self.assertIs(reports, captured[0][1])
#             self.assertIs(reports['drift'], report)
#             self.assertEqual([row.status for row in proofs[0].checks], ['passed'] * 3)
#             self.assertEqual(len(proofs[1].checks), 1)
#             self.assertEqual(proofs[1].checks[0].status, 'passed')
#             self.assertEqual(proofs[1].checks[0].requirements, ('MYC-14.22',))
#             self.assertEqual(proofs[0].implementation_identity, proofs[1].implementation_identity)
#             self.assertTrue(reports['deployment']['sameProcessProviderGroupConsumed'])
#             self.assertEqual(reports['deployment']['additionalProviderCallsByConsumer'], 0)
#             self.assertFalse(reports['deployment']['sameBuildOnDemandProof'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::SameRunProviderDeploymentCallerTests.test_deployment_caller_retains_failed_provider_or_consumer_without_retry
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Deployment caller retains failed provider or consumer without retry.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deployment_caller_retains_failed_provider_or_consumer_without_retry(self):
#         for mutation in ('embedding-failure', 'bad-consumer-metric'):
#             with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
#                 settings, suite, report, embedding, _ = self.fixture(Path(temporary))
#                 if mutation == 'embedding-failure':
#                     embedding['passed'] = False
#                 else:
#                     report['diagnostics']['overall']['meaningfulMisses'] = 99
#                     report['reportFingerprint'] = fingerprint(report)
#                 proofs, reports, captured, calls = self.run_fixture(settings, suite, report, embedding)
#                 self.assertEqual(calls, {'producer': 1, 'embedding': 1,
#                                        'drift': 0 if mutation == 'embedding-failure' else 1})
#                 self.assertIs(proofs[0], captured[0][0])
#                 self.assertIs(reports, captured[0][1])
#                 self.assertEqual(proofs[1].checks[0].status, 'failed')
#                 self.assertNotIn('deployment', reports)
#                 if mutation == 'bad-consumer-metric':
#                     self.assertTrue(all(row.status == 'passed' for row in proofs[0].checks))
#                     self.assertIs(reports['drift'], report)
#                 else:
#                     self.assertEqual(proofs[0].checks[0].status, 'failed')
#                     self.assertNotIn('drift', reports)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provider_deployment.py::SameRunProviderDeploymentCallerTests.test_deployment_caller_rejects_changed_settings_or_reviewer_identity_after_group
# Reason: Narrower case removed from this family after retaining test_exact_wire_decimals_survive_report_json_and_drive_jev_only_routing. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Deployment caller rejects changed settings or reviewer identity after group.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provider_deployment.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_deployment_caller_rejects_changed_settings_or_reviewer_identity_after_group(self):
#         for mutation in ('settings', 'reviewer'):
#             with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
#                 settings, suite, report, embedding, adapter = self.fixture(Path(temporary))
#                 def changed():
#                     path = settings.file if mutation == 'settings' else adapter
#                     if mutation == 'settings':
#                         path.write_text(path.read_text() + '\nconfidence_floor=0.8\n')
#                     else:
#                         path.write_text(path.read_text() + '\n# changed after controlled provider group\n')
#                 proofs, reports, captured, calls = self.run_fixture(settings, suite, report, embedding,
#                                                                    after_group=changed)
#                 self.assertEqual(calls, {'producer': 1, 'embedding': 1, 'drift': 1})
#                 self.assertTrue(all(row.status == 'passed' for row in proofs[0].checks))
#                 self.assertEqual(proofs[1].checks[0].status, 'failed')
#                 self.assertIs(proofs[0], captured[0][0])
#                 self.assertIs(reports['drift'], report)
#                 self.assertNotIn('deployment', reports)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
