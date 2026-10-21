"""UUID compatibility and atomic stated Origin Links over disposable stores."""
from dataclasses import replace
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._source_refs import format_entity_uri

REQ='11111111-2222-4333-8444-555555555555'
OTHER='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
SPEC=f'''---
role: authored
spec: FIX-1
status: accepted
---
# Fixture

## Requirements

| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| FIX-1.1 <!-- {REQ} --> | keep the value stable | New | store |
| FIX-1.2 <!-- {OTHER} --> | describe the value | New | store |
'''


class UriSyntaxTests(unittest.TestCase):
    @proves('MYC-17.5')
    def test_mutation_preflight_accepts_uuid_spelling_and_rejects_malformed_inputs(self):
        from mycel._derive import _validate_ref_syntax
        from mycel._source_refs import read_document_declarations
        from mycel._markdown import split_markdown
        uri=format_entity_uri('req',REQ,'title')
        _validate_ref_syntax((uri,'fixture:@code/value.py#value'))
        declarations=read_document_declarations(split_markdown('# Answer\n\n<!-- sources:\n'+uri+'\n-->\n'),
                                               file='fixture:@artifact/answer.md')
        source=declarations.chunk_sources[0].sources[0]
        self.assertEqual((source.ref,source.fault),(uri,None))
        self.assertIsNone(source.address)
        for raw in ('[req:broken:title]','not a ref',None):
            with self.subTest(raw=raw),self.assertRaises(MycelError):
                _validate_ref_syntax((raw,))


class UriMutationStoreTests(unittest.TestCase):
    def setUp(self):
        try:
            from . import test_clone_locations as fixtures
        except ImportError:
            import test_clone_locations as fixtures
        from mycel._settings import load_settings
        self.fixture=fixtures.CloneStoreTests()
        self.fixture.store_fixture=self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base=self.fixture.base
        self.origins=self.base.base/'origins';self.origins.mkdir()
        self.spec=self.origins/'spec.md';self.spec.write_text(SPEC)
        self.base.config.write_text(self.base.config.read_text()+'\n[repos.origins]\nenabled=true\nartifact_root='+
                                    json.dumps(str(self.origins))+'\n')
        settings=load_settings(path=self.base.config,home=self.base.base)
        self.primary=replace(settings,_cwd=self.base.code)
        self.secondary=replace(settings,_cwd=self.fixture.clone)
        self.uri=format_entity_uri('req',REQ,'keep the value stable')
        self.other=format_entity_uri('req',OTHER,'describe the value','origins')
        self.ref=self.fixture.ref
        self.ingest(self.primary,'origins')
        self.ingest(self.primary)
        self.ingest(self.secondary)

    def ingest(self,settings,repository='fixture'):
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        with patch('mycel._build_identity.current_build',return_value=1):
            result=ingest(Invocation('ingest',repositories=(repository,),settings=settings))
        self.assertEqual(result.status,0,result.value)
        return result.value

    def invoke(self,*arguments,settings=None):
        from mycel._cli import run
        output,diagnostic=StringIO(),StringIO()
        with patch('mycel._cli.load_settings',return_value=settings or self.secondary), \
                patch('mycel._build_identity.current_build',return_value=1):
            status=run(arguments,stdout=output,stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(),'')
        return status,json.loads(output.getvalue())

    @proves('MYC-7.26',kind='store')
    def test_entity_uris_work_in_declarations_and_existing_mutations(self):
        from mycel._derive import DeriveStore
        from mycel._relate import RelateStore
        from mycel._verification import ConfirmationStore
        answer=self.fixture.artifact/'answer.md'
        answer.write_text('---\nsources: ['+json.dumps(self.uri)+']\n---\n# Answer\nThe value is governed.\n')
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            declared=connection.execute("SELECT source_place,state FROM public.mycel_dependencies "
                "WHERE repository='fixture' AND kind='declared'").fetchall()
            self.assertEqual(len(declared),1)
            self.assertIn('#FIX-1.1',declared[0][0])
            self.assertEqual(declared[0][1]['resolution']['state'],'resolved')
            derived=DeriveStore(connection).apply(self.secondary,self.ref,self.uri)
            self.assertEqual(derived['source']['repository'],'origins')
            verification=ConfirmationStore(connection).apply(self.secondary,self.ref,by='fixture-owner')
            self.assertTrue(verification['current'])
            related=RelateStore(connection).apply(self.secondary,self.other,self.ref)
            self.assertTrue(related['changed'])
            entity_verification=ConfirmationStore(connection).apply(self.secondary,self.other,by='fixture-owner')
            self.assertTrue(entity_verification['current'])
        # The UUID keeps the assertion attached when its row moves to another file.
        moved=self.origins/'renamed.md';self.spec.rename(moved)
        self.ingest(self.secondary,'origins')
        with self.base.connect() as connection:
            row=connection.execute("SELECT source_place,state FROM public.mycel_dependencies "
                "WHERE repository='fixture' AND kind='asserted'").fetchone()
            self.assertIn('renamed.md',row[0])
            self.assertEqual(row[1]['resolution']['state'],'resolved')
            self.assertTrue(ConfirmationStore(connection).apply(self.secondary,self.ref)['current'])
        for arguments in (('derive',self.ref,self.other),('confirm',self.ref,'--by','fixture-owner'),
                          ('relate','--remove',self.other,self.ref),('confirm',self.other)):
            status,reply=self.invoke(*arguments)
            self.assertEqual(status,0,reply)
        # Wrong tags never select a different entity by a matching display name.
        wrong=format_entity_uri('dec',REQ,'the same UUID')
        status,reply=self.invoke('derive',self.ref,wrong)
        self.assertEqual(status,1)
        self.assertEqual(reply['error']['code'],'invalid_input')
