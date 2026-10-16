"""Pure closed receiver for the current Build's public-dummy credential check.

Structural records do not authenticate historical execution or restore native
ownership. The trusted current release operation supplies the actual result.
"""
from __future__ import annotations
import json
import math
import re
from ._core import BuildError, digest

COMMIT = 'db15acbe6a7f257a859ad9a3bb86097bfe0679d9'
FIXTURE_SOURCE = 'packaging/native-fixtures/apple-security/kc-keychain-file-helpers.c'
FIXTURE_LICENSE = 'packaging/native-fixtures/apple-security/APPLE_LICENSE'
FIXTURE_PROVENANCE = 'packaging/native-fixtures/apple-security/provenance.json'
SOURCE_SHA = '96b6cc13fa641e49c49a46ec06fa15c4ddd01de7e33fcbb2981241446060f9f2'
LICENSE_SHA = '212846e0145aa50fb3a5aef254a370311a93acf6c1e792e47e0068d64c8c3885'
FIXTURE_SHA = '87a34479ff2f4f9fd8c6c982a9e461f637a7bd9b88e82b03f3e765a58bf77582'
HELPERS = ('src/mycel_build/_credential_fixture_reader.py', 'src/mycel_build/_credential_probe_client.py')
PROVENANCE = {'upstreamCommit':COMMIT,'sourceSha256':SOURCE_SHA,'licenseSha256':LICENSE_SHA,
              'array':'test_keychain','bytes':45864,'sha256':FIXTURE_SHA}
TRUE_FIELDS = ('privateFixtureMaterialized','privateNativeHandleValidated','installedCredentialsRead',
    'dummyValueMatchedPrivately','nativeBufferZeroed','nativeCleanupSucceeded','fixtureCleaned',
    'programAndSourcePreserved','clientNetworkDenied','clientKeychainFileReadDenialApplied',
    'clientProcessReaped','clientProcessGroupAbsent','privateReaderGroupAbsent')
FALSE_FIELDS = ('credentialOutputPersisted','nativeItemCreated','newDummySecretGenerated',
    'defaultLoginReaderExercised','globalOwnerPreferencesAssessed','daemonIsolationClaimed',
    'securePythonStringErasureClaimed','unknownLaunch','interrupted')


def public_fixture(frozen: dict[str, bytes]) -> bytes:
    """Parse the exact licensed public array offline, without compiling C."""
    try:
        if digest(frozen[FIXTURE_SOURCE]) != SOURCE_SHA or digest(frozen[FIXTURE_LICENSE]) != LICENSE_SHA:
            raise ValueError('upstream bytes')
        meta = json.loads(frozen[FIXTURE_PROVENANCE])
        if any(meta.get(k) != v for k,v in PROVENANCE.items()): raise ValueError('provenance')
        match = re.search(rb'unsigned char test_keychain\[\]\s*=\s*\{([^}]+)\}', frozen[FIXTURE_SOURCE], re.S)
        if match is None: raise ValueError('array')
        raw = bytes(int(x,16) for x in re.findall(rb'0x([0-9a-fA-F]{2})',match.group(1)))
        if len(raw) != 45864 or digest(raw) != FIXTURE_SHA: raise ValueError('fixture')
        return raw
    except (KeyError,TypeError,ValueError):
        raise BuildError('refused','The offline public credential fixture provenance is invalid.') from None


def credential_probe_passed(row: dict, *, number: str, target: str, source_sha256: str,
                            program_sha256: str, check_inputs: list[dict]) -> bool:
    """Require honest scoped evidence bound to this exact source/program/Build."""
    try:
        helpers = {p:next(x['sha256'] for x in check_inputs if x['path']==p) for p in HELPERS}
        allowed={'schemaVersion','mechanism','name','passed','executed','target','build','sourceInputsSha256',
            'programManifestSha256','fixtureProvenance','helperSha256','profilePreferenceValues','nativeApiEvents',
            'observedSignals','errors','reason','elapsedSeconds',*TRUE_FIELDS,*FALSE_FIELDS}
        if set(row)-allowed: return False
        if (row.get('schemaVersion') != 2 or type(row.get('schemaVersion')) is not int
            or row.get('mechanism') != 'public_apple_fixture_explicit_handle_key_command'
            or row.get('passed') is not True or row.get('executed') is not True
            or row.get('target') != target or type(row.get('build')) is not int
            or row['build'] != int(number,16) or row.get('sourceInputsSha256') != source_sha256
            or row.get('programManifestSha256') != program_sha256
            or row.get('fixtureProvenance') != PROVENANCE or row.get('helperSha256') != helpers
            or any(row.get(k) is not True for k in TRUE_FIELDS)
            or any(row.get(k) is not False for k in FALSE_FIELDS)
            or row.get('observedSignals') != [] or row.get('errors') != []):
            return False
        if (type(row.get('elapsedSeconds')) not in {int,float} or not math.isfinite(row['elapsedSeconds'])
            or row['elapsedSeconds'] < 0): return False
        pref=row['profilePreferenceValues']
        if set(pref) != {'scope','before','after','unchanged'} or pref['scope'] != 'probe_profile_view' or pref['unchanged'] is not True:
            return False
        if pref['before'] != pref['after']: return False
        for value in (pref['before'],pref['after']):
            if (set(value) != {'searchList','defaultStatus','defaultPath'}
                or not isinstance(value['searchList'],list)
                or any(not isinstance(p,str) or not p.startswith('/') or '\0' in p for p in value['searchList'])
                or type(value['defaultStatus']) is not int or value['defaultStatus'] not in {0,-25307}
                or (value['defaultStatus']==0 and (not isinstance(value['defaultPath'],str)
                    or not value['defaultPath'].startswith('/') or '\0' in value['defaultPath']))
                or (value['defaultStatus']==-25307 and value['defaultPath'] is not None)):
                return False
        events=row['nativeApiEvents']
        return (events == [{'stage':s,'status':0} for s in ('interaction_disabled','open_explicit_fixture',
                   'unlock_explicit_fixture','find_explicit_fixture_item')])
    except (AttributeError,KeyError,TypeError,ValueError,StopIteration):
        return False
