"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_working_publication as _support
# from test_working_publication import (
#     FALSE_FIELDS,
#     HELPERS,
#     LauncherFixture,
#     PROVENANCE,
#     PublicationFixture,
#     ROOT,
#     TRUE_FIELDS,
#     WorkingPublicationTests,
#     allocate,
#     atomic_json,
#     automatic_contract,
#     bundle_fixture,
#     check_input_manifest,
#     closed_reply,
#     copy,
#     corrupt,
#     credential_reply,
#     digest,
#     file_manifest,
#     input_manifest,
#     json,
#     json_bytes,
#     os,
#     publication,
#     publication_contract_inputs,
#     qualification_certificate,
#     required_packaged_cases,
#     seal_program,
#     select_build,
#     selected,
#     thaw,
#     tomllib,
#     unittest,
# )


# class WorkingPublicationTests(_support.WorkingPublicationTests):
# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_working_record_is_last_replacement_and_only_then_changes_real_numeric_selector
#     def test_working_record_is_last_replacement_and_only_then_changes_real_numeric_selector(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture = PublicationFixture(temporary)
#             self.assertEqual(selected(fixture.root),'1')
#             writes=[]; original=publication.atomic_json
#             def record_write(path,value):
#                 writes.append(path.name)
#                 if path.name=='build.json':
#                     self.assertEqual(value['status'],'working')
#                     self.assertEqual(read_record(fixture.root,fixture.number)['status'],'building')
#                     self.assertEqual(json.loads((fixture.folder/'checks.json').read_bytes())['pending'],[])
#                     self.assertEqual((fixture.folder/'build.log').read_text(),publication.FINAL_LOG)
#                 return original(path,value)
#             with patch.object(publication,'atomic_json',side_effect=record_write):
#                 result=fixture.publish()
#             self.assertEqual(writes,['checks.json','build.json'])
#             self.assertEqual((result['status'],selected(fixture.root)),('working',fixture.number))
#             before=tree_state(fixture.root)
#             self.assertEqual(fixture.publish(),result)
#             self.assertEqual(tree_state(fixture.root),before)
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_working_record_is_last_replacement_and_only_then_changes_real_numeric_selector

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_each_precommit_failure_or_interrupt_preserves_old_default_and_exact_retry_is_controlled
#     def test_each_precommit_failure_or_interrupt_preserves_old_default_and_exact_retry_is_controlled(self):
#         for boundary in ('checks','log','record'):
#             for exception in (OSError,KeyboardInterrupt):
#                 with self.subTest(boundary=boundary,exception=exception),tempfile.TemporaryDirectory() as temporary:
#                     fixture=PublicationFixture(temporary); original=publication.atomic_json
#                     def write(path,value):
#                         if (boundary=='checks' and path.name=='checks.json') or (boundary=='record' and path.name=='build.json'):
#                             raise exception('private failure text')
#                         return original(path,value)
#                     with patch.object(publication,'atomic_json',side_effect=write),patch.object(publication,'_write_log',
#                             side_effect=exception('private failure text') if boundary=='log' else publication._write_log):
#                         with self.assertRaises(KeyboardInterrupt if exception is KeyboardInterrupt else BuildError):fixture.publish()
#                     self.assertEqual((read_record(fixture.root,fixture.number)['status'],selected(fixture.root)),('building','1'))
#                     result=fixture.publish()
#                     self.assertEqual((result['status'],selected(fixture.root)),('working',fixture.number))
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_each_precommit_failure_or_interrupt_preserves_old_default_and_exact_retry_is_controlled

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade
#     def test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade(self):
#         for exception in (OSError,KeyboardInterrupt):
#             with self.subTest(exception=exception),tempfile.TemporaryDirectory() as temporary:
#                 fixture=PublicationFixture(temporary); original=publication.atomic_json
#                 def write(path,value):
#                     original(path,value)
#                     if path.name=='build.json':raise exception('private postcommit sentinel')
#                 with patch.object(publication,'atomic_json',side_effect=write):
#                     with self.assertRaises(KeyboardInterrupt if exception is KeyboardInterrupt else BuildError) as failure:fixture.publish()
#                 self.assertEqual(failure.exception.partialResult['status'],'working')
#                 self.assertEqual((read_record(fixture.root,fixture.number)['status'],selected(fixture.root)),('working',fixture.number))
#                 self.assertNotIn('private postcommit sentinel',str(failure.exception) if isinstance(failure.exception,BuildError) else '')
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_corrupt_manifests_proofs_results_identities_or_missing_required_groups_never_publish
#     def test_corrupt_manifests_proofs_results_identities_or_missing_required_groups_never_publish(self):
#         mutations=(lambda f:f.checks['results'].pop(),
#             lambda f:f.checks['results'][2]['checks'].pop(),
#             lambda f:f.checks['results'][2]['checks'][0].update(kind='store'),
#             lambda f:f.checks['results'][2]['checks'][0].update(name='test_publication_protocol.PublicationProofs.test_invented'),
#             lambda f:f.checks['results'][3]['relocations'][1]['cases'].pop(),
#             lambda f:f.checks['results'][3]['relocations'][1]['cases'][0].update(name='invented_same_count_case'),
#             lambda f:f.checks['results'][3]['relocations'][0]['cases'].reverse(),
#             lambda f:f.checks['results'][2].update(gateErrorCount=1),
#             lambda f:f.checks['results'][4]['profilePreferenceValues'].update(unchanged=False),
#             lambda f:f.record.update(source={**f.identity,'inputsSha256':'f'*64}),
#             lambda f:f.record.update(qualification={**f.record['qualification'],'sha256':'f'*64}),
#             lambda f:f.record.update(checks={**f.record['checks'],'required':6}),
#             lambda f:(f.folder/'source-inputs.json').write_text('[]\n'),
#             lambda f:(f.folder/'check-inputs.json').write_text('[]\n'),
#             lambda f:(f.folder/'files.json').write_text('[]\n'),
#             lambda f:corrupt(f.program/'runtime/lib/python3.14/site-packages/mycel/_store.py'),
#             lambda f:corrupt(f.bundle/'program/launcher.py'))
#         for index,mutate in enumerate(mutations):
#             with self.subTest(index=index),tempfile.TemporaryDirectory() as temporary:
#                 fixture=PublicationFixture(temporary); mutate(fixture)
#                 if index<12:fixture.save()
#                 before=tree_state(fixture.root)
#                 with self.assertRaises(BuildError):fixture.publish()
#                 self.assertEqual(selected(fixture.root),'1')
#                 self.assertEqual(tree_state(fixture.root),before)
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_corrupt_manifests_proofs_results_identities_or_missing_required_groups_never_publish

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_peer_registry_lock_is_immediately_busy_with_no_write_or_default_change
#     def test_peer_registry_lock_is_immediately_busy_with_no_write_or_default_change(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture=PublicationFixture(temporary); before=tree_state(fixture.root)
#             with peer_lock(fixture.root/'.registry.lock',fcntl.LOCK_EX):
#                 with self.assertRaises(BuildError) as error:fixture.publish()
#                 self.assertEqual(error.exception.code,'busy')
#             self.assertEqual(selected(fixture.root),'1')
#             self.assertEqual(tree_state(fixture.root),before)
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_peer_registry_lock_is_immediately_busy_with_no_write_or_default_change

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_create_orchestration_recaptures_source_keeps_paid_probes_out_and_preserves_published_partial
#     def test_create_orchestration_recaptures_source_keeps_paid_probes_out_and_preserves_published_partial(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture=PublicationFixture(temporary)
#             failed={**fixture.stage_record(),'status':'failed','automaticQualification':False,
#                 'reason':'A required installed check failed; see checks.json.'}
#             before=tree_state(fixture.root)
#             with patch.object(release,'create_stage',return_value=failed), \
#                     patch.object(release,'source_inputs') as source, \
#                     patch.object(release,'probe_private_keychain') as credential, \
#                     patch.object(release,'publish') as publisher:
#                 self.assertIs(release.create_release(ROOT,ROOT/'packaging/build-lock.json',Path(temporary),
#                     fixture.root,'macos-arm64'),failed)
#             source.assert_not_called(); credential.assert_not_called(); publisher.assert_not_called()
#             self.assertEqual(tree_state(fixture.root),before)
#             self.assertEqual(selected(fixture.root),'1')
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture=PublicationFixture(temporary)
#             staged=fixture.stage_record()
#             basechecks=copy.deepcopy(fixture.checks); keychain=basechecks['results'].pop()
#             atomic_json(fixture.folder/'checks.json',basechecks)
#             with patch.object(release,'create_stage',return_value=staged),patch.object(release,'source_inputs',
#                     return_value=(fixture.identity,fixture.frozen)),patch.object(release,'probe_private_keychain',return_value=keychain) as probe:
#                 result=release.create_release(ROOT,ROOT/'packaging/build-lock.json',Path(temporary),fixture.root,'macos-arm64')
#             self.assertEqual((result['status'],selected(fixture.root)),('working',fixture.number))
#             probe.assert_called_once()
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture=PublicationFixture(temporary)
#             with patch.object(release,'create_stage',return_value=fixture.record),patch.object(release,'source_inputs',
#                     return_value=({**fixture.identity,'inputsSha256':'f'*64},fixture.frozen)),patch.object(release,'probe_private_keychain') as probe:
#                 result=release.create_release(ROOT,ROOT/'packaging/build-lock.json',Path(temporary),fixture.root,'macos-arm64')
#             self.assertEqual((result['status'],selected(fixture.root)),('failed','1')); probe.assert_not_called()
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture=PublicationFixture(temporary)
#             staged=fixture.stage_record()
#             checks=copy.deepcopy(fixture.checks); checks['results'].pop()
#             atomic_json(fixture.folder/'checks.json',checks)
#             with patch.object(release,'create_stage',return_value=staged),patch.object(release,'source_inputs',
#                     return_value=(fixture.identity,fixture.frozen)),patch.object(release,'probe_private_keychain',
#                     return_value={'passed':False,'executed':False,'target':'macos-arm64'}):
#                 result=release.create_release(ROOT,ROOT/'packaging/build-lock.json',Path(temporary),fixture.root,'macos-arm64')
#             self.assertEqual((result['status'],selected(fixture.root)),('failed','1'))
#             named=json.loads((fixture.folder/'checks.json').read_bytes())['results'][-1]
#             self.assertEqual((named['name'],named['passed'],named['executed']),
#                              (publication.KEYCHAIN_CHECK,False,False))
#         for exception,expected in ((OSError,1),(KeyboardInterrupt,2)):
#             with self.subTest(exception=exception),tempfile.TemporaryDirectory() as temporary:
#                 fixture=PublicationFixture(temporary); staged=fixture.stage_record()
#                 checks=copy.deepcopy(fixture.checks); keychain=checks['results'].pop()
#                 atomic_json(fixture.folder/'checks.json',checks); original=publication.atomic_json
#                 def late(path,value):
#                     original(path,value)
#                     if path.name=='build.json':raise exception('private postpublication sentinel')
#                 with patch.object(release,'create_stage',return_value=staged),patch.object(release,'source_inputs',
#                         return_value=(fixture.identity,fixture.frozen)),patch.object(release,'probe_private_keychain',
#                         return_value=keychain),patch.object(publication,'atomic_json',side_effect=late), \
#                         contextlib.redirect_stdout(io.StringIO()) as output:
#                     self.assertEqual(main(['create','--target','macos-arm64','--assets',temporary,
#                                            '--registry',str(fixture.root)]),expected)
#                 result=json.loads(output.getvalue())
#                 self.assertEqual(result['partial']['status'],'working')
#                 self.assertEqual((read_record(fixture.root,fixture.number)['status'],selected(fixture.root)),('working',fixture.number))
#                 self.assertNotIn('private postpublication sentinel',output.getvalue())
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_create_orchestration_recaptures_source_keeps_paid_probes_out_and_preserves_published_partial

# TEST-TIER-DISABLED-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_unavailable_private_keychain_boundary_refuses_without_native_operations_or_publication
#     def test_unavailable_private_keychain_boundary_refuses_without_native_operations_or_publication(self):
#         # This is a controller protocol fixture, never actual Keychain proof.
#         # A failed qualification is explicit; no real or synthetic native pass.
#         with tempfile.TemporaryDirectory() as temporary:
#             fixture = PublicationFixture(temporary)
#             before = tree_state(fixture.root)
#             program_before = tree_state(fixture.program)
#             with patch.object(subprocess,'Popen',side_effect=AssertionError('No credential or metadata child is allowed.')) as children, \
#                     patch('ctypes.CDLL',side_effect=AssertionError('No native library is allowed.')) as libraries, \
#                     patch('secrets.token_hex',side_effect=AssertionError('No dummy secret may be created.')) as secrets, \
#                     patch.object(keychain_probe.sys,'platform','unsupported'):
#                 result = keychain_probe.probe_private_keychain(fixture.program,'macos-arm64',
#                     source_root=ROOT,number=fixture.number)
#                 self.assertFalse(result['passed'])
#                 self.assertFalse(result['executed'])
#                 self.assertFalse(result['privateFixtureMaterialized'] or result['nativeItemCreated'])
#                 self.assertFalse(result['installedCredentialsRead'] or result['globalOwnerPreferencesAssessed'])
#                 self.assertFalse(result['daemonIsolationClaimed'])
#                 self.assertTrue(result['errors'])
#                 self.assertEqual(tree_state(fixture.root),before)
#                 children.assert_not_called(); libraries.assert_not_called(); secrets.assert_not_called()
#                 staged = fixture.stage_record()
#                 checks = copy.deepcopy(fixture.checks); checks['results'].pop()
#                 atomic_json(fixture.folder/'checks.json',checks)
#                 old_default_before = tree_state(fixture.root/'1')
#                 with patch.object(release,'create_stage',return_value=staged), \
#                         patch.object(release,'source_inputs',return_value=(fixture.identity,fixture.frozen)):
#                     actual = release.create_release(ROOT,ROOT/'packaging/build-lock.json',Path(temporary),
#                                                     fixture.root,'macos-arm64')
#                 self.assertEqual(actual['status'],'failed')
#                 self.assertFalse(actual['automaticQualification'])
#                 self.assertIsNone(actual['qualification'])
#                 self.assertEqual(actual['checks'],{'required':fixture.automatic_count+4,'passed':fixture.automatic_count+3,'failed':1,'report':'checks.json'})
#                 named = [row for row in json.loads((fixture.folder/'checks.json').read_bytes())['results']
#                          if row['name']==publication.KEYCHAIN_CHECK]
#                 self.assertEqual(len(named),1)
#                 self.assertFalse(named[0]['passed'] or named[0]['executed'])
#                 self.assertFalse(named[0]['nativeItemCreated'] or named[0]['globalOwnerPreferencesAssessed'])
#                 self.assertEqual(selected(fixture.root),'1')
#                 self.assertEqual(tree_state(fixture.root/'1'),old_default_before)
#                 self.assertEqual(tree_state(fixture.program),program_before)
#                 children.assert_not_called(); libraries.assert_not_called(); secrets.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_working_publication.py::WorkingPublicationTests.test_unavailable_private_keychain_boundary_refuses_without_native_operations_or_publication


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:8
# import contextlib
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:9
# import fcntl
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:10
# import io
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:13
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:13

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:14
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:14

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:15
# import subprocess
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:15

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:18
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:18

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:21
# from mycel_build import _release as release
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:21

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:22
# from mycel_build import _keychain_probe as keychain_probe
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:22

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:24
# from mycel_build.__main__ import main
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:24

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:25
# from mycel_build._core import BuildError, atomic_json, digest, file_manifest, json_bytes, seal_program
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:25

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:28
# from mycel_build._registry import allocate, read_record
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:28

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:34
#     from .test_launcher_maintenance import peer_lock
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:34

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:35
#     from .test_launcher_selection import LauncherFixture, ROOT, thaw, tree_state
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:35

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:39
#     from test_launcher_maintenance import peer_lock
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:39

# TEST-TIER-IMPORTS-BEGIN tests/test_working_publication.py:40
#     from test_launcher_selection import LauncherFixture, ROOT, thaw, tree_state
# TEST-TIER-IMPORTS-END tests/test_working_publication.py:40

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
