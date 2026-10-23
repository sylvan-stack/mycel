"""Origin audit proofs over real isolated stores and public classifier stand-ins."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from mycel._audit import AuditStore, DETERMINISTIC
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._locks import read_snapshot
from mycel._settings import load_settings

REQ='11111111-2222-4333-8444-555555555555'
OTHER='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
UNUSED='99999999-2222-4333-8444-555555555555'


def specification(number, rows, decisions=''):
    return ('---\nrole: authored\nspec: FIX-'+str(number)+'\nstatus: accepted\n---\n# Fixture '+str(number)+
        '\n\n## Requirements\n\n| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n'+
        ''.join('| FIX-'+str(number)+'.'+str(index)+' <!-- '+identifier+' --> | '+text+' | New | store |\n'
                for index,(identifier,text) in enumerate(rows,1))+decisions)


class AuditStoreTests(unittest.TestCase):
    def setUp(self):
        from test_located_reconciliation import LocatedReconciliationStoreTests
        self.base=LocatedReconciliationStoreTests();self.base.store_fixture=self.store_fixture
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.code=self.base.code;self.artifact=self.base.base/'origins';self.artifact.mkdir()
        self.source=self.code/'value.py';self.source.write_text('def value():\n    return 1\n\ndef spare():\n    return 2\n')
        self.spec=self.artifact/'spec.md';self.spec.write_text(specification(1,[(REQ,'return one'),(UNUSED,'retain an unused contract')]))
        (self.artifact/'other.md').write_text(specification(2,[(OTHER,'keep a stable result')]))
        self.settings=self.base.configure(artifact=self.artifact)
        self.ref='fixture:@code/value.py#value';self.calls=[]
        self.ingest();self.old_files()

    def ingest(self,settings=None):
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        with patch('mycel._build_identity.current_build',return_value=1):
            result=ingest(Invocation('ingest',repositories=('fixture',),settings=settings or self.settings))
        self.assertEqual(result.status,0,result.value)

    def old_files(self):
        stamp=(datetime.now(timezone.utc)-timedelta(hours=1)).timestamp()
        for root in (self.code,self.artifact):
            for path in root.rglob('*'):
                if path.is_file() and '.git' not in path.parts:os.utime(path,(stamp,stamp))

    def justify(self,origin='fixture:@artifact/spec.md#FIX-1.1',chunk=None):
        from mycel._justify import JustifyStore
        with self.base.connect() as connection:
            return JustifyStore(connection).apply(self.settings,chunk or self.ref,origin,by='fixture-owner')

    def deterministic(self,**options):
        with self.base.connect() as connection:
            return AuditStore(connection).deterministic(self.settings,'fixture',**options)

    def state(self):
        from mycel._store import TABLES
        with self.base.connect() as connection:
            return {table.name:connection.execute('SELECT to_jsonb(t),xmin::text FROM public.'+table.name+
                ' t ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    @proves('MYC-17.16',kind='store')
    def test_seven_deterministic_rules_use_only_current_indexed_evidence(self):
        decisions=('\n## Decisions\n\n| Decision | Question | Outcome | Discussion |\n|---|---|---|---|\n'
            '| FIX-D1 <!-- 12345678-2222-4333-8444-555555555555 --> | Why? | Decided 19 October 2026 by owner: Keep it. | |\n'
            '| FIX-D2 <!-- 22345678-2222-4333-8444-555555555555 --> | Why? | Decided 19 October 2026 by owner: Keep it. | [cht:33333333-2222-4333-8444-555555555555:VGVzdA==] |\n'
            '| FIX-D2 <!-- 32345678-2222-4333-8444-555555555555 --> | Why again? | Decided 19 October 2026 by owner: Keep it. | [cht:33333333-2222-4333-8444-555555555555:VGVzdA==] |\n')
        (self.artifact/'decisions.md').write_text('# Decisions fixture\n'+decisions)
        (self.artifact/'GLOSSARY.md').write_text('# Known term\nAn indexed definition.\n')
        (self.artifact/'term.md').write_text('# Terms\n\n<!-- sources:\nfixture:@artifact/GLOSSARY.md#Absent term\n-->\n')
        self.ingest();self.justify();self.justify('fixture:@artifact/other.md#FIX-2.1')
        self.spec.write_text(self.spec.read_text().replace('return one','return exactly one'))
        self.ingest()
        # Deliberately changed disk text and a quiet-period violation cannot
        # affect deterministic queries over the retained Index Store.
        self.source.write_text('def another():\n    return 99\n')
        with patch('mycel._credentials.Credentials.require_jev_key',side_effect=AssertionError('no model key')), \
             patch('mycel._drift_store.DriftStore._physical',side_effect=AssertionError('no live file observation')):
            findings,new=self.deterministic()
        self.assertEqual(len(findings),7,findings)
        self.assertEqual({item['kind'] for item in findings},set(DETERMINISTIC))
        self.assertEqual(new,7)
        self.assertTrue(all(item['subject'] and item['facts'] and item['id'] for item in findings))
        self.assertTrue(all(item['links'] for item in findings if item['kind'] in {'multiple_chapters','stale_chain'}))
        again,new=self.deterministic();self.assertEqual(new,0)
        self.assertEqual(again,findings)

    @proves('MYC-17.18',kind='store')
    def test_person_settles_with_reason_history_and_exact_observation_never_reopens(self):
        findings,_=self.deterministic();target=findings[0]
        with self.base.connect() as connection:
            store=AuditStore(connection)
            with self.assertRaises(MycelError):store.settle(self.settings,'fixture',target['id'],reason=' ')
            settled,changed=store.settle(self.settings,'fixture',target['id'],reason='Accepted for this fixture.',by='fixture-owner')
            self.assertTrue(changed);self.assertEqual(settled['state'],'settled')
            self.assertFalse(store.settle(self.settings,'fixture',target['id'],reason='Accepted for this fixture.',by='fixture-owner')[1])
            with self.assertRaises(MycelError):store.settle(self.settings,'fixture',target['id'],reason='Changed my mind.',by='fixture-owner')
        pending,new=self.deterministic();self.assertEqual(new,0);self.assertNotIn(target['id'],[r['id'] for r in pending])
        history,_=self.deterministic(closed=True);self.assertIn(settled,history)
        preview,_=self.deterministic(dry_run=True);self.assertNotIn(target['id'],[r['id'] for r in preview])
        # A new exact requirement version is a new observable condition.
        self.spec.write_text(self.spec.read_text().replace('return one','return exactly one'));self.ingest()
        changed,new=self.deterministic();self.assertGreater(new,0)
        self.assertNotIn(target['id'],[r['id'] for r in changed])

    @proves('MYC-17.16','MYC-17.18',kind='store')
    def test_dry_run_is_readonly_and_paths_are_component_scoped(self):
        before=self.state();findings,new=self.deterministic(dry_run=True,paths=('value.py',))
        self.assertEqual(new,0);self.assertEqual(len(findings),2,findings)
        self.assertTrue(all(row['state']=='proposed' and row['path']=='value.py' for row in findings))
        self.assertEqual(before,self.state())
        empty,_=self.deterministic(paths=('value',));self.assertEqual(empty,[])
        with self.assertRaises(MycelError):self.deterministic(paths=('../escape',))
        self.assertEqual(before,self.state())

    @proves('MYC-17.16',kind='store')
    def test_requirement_marks_and_withdrawal_exempt_only_unresting_requirements(self):
        from mycel._origins import mark_needs_nothing
        with self.base.connect() as connection:
            mark_needs_nothing(connection,self.settings,'fixture:@artifact/spec.md#FIX-1.1',reason='No implementation is required.',by='fixture-owner')
        findings,_=self.deterministic()
        unused=[row for row in findings if row['kind']=='unresting_requirement']
        self.assertEqual(len(unused),2,unused)
        self.assertFalse(any(REQ in row['subject'] for row in unused))

    @proves('MYC-17.16',kind='store')
    def test_repeated_human_names_are_ambiguous_but_uuid_diagnostics_remain_auditable(self):
        from mycel._resolver import SourceResolver
        self.spec.write_text(self.spec.read_text().replace('FIX-1.2','FIX-1.1'))
        self.ingest()
        with self.base.connect() as connection:
            catalog=SourceResolver.from_store(connection,self.settings)
            self.assertEqual(catalog.resolve('fixture:@artifact/spec.md#FIX-1.1',purpose='endpoint').fault,'ambiguous_name')
            from mycel._source_refs import format_entity_uri
            self.assertEqual(catalog.resolve(format_entity_uri('req',REQ,'ignored'),purpose='endpoint').state,'resolved')
        findings,_=self.deterministic();duplicates=[r for r in findings if r['kind']=='duplicate_id']
        self.assertEqual(len(duplicates),1,duplicates)
        self.assertEqual(duplicates[0]['facts']['identity'],'FIX-1.1')
        self.assertEqual(len(duplicates[0]['facts']['occurrences']),2)
        self.spec.write_text(self.spec.read_text().replace(UNUSED,REQ));self.ingest()
        findings,_=self.deterministic();duplicates=[r for r in findings if r['kind']=='duplicate_id' and r['facts']['identityKind']=='uuid']
        self.assertEqual(len(duplicates),1,duplicates)
        self.assertEqual(duplicates[0]['facts']['identity'],REQ)
