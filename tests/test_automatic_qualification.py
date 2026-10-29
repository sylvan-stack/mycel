# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Independent frozen inventory, check kinds and real process boundary regressions.

Protocol fixture outcomes test receiver validation, not a native Build pass.
The process fixtures execute real OS processes without credentials or a store.
"""
import copy
import unittest
from pathlib import Path

try:
    pass
except ImportError:
    pass


ROOT = Path(__file__).resolve().parents[1]


def contract_inputs():
    return {'tests/test_fixture.py': b'''raise AssertionError("receiver must never import frozen tests")
class Proofs:
 def test_one(self): raise AssertionError("never execute while discovering")
 def test_two(self): pass
class StoreProofs:
 check_kind = "store"
 def test_store(self): pass
class EvalProofs:
 check_kind = "eval"
 def test_eval(self): raise AssertionError("paid or eval dispatch")
class LiveProofs:
 check_kind = "live"
 def test_live(self): raise AssertionError("paid or live dispatch")
'''}


def closed_reply(contract, *, failed=()):
    checks = [{**copy.deepcopy(row), 'status': 'failed' if row['name'] in failed else 'passed',
        'passed': row['name'] not in failed, 'detail': 'private-provider-body'} for row in contract['declarations']]
    return {'passed': not failed, 'executed': True, 'python': '3.14.7', 'machine': 'arm64',
        'isolated': True, 'dontWriteBytecode': True, 'installedProductImports': True, 'build': 10,
        'checks': checks, 'inventorySha256': contract['inventorySha256'],
        'gateErrorCount': int(bool(failed)), 'gateErrors': ['private-provider-body'] if failed else []}


class AutomaticQualificationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


        # contract_inputs begins by raising: deriving this inventory must never
        # import or execute the frozen class or any inherited body.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
