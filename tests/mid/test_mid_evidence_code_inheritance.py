
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceUnitTests.test_invalid_pin_options_refuse_before_guard_or_reread
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Invalid pin options refuse before guard or reread.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_invalid_pin_options_refuse_before_guard_or_reread(self):
#         inputs = fixtures.inputs()
#         writer = evidence.EvidenceStore(object())
#         valid = dict(dependency_id=uuid4(), kind='declared', declaration=inputs.resolution.declaration,
#                      captured_at='2026-10-09T00:00:00Z', authorization='initial_resolution')
#         for changed in ({'authorization': 'unknown'}, {'kind': 'unknown'}, {'declaration': 'changed'},
#                         {'dependency_id': 'not-a-uuid'}, {'expected_owner': 'not-a-uuid'},
#                         {'expected_owner': uuid4()}):
#             with self.subTest(options=changed), patch.object(evidence, 'checked_input_guard',
#                     side_effect=AssertionError('invalid options reached the guard')), self.assertRaises(evidence.EvidenceError):
#                 writer.pin(inputs, lambda: self.fail('invalid options reached reread'), **{**valid, **changed})
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceUnitTests.test_function_and_method_renames_keep_source_pin_and_exact_new_comparison
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Function and method renames keep source pin and exact new comparison.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_function_and_method_renames_keep_source_pin_and_exact_new_comparison(self):
#         examples = (
#             ('# prefix\ndef old(x):\n    return x + 1\n', '# prefix\ndef new(x):\n    return x + 1\n', 'old', 'new', 'answer.py'),
#             ('class Box:\n    def old(self, x):\n        return x\n',
#              'class Box:\n    def new(self, x):\n        return x\n', 'Box.old', 'Box.new', 'answer.py'),
#             ('# préface\r\ndef ancien(é):\r\n    return é + 1\r\n',
#              '# préface\r\ndef nouveau(é):\r\n    return é + 1\r\n', 'ancien', 'nouveau', 'answer.py'),
#             ('function old(x: number): number { return x + 1; }\n',
#              'function newName(x: number): number { return x + 1; }\n', 'old', 'newName', 'answer.ts'),
#             ('function old(x) { return x + 1; }\n',
#              'function newName(x) { return x + 1; }\n', 'old', 'newName', 'answer.js'),
#         )
#         for old, new, old_name, new_name, path in examples:
#             with self.subTest(name=new_name, path=path):
#                 previous, current = pair(old, new, old_name, new_name, path=path)
#                 baseline = fixtures.capture(previous)
#                 inherited = evidence.inherit_baseline(baseline, current.dependant, current.dependant_file,
#                     authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
#                 for key in ('members', 'source', 'pinnedHash', 'ref', 'location', 'capturedAt'):
#                     self.assertEqual(inherited.manifest.payload[key], baseline.manifest.payload[key])
#                 self.assertNotEqual(inherited.manifest.payload['dependant']['hash'], baseline.manifest.payload['dependant']['hash'])
#                 self.assertEqual(inherited.manifest.payload['dependant']['comparison'],
#                                  current.dependant.chunk.comparison)
#                 self.assertEqual(inherited.manifest.payload['dependantVersion'], str(current.dependant.chunk.version))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceUnitTests.test_changed_signature_body_comment_or_line_endings_never_inherit
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Changed signature body comment or line endings never inherit.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_signature_body_comment_or_line_endings_never_inherit(self):
#         old = '# prefix\ndef old(x):\n    return x + 1\n'
#         changes = ('# prefix\ndef new(y):\n    return x + 1\n',
#                    '# prefix\ndef new(x):\n    return x + 2\n',
#                    '# changed\ndef new(x):\n    return x + 1\n',
#                    '# prefix\r\ndef new(x):\r\n    return x + 1\r\n')
#         for new in changes:
#             previous, current = pair(old, new)
#             with self.subTest(source=new), self.assertRaises(evidence.EvidenceError):
#                 evidence.inherit_baseline(fixtures.capture(previous), current.dependant, current.dependant_file,
#                     authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
#         for path, old, new in (
#                 ('answer.ts', 'function old(x: number): number { return x + 1; }\n',
#                  'function newName(x: number): number { return x + 2; }\n'),
#                 ('answer.js', 'function old(x) { return x + 1; }\n',
#                  'function newName(x) { return x + 2; }\n')):
#             previous, current = pair(old, new, 'old', 'newName', path=path)
#             with self.subTest(path=path), self.assertRaises(evidence.EvidenceError):
#                 evidence.inherit_baseline(fixtures.capture(previous), current.dependant, current.dependant_file,
#                     authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceUnitTests.test_code_rename_requires_authorization_complete_old_file_and_fresh_parse_spans
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Code rename requires authorization complete old file and fresh parse spans.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_code_rename_requires_authorization_complete_old_file_and_fresh_parse_spans(self):
#         previous, current = pair('# prefix\ndef old(x):\n    return x\n', '# prefix\ndef new(x):\n    return x\n')
#         baseline = fixtures.capture(previous)
#         for authorization, source in ((None, previous.dependant_file.source),
#                 ('normalized_equivalent_edit', previous.dependant_file.source),
#                 ('recognized_rename', None), ('recognized_rename', b'def old(x):\n    return x\n')):
#             with self.subTest(authorization=authorization, missing=source is None), self.assertRaises(evidence.EvidenceError):
#                 evidence.inherit_baseline(baseline, current.dependant, current.dependant_file,
#                     authorization=authorization, previous_file_source=source)
#         raw = b'def new(x):\n    return x\n'
#         forged = replace(current.dependant.chunk, source=raw, snapshot_hash=sha256(raw).hexdigest(),
#             span=(len(b'# prefix\n'), len(current.dependant_file.source)),
#             comparison=evidence.exact_comparison(raw, 'code_text').as_dict())
#         with self.assertRaises(evidence.EvidenceError):
#             evidence.inherit_baseline(baseline, replace(current.dependant, chunk=forged), current.dependant_file,
#                 authorization='recognized_rename', previous_file_source=previous.dependant_file.source)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceStoreTests.test_both_wrappers_preserve_code_rename_pin_with_new_exact_version
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Both wrappers preserve code rename pin with new exact version.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_both_wrappers_preserve_code_rename_pin_with_new_exact_version(self):
#         with self.connect() as connection:
#             writer, previous, original, old, current = self.prepare(connection,
#                 '# préface\r\ndef ancien(é):\r\n    return é\r\n', '# préface\r\ndef nouveau(é):\r\n    return é\r\n',
#                 old_name='ancien', new_name='nouveau')
#             baseline = writer.read_baseline('owner', original)
#             connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
#             catalog = SourceResolver.from_store(connection, current.settings)
#             selected = catalog.resolve(current.dependant.place.address, purpose='endpoint').selection
#             current = evidence.InheritanceInputs(current.settings, selected.members[0], selected.file,
#                 current.location, catalog.resolve(current.resolution.declaration), catalog)
#             for native in (False, True):
#                 identifier = uuid4()
#                 if native:
#                     with evidence.checked_input_guard(connection, current, lambda: current) as token, atomic_transaction(connection):
#                         inherited = writer.inherit_in_transaction(token, previous_dependency=previous,
#                             dependency_id=identifier, authorization='recognized_rename')
#                 else:
#                     inherited = writer.inherit_pin(current, lambda: current, previous_dependency=previous,
#                         dependency_id=identifier, authorization='recognized_rename')
#                 result = writer.read_baseline('owner', inherited)
#                 self.assertEqual(result.manifest.payload['members'], baseline.manifest.payload['members'])
#                 self.assertEqual(result.manifest.payload['pinnedHash'], baseline.manifest.payload['pinnedHash'])
#                 self.assertEqual(result.manifest.payload['dependantVersion'], str(current.dependant.chunk.version))
#                 self.assertNotEqual(result.manifest.payload['dependant']['hash'], baseline.manifest.payload['dependant']['hash'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceStoreTests.test_changed_code_refuses_without_writing_or_renewing_owner
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Changed code refuses without writing or renewing owner.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_changed_code_refuses_without_writing_or_renewing_owner(self):
#         with self.connect() as connection:
#             writer, previous, original, _, current = self.prepare(connection, new='def new(x):\n    return x + 1\n')
#             before = connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone()
#             for native in (False, True):
#                 with self.subTest(native=native), self.assertRaises(evidence.EvidenceError):
#                     if native:
#                         with evidence.checked_input_guard(connection, current, lambda: current) as token, atomic_transaction(connection):
#                             writer.inherit_in_transaction(token, previous_dependency=previous,
#                                 dependency_id=uuid4(), authorization='recognized_rename')
#                     else:
#                         writer.inherit_pin(current, lambda: current, previous_dependency=previous,
#                             dependency_id=uuid4(), authorization='recognized_rename')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0], 1)
#             self.assertEqual(connection.execute('SELECT baseline_owner FROM public.mycel_dependencies WHERE id=%s', (previous,)).fetchone(), before)
#             self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_evidence_code_inheritance.py::CodeInheritanceStoreTests.test_prior_complete_file_lock_is_nonblocking_and_missing_file_is_not_substituted
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Prior complete file lock is nonblocking and missing file is not substituted.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_evidence_code_inheritance.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_prior_complete_file_lock_is_nonblocking_and_missing_file_is_not_substituted(self):
#         with self.connect() as connection, self.connect() as blocker:
#             writer, previous, original, old, current = self.prepare(connection)
#             with blocker.transaction():
#                 blocker.execute('SELECT id FROM public.mycel_file_versions WHERE file_id=%s AND snapshot_hash=%s FOR UPDATE',
#                                 (old.dependant_file.identifier, old.dependant_file.snapshot_hash))
#                 with evidence.checked_input_guard(connection, current, lambda: current) as token:
#                     with self.assertRaises(MycelError) as error, atomic_transaction(connection):
#                         writer.inherit_in_transaction(token, previous_dependency=previous,
#                             dependency_id=uuid4(), authorization='recognized_rename')
#                 self.assertEqual(error.exception.code.value, 'busy')
#             connection.execute('DELETE FROM public.mycel_file_versions WHERE file_id=%s AND snapshot_hash=%s',
#                                (old.dependant_file.identifier, old.dependant_file.snapshot_hash))
#             with self.assertRaises(evidence.EvidenceError) as error:
#                 writer.inherit_pin(current, lambda: current, previous_dependency=previous,
#                     dependency_id=uuid4(), authorization='recognized_rename')
#             self.assertEqual(error.exception.status, 'baseline_missing')
#             self.assertEqual(writer.read_baseline('owner', original).manifest.identifier, original)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
