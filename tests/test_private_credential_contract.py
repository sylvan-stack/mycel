# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Constructed credential protocol rows, never native Keychain evidence."""
import json
import os
import tempfile
from unittest.mock import patch

from mycel_build._core import BuildError, atomic_json, digest
from mycel_build import _keychain_probe as probe
from mycel_build._credential_contract import (PROVENANCE, TRUE_FIELDS, FALSE_FIELDS, HELPERS,
    FIXTURE_SOURCE, FIXTURE_LICENSE, FIXTURE_PROVENANCE, credential_probe_passed, public_fixture)
from mycel_build._qualification import qualification_certificate
from mycel_build import _publication as publication

import copy
import unittest
from pathlib import Path

from mycel_build._core import digest
from mycel_build._credential_contract import (
    FALSE_FIELDS,
    HELPERS,
    PROVENANCE,
    TRUE_FIELDS,
)

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
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
