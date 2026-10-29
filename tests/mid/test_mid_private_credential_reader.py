"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_private_credential_reader as _support
# from test_private_credential_reader import (
#     API,
#     FIXTURE_SOURCE,
#     Path,
#     PrivateCredentialReaderTests,
#     ROOT,
#     ctypes,
#     re,
#     reader,
#     tempfile,
#     unittest,
# )


# class PrivateCredentialReaderTests(_support.PrivateCredentialReaderTests):
# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_exact_handle_is_used_and_native_buffer_is_zeroed_before_free
#     def test_exact_handle_is_used_and_native_buffer_is_zeroed_before_free(self):
#         api=API(self.path);value,receipt=self.run_fake(api)
#         self.assertEqual(value,b'public-standin');self.assertTrue(api.zeroed)
#         self.assertEqual([x[1] for x in api.calls if x[0] in {'unlock','find','lock','release'}],[101]*4)
#         self.assertTrue(receipt['explicitHandleOnly']);self.assertEqual(api.calls[0],('interaction',False));value[:]=b'\0'*len(value)
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_exact_handle_is_used_and_native_buffer_is_zeroed_before_free

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_failed_open_never_unlocks_or_searches_another_keychain
#     def test_failed_open_never_unlocks_or_searches_another_keychain(self):
#         api=API(self.path,open_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0] in {'unlock','find'} for x in api.calls))
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_failed_open_never_unlocks_or_searches_another_keychain

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_success_status_with_null_handle_refuses_before_lookup
#     def test_success_status_with_null_handle_refuses_before_lookup(self):
#         api=API(self.path,null_handle=True)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0]=='find' for x in api.calls))
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_success_status_with_null_handle_refuses_before_lookup

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_handle_path_outside_live_root_refuses_before_unlock
#     def test_handle_path_outside_live_root_refuses_before_unlock(self):
#         api=API(self.path,native_path=Path('/unowned/default.keychain'))
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0] in {'unlock','find','lock'} for x in api.calls))
#         self.assertIn(('release',101),api.calls)
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_handle_path_outside_live_root_refuses_before_unlock

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_unlock_failure_never_attempts_password_lookup
#     def test_unlock_failure_never_attempts_password_lookup(self):
#         api=API(self.path,unlock_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertFalse(any(x[0]=='find' for x in api.calls));self.assertIn(('lock',101),api.calls)
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_unlock_failure_never_attempts_password_lookup

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_lookup_failure_still_locks_and_releases_only_actual_handle
#     def test_lookup_failure_still_locks_and_releases_only_actual_handle(self):
#         api=API(self.path,find_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertIn(('lock',101),api.calls);self.assertIn(('release',101),api.calls)
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_lookup_failure_still_locks_and_releases_only_actual_handle

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_lock_failure_prevents_payload_return
#     def test_lock_failure_prevents_payload_return(self):
#         api=API(self.path,lock_status=-1)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertTrue(api.zeroed)
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_lock_failure_prevents_payload_return

# TEST-TIER-DISABLED-BEGIN tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_modified_fixture_refuses_before_any_native_call
#     def test_modified_fixture_refuses_before_any_native_call(self):
#         self.path.write_bytes(b'not a fixture');api=API(self.path)
#         with self.assertRaises(reader.Refusal):self.run_fake(api)
#         self.assertEqual(api.calls,[])
# TEST-TIER-DISABLED-END tests/test_private_credential_reader.py::PrivateCredentialReaderTests.test_modified_fixture_refuses_before_any_native_call


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_private_credential_reader.py:3
# import hashlib
# TEST-TIER-IMPORTS-END tests/test_private_credential_reader.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_private_credential_reader.py:4
# import json
# TEST-TIER-IMPORTS-END tests/test_private_credential_reader.py:4

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
