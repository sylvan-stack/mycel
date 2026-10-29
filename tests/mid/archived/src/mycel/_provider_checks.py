# Mid-tier source from src/mycel/_provider_checks.py; see MID_TIER.md.
# Shared helpers and refusal entry points remain at the original path.

# TEST-TIER-DISABLED-BEGIN src/mycel/_provider_checks.py::ProviderAcceptance.test_fixed_embedding_compatibility
#         def test_fixed_embedding_compatibility(self):
#             from ._embedding_live import run_embedding_live_check
#             report = run_embedding_live_check(settings, build=build, live=True)
#             reports['embedding'] = report
#             self.assertTrue(report['passed'], 'Actual fixed embedding compatibility did not pass.')
# TEST-TIER-DISABLED-END src/mycel/_provider_checks.py::ProviderAcceptance.test_fixed_embedding_compatibility

# TEST-TIER-DISABLED-BEGIN src/mycel/_provider_checks.py::ProviderAcceptance.test_configured_drift_live_pipeline
#         def test_configured_drift_live_pipeline(self):
#             self.assertTrue(reports.get('embedding', {}).get('passed'), 'Embedding compatibility did not pass; no Drift qualification calls were sent.')
#             from ._evaluation_live import run_live_drift_evaluation
#             report = run_live_drift_evaluation(suite, settings, repository=repository, build=build)
#             reports['drift'] = report
#             self.assertEqual(report['providerExecution'], 'production-defaults')
#             self.assertFalse(report['incomplete'])
#             self.assertEqual(report['cases'], len(suite.drifts))
#             self.assertTrue(report['qualified'], 'Actual configured provider-profile qualification did not pass.')
# TEST-TIER-DISABLED-END src/mycel/_provider_checks.py::ProviderAcceptance.test_configured_drift_live_pipeline

# TEST-TIER-DISABLED-BEGIN src/mycel/_provider_checks.py::ProviderAcceptance.test_same_run_finite_profile_qualification
#         def test_same_run_finite_profile_qualification(self):
#             report = reports.get('drift')
#             self.assertIsNotNone(report, 'The same process did not complete its real live Drift evaluation.')
#             self.assertTrue(report['qualified'])
#             self.assertEqual(report['fileHash'], suite.file_hash)
#             self.assertEqual(report['build'], build)
#             self.assertFalse(report['profileQualificationIsSameBuildProof'])
# TEST-TIER-DISABLED-END src/mycel/_provider_checks.py::ProviderAcceptance.test_same_run_finite_profile_qualification


raise RuntimeError("Mid-tier checks require an explicitly requested testing task; see MID_TIER.md.")
