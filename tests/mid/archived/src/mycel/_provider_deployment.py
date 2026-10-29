# Mid-tier source from src/mycel/_provider_deployment.py; see MID_TIER.md.
# Shared helpers and refusal entry points remain at the original path.

# TEST-TIER-DISABLED-BEGIN src/mycel/_provider_deployment.py::ProviderDeploymentAcceptance.test_same_run_provider_qualification_required_for_deployment
#         def test_same_run_provider_qualification_required_for_deployment(self):
#             self.assertIs(type(provider_proofs), OnDemandProofs)
#             self.assertEqual(provider_proofs.implementation_identity, implementation_identity)
#             self.assertEqual(len(provider_proofs.checks), len(expected_checks))
#             for check, expected in zip(provider_proofs.checks, expected_checks, strict=True):
#                 self.assertIs(type(check), CheckResult)
#                 self.assertEqual((check.name, check.kind, check.requirements), expected)
#                 self.assertEqual(check.status, 'passed', 'The same provider group did not complete successfully.')
#             self.assertIs(type(reports), dict)
#             actual_drift_report = reports.get('drift')
#             embedding = reports.get('embedding')
#             self.assertIsInstance(embedding, dict)
#             self.assertIs(embedding.get('passed'), True)
#             self.assertIs(embedding.get('live'), True)
#             self.assertEqual(embedding.get('providerExecution'), 'production-defaults')
#             self.assertEqual(embedding.get('build'), build)
#             self.assertIsInstance(actual_drift_report, dict)
#             self.assertEqual(actual_drift_report.get('build'), build)
#             self.assertEqual(actual_drift_report.get('repository'), repository)
#             settings.require_valid(require_store=False)
#             settings.require_current()
#             options = settings.values['drifts']
#             _require(bool(options.get('review_command')))
#             command = ReviewCommandIdentity.inspect(options['review_command'],
#                 options['review_revision'], settings._home or '/')
#             _require(command.available)
#             from ._evaluation_live import _pipeline
#             record = require_qualification(actual_drift_report, suite, _pipeline(settings, command))
#             settings.require_current()
#             _require(command == ReviewCommandIdentity.inspect(options['review_command'],
#                 options['review_revision'], settings._home or '/'))
#             # This record is provenance only. Only the executor below creates
#             # this consumer's actual live proof, including when it fails.
#             reports['deployment'] = {**record, 'sameProcessProviderGroupConsumed': True,
#                 'reportObjectOrigin': 'trusted-same-process-group-caller',
#                 'implementationIdentity': implementation_identity,
#                 'providerCheckNames': [row.name for row in provider_proofs.checks],
#                 'additionalProviderCallsByConsumer': 0}
# TEST-TIER-DISABLED-END src/mycel/_provider_deployment.py::ProviderDeploymentAcceptance.test_same_run_provider_qualification_required_for_deployment

# TEST-TIER-IMPORTS-BEGIN src/mycel/_provider_deployment.py:8
# from decimal import Decimal, InvalidOperation
# TEST-TIER-IMPORTS-END src/mycel/_provider_deployment.py:8

# TEST-TIER-IMPORTS-BEGIN src/mycel/_provider_deployment.py:196
#     from ._coverage import CheckResult, OnDemandProofs, run_on_demand_checks
# TEST-TIER-IMPORTS-END src/mycel/_provider_deployment.py:196

raise RuntimeError("Mid-tier checks require an explicitly requested testing task; see MID_TIER.md.")
