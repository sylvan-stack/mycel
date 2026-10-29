"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evidence as _support
from test_evidence import (MycelError ,evidence ,inputs ,patch)


class EvidenceStoreTests(_support.EvidenceStoreTests):

# TEST-TIER-BEGIN tests/test_evidence.py::EvidenceStoreTests.test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable
    def test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            observed = self.seed(connection, inputs(source='---\nrole: authored\n---\n# Source\r\nComplete source.\r\n', whole=True))
            writer = evidence.EvidenceStore(connection)
            identifier = self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
            baseline = writer.read_baseline('owner', identifier)
            self.assertEqual(baseline.manifest.payload['ownerRepository'], 'owner')
            self.assertEqual(baseline.manifest.payload['members'][0]['evidence']['hash'], observed.selection.file.snapshot_hash)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots WHERE repository=%s', ('source',)).fetchone()[0], 0)
            counts = connection.execute('SELECT (SELECT count(*) FROM public.mycel_chunks),'
                                        '(SELECT count(*) FROM public.mycel_locations),(SELECT count(*) FROM public.mycel_vectors)').fetchone()
            self.assertEqual(counts, (2, 2, 0))
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            self.assertEqual(writer.read_baseline('owner', identifier), baseline)
            self.assertIsNone(connection.execute('SELECT id FROM public.mycel_chunks WHERE repository=%s', ('source',)).fetchone())
# TEST-TIER-END tests/test_evidence.py::EvidenceStoreTests.test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable

# TEST-TIER-BEGIN tests/test_evidence.py::EvidenceStoreTests.test_real_callback_and_mid_transaction_failure_write_no_partial_baseline
    def test_real_callback_and_mid_transaction_failure_write_no_partial_baseline(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            observed = self.seed(connection, inputs())
            writer = evidence.EvidenceStore(connection)
            changed = inputs(source='# Source\nChanged current source\n')
            with self.assertRaises(evidence.EvidenceError) as error:
                self.pin(writer, observed, reread=lambda: changed)
            self.assertEqual(error.exception.status, 'changed_since_ingest')
            original = writer._write
            def fail_after_write(*args):
                original(*args)
                connection.execute('SELECT 1/0')
            with patch.object(writer, '_write', fail_after_write), self.assertRaises(MycelError):
                self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
            counts = connection.execute('SELECT (SELECT count(*) FROM public.mycel_snapshots),'
                    '(SELECT count(*) FROM public.mycel_manifests),(SELECT count(*) FROM public.mycel_evidence_owners),'
                    '(SELECT count(*) FROM public.mycel_evidence_references),(SELECT count(*) FROM public.mycel_dependencies)').fetchone()
            self.assertEqual(counts, (0, 0, 0, 0, 0))
# TEST-TIER-END tests/test_evidence.py::EvidenceStoreTests.test_real_callback_and_mid_transaction_failure_write_no_partial_baseline

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_document_body_and_title_normalize_separately_exact_versions_do_not
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Document body and title normalize separately exact versions do not.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_document_body_and_title_normalize_separately_exact_versions_do_not(self):
#         first = document('source', 'guide.md', '# Ａ title\r\nBody\twith  space.\r\n')
#         second = document('source', 'guide.md', '# A title\nBody with\nspace.\n', version=2)
#         body1 = evidence.chunk_comparison(first.chunks[0])
#         body2 = evidence.chunk_comparison(second.chunks[0])
#         self.assertEqual(body1.hash, body2.hash)
#         self.assertEqual(first.chunks[0].comparison['title']['hash'], second.chunks[0].comparison['title']['hash'])
#         self.assertNotEqual(first.chunks[0].snapshot_hash, second.chunks[0].snapshot_hash)
#         self.assertEqual(body1.revision, COMPARISON_REVISION)
#         self.assertEqual(body1.unicode_version, UNICODE_VERSION)
#         renamed = document('source', 'guide.md', '# Renamed\nBody with space.\n')
#         self.assertEqual(evidence.chunk_comparison(renamed.chunks[0]).hash, body1.hash)
#         self.assertNotEqual(renamed.chunks[0].comparison['title']['hash'], first.chunks[0].comparison['title']['hash'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_code_file_and_snapshot_hashes_cover_original_complete_bytes
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Code file and snapshot hashes cover original complete bytes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_code_file_and_snapshot_hashes_cover_original_complete_bytes(self):
#         raw = b'#!/bin/sh\r\n# comment\r\necho exact  \r\n'
#         for kind in ('code_text', 'file_bytes'):
#             record = evidence.exact_comparison(raw, kind)
#             self.assertEqual(record.hash, sha256(raw).hexdigest())
#             self.assertEqual(record.revision, evidence.EXACT_REVISION)
#             self.assertIsNone(record.unicode_version)
#             with self.assertRaises(evidence.EvidenceError):
#                 record.verify(raw.replace(b'\r\n', b'\n'))
#         complete = b'---\nsources: source:file\n---\n# Title\nText\n'
#         self.assertEqual(evidence.snapshot(complete).evidence.hash, sha256(complete).hexdigest())
#         self.assertNotEqual(evidence.snapshot(complete).evidence.hash, evidence.snapshot(complete.split(b'---\n')[-1]).evidence.hash)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_canonical_json_fixed_bytes_and_sha_vector_reject_non_semantic_numbers
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Canonical json fixed bytes and sha vector reject non semantic numbers.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_canonical_json_fixed_bytes_and_sha_vector_reject_non_semantic_numbers(self):
#         value = {'é': 'literal Å', 'a': ['\x00\b\t\n\f\r"\\', -12, True, None], '𐀀': 'x'}
#         expected = b'{"a":["\\u0000\\b\\t\\n\\f\\r\\"\\\\",-12,true,null],"\xc3\xa9":"literal \xe2\x84\xab","\xf0\x90\x80\x80":"x"}'
#         self.assertEqual(evidence.canonical_json(value), expected)
#         self.assertEqual(sha256(evidence.canonical_json({'a': 1, 'b': 'é'})).hexdigest(),
#                          '09ad9fd2fb648cb2f62141215828ea00a62c299db05d20aa9ade2f527a301cc6')
#         for bad in (1.0, float('nan'), float('inf'), {1: 'key'}, b'bytes', '\ud800'):
#             with self.subTest(bad=repr(bad)), self.assertRaises(evidence.EvidenceError):
#                 evidence.canonical_json(bad)
#         recursive = []
#         recursive.append(recursive)
#         with self.assertRaises(evidence.EvidenceError):
#             evidence.canonical_json(recursive)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_unavailable_pinned_revision_and_unicode_identity_never_repin_or_reparse
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unavailable pinned revision and unicode identity never repin or reparse.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unavailable_pinned_revision_and_unicode_identity_never_repin_or_reparse(self):
#         observation = inputs()
#         good = observation.selection.members[0].chunk
#         for key, replacement in (('revision', 'future-normalization-v2'), ('unicodeVersion', '0.0')):
#             comparisons = json.loads(evidence.canonical_json(good.comparison))
#             comparisons['body'][key] = replacement
#             bad = replace(good, comparison=comparisons)
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 evidence.chunk_comparison(bad)
#             self.assertEqual(error.exception.status, 'unsupported_comparison')
#             self.assertEqual(comparisons['body'][key], replacement)
#         for bad in (replace(good, comparison={}), replace(good, body=None)):
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 evidence.chunk_comparison(bad)
#             self.assertEqual(error.exception.status, 'unsupported_comparison')
#         code = evidence.exact_comparison(b'print("exact")\n', 'code_text')
#         with patch.object(evidence, 'UNICODE_VERSION', 'future'):
#             code.verify(b'print("exact")\n')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_recorded_body_and_title_mismatch_are_corruption
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Recorded body and title mismatch are corruption.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_recorded_body_and_title_mismatch_are_corruption(self):
#         chunk = inputs().selection.members[0].chunk
#         for bad in (replace(chunk, body=b'other body'), replace(chunk, title='other title')):
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 evidence.chunk_comparison(bad)
#             self.assertEqual(error.exception.status, 'snapshot_corrupt')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_family_membership_and_order_are_in_the_comparison_hash
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Family membership and order are in the comparison hash.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_family_membership_and_order_are_in_the_comparison_hash(self):
#         raw = b'class C:\n def a(self): pass\n def z(self): pass\n'
#         primary = SourceAddress('source', 'code', 'c.py')
#         chunks = []
#         start = 0
#         for number, (name, part, kind) in enumerate((('C', b'class C:\n', 'class'),
#                 ('C.a', b' def a(self): pass\n', 'method'), ('C.z', b' def z(self): pass\n', 'method'))):
#             chunks.append(ResolvedChunk(str(uuid4()), 20 + number, name, kind, part, sha256(part).hexdigest(),
#                           (start, start + len(part)), None, 'C' if kind == 'method' else None,
#                           evidence.exact_comparison(part, 'code_text').as_dict()))
#             start += len(part)
#         file = ResolvedFile(str(uuid4()), 'source', primary, (primary,), raw, sha256(raw).hexdigest(), tuple(chunks))
#         dep = inputs()
#         resolver = SourceResolver(dep.settings, (dep.dependant_file, file))
#         resolution = resolver.resolve('source:@code/c.py#C')
#         observation = replace(dep, selection=resolution.selection, resolution=resolution, catalog=resolver)
#         full = capture(observation)
#         self.assertEqual([item['place']['name'] for item in full.manifest.payload['members']], ['C', 'C.a', 'C.z'])
#         smaller_file = replace(file, chunks=file.chunks[:2])
#         resolver2 = SourceResolver(dep.settings, (dep.dependant_file, smaller_file))
#         resolution2 = resolver2.resolve('source:@code/c.py#C')
#         smaller = capture(replace(dep, selection=resolution2.selection, resolution=resolution2, catalog=resolver2))
#         self.assertNotEqual(full.manifest.payload['pinnedHash'], smaller.manifest.payload['pinnedHash'])
#         recreated_file = replace(file, chunks=tuple(replace(chunk, identifier=str(uuid4())) for chunk in file.chunks))
#         recreated_resolver = SourceResolver(dep.settings, (dep.dependant_file, recreated_file))
#         recreated_resolution = recreated_resolver.resolve('source:@code/c.py#C')
#         recreated = capture(replace(dep, selection=recreated_resolution.selection, resolution=recreated_resolution,
#                                    catalog=recreated_resolver))
#         self.assertEqual(full.manifest.payload['pinnedHash'], recreated.manifest.payload['pinnedHash'])
#         self.assertNotEqual(full.manifest.payload['members'], recreated.manifest.payload['members'])
#         duplicated = json.loads(full.manifest.canonical_bytes)
#         repeated = deepcopy(duplicated['members'][1])
#         repeated['id'] = str(uuid4())
#         duplicated['members'].append(repeated)
#         duplicated['members'].sort(key=lambda item: (item['place']['address'], item['id']))
#         repeated_hash = sha256(evidence.canonical_json(evidence._family_projection(duplicated['members']))).hexdigest()
#         duplicated['pinnedHash'] = duplicated['selectionComparison']['hash'] = repeated_hash
#         with self.assertRaises(evidence.EvidenceError):
#             evidence.BaselineCapture(evidence.BaselineManifest(duplicated), full.snapshots)
#         unsupported = json.loads(full.manifest.canonical_bytes)
#         unsupported['selectionComparison']['revision'] = 'future-family-v2'
#         raw = evidence.canonical_json(unsupported)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             evidence.BaselineManifest.from_bytes(raw, sha256(raw).hexdigest())
#         self.assertEqual(error.exception.status, 'unsupported_comparison')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_rehashed_manifest_rejects_wrong_pins_places_kinds_missing_spans_and_body_hash
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Rehashed manifest rejects wrong pins places kinds missing spans and body hash.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_rehashed_manifest_rejects_wrong_pins_places_kinds_missing_spans_and_body_hash(self):
#         baseline = capture(inputs())
#         original = json.loads(baseline.manifest.canonical_bytes)
#         variants = []
#         bad = deepcopy(original)
#         bad['pinnedHash'] = '0' * 64
#         variants.append(bad)
#         bad = deepcopy(original)
#         changed_place = SourceAddress('source', 'artifact', 'other.md', 'Other')
#         bad['source'] = evidence._place(changed_place)
#         variants.append(bad)
#         for key in ('comparison', 'span', 'fileHash', 'comparisonSpan'):
#             bad = deepcopy(original)
#             del bad['members'][0]['evidence'][key]
#             variants.append(bad)
#         bad = deepcopy(original)
#         bad['members'][0]['evidence']['comparison']['kind'] = 'file_bytes'
#         variants.append(bad)
#         bad = deepcopy(original)
#         bad['members'][0]['evidence']['comparison']['hash'] = bad['pinnedHash'] = bad['selectionComparison']['hash'] = '0' * 64
#         variants.append(bad)
#         for variant in variants:
#             with self.subTest(variant=variant), self.assertRaises(evidence.EvidenceError):
#                 evidence.BaselineCapture(evidence.BaselineManifest(variant), baseline.snapshots)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_manifest_and_snapshots_are_immutable_complete_owner_scoped_and_fixed_id
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Manifest and snapshots are immutable complete owner scoped and fixed id.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_manifest_and_snapshots_are_immutable_complete_owner_scoped_and_fixed_id(self):
#         observed = inputs(source='---\nrole: authored\n---\n# Source\r\n Exact source.  \r\n', whole=True)
#         recorded = capture(observed)
#         manifest = recorded.manifest
#         self.assertEqual(manifest.identifier, sha256(manifest.canonical_bytes).hexdigest())
#         self.assertNotIn(b'"id":', evidence.canonical_json({'schema': 1}))
#         self.assertEqual(manifest.payload['members'][0]['evidence']['hash'], observed.selection.file.snapshot_hash)
#         original = next(blob.source for blob in recorded.snapshots if blob.evidence.hash == observed.selection.file.snapshot_hash)
#         self.assertEqual(original, observed.selection.file.source)
#         self.assertEqual(manifest.payload['ownerRepository'], 'owner')
#         self.assertEqual(manifest.payload['ref'], 'source:source.md')
#         with self.assertRaises(TypeError):
#             manifest.payload['members'][0]['evidence']['bytes'] = 0
#         self.assertEqual(evidence.BaselineManifest.from_bytes(manifest.canonical_bytes, manifest.identifier), manifest)
#         with self.assertRaises(evidence.EvidenceError):
#             evidence.BaselineManifest.from_bytes(manifest.canonical_bytes + b' ', manifest.identifier)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_snapshot_verifies_length_hash_exact_text_limits_and_extraction
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Snapshot verifies length hash exact text limits and extraction.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_snapshot_verifies_length_hash_exact_text_limits_and_extraction(self):
#         raw = b'prefix\n# Exact\r\nbody\t\r\nsuffix'
#         begin, end = 7, len(raw) - 6
#         blob = evidence.snapshot(raw[begin:end], file_source=raw, span=(begin, end))
#         self.assertEqual(evidence.reconstruct(blob.evidence, (b'newer file', raw)), raw[begin:end])
#         for candidates in ((raw[begin:end],), (raw.replace(b'prefix', b'PREFIX'),), ()):
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 evidence.reconstruct(blob.evidence, candidates)
#             self.assertEqual(error.exception.status, 'baseline_missing')
#         for corrupt in (blob.source[:-1], b'x' * len(blob.source)):
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 blob.evidence.verify(corrupt)
#             self.assertEqual(error.exception.status, 'snapshot_corrupt')
#         with self.assertRaises(evidence.EvidenceError) as error:
#             blob.evidence.verify(blob.source, limit=len(blob.source)-1)
#         self.assertEqual(error.exception.status, 'input_too_large')
#         binary = evidence.snapshot(b'\xff\x00')
#         self.assertEqual(binary.evidence.encoding, 'bytes')
#         self.assertEqual(binary.evidence.verify(binary.source), binary.source)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             binary.evidence.verify(binary.source, textual=True)
#         self.assertEqual(error.exception.status, 'insufficient_evidence')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceUnitTests.test_inheritance_keeps_original_sources_and_its_audit_location
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Inheritance keeps original sources and its audit location.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_inheritance_keeps_original_sources_and_its_audit_location(self):
#         observed = inputs(location=evidence.CaptureLocation('branch', 'a'*40))
#         baseline = capture(observed)
#         moved_dep = document('owner', 'renamed.md', '# Answer\nExact\tanswer.\n', version=2,
#                              identifier=observed.dependant.chunk.identifier)
#         inherited = evidence.inherit_baseline(baseline, member(moved_dep), moved_dep)
#         for key in ('members', 'source', 'pinnedHash', 'ref', 'capturedAt', 'location'):
#             self.assertEqual(inherited.manifest.payload[key], baseline.manifest.payload[key])
#         self.assertEqual(inherited.manifest.payload['dependantVersion'], '2')
#         self.assertNotEqual(inherited.manifest.identifier, baseline.manifest.identifier)
#         self.assertNotEqual(inherited.manifest.payload['dependant']['hash'], baseline.manifest.payload['dependant']['hash'])
#         changed = document('owner', 'renamed.md', '# Answer\nSubstantive edit.\n', version=3,
#                            identifier=observed.dependant.chunk.identifier)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             evidence.inherit_baseline(baseline, member(changed), changed)
#         self.assertEqual(error.exception.status, 'invalid_input')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_locked_atomic_owner_capture_and_read_never_create_searchable_rows
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Locked atomic owner capture and read never create searchable rows.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_locked_atomic_owner_capture_and_read_never_create_searchable_rows(self):
#         def reread():
#             self.assertEqual(self.connection.guards, ['owner', 'source'])
#             self.assertNotIn('begin', self.connection.events)
#             return self.observed
#         identifier = self.pin(reread=reread)
#         baseline = self.store.read_baseline('owner', identifier)
#         self.assertEqual(baseline, capture(self.observed))
#         self.assertEqual(self.connection.events[:3], ['checked', 'begin', 'commit'])
#         self.assertTrue(all(key[0] == 'owner' for key in self.connection.snapshots))
#         self.assertEqual(len(self.connection.dependencies), 1)
#         self.assertFalse(any(sql.startswith(('CREATE ', 'ALTER ', 'DROP ', 'INSERT INTO public.mycel_chunks',
#                                             'INSERT INTO public.mycel_locations', 'INSERT INTO public.mycel_vectors'))
#                              for sql, _ in self.connection.sql))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_changed_files_versions_resolution_and_settings_refuse_before_any_write
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Changed files versions resolution and settings refuse before any write.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_files_versions_resolution_and_settings_refuse_before_any_write(self):
#         changed = inputs(source='# Source\nChanged\n')
#         dep_changed = inputs(dependant='# Answer\nChanged\n')
#         renamed = document('source', 'moved.md', '# Source\nExact source.\n', version=11)
#         moved_resolver = SourceResolver(self.observed.settings, (self.observed.dependant_file, renamed))
#         moved_resolution = moved_resolver.resolve(member(renamed).place.address)
#         moved = replace(self.observed, selection=moved_resolution.selection, resolution=moved_resolution, catalog=moved_resolver)
#         altered = replace(self.observed.settings,
#             values=_freeze({'repos': {'owner': {'enabled': True}, 'source': {'enabled': True}}, 'store': {'address': 'new'}}))
#         altered_resolver = SourceResolver(altered, (self.observed.dependant_file, self.observed.selection.file))
#         altered_settings = replace(self.observed, settings=altered, catalog=altered_resolver)
#         for observation in (None, changed, dep_changed, moved, altered_settings,
#                             replace(self.observed, guards={'locationIdentity':'another location'})):
#             with self.subTest(observation=observation), self.assertRaises(evidence.EvidenceError) as error:
#                 self.pin(reread=lambda: observation)
#             self.assertEqual(error.exception.status, 'changed_since_ingest')
#             self.assertTrue(error.exception.addresses)
#         self.assertEqual(self.connection.snapshots, {})
#         self.assertNotIn('begin', self.connection.events)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_store_changed_version_and_file_checks_roll_back_before_blob_insert
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Store changed version and file checks roll back before blob insert.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_store_changed_version_and_file_checks_roll_back_before_blob_insert(self):
#         for mutate in (lambda: self.connection.versions.pop(11), lambda: self.connection.files.clear()):
#             with self.subTest(mutate=mutate):
#                 self.connection.seed(self.observed)
#                 mutate()
#                 with self.assertRaises(evidence.EvidenceError) as error:
#                     self.pin()
#                 self.assertEqual(error.exception.status, 'changed_since_ingest')
#                 self.assertFalse(self.connection.snapshots)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_existing_pin_requires_exact_expected_owner_no_initial_silent_repin
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Existing pin requires exact expected owner no initial silent repin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_existing_pin_requires_exact_expected_owner_no_initial_silent_repin(self):
#         dependency = uuid4()
#         identifier = self.pin(identifier=dependency)
#         original = self.connection.dependencies[dependency][-1]
#         with self.assertRaises(evidence.EvidenceError):
#             self.pin(identifier=dependency)
#         self.assertEqual(self.connection.dependencies[dependency][-1], original)
#         repeated = self.pin(identifier=dependency, authorization='owner_confirmation', expected_owner=original)
#         self.assertEqual(repeated, identifier)
#         self.assertEqual(len(self.connection.manifests), 1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_raw_declaration_fresh_full_catalog_collision_and_missing_resolution_fail_closed
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Raw declaration fresh full catalog collision and missing resolution fail closed.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_raw_declaration_fresh_full_catalog_collision_and_missing_resolution_fail_closed(self):
#         for ref in ('not a ref', 'source:missing.md', 'source:source.md#Missing', 'source:@index/summaries'):
#             with self.subTest(ref=ref), self.assertRaises(evidence.EvidenceError):
#                 self.pin(declaration=ref)
#         collision = replace(self.observed.selection.file, identifier=str(uuid4()),
#                             primary=SourceAddress('source','code','source.md'),
#                             aliases=(SourceAddress('source','code','source.md'),))
#         def newly_ambiguous():
#             catalog = SourceResolver(self.observed.settings, (self.observed.dependant_file,
#                                     self.observed.selection.file, collision))
#             resolution = catalog.resolve(self.observed.resolution.declaration)
#             self.assertEqual(resolution.fault, 'ambiguous_path')
#             return replace(self.observed, resolution=resolution, catalog=catalog)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.pin(reread=newly_ambiguous)
#         self.assertEqual(error.exception.status, 'changed_since_ingest')
#         self.assertFalse(self.connection.snapshots)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_version_rows_must_belong_to_each_exact_repository_and_file
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Version rows must belong to each exact repository and file.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_version_rows_must_belong_to_each_exact_repository_and_file(self):
#         for position, value in ((2,'source'), (3,uuid4())):
#             with self.subTest(position=position):
#                 self.connection.seed(self.observed)
#                 row = list(self.connection.versions[1])
#                 row[position] = value
#                 self.connection.versions[1] = tuple(row)
#                 with self.assertRaises(evidence.EvidenceError) as error:
#                     self.pin()
#                 self.assertEqual(error.exception.status, 'changed_since_ingest')
#                 self.assertFalse(self.connection.snapshots)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_missing_and_corrupt_snapshot_and_unknown_comparison_stay_visible
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Missing and corrupt snapshot and unknown comparison stay visible.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_missing_and_corrupt_snapshot_and_unknown_comparison_stay_visible(self):
#         identifier = self.pin()
#         baseline = self.store.read_baseline('owner', identifier)
#         blob = baseline.snapshots[0]
#         key = ('owner', blob.evidence.hash)
#         original = self.connection.snapshots.pop(key)
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.store.read_baseline('owner', identifier)
#         self.assertEqual(error.exception.status, 'baseline_missing')
#         self.connection.snapshots[key] = (b'corrupt', original[1])
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.store.read_snapshot('owner', blob.evidence)
#         self.assertEqual(error.exception.status, 'snapshot_corrupt')
#         self.connection.snapshots[key] = original
#         with self.assertRaises(evidence.EvidenceError) as error:
#             self.store.read_snapshot('owner', replace(blob.evidence, comparison=replace(blob.evidence.comparison, revision='future')))
#         self.assertEqual(error.exception.status, 'unsupported_comparison')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceSQLTests.test_reconstruction_only_exact_owned_blob_never_changes_pin
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Reconstruction only exact owned blob never changes pin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_reconstruction_only_exact_owned_blob_never_changes_pin(self):
#         dependency = uuid4()
#         identifier = self.pin(identifier=dependency)
#         baseline = self.store.read_baseline('owner', identifier)
#         descriptor = baseline.snapshots[0].evidence
#         original_owner = self.connection.dependencies[dependency][-1]
#         expected = self.connection.snapshots.pop(('owner', descriptor.hash))[0]
#         candidates = tuple(file.source for file in (self.observed.dependant_file, self.observed.selection.file))
#         self.assertEqual(self.store.restore_snapshot(self.observed, lambda: self.observed, descriptor, candidates), expected)
#         self.assertEqual(self.connection.dependencies[dependency][-1], original_owner)
#         self.assertEqual(self.store.read_baseline('owner', identifier), baseline)
#         with self.assertRaises(evidence.EvidenceError):
#             self.store.restore_snapshot(self.observed, lambda: self.observed, evidence.snapshot(b'random').evidence, (b'random',))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceStoreTests.test_real_body_nul_pin_and_snapshot_roundtrip_never_uses_projection
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real body nul pin and snapshot roundtrip never uses projection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_body_nul_pin_and_snapshot_roundtrip_never_uses_projection(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             observed = self.seed(connection,inputs(dependant='# Answer\nExact\0answer.\n',source='# Source\nComplete\0source.\n'))
#             writer = evidence.EvidenceStore(connection)
#             identifier = self.pin(writer,observed,reread=lambda:self.observe(connection,observed))
#             baseline = writer.read_baseline('owner',identifier)
#             descriptor = evidence.SnapshotEvidence.from_record(json.loads(evidence.canonical_json(baseline.manifest.payload['dependant'])))
#             self.assertEqual(writer.read_snapshot('owner',descriptor,textual=True),observed.dependant.chunk.source)
#             source_descriptor = evidence.SnapshotEvidence.from_record(json.loads(evidence.canonical_json(baseline.manifest.payload['members'][0]['evidence'])))
#             self.assertEqual(writer.read_snapshot('owner',source_descriptor,textual=True),observed.selection.members[0].chunk.source)
#             self.assertEqual(connection.execute('SELECT source_bytes FROM public.mycel_chunk_versions WHERE id=%s',
#                                                (observed.dependant.chunk.version,)).fetchone()[0],observed.dependant.chunk.source)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceStoreTests.test_real_branch_stash_baselines_restore_own_exact_versions_and_inherit_without_source_repin
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real branch stash baselines restore own exact versions and inherit without source repin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_branch_stash_baselines_restore_own_exact_versions_and_inherit_without_source_repin(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             branch = self.seed(connection, inputs(location=evidence.CaptureLocation('branch','a'*40)))
#             writer = evidence.EvidenceStore(connection)
#             dependency = uuid4()
#             branch_id = self.pin(writer, branch, dependency=dependency, reread=lambda: self.observe(connection, branch))
#             branch_baseline = writer.read_baseline('owner', branch_id)
#             stash_input = inputs(dependant='# Answer\nNew exact answer.\n', source='# Source\nChanged source.\n',
#                                  location=evidence.CaptureLocation('stash','b'*40))
#             stash = self.seed(connection, stash_input)
#             stash_id = self.pin(writer, stash, reread=lambda: self.observe(connection, stash))
#             self.assertNotEqual(stash_id, branch_id)
#             self.assertEqual(writer.read_baseline('owner', branch_id), branch_baseline)
#             restored = self.observe(connection, branch)
#             self.assertEqual(restored.dependant.chunk.version, branch.dependant.chunk.version)
#             changed = inputs(dependant='# Answer\nExact\tanswer.\n', source='# Source\nLatest source.\n')
#             current = self.seed(connection, changed)
#             inherited_id = writer.inherit_pin(current, lambda: self.observe(connection, current), previous_dependency=dependency,
#                     dependency_id=uuid4(), authorization='normalized_equivalent_edit')
#             inherited = writer.read_baseline('owner', inherited_id)
#             self.assertEqual(inherited.manifest.payload['members'], branch_baseline.manifest.payload['members'])
#             self.assertEqual(inherited.manifest.payload['pinnedHash'], branch_baseline.manifest.payload['pinnedHash'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceStoreTests.test_real_exact_reconstruction_limits_non_utf8_and_unsupported_comparison_never_repin
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real exact reconstruction limits non utf8 and unsupported comparison never repin.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_exact_reconstruction_limits_non_utf8_and_unsupported_comparison_never_repin(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             observed = self.seed(connection, inputs())
#             writer = evidence.EvidenceStore(connection)
#             identifier = self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
#             baseline = writer.read_baseline('owner', identifier)
#             descriptor = evidence.SnapshotEvidence.from_record(json.loads(evidence.canonical_json(baseline.manifest.payload['dependant'])))
#             exact = writer.read_snapshot('owner', descriptor)
#             self.assertEqual(evidence.reconstruct(descriptor, (observed.dependant_file.source,)), exact)
#             for request, status in ((lambda: writer.read_snapshot('owner', descriptor, limit=1), 'input_too_large'),
#                     (lambda: writer.read_snapshot('owner', replace(descriptor, hash='0'*64)), 'baseline_missing'),
#                     (lambda: writer.read_snapshot('owner', replace(descriptor, comparison=replace(descriptor.comparison, revision='unknown'))), 'unsupported_comparison')):
#                 with self.assertRaises(evidence.EvidenceError) as error:
#                     request()
#                 self.assertEqual(error.exception.status, status)
#             self.assertEqual(writer.read_baseline('owner', identifier), baseline)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceStoreTests.test_real_binary_file_evidence_and_corrupt_metadata_are_visible_without_lossy_text
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real binary file evidence and corrupt metadata are visible without lossy text.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_binary_file_evidence_and_corrupt_metadata_are_visible_without_lossy_text(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             observed = inputs(whole=True)
#             binary = replace(observed.selection.file, source=b'\xff\x00exact bytes',
#                              snapshot_hash=sha256(b'\xff\x00exact bytes').hexdigest(), chunks=())
#             catalog = SourceResolver(observed.settings, (observed.dependant_file, binary))
#             resolution = catalog.resolve(observed.resolution.declaration)
#             observed = replace(observed, selection=resolution.selection, resolution=resolution, catalog=catalog)
#             observed = self.seed(connection, observed)
#             writer = evidence.EvidenceStore(connection)
#             identifier = self.pin(writer, observed, reread=lambda: self.observe(connection, observed))
#             baseline = writer.read_baseline('owner', identifier)
#             descriptor = evidence.SnapshotEvidence.from_record(json.loads(evidence.canonical_json(
#                 baseline.manifest.payload['members'][0]['evidence'])))
#             self.assertEqual(writer.read_snapshot('owner', descriptor), binary.source)
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.read_snapshot('owner', descriptor, textual=True)
#             self.assertEqual(error.exception.status, 'insufficient_evidence')
#             connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
#                                (Jsonb({'schema':1,'bytes':0,'encoding':'bytes'}),'owner',descriptor.hash))
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.read_baseline('owner', identifier)
#             self.assertEqual(error.exception.status, 'snapshot_corrupt')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0],1)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence.py::EvidenceStoreTests.test_real_confirmation_releases_old_live_pin_but_preserves_verification_owner
# Reason: Narrower case removed from this family after retaining test_real_owner_owned_complete_evidence_survives_source_deletion_and_is_not_searchable, test_real_callback_and_mid_transaction_failure_write_no_partial_baseline. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real confirmation releases old live pin but preserves verification owner.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_confirmation_releases_old_live_pin_but_preserves_verification_owner(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             observed = self.seed(connection, inputs())
#             writer = evidence.EvidenceStore(connection)
#             dependency = uuid4()
#             first = self.pin(writer, observed, dependency=dependency, reread=lambda: self.observe(connection, observed))
#             owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (dependency,)).fetchone()[0]
#             connection.execute('INSERT INTO public.mycel_verifications VALUES (%s,%s,%s,clock_timestamp(),%s,%s)',
#                                (uuid4(),'owner',observed.dependant.chunk.identifier,Jsonb({}),owner))
#             second = writer.pin(observed, lambda: self.observe(connection, observed), dependency_id=dependency,
#                  kind='declared',declaration=observed.resolution.declaration,captured_at='2026-10-09T00:01:00Z',
#                  authorization='owner_confirmation',expected_owner=owner)
#             self.assertNotEqual(first, second)
#             self.assertIsNotNone(connection.execute('SELECT id FROM public.mycel_evidence_owners WHERE id=%s',(owner,)).fetchone())
#             self.assertEqual(writer.read_baseline('owner', first).manifest.identifier, first)
#             second_owner = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (dependency,)).fetchone()[0]
#             third = writer.pin(observed, lambda: self.observe(connection, observed), dependency_id=dependency,
#                  kind='declared',declaration=observed.resolution.declaration,captured_at='2026-10-09T00:02:00Z',
#                  authorization='owner_confirmation',expected_owner=second_owner)
#             self.assertIsNone(connection.execute('SELECT id FROM public.mycel_evidence_owners WHERE id=%s',(second_owner,)).fetchone())
#             self.assertIsNotNone(connection.execute('SELECT hash FROM public.mycel_manifests WHERE repository=%s AND hash=%s',('owner',first)).fetchone())
#             self.assertEqual(writer.read_baseline('owner', third).manifest.identifier, third)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
