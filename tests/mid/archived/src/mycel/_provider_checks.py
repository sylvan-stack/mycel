"""Explicit genuine on-demand operations, kept outside automatic discovery.

No serialized report is accepted as a proof. The caller retains the returned
live OnDemandProofs object in this process for the exact immutable Build.
Component profile reports remain separately reviewable provenance.
"""
from __future__ import annotations



import unittest

from ._coverage import run_on_demand_checks
from ._errors import MycelError


def run_provider_checks(settings, suite, *, repository, build, implementation_identity,
                        live=False):
    """Execute only after explicit approval of this concrete suite and budgets.

    This helper itself asks for no approval and performs no operation on import.
    The caller owns immutable source/fixture/profile binding and report retention.
    """
    if live is not True:
        raise MycelError('refused', 'Provider acceptance requires explicit live selection.')
    if not isinstance(implementation_identity, str) or not implementation_identity:
        raise MycelError('invalid_input', 'Provider acceptance requires an immutable implementation identity.')
    # Avoid spending quota on a corpus which cannot meet even the local floors.
    from ._evaluation_drift import _fingerprint
    from ._provider_qualification import CRITICAL_CATEGORIES
    groups = {}
    for case in suite.drifts:
        groups.setdefault(_fingerprint(case), []).append(case)
    if (len(groups) < 200 or sum(any(case.critical for case in group) for group in groups.values()) < 50
            or sum(any(case.unchanged for case in group) for group in groups.values()) < 50
            or any(len({case.expect for case in group}) != 1 for group in groups.values())
            or not CRITICAL_CATEGORIES <= {tag for case in suite.drifts for tag in case.critical}):
        raise MycelError('refused', 'The versioned qualification set does not meet the distinct labelled coverage floors.')
    settings.require_valid(require_store=False)
    settings.require_current()
    from ._classification_payload import ReviewCommandIdentity
    from ._credentials import Credentials, CredentialUnavailable
    from ._safeguards import InvocationPolicy
    options = settings.values['drifts']
    if not options.get('review_command') or not ReviewCommandIdentity.inspect(
            options['review_command'], options['review_revision'], settings._home or '/').available:
        raise MycelError('refused', 'Configured reviewer readiness is required before any paid acceptance check.')
    try:
        Credentials(settings, InvocationPolicy('evaluate', kind='drift', live=True)).require_jev_key()
    except CredentialUnavailable:
        raise MycelError('refused', 'Jev credential readiness is required before any paid acceptance check.') from None
    reports = {}
    class ProviderAcceptance(unittest.TestCase):
        pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
        def test_fixed_embedding_compatibility(self):
            from ._embedding_live import run_embedding_live_check
            report = run_embedding_live_check(settings, build=build, live=True)
            reports['embedding'] = report
            self.assertTrue(report['passed'], 'Actual fixed embedding compatibility did not pass.')

        def test_configured_drift_live_pipeline(self):
            self.assertTrue(reports.get('embedding', {}).get('passed'), 'Embedding compatibility did not pass; no Drift qualification calls were sent.')
            from ._evaluation_live import run_live_drift_evaluation
            report = run_live_drift_evaluation(suite, settings, repository=repository, build=build)
            reports['drift'] = report
            self.assertEqual(report['providerExecution'], 'production-defaults')
            self.assertFalse(report['incomplete'])
            self.assertEqual(report['cases'], len(suite.drifts))
            self.assertTrue(report['qualified'], 'Actual configured provider-profile qualification did not pass.')

        def test_same_run_finite_profile_qualification(self):
            report = reports.get('drift')
            self.assertIsNotNone(report, 'The same process did not complete its real live Drift evaluation.')
            self.assertTrue(report['qualified'])
            self.assertEqual(report['fileHash'], suite.file_hash)
            self.assertEqual(report['build'], build)
            self.assertFalse(report['profileQualificationIsSameBuildProof'])
    checks = ((ProviderAcceptance('test_fixed_embedding_compatibility'), 'live', ('MYC-13.9',)),
              (ProviderAcceptance('test_configured_drift_live_pipeline'), 'live', ('MYC-13.19',)),
              (ProviderAcceptance('test_same_run_finite_profile_qualification'), 'eval', ('MYC-13.20',)))
    proofs = run_on_demand_checks(checks, implementation_identity=implementation_identity)
    return proofs, reports
