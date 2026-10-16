"""Constructed credential protocol rows, never native Keychain evidence."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mycel._coverage import proves
from mycel_build._core import BuildError, atomic_json, digest
from mycel_build import _keychain_probe as probe
from mycel_build._credential_contract import (PROVENANCE, TRUE_FIELDS, FALSE_FIELDS, HELPERS,
    FIXTURE_SOURCE, FIXTURE_LICENSE, FIXTURE_PROVENANCE, credential_probe_passed, public_fixture)
from mycel_build._qualification import qualification_certificate
from mycel_build import _publication as publication

ROOT=Path(__file__).resolve().parents[1]


def protocol():
    """Only the receiver's wire contract; not a proof object or actual result."""
    inputs=[{'path':p,'sha256':digest((ROOT/p).read_bytes()),'size':(ROOT/p).stat().st_size} for p in HELPERS]
    pref={'searchList':['/Library/Keychains/System.keychain'],'defaultStatus':-25307,'defaultPath':None}
    row={'schemaVersion':2,'mechanism':'public_apple_fixture_explicit_handle_key_command','passed':True,'executed':True,
        'target':'macos-arm64','build':2,'sourceInputsSha256':'a'*64,'programManifestSha256':'b'*64,
        'fixtureProvenance':dict(PROVENANCE),'helperSha256':{p:x['sha256'] for p,x in zip(HELPERS,inputs)},
        **{k:True for k in TRUE_FIELDS},**{k:False for k in FALSE_FIELDS},'observedSignals':[],'errors':[],
        'profilePreferenceValues':{'scope':'probe_profile_view','before':pref,'after':copy.deepcopy(pref),'unchanged':True},
        'nativeApiEvents':[{'stage':s,'status':0} for s in ('interaction_disabled','open_explicit_fixture','unlock_explicit_fixture','find_explicit_fixture_item')],
        'elapsedSeconds':.1}
    return row,inputs


class PrivateCredentialContractTests(unittest.TestCase):
    @proves('MYC-15.8')
    def test_scoped_protocol_requires_current_source_program_helpers_and_real_cleanup_shape(self):
        row,inputs=protocol()
        def accepted(value):return credential_probe_passed(value,number='2',target='macos-arm64',source_sha256='a'*64,program_sha256='b'*64,check_inputs=inputs)
        self.assertTrue(accepted(row))
        mutations=[lambda r:r.update(build=True),lambda r:r.update(build=3),lambda r:r.update(sourceInputsSha256='c'*64),
            lambda r:r.update(programManifestSha256='c'*64),lambda r:r['fixtureProvenance'].update(sha256='c'*64),
            lambda r:r['helperSha256'].update({HELPERS[0]:'c'*64}),lambda r:r.update(observedSignals=[2]),
            lambda r:r['nativeApiEvents'][2].update(status=-1),lambda r:r['profilePreferenceValues'].update(scope='global_owner'),
            lambda r:r['profilePreferenceValues']['after'].update(defaultStatus=0,defaultPath='/other'),
            lambda r:r.update(elapsedSeconds=float('nan')),lambda r:r.update(ownerMetadataUnchanged=True)]
        mutations.extend((lambda r,k=k:r.update({k:False})) for k in TRUE_FIELDS)
        mutations.extend((lambda r,k=k:r.update({k:True})) for k in FALSE_FIELDS)
        for mutate in mutations:
            value=copy.deepcopy(row);mutate(value)
            with self.subTest(mutate=mutate):self.assertFalse(accepted(value))
        self.assertFalse(credential_probe_passed(row,number='2',target='macos-arm64',source_sha256='a'*64,program_sha256='b'*64,check_inputs=[]))

    @proves('MYC-15.8')
    def test_both_publication_receivers_refuse_global_preference_claim_over_profile_view(self):
        try:from .test_working_publication import PublicationFixture
        except ImportError:from test_working_publication import PublicationFixture
        with tempfile.TemporaryDirectory() as temporary:
            fixture=PublicationFixture(temporary)
            self.assertIsNotNone(fixture.record['qualification'])
            row=fixture.checks['results'][-1];row['profilePreferenceValues']['scope']='global_owner'
            atomic_json(fixture.folder/'checks.json',fixture.checks)
            check_inputs=json.loads((fixture.folder/'check-inputs.json').read_bytes())
            self.assertIsNone(qualification_certificate(number=fixture.number,source=fixture.identity,check_inputs=check_inputs,
                program_sha256=fixture.record['filesSha256'],launcher_sha256=fixture.record['launcherBundleSha256'],
                target='macos-arm64',runtime=fixture.record['runtime'],results=fixture.checks['results'],publication=True))
            with self.assertRaises(BuildError):publication._verify(fixture.folder,fixture.record,fixture.frozen,fixture.identity)

    @proves('MYC-15.8')
    def test_public_fixture_is_offline_exact_licensed_source_and_rejects_tampering(self):
        frozen={p:(ROOT/p).read_bytes() for p in (FIXTURE_SOURCE,FIXTURE_LICENSE,FIXTURE_PROVENANCE)}
        raw=public_fixture(frozen);self.assertEqual(len(raw),45864);self.assertEqual(digest(raw),PROVENANCE['sha256'])
        for path in frozen:
            changed=dict(frozen);changed[path]=b'changed'
            with self.subTest(path=path),self.assertRaises(BuildError):public_fixture(changed)

    @proves('MYC-15.8')
    def test_missing_current_build_provenance_refuses_before_native_child_or_fixture_allocation(self):
        with patch.object(probe.sys,'platform','darwin'),patch.object(probe,'owned_process',side_effect=AssertionError('no child')) as child,\
             patch.object(probe.tempfile,'mkdtemp',side_effect=AssertionError('no fixture')) as allocate:
            result=probe.probe_private_keychain(Path('/not/a/staged/program'),'macos-arm64',source_root=ROOT,number='2')
        self.assertFalse(result['passed'] or result['executed'] or result['privateFixtureMaterialized'])
        self.assertFalse(result['globalOwnerPreferencesAssessed'] or result['nativeItemCreated'])
        child.assert_not_called();allocate.assert_not_called()

    @proves('MYC-15.8')
    def test_reader_group_cleanup_rejects_unlinked_nonpositive_or_parent_group_without_signals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for change in ({'pgid':0},{'pid':True},{'parentPid':8},{'pgid':os.getpgrp()}):
                live={'pid':90123,'pgid':90123,'parentPid':7,'readerSha256':'a'*64};live.update(change)
                (root/'reader-live.json').write_text(json.dumps(live))
                with patch.object(probe,'group_absent',side_effect=AssertionError('no group probe')) as absent,\
                     patch.object(probe.os,'killpg',side_effect=AssertionError('no signal')) as kill:
                    with self.assertRaises(BuildError):probe._reader_cleanup(root,client_pid=7,reader_sha='a'*64)
                absent.assert_not_called();kill.assert_not_called()

    @proves('MYC-15.8')
    def test_unknown_reader_attempt_remains_unknown_without_group_adoption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'reader-launch-attempt.json').write_text('{}')
            with patch.object(probe.os,'killpg',side_effect=AssertionError('no guessed group')) as kill:
                self.assertEqual(probe._reader_cleanup(root,client_pid=7,reader_sha='a'*64),(None,True))
            kill.assert_not_called()

    @proves('MYC-15.8')
    def test_invalid_client_admission_never_loads_native_library_or_writes_foreign_root(self):
        from mycel_build import _credential_probe_client as client
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'sentinel').write_text('unchanged')
            before={p.name:p.read_bytes() for p in root.iterdir()}
            with patch.object(client.sys,'argv',['client',str(root),str(root/'missing-context.json')]),\
                 patch.object(client.signal,'signal'),\
                 patch.object(client.ctypes,'CDLL',side_effect=AssertionError('no native API')) as library:
                self.assertEqual(client.main(),1)
            library.assert_not_called()
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
