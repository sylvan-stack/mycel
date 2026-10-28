"""Synthetic complete evidence proves publication policy, not native release.

These fixtures use real files, fsynced replacements, non-waiting kernel locks
and the actual independent selector. No package, Keychain, database or provider
probe is run by these unit checks.
"""
import copy
import json
import os
import tomllib
import unittest

from mycel_build import _publication as publication
from mycel_build._core import (
    atomic_json,
    digest,
    file_manifest,
    json_bytes,
    seal_program,
)
from mycel_build._credential_contract import (
    FALSE_FIELDS,
    HELPERS,
    PROVENANCE,
    TRUE_FIELDS,
)
from mycel_build._launcher_runtime import select_build
from mycel_build._qualification import (
    automatic_contract,
    qualification_certificate,
    required_packaged_cases,
)
from mycel_build._registry import allocate
from mycel_build._staging import check_input_manifest, input_manifest

try:
    from .test_automatic_qualification import closed_reply
    from .test_launcher_installation import bundle_fixture
    pass
    from .test_launcher_selection import ROOT, LauncherFixture, thaw
except ImportError:
    from test_automatic_qualification import closed_reply
    from test_launcher_installation import bundle_fixture
    from test_launcher_selection import ROOT, LauncherFixture, thaw


def selected(root):
    value = select_build(root, [], target='macos-arm64')
    try:
        return value.number
    finally:
        os.close(value.run_fd)


def corrupt(path):
    path.chmod(0o644)
    path.write_bytes(path.read_bytes()+b'corrupt')
    path.chmod(0o444)


def publication_contract_inputs():
    """Complete fictional protocol preconditions, never executed check evidence."""
    return {'tests/test_publication_protocol.py': b'''raise AssertionError("synthetic declaration bytes must never execute")
class PublicationProofs:
 def test_a_unit(self): pass
 def test_b_unit(self): pass
class PublicationStoreProofs:
 check_kind = "store"
 def test_store(self): pass
'''}


def credential_reply(number, source_identity, program_sha, check_inputs):
    """Fictional closed protocol row, never a native result or restored proof."""
    pref={'searchList':['/Library/Keychains/System.keychain'],'defaultStatus':-25307,'defaultPath':None}
    return {'schemaVersion':2,'mechanism':'public_apple_fixture_explicit_handle_key_command',
        'name':publication.KEYCHAIN_CHECK,'passed':True,'executed':True,'target':'macos-arm64','build':int(number,16),
        'sourceInputsSha256':source_identity['inputsSha256'],'programManifestSha256':program_sha,
        'fixtureProvenance':dict(PROVENANCE),'helperSha256':{p:next(x['sha256'] for x in check_inputs if x['path']==p) for p in HELPERS},
        **{k:True for k in TRUE_FIELDS},**{k:False for k in FALSE_FIELDS},'observedSignals':[],'errors':[],
        'profilePreferenceValues':{'scope':'probe_profile_view','before':pref,'after':dict(pref),'unchanged':True},
        'nativeApiEvents':[{'stage':stage,'status':0} for stage in ('interaction_disabled','open_explicit_fixture',
            'unlock_explicit_fixture','find_explicit_fixture_item')],'elapsedSeconds':0.01}


class PublicationFixture:
    def __init__(self, base):
        self.launcher = LauncherFixture(base)
        self.root = self.launcher.registry
        self.old = self.launcher.build('1')
        self.frozen = {**publication_contract_inputs(),
            'src/mycel/__init__.py': b'', 'src/mycel/_store.py': b'STORE_FORMAT = 2\n',
            'src/mycel_build/_launcher_runtime.py': (ROOT / 'src/mycel_build/_launcher_runtime.py').read_bytes(),
            'pyproject.toml': (ROOT / 'pyproject.toml').read_bytes(),
            'packaging/build-lock.json': (ROOT / 'packaging/build-lock.json').read_bytes()}
        for path in HELPERS:
            self.frozen[path]=(ROOT/path).read_bytes()
        for path in (ROOT / 'packaging/licenses').rglob('*'):
            if path.is_file():
                self.frozen[path.relative_to(ROOT).as_posix()] = path.read_bytes()
        self.identity = {'commit': 'a' * 40, 'dirty': True,
                         'inputsSha256': digest(json_bytes(input_manifest(self.frozen)))}
        self.record = allocate(self.root, target='macos-arm64', version='2.0.0', source=self.identity)
        self.number = self.record['build']
        self.folder = self.root / self.number
        self.program = self.folder / 'program'
        site = self.program / 'runtime/lib/python3.14/site-packages'
        for name, raw in self.frozen.items():
            if name.startswith('src/mycel/'):
                target = site / name.removeprefix('src/')
            elif name.startswith('packaging/licenses/'):
                target = self.program / name.removeprefix('packaging/')
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (site / 'mycel/data').mkdir(parents=True, exist_ok=True)
        atomic_json(site / 'mycel/data/build-identity.json', {'schemaVersion': 1, 'build': int(self.number, 16)})
        interpreter = self.program / 'runtime/bin/python3'
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text('#!/bin/sh\nexit 0\n'); interpreter.chmod(0o755)
        (self.program / 'build-lock.json').write_bytes(self.frozen['packaging/build-lock.json'])
        project = tomllib.loads(self.frozen['pyproject.toml'].decode())['project']
        dist = site / ('mycel-' + project['version'] + '.dist-info'); dist.mkdir()
        metadata = ['Metadata-Version: 2.4', 'Name: mycel', 'Version: ' + project['version'],
            'Summary: A finite command line for maintained repository knowledge',
            'Requires-Python: ' + project['requires-python']]
        metadata += ['Requires-Dist: ' + row for row in project['dependencies']]
        (dist / 'METADATA').write_text('\n'.join(metadata) + '\n')
        (dist / 'WHEEL').write_bytes(b'Wheel-Version: 1.0\nGenerator: mycel_build (stdlib)\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        (dist / 'entry_points.txt').write_bytes(b'[console_scripts]\nmycel = mycel._cli:main\n')
        seal_program(self.program)
        manifest = file_manifest(self.program)
        atomic_json(self.folder / 'files.json', manifest)
        atomic_json(self.folder / 'source-inputs.json', input_manifest(self.frozen))
        check_inputs = check_input_manifest(input_manifest(self.frozen))
        atomic_json(self.folder / 'check-inputs.json', check_inputs)
        self.bundle = bundle_fixture(self.folder, 'launcher-bundle')
        thaw(self.bundle)
        (self.bundle / 'program/launcher.py').write_bytes(self.frozen['src/mycel_build/_launcher_runtime.py'])
        pin = json.loads(self.frozen['packaging/build-lock.json'])['targets']['macos-arm64']
        for row in pin['runtime']['licenses']:
            destination = self.bundle / 'program' / row['path']
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(self.frozen['packaging/' + row['path']])
        seal_program(self.bundle / 'program')
        bundle = json.loads((self.bundle / 'bundle.json').read_bytes())
        bundle_manifest = file_manifest(self.bundle / 'program')
        bundle.update(filesSha256=digest(json_bytes(bundle_manifest)),
                      payloadSha256=digest(self.frozen['src/mycel_build/_launcher_runtime.py']))
        atomic_json(self.bundle / 'files.json', bundle_manifest)
        atomic_json(self.bundle / 'bundle.json', bundle)
        (self.bundle / 'files.json').chmod(0o444); (self.bundle / 'bundle.json').chmod(0o444)
        self.bundle.chmod(0o555)
        self.record.update(program='program', runtime=pin['runtime'], dependencies=pin['dependencies'],
            filesManifest='files.json', filesSha256=digest(json_bytes(manifest)),
            checkInputs='check-inputs.json', checkManifestSha256=digest(json_bytes(check_inputs)),
            lockSha256=digest(self.frozen['packaging/build-lock.json']), storeFormat=2, searchReply=3,
            dataFiles=[row for row in manifest if '/mycel/data/' in row['path'] or row['path'].startswith('licenses/')],
            launcherBundle='launcher-bundle', launcherBundleSha256=digest(json_bytes(bundle)),
            phase='qualified', automaticQualification=True)
        contract = automatic_contract(self.frozen)
        self.automatic_count = len(contract['declarations'])
        automatic = closed_reply(contract)
        for row in automatic['checks']:row['detail'] = None
        automatic.update(name='installed_automatic_unit_store_gate', target='macos-arm64', build=int(self.number,16),
            required=self.automatic_count, passedCount=self.automatic_count, failedCount=0, completeFrozenInventory=True,
            sourceInputsSha256=self.identity['inputsSha256'], networkRestrictedToCheckStore=True,
            sourceReadDenied=True, developerReadDenied=True, installedFilesUnchanged=True, verifiedPrivateRelocation=True)
        probe = {'name':'installed_native_and_two_path_probe', 'passed':True, 'executed':True,
            'target':'macos-arm64', 'sourceReadDenied':True, 'networkAndWritesDenied':True,
            'relocations':[{'python':'3.14.7','machine':'arm64','macOS':'14.0','isolated':True,'dontWriteBytecode':True,
                           'build':int(self.number,16)} for _ in range(2)]}
        names = required_packaged_cases(self.number)
        packaged = {'name':'packaged_selector_and_cli_two_path_probe','passed':True,'executed':True,
            'target':'macos-arm64','runtime':'3.14.7','machine':'arm64',
            **{name:True for name in ('networkAndWritesDenied','sourceReadDenied','developerReadDenied',
                                     'ownerStateDenied','retainedInputsUnchanged')},
            'relocations':[{'label':label,'passed':True,'executed':True,'privateWorkingRecordFixtureOnly':True,
                'ownerPublished':False,'cases':[{'name':name,'passed':True,'executed':True,'elapsedSeconds':0.001}
                                              for name in names]}
                for label in ('first installation','second relocated installation')]}
        keychain = credential_reply(self.number,self.identity,self.record['filesSha256'],check_inputs)
        self.checks = {'schemaVersion':1,'results':[probe,
            {'name':'independent_launcher_bootstrap_two_path_probe',**bundle['checks']},automatic,packaged,keychain],
            'pending':['publication']}
        self.record['checks'] = {'required':self.automatic_count+4,'passed':self.automatic_count+4,'failed':0,'report':'checks.json'}
        self.record['qualification'] = qualification_certificate(number=self.number,source=self.identity,
            check_inputs=check_inputs,program_sha256=self.record['filesSha256'],
            launcher_sha256=self.record['launcherBundleSha256'],target='macos-arm64',runtime=pin['runtime'],
            results=self.checks['results'],publication=True)
        assert self.record['qualification'] is not None
        self.save()

    def stage_record(self):
        '''Coherent fictional four-group staged precondition; no probes run.'''
        checks = copy.deepcopy(self.checks)
        assert checks['results'].pop()['name'] == publication.KEYCHAIN_CHECK
        staged = {**self.record, 'checks': {'required': self.automatic_count + 3,
                  'passed': self.automatic_count + 3, 'failed': 0, 'report': 'checks.json'}}
        staged['qualification'] = qualification_certificate(number=self.number, source=self.identity,
            check_inputs=check_input_manifest(input_manifest(self.frozen)), program_sha256=staged['filesSha256'],
            launcher_sha256=staged['launcherBundleSha256'], target='macos-arm64', runtime=staged['runtime'],
            results=checks['results'])
        assert staged['qualification'] is not None
        atomic_json(self.folder / 'checks.json', checks)
        atomic_json(self.folder / 'build.json', staged)
        return staged

    def save(self):
        atomic_json(self.folder / 'checks.json',self.checks)
        atomic_json(self.folder / 'build.json',self.record)

    def publish(self):
        return publication.publish(self.root,self.number,frozen=self.frozen,source_identity=self.identity)


class WorkingPublicationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
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

# Archived complete imports; restore needed names in their original scope, not at this file tail.
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
