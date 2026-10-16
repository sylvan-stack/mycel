"""Supplemental pure checks; native store tests own classifier acceptance claims."""

from copy import deepcopy
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel import _classification_payload as payload
from mycel import _evidence as evidence
from mycel._coverage import proves
from mycel._markdown import COMPARISON_REVISION, UNICODE_VERSION, comparison_hash
from mycel._source_refs import SourceAddress


def fixture(*, current=b'return "admin"\n', capture_time='2026-10-09T00:00:00Z', padding=b''):
    source = SourceAddress('source', 'code', 'access.py', 'permission')
    dependant = SourceAddress('owner', 'code', 'guide.py', 'claim')
    before_bytes, dependant_bytes = b'return "reader"\n', b'readers_may_delete = True\n'
    before = evidence.snapshot(before_bytes, comparison=evidence.exact_comparison(before_bytes, 'code_text'),
              place=source, file_source=padding + before_bytes, span=(len(padding), len(padding) + len(before_bytes)))
    dep = evidence.snapshot(dependant_bytes, comparison=evidence.exact_comparison(dependant_bytes, 'code_text'),
              place=dependant, file_source=padding + dependant_bytes,
              span=(len(padding), len(padding) + len(dependant_bytes)))
    manifest = evidence.BaselineManifest({
        'schema': 1, 'ownerRepository': 'owner', 'dependantId': '00000000-0000-0000-0000-000000000002',
        'dependantVersion': '7', 'dependant': dep.evidence.as_dict(), 'kind': 'declared',
        'ref': source.address, 'source': evidence._place(source), 'selection': 'chunk',
        'members': [{'id': '00000000-0000-0000-0000-000000000001', 'place': evidence._place(source),
                     'evidence': before.evidence.as_dict()}],
        'pinnedHash': before.evidence.comparison.hash, 'selectionComparison': before.evidence.comparison.as_dict(),
        'capturedAt': capture_time, 'location': {'kind': 'disk'}})
    now = evidence.snapshot(current, comparison=evidence.exact_comparison(current, 'code_text'), place=source,
                           file_source=padding + current, span=(len(padding), len(padding) + len(current)))
    before_text, current_text, dep_text = (payload.DecisionText.create(item.evidence, item.source)
                                         for item in (before, now, dep))
    selection = payload.CurrentSelection.create('present', source, 'chunk', (current_text,))
    decision = payload.DecisionPayload.create(baseline=manifest, before=(before_text,), current=selection,
                                             dependant=dep_text)
    return manifest, (before, now, dep), decision


def reviewer_identity():
    return payload.ReviewCommandIdentity({
        'argv': ['/Users/example/.local/bin/mycel-review-adapter', '--config',
                 '/Users/example/.config/reviewer/config.toml'],
        'executableSha256': sha256(b'fictional adapter bytes; not an installed executable\n').hexdigest(),
        'adapterRevision': 'example-adapter-v1', 'protocol': 1,
        'instructionVersion': 'mycel-review-v1', 'environmentVersion': 'mycel-review-env-v1'})


def reviewed(decision):
    value = decision.as_dict()
    value['models']['review'] = reviewer_identity().model_identity('example-provider', 'example-model-2026-10-01')
    return payload.DecisionPayload(value)


def guards(decision, *, changed_at='2026-10-09T00:00:00Z', file_hash='a' * 64):
    return [{'place': decision.payload['current']['place'], 'event': 'file_changed',
             'hash': file_hash, 'changedAt': changed_at}]


class ClassificationPayloadTests(unittest.TestCase):
    def setUp(self):
        # Payload preparation and dry-run command inspection have no model or
        # child-process channel. Fail immediately if any case creates one.
        blocked = ExitStack()
        self.addCleanup(blocked.close)
        for entry in ('mycel._voyage._https_request', 'http.client.HTTPConnection.request',
                      'urllib.request.urlopen', 'socket.create_connection', 'socket.socket.connect',
                      'subprocess.Popen', 'subprocess.run'):
            blocked.enter_context(patch(entry, side_effect=AssertionError('preparation must not call or spawn')))

    @proves('MYC-0.10')
    def test_fixed_instruction_choices_and_command_hash_match_accepted_vector(self):
        self.assertEqual(payload.LABELS, ('needs_review', 'insufficient_evidence', 'still_supported'))
        self.assertEqual(payload.CRITERIA, payload.INSTRUCTION + '\n\n' +
            'needs_review: Current evidence contradicts, invalidates or removes support for a relevant dependant claim, or shows that it needs checking\n'
            'insufficient_evidence: Supplied complete inputs do not establish whether the selected dependency remains supported\n'
            'still_supported: Current source still supports all dependant claims relevant to the selected dependency, with enough evidence to judge them')
        self.assertFalse(payload.CRITERIA.endswith('\n'))
        self.assertEqual(reviewer_identity().command_hash,
                         '16c0bf93cef288f7672f295ff1281a3de720822efb052e3cd81646ac3b9afdc3')

    @proves('MYC-0.10')
    def test_canonical_payload_fixed_vector_and_utf8_are_not_normalized(self):
        _, _, decision = fixture()
        self.assertEqual(decision.input_hash, 'b32ddb86d5f2a372397d5cabc18ca7f9e230b4ab3a0e0ba33f6b8b0d8b14ca5b')
        self.assertEqual(decision.input_hash, sha256(decision.canonical_bytes).hexdigest())
        self.assertNotIn('inputHash', decision.payload)
        self.assertEqual(payload.DecisionPayload.from_bytes(decision.canonical_bytes, decision.input_hash), decision)
        unicode_text = b'# literal ' + 'Å é\x00\t\n'.encode()
        _, _, composed = fixture(current=unicode_text)
        _, _, decomposed = fixture(current=unicode_text.replace('é'.encode(), 'e\u0301'.encode()))
        self.assertNotEqual(composed.input_hash, decomposed.input_hash)
        self.assertIn('Å'.encode(), composed.canonical_bytes)
        self.assertIn(b'\\u0000\\t\\n', composed.canonical_bytes)

    @proves('MYC-0.10')
    def test_semantic_projection_omits_all_capture_and_full_file_guards(self):
        manifest, blobs, decision = fixture()
        later, later_blobs, later_decision = fixture(capture_time='2026-10-12T00:00:00Z', padding=b'# outside section\n')
        self.assertNotEqual(manifest.identifier, later.identifier)
        self.assertNotEqual(blobs[0].evidence.file_hash, later_blobs[0].evidence.file_hash)
        self.assertEqual(decision.input_hash, later_decision.input_hash)
        self.assertEqual(decision.payload, later_decision.payload)
        projection = payload.semantic_baseline(manifest)
        for key in ('id', 'capturedAt', 'location'):
            self.assertNotIn(key, projection)
        def inspect(value):
            if isinstance(value, dict):
                self.assertNotIn('fileHash', value)
                self.assertNotIn('span', value)
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(decision.as_dict())
        full = manifest.as_dict()
        self.assertEqual(payload.semantic_baseline(full), projection)
        full['id'] = '0' * 64
        with self.assertRaises(evidence.EvidenceError):
            payload.semantic_baseline(full)

    @proves('MYC-0.10')
    def test_document_comparison_span_is_retained_and_verified(self):
        raw, body = b'# Heading\nExact body.\n', b'Exact body.\n'
        comparison = evidence.ComparisonRecord('document_body', COMPARISON_REVISION,
                                               comparison_hash(body.decode()), UNICODE_VERSION)
        descriptor = evidence.snapshot(raw, comparison=comparison, place=SourceAddress('owner', 'artifact', 'a.md', 'Heading'),
                                       file_source=raw, span=(0, len(raw)), comparison_span=(len(raw) - len(body), len(raw)))
        text = payload.DecisionText.create(descriptor.evidence, raw)
        self.assertEqual(text.payload['snapshot']['comparisonSpan'], {'start': 10, 'end': 22})
        bad = text.as_dict()
        bad['snapshot']['comparisonSpan']['start'] = 0
        with self.assertRaises(evidence.EvidenceError):
            payload.DecisionText(bad)

    @proves('MYC-0.10')
    def test_complete_text_refuses_changed_length_hash_lossy_text_and_unsupported_comparison(self):
        _, blobs, _ = fixture()
        original = blobs[0]
        for source in (original.source + b'\n', original.source.replace(b'reader', b'writer')):
            with self.subTest(source=source), self.assertRaises(evidence.EvidenceError) as raised:
                payload.DecisionText.create(original.evidence, source)
            self.assertEqual(raised.exception.status, 'snapshot_corrupt')
        nontext = evidence.snapshot(b'\xff')
        with self.assertRaises(evidence.EvidenceError) as raised:
            payload.DecisionText.create(nontext.evidence, nontext.source)
        self.assertEqual(raised.exception.status, 'insufficient_evidence')
        record = original.evidence.as_dict()
        record['comparison']['revision'] = 'future-revision'
        with self.assertRaises(evidence.EvidenceError) as raised:
            payload.DecisionText.create(record, original.source)
        self.assertEqual(raised.exception.status, 'unsupported_comparison')

    @proves('MYC-0.10')
    def test_payload_rejects_changed_fixed_protocol_and_unhashed_unknown_semantics(self):
        _, _, decision = fixture()
        changes = [('protocol', True), ('questionVersion', 'next-question'), ('criteria', payload.CRITERIA + '\n'),
                   ('labels', list(reversed(payload.LABELS))), ('inputHash', decision.input_hash), ('deadline', 5)]
        for key, value in changes:
            bad = decision.as_dict()
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload(bad)
        for model in ('jev-latest', 'jev-preview', 'jev-1.13'):
            bad = decision.as_dict()
            bad['models']['jev']['model'] = model
            with self.subTest(model=model), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload(bad)
        bad = decision.as_dict()
        bad['routing']['confidenceFloor'] = 0.7
        with self.assertRaises(evidence.EvidenceError):
            payload.DecisionPayload(bad)

    @proves('MYC-0.10')
    def test_noncanonical_or_duplicate_bytes_are_refused_even_when_digest_matches(self):
        _, _, decision = fixture()
        for raw in (json.dumps(decision.as_dict()).encode(), decision.canonical_bytes + b'\n',
                    decision.canonical_bytes.replace(b'"protocol":1', b'"protocol":1,"protocol":1'),
                    decision.canonical_bytes.replace(b'"confidenceFloor":"0.7"', b'"confidenceFloor":NaN')):
            with self.subTest(raw=raw[:30]), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload.from_bytes(raw, sha256(raw).hexdigest())

    @proves('MYC-0.10')
    def test_frozen_copy_prevents_post_capture_input_or_hash_mutation(self):
        _, _, original = fixture()
        mutable = original.as_dict()
        frozen = payload.DecisionPayload(mutable)
        mutable['models']['jev']['model'] = 'jev-9.0.0'
        mutable['before'].clear()
        self.assertEqual(frozen, original)
        with self.assertRaises(TypeError):
            frozen.payload['models']['jev']['model'] = 'jev-9.0.0'
        with self.assertRaises(TypeError):
            frozen.payload['labels'][0] = 'other'
        copied = frozen.as_dict()
        copied['before'][0]['text'] = 'new'
        self.assertEqual(frozen.input_hash, original.input_hash)

    @proves('MYC-0.10')
    def test_decimal_fraction_is_canonical_without_float_in_semantic_payload(self):
        for value, expected in ((0.7, '0.7'), ('0.7000', '0.7'), ('7e-1', '0.7'), ('-0.00', '0'), (1, '1')):
            self.assertEqual(payload.canonical_decimal(value), expected)
        for value in (True, float('nan'), float('inf'), -0.1, 1.1, 'bad'):
            with self.subTest(value=value), self.assertRaises(evidence.EvidenceError):
                payload.canonical_decimal(value)
        _, _, decision = fixture()
        for value in ('0.70', '7e-1', '-0', 0.7):
            bad = decision.as_dict()
            bad['routing']['confidenceFloor'] = value
            with self.subTest(value=value), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload(bad)

    @proves('MYC-0.10')
    def test_source_absence_has_no_members_and_never_substitutes_empty_before(self):
        manifest, _, decision = fixture()
        hashes = {decision.input_hash}
        for state in ('deleted', 'away'):
            absent = payload.CurrentSelection.create(state, decision.payload['current']['place'], 'chunk')
            value = decision.as_dict()
            value['current'] = absent.as_dict()
            changed = payload.DecisionPayload(value)
            hashes.add(changed.input_hash)
            self.assertEqual(changed.payload['before'], decision.payload['before'])
            self.assertEqual(changed.payload['current']['members'], ())
            self.assertIn(absent.payload['locator'], changed.evidence_locators)
            with self.assertRaises(evidence.EvidenceError):
                payload.CurrentSelection.create(state, manifest.payload['source'], 'chunk',
                    (payload.DecisionText(decision.as_dict()['current']['members'][0]),))
        _, _, empty = fixture(current=b'')
        hashes.add(empty.input_hash)
        self.assertEqual(len(hashes), 4)
        with self.assertRaises(evidence.EvidenceError):
            payload.CurrentSelection.create('present', manifest.payload['source'], 'chunk')

    @proves('MYC-0.10')
    def test_before_is_complete_exact_baseline_membership_and_dependant_identity(self):
        _, _, decision = fixture()
        for key in ('before', 'dependant'):
            bad = decision.as_dict()
            bad[key] = [] if key == 'before' else bad['before'][0]
            with self.subTest(key=key), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload(bad)
        bad = decision.as_dict()
        bad['before'] = bad['current']['members']
        with self.assertRaises(evidence.EvidenceError):
            payload.DecisionPayload(bad)

    @proves('MYC-0.10')
    def test_family_membership_and_order_are_complete_semantic_inputs(self):
        manifest, blobs, _ = fixture()
        family_place = SourceAddress('source', 'code', 'family.py', 'C')
        parts = [('C', b'class C:\n'), ('C.a', b' def a(self): pass\n')]
        def family_snapshots(parts):
            full, start, result = b''.join(raw for _, raw in parts), 0, []
            for name, raw in parts:
                place = SourceAddress('source', 'code', 'family.py', name)
                result.append(evidence.snapshot(raw, comparison=evidence.exact_comparison(raw, 'code_text'),
                              place=place, file_source=full, span=(start, start + len(raw))))
                start += len(raw)
            return result
        before_blobs = family_snapshots(parts)
        baseline = manifest.as_dict()
        baseline.pop('id')
        baseline['source'], baseline['selection'] = evidence._place(family_place), 'family'
        baseline['members'] = [{'id': str(number), 'place': evidence._place(blob.evidence.place),
                                'evidence': blob.evidence.as_dict()} for number, blob in enumerate(before_blobs)]
        family_hash = sha256(evidence.canonical_json(evidence._family_projection(baseline['members']))).hexdigest()
        baseline['pinnedHash'] = family_hash
        baseline['selectionComparison'] = evidence.ComparisonRecord('family', evidence.FAMILY_REVISION, family_hash).as_dict()
        baseline = evidence.BaselineManifest(baseline)
        before = tuple(payload.DecisionText.create(blob.evidence, blob.source) for blob in before_blobs)
        first = payload.DecisionPayload.create(baseline=baseline, before=before,
            current=payload.CurrentSelection.create('present', family_place, 'family', before),
            dependant=payload.DecisionText.create(blobs[2].evidence, blobs[2].source))
        changed = tuple(payload.DecisionText.create(blob.evidence, blob.source)
                        for blob in family_snapshots([*parts, ('C.z', b' def z(self): pass\n')]))
        selection = payload.CurrentSelection.create('present', family_place, 'family', changed)
        value = first.as_dict()
        value['current'] = selection.as_dict()
        second = payload.DecisionPayload(value)
        self.assertNotEqual(first.input_hash, second.input_hash)
        self.assertNotEqual(first.payload['current']['locator'], second.payload['current']['locator'])
        self.assertEqual(first.payload['before'], second.payload['before'])
        for incomplete in (changed[1:], tuple(reversed(changed)), (changed[0], changed[0])):
            with self.subTest(incomplete=incomplete), self.assertRaises(evidence.EvidenceError):
                payload.CurrentSelection.create('present', family_place, 'family', incomplete)

    @proves('MYC-0.10')
    def test_context_is_ordered_complete_and_changes_input_identity_and_citations(self):
        manifest, blobs, decision = fixture()
        ancestors = []
        for name in ('A', 'Z'):
            raw = ('# ' + name + '\ncomplete context\n').encode()
            descriptor = evidence.snapshot(raw, place=SourceAddress('owner', 'artifact', 'ancestors.md', name))
            ancestors.append(payload.ancestor_context(payload.DecisionText.create(descriptor.evidence, raw)))
        governor = payload.governor_context(manifest,
                    (payload.DecisionText.create(blobs[0].evidence, blobs[0].source),),
                    payload.CurrentSelection(decision.as_dict()['current']), 'stale')
        value = decision.as_dict()
        value['context'] = [*ancestors, governor]
        complete = payload.DecisionPayload(value)
        self.assertNotEqual(complete.input_hash, decision.input_hash)
        self.assertEqual(complete.evidence_locators, tuple(sorted(set(complete.evidence_locators))))
        self.assertTrue(set(decision.evidence_locators) <= set(complete.evidence_locators))
        for malformed in ([ancestors[1], ancestors[0]], [ancestors[0], ancestors[0]], [{'role': 'ancestor'}]):
            bad = decision.as_dict()
            bad['context'] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(evidence.EvidenceError):
                payload.DecisionPayload(bad)
        value['context'][2] = deepcopy(payload._copy(governor))
        value['context'][2]['freshness'] = 'fresh'
        self.assertNotEqual(payload.DecisionPayload(value).input_hash, complete.input_hash)

    @proves('MYC-0.10')
    def test_model_routing_revision_command_revision_and_literal_arguments_bind_identity(self):
        _, _, initial = fixture()
        decision = reviewed(initial)
        for key, value in (('model', 'example-model-2026-10-02'), ('provider', 'second-provider'),
                           ('adapterRevision', 'example-adapter-v2'), ('commandHash', 'b' * 64)):
            changed = decision.as_dict()
            changed['models']['review'][key] = value
            self.assertNotEqual(payload.DecisionPayload(changed).input_hash, decision.input_hash)
        for key, value in (('revision', 'mycel-drift-routing-v2'), ('confidenceFloor', '0.8')):
            changed = decision.as_dict()
            changed['routing'][key] = value
            self.assertNotEqual(payload.DecisionPayload(changed).input_hash, decision.input_hash)
        changed = reviewer_identity().as_dict()
        changed['argv'].append('$TOKEN; *.md $(exit 1)')
        self.assertNotEqual(payload.ReviewCommandIdentity(changed).command_hash, reviewer_identity().command_hash)

    @proves('MYC-0.10')
    def test_reviewer_request_derives_identities_locators_and_exact_lf_count(self):
        _, _, initial = fixture()
        decision = reviewed(initial)
        request = payload.ReviewerRequest(decision, 120000)
        shorter = payload.ReviewerRequest(decision, 10)
        self.assertEqual(request.payload['inputHash'], decision.input_hash)
        self.assertEqual(request.payload['payload'], decision.payload)
        self.assertEqual(request.payload['judgements'], payload.LABELS)
        self.assertEqual(request.payload['evidenceLocators'], decision.evidence_locators)
        for key, value in decision.payload['models']['review'].items():
            self.assertEqual(request.payload[key], value)
        self.assertEqual(request.transmitted_bytes, evidence.canonical_json(request.payload) + b'\n')
        self.assertNotEqual(request.transmitted_bytes, shorter.transmitted_bytes)
        self.assertEqual(request.payload['inputHash'], shorter.payload['inputHash'])
        self.assertEqual(request.payload['budget']['maxProviderCalls'], 1)
        self.assertEqual(request.payload['budget']['maxOutputBytes'], 1048576)
        for timeout in (0, -1, True, 1.5):
            with self.subTest(timeout=timeout), self.assertRaises(evidence.EvidenceError):
                payload.ReviewerRequest(decision, timeout)
        with self.assertRaises(evidence.EvidenceError) as raised:
            payload.ReviewerRequest(initial, 10)
        self.assertEqual(raised.exception.status, 'reviewer_unconfigured')

    @proves('MYC-0.10')
    def test_command_inspection_expands_only_first_argument_resolves_and_never_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            installed = home / 'adapter'
            marker = home / 'was-executed'
            raw = ('#!/bin/sh\ntouch ' + str(marker) + '\n').encode()
            installed.write_bytes(raw)
            installed.chmod(0o700)
            (home / 'link').symlink_to(installed)
            args = ['~/link', '~/literal-config', '${SECRET}', '*.md', '$(echo hello)', '   ']
            command = payload.ReviewCommandIdentity.inspect(args, 'adapter-v1', home)
            self.assertTrue(command.available)
            self.assertEqual(command.payload['argv'], (str(installed.resolve()), *args[1:]))
            self.assertEqual(command.payload['executableSha256'], sha256(raw).hexdigest())
            self.assertFalse(marker.exists())
            frozen_hash = command.command_hash
            installed.write_bytes(raw + b'# changed\n')
            replacement = payload.ReviewCommandIdentity.inspect(args, 'adapter-v1', home)
            self.assertNotEqual(replacement.command_hash, frozen_hash)
            self.assertEqual(command.command_hash, frozen_hash)

    @proves('MYC-0.10')
    def test_unavailable_executable_has_null_digest_and_structural_faults_do_not_search_path(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            missing = payload.ReviewCommandIdentity.inspect(['~/missing'], 'adapter-v1', home)
            self.assertFalse(missing.available)
            self.assertIsNone(missing.payload['executableSha256'])
            nonexec = home / 'nonexec'
            nonexec.write_bytes(b'not executable')
            nonexec.chmod(0o600)
            self.assertFalse(payload.ReviewCommandIdentity.inspect([str(nonexec)], 'adapter-v1', home).available)
            (home / 'loop').symlink_to(home / 'loop')
            self.assertFalse(payload.ReviewCommandIdentity.inspect(['~/loop'], 'adapter-v1', home).available)
            with patch.object(payload.os, 'access', return_value=False):
                nonexec.chmod(0o700)
                self.assertFalse(payload.ReviewCommandIdentity.inspect([str(nonexec)], 'adapter-v1', home).available)
            for argv in ([], ['adapter'], ['$HOME/adapter'], ['~/missing', ''], ['~/missing', '\0']):
                with self.subTest(argv=argv), self.assertRaises(evidence.EvidenceError):
                    payload.ReviewCommandIdentity.inspect(argv, 'adapter-v1', home)

    @proves('MYC-0.10')
    def test_bundle_full_manifest_guard_identity_is_separate_from_payload_cache_identity(self):
        manifest, blobs, decision = fixture()
        bundle = payload.EvidenceBundle.create(owner_repository='owner', baseline_id=manifest.identifier,
                  decision=decision, evidence=[blob.evidence for blob in blobs], guards=guards(decision))
        later_manifest, later_blobs, later = fixture(capture_time='2026-10-12T00:00:00Z', padding=b'# new full guard\n')
        changed = payload.EvidenceBundle.create(owner_repository='owner', baseline_id=later_manifest.identifier,
                   decision=later, evidence=[blob.evidence for blob in later_blobs],
                   guards=guards(later, changed_at='2026-10-12T00:00:00Z', file_hash='b' * 64))
        self.assertEqual(bundle.payload['inputHash'], changed.payload['inputHash'])
        self.assertNotEqual(bundle.evidence_hash, changed.evidence_hash)
        self.assertEqual(bundle.payload['requestSnapshot'], 'snapshot:' + decision.input_hash)
        self.assertEqual(bundle.evidence_hash, sha256(bundle.canonical_bytes).hexdigest())
        self.assertEqual(payload.EvidenceBundle.from_bytes(bundle.canonical_bytes, bundle.evidence_hash), bundle)
        self.assertTrue(any('fileHash' in descriptor and 'span' in descriptor for descriptor in bundle.payload['evidence']))
        self.assertNotIn('guards', decision.payload)

    @proves('MYC-0.10')
    def test_bundle_refuses_missing_text_evidence_wrong_owner_and_invalid_guards(self):
        manifest, blobs, decision = fixture()
        with self.assertRaises(evidence.EvidenceError) as raised:
            payload.EvidenceBundle.create(owner_repository='owner', baseline_id=manifest.identifier, decision=decision,
                evidence=[blobs[0].evidence], guards=guards(decision))
        self.assertEqual(raised.exception.status, 'baseline_missing')
        with self.assertRaises(evidence.EvidenceError):
            payload.EvidenceBundle.create(owner_repository='other', baseline_id=manifest.identifier, decision=decision,
                evidence=[blob.evidence for blob in blobs], guards=guards(decision))
        variants = [guards(decision, changed_at='2026-10-09T01:00:00+01:00'),
                    guards(decision) * 2, [{'place': decision.payload['current']['place'], 'event': 'file_changed'}],
                    [{'place': decision.payload['current']['place'], 'event': 'deleted', 'hash': 'a' * 64}]]
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises(evidence.EvidenceError):
                payload.EvidenceBundle.create(owner_repository='owner', baseline_id=manifest.identifier, decision=decision,
                    evidence=[blob.evidence for blob in blobs], guards=invalid)


if __name__ == '__main__':
    unittest.main()
