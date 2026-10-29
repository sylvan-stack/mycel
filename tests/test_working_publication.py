# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
