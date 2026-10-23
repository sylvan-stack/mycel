"""Legacy proof migration freezes declarations and commits guarded real-store pairs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._source_refs import format_entity_uri

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

    @proves('MYC-13.3', 'MYC-17.5')
    def test_literal_planning_never_imports_and_preserves_defining_symbol_and_kinds(self):
        plan = self.plan()
        self.assertEqual(len(plan['declarations']), 1)
        self.assertEqual(plan['declarations'][0]['kind'], 'store')
        self.assertEqual(len(plan['pairs']), 2)
        self.assertEqual(plan['pairs'][0]['chunk'], 'fixture:@code/tests/test_proof.py#Proof.test_value')
        self.assertEqual(plan['pairs'][0]['origin'], format_entity_uri('req', REQ, 'keep the value', 'fixture'))
        migration.validate_plan(plan)

    @proves('MYC-13.3', 'MYC-17.3')
    def test_unknown_dynamic_duplicate_and_unnormalized_inputs_refuse_before_store_work(self):
        for raw in (SOURCE.replace("'MYC-1.1'", "'MYC-1.3'"),
                    SOURCE.replace("'MYC-1.1'", 'choose_requirement()'),
                    SOURCE.replace("'MYC-1.2'", "'MYC-1.1'"),
                    SOURCE.replace("kind='store'", "kind='live'")):
            with self.subTest(raw=raw):
                self.test.write_text(raw)
                with self.assertRaises(ValueError):
                    self.plan()
        self.test.write_text(SOURCE)
        (self.specs / '01-fixture.md').write_text(SPEC.replace(' <!-- ' + REQ + ' -->', ''))
        with self.assertRaisesRegex(ValueError, 'Normalize'):
            self.plan()

    @proves('MYC-13.3')
    def test_complete_input_and_plan_changes_refuse_and_private_outputs_cannot_enter_corpora(self):
        plan = self.plan()
        (self.root / 'new.py').write_text('NEW = 1\n')
        with self.assertRaises(MycelError):
            migration.validate_plan(plan)
        (self.root / 'new.py').unlink()
        plan['pairs'][0]['chunk'] = 'fixture:@code/unrelated.py#value'
        with self.assertRaises(MycelError):
            migration.validate_plan(plan)
        for path in (self.root / 'result.json', self.specs.parent / 'result.json'):
            with self.assertRaises(ValueError):
                migration.write_private(path, {}, self.plan())

    @proves('MYC-13.3')
    def test_owner_target_is_refused_before_opening_a_connection(self):
        from mycel._settings import load_settings
        config = self.base / 'config.toml'
        config.write_text('[store]\naddress="postgresql://fixture@localhost:55432/mycel"\n')
        settings = load_settings(path=config)
        with self.assertRaisesRegex(ValueError, 'mycel_check_'):
            migration.apply_disposable(None, settings, self.plan())

    @proves('MYC-13.3')
    def test_owner_import_requires_the_named_database_and_the_indexed_clone(self):
        from mycel._settings import load_settings
        other = self.base / 'other'
        other.mkdir()

        def settings(database, code_root):
            config = self.base / f'{database}-{code_root.name}.toml'
            config.write_text(f'[store]\naddress="postgresql://fixture@localhost:55432/{database}"\n'
                              f'[repos.fixture]\nenabled=true\ncode_root="{code_root}"\n'
                              f'artifact_root="{self.specs.parent}"\n')
            return load_settings(path=config)
        for values, owner, message in ((settings('mycel', self.root), 'other', '--owner-store'),
                                       (settings('mycel_check_x1', self.root), 'mycel_check_x1', 'apply-disposable'),
                                       (settings('mycel', other), 'mycel', 'indexed code root')):
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                migration.apply_owner(None, values, self.plan(), owner_database=owner)


class ProvenImportStoreTests(unittest.TestCase):
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

    @proves('MYC-17.8', 'MYC-17.9', kind='store')
    def test_imports_every_uuid_pair_as_proven_with_one_complete_check_verification(self):
        with self.base.connect() as connection:
            replies = migration.apply_disposable(connection, self.settings, self.plan)
            self.assertEqual(len(replies), 2)
            self.assertEqual(replies[0]['verification'], replies[1]['verification'])
            self.assertEqual(replies[0]['verification']['how'], 'check')
            self.assertEqual(len(replies[0]['verification']['sources']), 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (1,))
            for reply in replies:
                self.assertEqual(reply['link']['method'], 'proven')
                self.assertEqual(reply['link']['confidence'], 'proven')
                self.assertEqual(reply['link']['confidenceScore'], 0.8)
                self.assertEqual(reply['link']['who'], 'fixture-owner')
            links = connection.execute("SELECT state FROM public.mycel_dependencies WHERE kind='asserted'").fetchall()
            self.assertEqual({row[0]['originId'] for row in links}, {REQ, OTHER})

    @proves('MYC-17.10', kind='store')
    def test_late_input_edit_rolls_back_all_links_verifications_and_evidence(self):
        original = migration.validate_plan
        calls = []
        def changed(plan):
            calls.append(True)
            if len(calls) == 3:
                self.source.write_text(self.source.read_text() + '\n# late edit\n')
            return original(plan)
        with self.base.connect() as connection:
            before = connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()
            with patch.object(migration, 'validate_plan', side_effect=changed), self.assertRaises(MycelError):
                migration.apply_disposable(connection, self.settings, self.plan)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='asserted'").fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), before)

    @proves('MYC-17.8', 'MYC-17.10', kind='store')
    def test_import_refuses_to_replace_a_newer_human_statement(self):
        from mycel._justify import JustifyStore
        pairs = [(row['chunk'], row['origin']) for row in self.plan['pairs']]
        with self.base.connect() as connection:
            stated = JustifyStore(connection).apply(self.settings, *pairs[1], by='maintainer')
            before = connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()
            with self.assertRaisesRegex(MycelError, 'replace an existing'):
                migration.apply_disposable(connection, self.settings, self.plan)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), before)
            link, = connection.execute("SELECT state->'originLink' FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
            self.assertEqual(link, stated['link'])

    @proves('MYC-17.10', kind='store')
    def test_replay_preserves_a_reviewed_score_and_its_verification_history(self):
        from psycopg.types.json import Jsonb
        with self.base.connect() as connection:
            migration.apply_disposable(connection, self.settings, self.plan)
            identifier, state = connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE kind='asserted' ORDER BY id LIMIT 1").fetchone()
            state['originLink'].update(confidenceScore=0.4, confidence='candidate',
                review={'who': 'reviewer', 'when': WHEN, 'outcome': 'nonconforming'})
            connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s', (Jsonb(state), identifier))
            before = connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()
            with self.assertRaisesRegex(MycelError, 'replace an existing'):
                migration.apply_disposable(connection, self.settings, self.plan)
            self.assertEqual(connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s', (identifier,)).fetchone()[0], state)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), before)
