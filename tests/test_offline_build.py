# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Installed automatic-check provenance and retention boundary fixtures."""

import unittest

from mycel_build._qualification import automatic_contract, required_packaged_cases


def frozen_contract_fixture():
    return {'tests/test_fixture.py': b'class AutomaticTests:\n def test_one(self): pass\n'}


def contract_fixture():
    return automatic_contract(frozen_contract_fixture())


def relocation_results(build):
    # Closed protocol fixtures only; these are not observed native outcomes.
    labels = ('first installation', 'second relocated installation')
    interpreter = {'python': '3.14.7', 'machine': 'arm64', 'isolated': True,
                   'dontWriteBytecode': True}
    common = {'passed': True, 'executed': True, 'target': 'macos-arm64',
              'sourceReadDenied': True, 'networkAndWritesDenied': True}
    native = {**common, 'relocations': [{**interpreter, 'build': build} for _ in labels]}
    launcher = {**common, 'relocations': [{'label': label, **interpreter,
                                         'standaloneSelector': True} for label in labels]}
    packaged = {**common, 'retainedInputsUnchanged': True, 'developerReadDenied': True,
        'ownerStateDenied': True, 'relocations': [{'label': label, 'passed': True, 'executed': True,
            'privateWorkingRecordFixtureOnly': True, 'ownerPublished': False,
            'cases': [{'name': name, 'passed': True, 'executed': True}
                      for name in required_packaged_cases(format(build, 'x'))]} for label in labels]}
    return native, launcher, packaged


def report(*, passed=True, errors=0):
    result = {"passed": passed, "executed": True, "python": "3.14.7", "machine": "arm64",
            "isolated": True, "dontWriteBytecode": True, "installedProductImports": True, "build": 10,
            "checks": [{"name": "test_fixture.AutomaticTests.test_one", "kind": "unit",
                        "status": "passed" if passed else "failed",
                        "passed": passed, "detail": "private-password-provider-body"}],
            "gateErrorCount": errors, "gateErrors": ["private-password-provider-body"] * errors}
    result.update(inventorySha256=contract_fixture()['inventorySha256'])
    return result


class InstalledAutomaticTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
