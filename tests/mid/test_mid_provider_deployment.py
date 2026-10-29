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
