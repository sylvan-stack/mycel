
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_exact_handle_is_used_and_native_buffer_is_zeroed_before_free
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Exact handle is used and native buffer is zeroed before free.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_exact_handle_is_used_and_native_buffer_is_zeroed_before_free(self):
#         api=API(self.path);value,receipt=self.run_fake(api)
#         self.assertEqual(value,b'public-standin');self.assertTrue(api.zeroed)
#         self.assertEqual([x[1] for x in api.calls if x[0] in {'unlock','find','lock','release'}],[101]*4)
#         self.assertTrue(receipt['explicitHandleOnly']);self.assertEqual(api.calls[0],('interaction',False));value[:]=b'\0'*len(value)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_failed_open_never_unlocks_or_searches_another_keychain
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Failed open never unlocks or searches another keychain.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_failed_open_never_unlocks_or_searches_another_keychain(self):
#         api=API(self.path,open_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0] in {'unlock','find'} for x in api.calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_success_status_with_null_handle_refuses_before_lookup
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Success status with null handle refuses before lookup.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_success_status_with_null_handle_refuses_before_lookup(self):
#         api=API(self.path,null_handle=True)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0]=='find' for x in api.calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_handle_path_outside_live_root_refuses_before_unlock
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Handle path outside live root refuses before unlock.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_handle_path_outside_live_root_refuses_before_unlock(self):
#         api=API(self.path,native_path=Path('/unowned/default.keychain'))
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0] in {'unlock','find','lock'} for x in api.calls))
#         self.assertIn(('release',101),api.calls)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_unlock_failure_never_attempts_password_lookup
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Unlock failure never attempts password lookup.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unlock_failure_never_attempts_password_lookup(self):
#         api=API(self.path,unlock_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0]=='find' for x in api.calls));self.assertIn(('lock',101),api.calls)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_lookup_failure_still_locks_and_releases_only_actual_handle
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Lookup failure still locks and releases only actual handle.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_lookup_failure_still_locks_and_releases_only_actual_handle(self):
#         api=API(self.path,find_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertIn(('lock',101),api.calls);self.assertIn(('release',101),api.calls)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_lock_failure_prevents_payload_return
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Lock failure prevents payload return.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_lock_failure_prevents_payload_return(self):
#         api=API(self.path,lock_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertTrue(api.zeroed)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_private_credential_reader.py::PrivateCredentialReaderTests.test_modified_fixture_refuses_before_any_native_call
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Modified fixture refuses before any native call.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_private_credential_reader.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_modified_fixture_refuses_before_any_native_call(self):
#         self.path.write_bytes(b'not a fixture');api=API(self.path)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertEqual(api.calls,[])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
