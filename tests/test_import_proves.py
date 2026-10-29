# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Legacy proof migration freezes declarations and commits guarded real-store pairs."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mycel_legacy_import', ROOT / 'scripts/import_proves.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
REQ = '11111111-2222-4333-8444-555555555555'
OTHER = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
WHEN = '2026-10-01T12:00:00+00:00'
SPEC = f'''---
role: authored
status: accepted
---
# Fixture
## Requirements
| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| MYC-1.1 <!-- {REQ} --> | keep the value | New | store |
| MYC-1.2 <!-- {OTHER} --> | describe the value | New | store |
'''
SOURCE = '''raise AssertionError('The planner must not execute test modules')
from mycel._coverage import proves as evidence
class Proof:
    @evidence('MYC-1.1', 'MYC-1.2', kind='store')
    def test_value(self):
        pass
class Inherited(Proof):
    pass
'''


class ImportPlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mycel_import_plan_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'source'
        (self.root / 'tests').mkdir(parents=True)
        self.specs = self.base / 'artifacts/specs'
        self.specs.mkdir(parents=True)
        (self.specs / '01-fixture.md').write_text(SPEC)
        self.test = self.root / 'tests/test_proof.py'
        self.test.write_text(SOURCE)
        subprocess.run(['/usr/bin/git', 'init', '--initial-branch=main', str(self.root)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def plan(self):
        return migration.make_plan(self.root, self.specs, repository='fixture', by='fixture-owner', when=WHEN)


class ProvenImportStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        try:
            from .test_clone_locations import CloneStoreTests
        except ImportError:
            from test_clone_locations import CloneStoreTests
        self.fixture = CloneStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.specs = self.fixture.artifact / 'specs'
        self.specs.mkdir()
        (self.specs / '01-fixture.md').write_text(SPEC)
        self.tests = self.base.code / 'tests'
        self.tests.mkdir()
        self.source = self.tests / 'test_proof.py'
        self.source.write_text(SOURCE.replace("raise AssertionError('The planner must not execute test modules')\n", ''))
        self.settings = self.fixture.primary
        self.fixture.ingest(self.settings)
        self.plan = migration.make_plan(self.base.code, self.specs,
                                       repository='fixture', by='fixture-owner', when=WHEN)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
