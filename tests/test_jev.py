"""Jev contract proofs using public stand-ins; no provider or real credential."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mycel._classification_payload import (CHOICE_CRITERIA, INSTRUCTION, LABELS,
    CurrentSelection, DecisionPayload, DecisionText, ancestor_context, governor_context)
from mycel._coverage import proves
from mycel._credentials import Credentials, Secret
from mycel._errors import MycelError
from mycel._evidence import exact_comparison, snapshot
from mycel._jev import (ENDPOINT, HTTPResult, JevClient, JevFailure, JevLimits,
                        JevRequest, MAX_RESPONSE_BYTES, _https_request, _retry_after,
                        route_response, validate_response)
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress
from test_classification_payload import fixture, reviewed


KEY = "public-jev-credential-sentinel"


def response(*, label="still_supported", top=0.8, confidence=0.7, model="jev-1.13.0"):
    probabilities = {member: 0.1 for member in LABELS}
    probabilities[label] = top
    return {"model": model, "answers": {"dependency": {"type": "choice", "choice": label,
            "probabilities": probabilities, "confidence": confidence}},
            "usage": {"input_tokens": 100, "output_tokens": 8}}


def http(value=None, *, status=200, body=None, headers=None):
    return HTTPResult(status, body if body is not None else json.dumps(value or response()).encode(), headers or {})


class JevTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        path = self.root / "config.toml"
        path.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n')
        self.settings = load_settings(path=path, home=self.root)
        self.key_reads, self.requests, self.guards = [], [], []
        self.decision = reviewed(fixture()[2])
        # Every network test explicitly installs a fake HTTPSConnection.
        self.network = patch("http.client.HTTPSConnection",
                             side_effect=AssertionError("Jev proofs cannot reach a provider"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def credentials(self, policy, *, present=True, runner=None):
        def read(argv, **kwargs):
            self.key_reads.append((argv, kwargs))
            return CompletedChild(0 if present else 1, (KEY + "\n").encode(), KEY.encode(), 0.0)
        return Credentials(self.settings, policy, home=self.root, _runner=runner or read)

    def transport(self, body, key, **kwargs):
        self.assertEqual(key.reveal(), KEY)
        self.requests.append((body, kwargs))
        return http()

    def client(self, *, limits=None, policy=None, present=True, transport=None, runner=None):
        policy = policy or InvocationPolicy("classify")
        return JevClient(self.credentials(policy, present=present, runner=runner), policy,
                         limits=limits, _transport=transport or self.transport)

    def guard(self):
        self.guards.append(len(self.key_reads))

    def classify(self, client=None, decision=None, **kwargs):
        return (client or self.client()).classify(decision or self.decision,
            deadline=kwargs.pop("deadline", time.monotonic() + 2),
            before_call=kwargs.pop("before_call", self.guard), **kwargs)

    @proves("MYC-14.1", "MYC-14.12")
    def test_complete_single_state_fixed_choice_order_pinned_model_and_independent_keychain(self):
        with patch.dict(os.environ, {"JEV_API_KEY": "wrong", "VOYAGE_API_KEY": "wrong",
                                    "MYCEL_JEV_ENDPOINT": "wrong"}):
            outcome = self.classify()
        request = json.loads(self.requests[0][0])
        self.assertEqual(set(request), {"state", "model", "questions"})
        self.assertEqual(request["state"], self.decision.as_dict())
        self.assertEqual(request["model"], "jev-1.13.0")
        self.assertEqual(set(request["questions"]), {"dependency"})
        question = request["questions"]["dependency"]
        self.assertEqual(question, {"type": "choice", "instructions": INSTRUCTION,
            "criteria": dict(zip(LABELS, CHOICE_CRITERIA, strict=True))})
        self.assertEqual(tuple(question["criteria"]), LABELS)
        self.assertEqual(self.guards, [0, 1])
        argv, acquisition = self.key_reads[0]
        self.assertEqual(argv[:6], ("/usr/bin/security", "find-generic-password", "-s", "mycel", "-a", "jev-api-key"))
        self.assertEqual(argv[-1], str(self.root / "Library/Keychains/login.keychain-db"))
        self.assertLessEqual(acquisition["timeout_seconds"], 2)
        self.assertEqual(outcome.judgement, "still_supported")
        self.assertNotIn(KEY, repr(outcome) + json.dumps(outcome.as_dict()) + self.requests[0][0].decode())
        self.assertEqual(ENDPOINT, "https://api.typesafe.ai/v1/systemone")

    @proves("MYC-14.1")
    def test_tiny_negation_rewrite_and_related_pair_have_identical_decision_opportunity(self):
        client = self.client(limits=JevLimits(max_input_bytes=100000))
        for current, kind in ((b'return "reader" != True\n', 'declared'),
                              (b'return "reader"\n' * 1000, 'asserted'),
                              (b'return "reader" != True\n', 'related')):
            decision = fixture(current=current)[2]
            value = decision.as_dict()
            value['baseline']['kind'] = kind
            decision = DecisionPayload(value)
            self.assertEqual(self.classify(client, decision).judgement, "still_supported")
            self.assertEqual(json.loads(self.requests[-1][0])['state'], decision.as_dict())
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(len(self.key_reads), 1)

    @proves("MYC-14.1", "MYC-14.20")
    def test_governor_ancestor_removal_and_away_states_transmit_complete_exact_evidence(self):
        manifest, _, base = fixture()
        ancestor_bytes = b'Complete ancestor evidence including all claim context.\n'
        ancestor = snapshot(ancestor_bytes, comparison=exact_comparison(ancestor_bytes, 'code_text'),
            place=SourceAddress('owner', 'artifact', 'guide.md', 'Overview'))
        contexts = [ancestor_context(DecisionText.create(ancestor.evidence, ancestor.source)),
            governor_context(manifest, tuple(DecisionText(member) for member in base.payload['before']),
                             CurrentSelection(base.payload['current']), 'stale')]
        for state in ('present', 'deleted', 'away'):
            value = self.decision.as_dict()
            value['context'] = contexts
            if state != 'present':
                value['current'] = CurrentSelection.create(state, value['current']['place'], 'chunk').as_dict()
            decision = DecisionPayload(value)
            outcome = self.classify(decision=decision)
            self.assertEqual(json.loads(self.requests[-1][0])['state'], decision.as_dict())
            self.assertEqual(outcome.decision.payload['before'], self.decision.payload['before'])
            self.assertEqual(outcome.decision.payload['current']['state'], state)
            self.assertEqual(len(outcome.decision.payload['context']), 2)

    @proves("MYC-14.1", "MYC-14.17")
    def test_floor_equality_completes_both_categorical_labels_and_retains_routing_identity(self):
        for label in ("needs_review", "still_supported"):
            with self.subTest(label=label):
                outcome = self.classify(self.client(transport=lambda *a, **k: http(response(label=label))))
                self.assertEqual(outcome.judgement, label)
                self.assertEqual(outcome.status, "complete")
                self.assertEqual(outcome.response.confidence, Decimal("0.7"))
                self.assertEqual(outcome.as_dict()['routing'],
                    {'revision': 'mycel-drift-routing-v2', 'confidenceFloor': '0.7'})
                self.assertEqual(outcome.as_dict()['model'], 'jev-1.13.0')
                with self.assertRaises(MycelError):
                    outcome.reviewer_handoff(timeout_ms=1)

    @proves("MYC-14.17")
    def test_rounded_reported_confidence_is_retained_without_rejecting_valid_probabilities(self):
        value = response(label='needs_review', top=0.99, confidence=0.98)
        value['answers']['dependency']['probabilities'] = {
            'needs_review': 0.99, 'still_supported': 0.01, 'insufficient_evidence': 0.0}
        outcome = self.classify(self.client(transport=lambda *a, **k: http(value)))
        self.assertEqual((outcome.status, outcome.judgement), ('complete', 'needs_review'))
        self.assertEqual(outcome.response.confidence, Decimal('0.985'))
        self.assertEqual(outcome.response.reported_confidence, Decimal('0.98'))
        self.assertEqual(dict(outcome.response.probabilities), {
            'needs_review': Decimal('0.99'), 'still_supported': Decimal('0.01'),
            'insufficient_evidence': Decimal('0.0')})
        evidence = outcome.as_dict()['jev']
        self.assertEqual(evidence['confidenceComparison'],
            {'matches': False, 'reportedMinusCanonical': -0.005})
        self.assertEqual((evidence['confidence'], evidence['reportedConfidence']), (0.985, 0.98))

    @proves("MYC-14.17")
    def test_canonical_confidence_controls_both_sides_of_floor_despite_reported_value(self):
        for label in ('needs_review', 'still_supported'):
            value = response(label=label, top=0.8, confidence=0.69)
            outcome = self.classify(self.client(transport=lambda *a, **k: http(value)))
            self.assertEqual((outcome.response.confidence, outcome.response.reported_confidence),
                             (Decimal('0.7'), Decimal('0.69')))
            self.assertEqual((outcome.status, outcome.judgement), ('complete', label))
        value = response(top=0.79, confidence=0.99)
        value['answers']['dependency']['probabilities']['needs_review'] = 0.11
        outcome = self.classify(self.client(transport=lambda *a, **k: http(value)))
        self.assertEqual(outcome.response.confidence, Decimal('0.685'))
        self.assertEqual(outcome.response.reported_confidence, Decimal('0.99'))
        self.assertEqual((outcome.status, outcome.reason, outcome.judgement),
                         ('needs_llm_review', 'jev_low_confidence', None))

    @proves("MYC-14.17", "MYC-14.20")
    def test_low_confidence_tied_maximum_and_insufficient_evidence_route_complete_review(self):
        cases = []
        low = response(top=0.79, confidence=0.685)
        low['answers']['dependency']['probabilities']['needs_review'] = 0.11
        cases.append((low, 'jev_low_confidence'))
        tied = response(top=0.5, confidence=0.25)
        tied['answers']['dependency']['probabilities'] = {'needs_review': 0.5,
            'insufficient_evidence': 0, 'still_supported': 0.5}
        cases.append((tied, 'jev_tied'))
        cases.append((response(label='insufficient_evidence'), 'insufficient_evidence'))
        for value, reason in cases:
            outcome = self.classify(self.client(transport=lambda *a, **k: http(value)))
            self.assertEqual(outcome.status, 'needs_llm_review')
            self.assertEqual(outcome.reason, reason)
            self.assertIsNone(outcome.judgement)
            handoff = outcome.reviewer_handoff(timeout_ms=123)
            self.assertIs(handoff.decision, self.decision)
            self.assertEqual(handoff.request.payload['payload'], self.decision.payload)
            self.assertEqual(handoff.request.payload['inputHash'], self.decision.input_hash)
            self.assertEqual(handoff.request.payload['budget']['timeoutMs'], 123)
            self.assertTrue(handoff.request.transmitted_bytes.endswith(b'\n'))
            self.assertEqual(handoff.request.payload['protocol'], 1)
            self.assertEqual(outcome.as_dict()['jev']['label'], value['answers']['dependency']['choice'])

    @proves("MYC-14.17")
    def test_configured_floor_and_routing_revision_are_taken_from_exact_decision(self):
        value = self.decision.as_dict()
        value['routing'] = {'revision': 'mycel-drift-routing-tuned-v2', 'confidenceFloor': '0.71'}
        decision = DecisionPayload(value)
        outcome = self.classify(decision=decision)
        self.assertEqual(outcome.reason, 'jev_low_confidence')
        self.assertEqual(outcome.as_dict()['routing'], value['routing'])
        self.assertNotEqual(outcome.decision.input_hash, self.decision.input_hash)

    @proves("MYC-14.17")
    def test_all_known_probability_keys_finite_bounds_highest_label_type_usage_and_model_are_strict(self):
        mutations = [
            lambda v: v.update(model='jev-latest'),
            lambda v: v.update(model='jev-1.14.0'),
            lambda v: v.pop('model'),
            lambda v: v['answers'].update(unrelated=v['answers']['dependency']),
            lambda v: v['answers']['dependency'].update(type='noul'),
            lambda v: v['answers']['dependency'].update(choice='unknown'),
            lambda v: v['answers']['dependency'].update(choice=[]),
            lambda v: v['answers']['dependency'].update(choice='needs_review'),
            lambda v: v['answers']['dependency'].pop('confidence'),
            lambda v: v['answers']['dependency'].update(confidence=True),
            lambda v: v['answers']['dependency'].update(confidence='0.7'),
            lambda v: v['answers']['dependency'].update(confidence=-0.1),
            lambda v: v['answers']['dependency'].update(confidence=1.1),
            lambda v: v['answers']['dependency']['probabilities'].update(unknown=0),
            lambda v: v['answers']['dependency']['probabilities'].pop('needs_review'),
            lambda v: v['answers']['dependency']['probabilities'].update(needs_review=True),
            lambda v: v['answers']['dependency']['probabilities'].update(needs_review=-0.1),
            lambda v: v['answers']['dependency']['probabilities'].update(still_supported=1.1),
            lambda v: v['answers']['dependency']['probabilities'].update(needs_review=0.2),
            lambda v: v.update(usage={'input_tokens': True, 'output_tokens': 0}),
            lambda v: v.update(usage={'input_tokens': -1, 'output_tokens': 0}),
            lambda v: v.pop('usage'),
        ]
        for mutate in mutations:
            value = response()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(JevFailure) as caught:
                validate_response(http(value), model='jev-1.13.0')
            self.assertEqual(caught.exception.code, 'provider_result_invalid')
            self.assertFalse(caught.exception.retryable)

    @proves("MYC-14.17")
    def test_exact_decimal_total_and_confidence_tolerance_boundaries(self):
        body = json.dumps(response()).encode()
        for member, accepted in ((b'0.100001', True), (b'0.1000010000001', False),
                                  (b'0.1000010000000000000000000001', False),
                                  (b'0.099999', True), (b'0.0999989999999', False)):
            candidate = body.replace(b'"needs_review": 0.1', b'"needs_review": ' + member)
            if accepted:
                validate_response(http(body=candidate), model='jev-1.13.0')
            else:
                with self.assertRaises(JevFailure):
                    validate_response(http(body=candidate), model='jev-1.13.0')
        for member in (b'0.700001', b'0.7000010000001', b'0.7000010000000000000000000001',
                       b'0.699999', b'0.6999989999999'):
            candidate = body.replace(b'"confidence": 0.7', b'"confidence": ' + member)
            result = validate_response(http(body=candidate), model='jev-1.13.0')
            self.assertEqual(result.confidence, Decimal('0.7'))
            self.assertEqual(result.reported_confidence, Decimal(member.decode()))
            self.assertFalse(result.as_dict()['confidenceComparison']['matches'])

    @proves("MYC-14.17")
    def test_duplicate_json_keys_nonfinite_numbers_nonutf8_extra_types_and_byte_overflow_fail(self):
        valid = json.dumps(response()).encode()
        invalid = [valid.replace(b'"model":', b'"model":"jev-1.13.0","model":'),
            valid.replace(b'"needs_review": 0.1', b'"needs_review":0.1,"needs_review":0.1'),
            b'\xff', b'[]', b'null', b'{' + b' ' * MAX_RESPONSE_BYTES + b'}']
        for number in (b'NaN', b'Infinity', b'-Infinity', b'1e10000', b'1e-10000000000'):
            invalid.append(valid.replace(b'"confidence": 0.7', b'"confidence": ' + number))
            invalid.append(valid.replace(b'"needs_review": 0.1', b'"needs_review": ' + number))
        for body in invalid:
            with self.subTest(size=len(body)), self.assertRaises(JevFailure) as caught:
                validate_response(http(body=body), model='jev-1.13.0')
            self.assertEqual(caught.exception.code, 'provider_result_invalid')

    @proves("MYC-14.17")
    def test_distribution_evidence_is_immutable_and_cannot_be_relabelled_or_given_wrong_model(self):
        result = validate_response(http(), model='jev-1.13.0')
        with self.assertRaises(TypeError):
            result.probabilities['still_supported'] = Decimal('0')
        with self.assertRaises(JevFailure):
            replace(result, label='needs_review')
        with self.assertRaises(JevFailure):
            replace(result, tied=True)
        for invalid in (Decimal('NaN'), Decimal('Infinity'), Decimal('-0.1'), Decimal('1.1'), True):
            with self.assertRaises(JevFailure):
                replace(result, reported_confidence=invalid)
        with self.assertRaises(JevFailure):
            replace(result, confidence=Decimal('0.8'))
        with self.assertRaises(JevFailure):
            replace(result, confidence=Decimal('0.7000000000000000000000000001'))
        self.assertEqual(result.reported_confidence, Decimal('0.7'))
        self.assertEqual(result.as_dict()['confidenceComparison'],
                         {'matches': True, 'reportedMinusCanonical': 0.0})
        changed = self.decision.as_dict()
        changed['models']['jev']['model'] = 'jev-1.14.0'
        with self.assertRaises(JevFailure):
            route_response(DecisionPayload(changed), result)

    @proves("MYC-14.17")
    def test_derived_fraction_invariant_does_not_clamp_or_renormalize_nearly_uniform_values(self):
        value = response(label='still_supported', confidence=0)
        value['answers']['dependency']['probabilities'] = {label: 0.333333 for label in LABELS}
        with self.assertRaises(JevFailure) as caught:
            validate_response(http(value), model='jev-1.13.0')
        self.assertEqual(caught.exception.code, 'provider_result_invalid')

    @proves("MYC-14.12", "MYC-14.20")
    def test_complete_http_body_cap_bypasses_before_credential_and_never_truncates(self):
        body = JevRequest(self.decision).body
        too_small = self.client(limits=JevLimits(max_input_bytes=len(body) - 1))
        outcome = self.classify(too_small)
        self.assertEqual(outcome.reason, 'jev_input_too_large')
        self.assertEqual(self.key_reads, [])
        self.assertEqual(self.requests, [])
        self.assertEqual(outcome.reviewer_handoff(timeout_ms=100).request.payload['payload'], self.decision.payload)
        self.assertEqual(self.classify(self.client(limits=JevLimits(max_input_bytes=len(body)))).status, 'complete')
        self.assertEqual(self.requests[0][0], body)
        large = reviewed(fixture(current=b'\xe2\x84\xab' * 10000)[2])
        large_outcome = self.classify(decision=large)
        self.assertEqual(large_outcome.reason, 'jev_input_too_large')
        self.assertEqual(large_outcome.reviewer_handoff(timeout_ms=100).request.payload['payload'], large.payload)
        self.assertEqual(len(self.requests), 1)

    @proves("MYC-14.20")
    def test_reviewer_byte_budget_counts_lf_and_unconfigured_review_keeps_complete_unresolved_input(self):
        outcome = self.classify(self.client(limits=JevLimits(max_input_bytes=1)))
        request = outcome.reviewer_handoff(timeout_ms=100).request
        length = len(request.transmitted_bytes)
        self.assertEqual(outcome.reviewer_handoff(timeout_ms=100, max_input_bytes=length).request.transmitted_bytes,
                         request.transmitted_bytes)
        blocked = outcome.reviewer_handoff(timeout_ms=100, max_input_bytes=length - 1)
        self.assertEqual((blocked.status, blocked.reason), ('error', 'review_input_too_large'))
        self.assertIsNone(blocked.request)
        self.assertIs(blocked.decision, self.decision)
        unconfigured = self.classify(self.client(limits=JevLimits(max_input_bytes=1)), fixture()[2])
        handoff = unconfigured.reviewer_handoff(timeout_ms=1)
        self.assertEqual(handoff.reason, 'reviewer_unconfigured')
        self.assertIsNone(handoff.request)
        self.assertEqual(handoff.decision.canonical_bytes, fixture()[2].canonical_bytes)
        self.assertEqual(self.key_reads, [])

    @proves("MYC-14.12", "MYC-14.20")
    def test_explicit_provider_context_refusal_routes_complete_review_but_other_422_is_terminal(self):
        for status in (400, 413, 422):
            outcome = self.classify(self.client(transport=lambda *a, **k:
                http(status=status, body=b'{"error":{"code":"context_length_exceeded","message":"' + KEY.encode() + b'"}}')))
            self.assertEqual(outcome.reason, 'jev_context_refused')
            self.assertEqual(outcome.reviewer_handoff(timeout_ms=1).request.payload['payload'], self.decision.payload)
            self.assertNotIn(KEY, json.dumps(outcome.as_dict()))
        for body in (b'{"detail":"context validation failed"}', b'{"error":{"code":[]}}',
                     b'{"error":{"code":"invalid_request"}}', b'not JSON'):
            with self.assertRaises(JevFailure) as caught:
                self.classify(self.client(transport=lambda *a, **k: http(status=422, body=body)))
            self.assertEqual(caught.exception.code, 'invalid_request')

    @proves("MYC-14.12")
    def test_authentication_invalid_request_invalid_result_are_terminal_and_single_call(self):
        for status, code in ((401, 'authentication'), (403, 'authentication'),
                             (422, 'invalid_request'), (302, 'invalid_request'), (200, 'provider_result_invalid')):
            calls = []
            def transport(*a, **k):
                calls.append(1)
                return http(status=status, body=KEY.encode())
            with self.assertRaises(JevFailure) as caught:
                self.classify(self.client(transport=transport))
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(caught.exception.retryable)
            self.assertNotIn(KEY, str(caught.exception) + json.dumps(caught.exception.as_dict()))
            self.assertEqual(calls, [1])
        with self.assertRaises(JevFailure) as caught:
            self.classify(self.client(present=False))
        self.assertEqual(caught.exception.code, 'authentication')
        self.assertEqual(self.requests, [])

    @proves("MYC-14.12")
    def test_transport_faults_are_typed_transient_with_retry_after_but_no_internal_retry(self):
        for status, code in ((429, 'rate_limited'), (529, 'unavailable'), (500, 'unavailable'), (599, 'unavailable')):
            with self.assertRaises(JevFailure) as caught:
                self.classify(self.client(transport=lambda *a, **k:
                    http(status=status, body=KEY.encode(), headers={'Retry-After': '3'})))
            self.assertEqual(caught.exception.code, code)
            self.assertTrue(caught.exception.retryable)
            self.assertEqual(caught.exception.retry_after_seconds, 3)
        for error, code in ((OSError(KEY), 'connection'), (TimeoutError(KEY), 'timeout'), (RuntimeError(KEY), 'invalid_request')):
            def fail(*a, **k):
                raise error
            with self.assertRaises(JevFailure) as caught:
                self.classify(self.client(transport=fail))
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(KEY, str(caught.exception))
        self.assertIsNone(_retry_after({'Retry-After': '99999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999'}))
        self.assertIsNone(_retry_after({'Retry-After': 'NaN'}))
        with self.assertRaises(ValueError):
            JevFailure('authentication', retry_after_seconds=1)

    @proves("MYC-14.12")
    def test_finite_settings_limits_clamp_keychain_and_transport_to_same_remaining_deadline(self):
        limits = JevLimits.from_settings(self.settings)
        self.assertEqual(limits, JevLimits())
        for timeout in (True, 0, -1, float('nan'), float('inf')):
            with self.assertRaises(MycelError):
                JevLimits(timeout_seconds=timeout)
        for size in (True, 0, -1, 1.2):
            with self.assertRaises(MycelError):
                JevLimits(max_input_bytes=size)
        started = time.monotonic()
        self.classify(self.client(limits=JevLimits(timeout_seconds=0.5)), deadline=started + 10)
        self.assertLessEqual(self.requests[-1][1]['deadline'], started + 0.51)
        self.assertLessEqual(self.key_reads[-1][1]['timeout_seconds'], 0.5)
        self.assertGreater(self.key_reads[-1][1]['timeout_seconds'], 0)

    @proves("MYC-14.12")
    def test_only_explicit_classify_and_live_drift_evaluation_authorize_jev(self):
        for policy in (InvocationPolicy('ingest'), InvocationPolicy('search'), InvocationPolicy('read'),
                       InvocationPolicy('drifts'), InvocationPolicy('evaluate', kind='drift'),
                       InvocationPolicy('classify', dry_run=True)):
            with self.assertRaises(MycelError):
                self.classify(self.client(policy=policy))
        self.assertEqual(self.key_reads, [])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.classify(self.client(policy=InvocationPolicy('evaluate', kind='drift', live=True))).status,
                         'complete')

    @proves("MYC-14.12")
    def test_expired_cancelled_missing_input_and_failed_guard_do_not_acquire_credentials(self):
        with self.assertRaises(JevFailure) as caught:
            self.classify(deadline=time.monotonic() - 1)
        self.assertEqual(caught.exception.code, 'timeout')
        with self.assertRaises(JevFailure) as caught:
            self.classify(cancelled=lambda: True)
        self.assertEqual(caught.exception.code, 'cancelled')
        with self.assertRaises(MycelError):
            self.client().classify(None, deadline=time.monotonic() + 1, before_call=self.guard)
        def obsolete():
            raise MycelError('invalid_input', 'The exact pair is obsolete.')
        with self.assertRaises(MycelError):
            self.classify(before_call=obsolete)
        self.assertEqual(self.key_reads, [])
        self.assertEqual(self.requests, [])

    @proves("MYC-14.12")
    def test_guard_after_keychain_and_acquisition_deadline_prevent_transmission(self):
        def second_guard():
            if self.key_reads:
                raise MycelError('invalid_input', 'The exact pair is obsolete.')
        with self.assertRaises(MycelError):
            self.classify(before_call=second_guard)
        self.assertEqual(self.requests, [])
        def read(argv, **kwargs):
            time.sleep(0.02)
            return CompletedChild(0, (KEY + '\n').encode(), b'', 0.02)
        with self.assertRaises(JevFailure) as caught:
            self.classify(self.client(limits=JevLimits(timeout_seconds=0.01), runner=read))
        self.assertEqual(caught.exception.code, 'timeout')
        self.assertEqual(self.requests, [])

    @proves("MYC-14.12")
    def test_fixed_https_endpoint_bearer_tls_response_limit_no_proxy_or_tls_secret_log(self):
        calls, closed = [], []
        class Reply:
            status = 200
            def getheader(self, name):
                return str(len(json.dumps(response()).encode()))
            def getheaders(self):
                return [('Content-Type', 'application/json')]
            def read1(self, limit):
                value = getattr(self, 'remaining', json.dumps(response()).encode())
                chunk, self.remaining = value[:limit], value[limit:]
                return chunk
        class Connection:
            sock = None
            def __init__(self, host, **kwargs):
                calls.append((host, kwargs))
            def connect(self):
                pass
            def request(self, method, path, **kwargs):
                calls.append((method, path, kwargs))
            def getresponse(self):
                return Reply()
            def close(self):
                closed.append(True)
        log = self.root / 'tls-keys'
        with patch.dict(os.environ, {'SSLKEYLOGFILE': str(log), 'HTTPS_PROXY': 'http://wrong'}), \
                patch('http.client.HTTPSConnection', Connection):
            result = _https_request(JevRequest(self.decision).body, Secret(KEY),
                                   deadline=time.monotonic() + 2, cancelled=lambda: False)
        self.assertEqual(calls[0][0], 'api.typesafe.ai')
        self.assertIsNone(calls[0][1]['context'].keylog_filename)
        self.assertEqual(calls[1][:2], ('POST', '/v1/systemone'))
        self.assertEqual(calls[1][2]['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertFalse(log.exists())
        self.assertTrue(closed)
        self.assertEqual(validate_response(result, model='jev-1.13.0').label, 'still_supported')

    @proves("MYC-14.12")
    def test_cancelled_delayed_connect_cannot_send_late_paid_request(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        requests, closed = [], []
        class Connection:
            sock = None
            def __init__(self, *a, **k):
                pass
            def connect(self):
                entered.set()
                release.wait(2)
            def request(self, *a, **k):
                requests.append(1)
            def close(self):
                closed.append(1)
                if release.is_set():
                    finished.set()
        with patch('http.client.HTTPSConnection', Connection), patch('mycel._jev._tls_context', return_value=object()):
            try:
                with self.assertRaises(JevFailure) as caught:
                    _https_request(b'{}', Secret(KEY), deadline=time.monotonic() + 1,
                                   cancelled=entered.is_set)
                self.assertEqual(caught.exception.code, 'cancelled')
            finally:
                release.set()
                self.assertTrue(finished.wait(1))
        self.assertEqual(requests, [])
        self.assertTrue(closed)

    @proves("MYC-14.12")
    def test_cancelled_connection_close_response_shuts_down_detached_socket_and_finishes_worker(self):
        entered, stopped, finished = threading.Event(), threading.Event(), threading.Event()
        shutdowns, closes = [], []
        class Socket:
            def settimeout(self, duration):
                pass
            def shutdown(self, direction):
                shutdowns.append(direction)
                stopped.set()
            def close(self):
                closes.append(1)
        socket = Socket()
        class Reply:
            status = 200
            def getheader(self, name):
                return None
            def read1(self, limit):
                entered.set()
                if not stopped.wait(2):
                    raise AssertionError('detached response worker survived cancellation')
                finished.set()
                raise OSError('public fixture socket was closed')
        class Connection:
            sock = socket
            def __init__(self, *a, **k):
                pass
            def connect(self):
                pass
            def request(self, *a, **k):
                pass
            def getresponse(self):
                self.sock = None  # http.client's will_close response behavior.
                return Reply()
            def close(self):
                pass
        with patch('http.client.HTTPSConnection', Connection), patch('mycel._jev._tls_context', return_value=object()):
            with self.assertRaises(JevFailure) as caught:
                _https_request(b'{}', Secret(KEY), deadline=time.monotonic() + 2,
                               cancelled=entered.is_set)
        self.assertEqual(caught.exception.code, 'cancelled')
        self.assertTrue(finished.is_set())
        self.assertEqual(shutdowns, [2])
        self.assertTrue(closes)

    @proves("MYC-14.12", "MYC-14.17")
    def test_https_advertised_and_streamed_response_overflow_close_the_connection(self):
        for advertised in (str(MAX_RESPONSE_BYTES + 1), 'malformed', None):
            closed = []
            class Reply:
                status = 200
                remaining = MAX_RESPONSE_BYTES + 1
                def getheader(self, name):
                    return advertised
                def read1(self, limit):
                    size = min(limit, self.remaining)
                    self.remaining -= size
                    return b' ' * size
            class Connection:
                sock = None
                def __init__(self, *a, **k):
                    pass
                def connect(self):
                    pass
                def request(self, *a, **k):
                    pass
                def getresponse(self):
                    return Reply()
                def close(self):
                    closed.append(1)
            with patch('http.client.HTTPSConnection', Connection), patch('mycel._jev._tls_context', return_value=object()):
                with self.assertRaises(JevFailure) as caught:
                    _https_request(b'{}', Secret(KEY), deadline=time.monotonic() + 2, cancelled=lambda: False)
            self.assertEqual(caught.exception.code, 'provider_result_invalid')
            self.assertTrue(closed)


if __name__ == '__main__':
    unittest.main()
