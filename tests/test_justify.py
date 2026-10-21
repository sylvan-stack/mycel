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


class JustifyInputTests(unittest.TestCase):
    @proves('MYC-0.6')
    def test_bulk_format_and_cli_reject_ambiguous_input_before_store_access(self):
        import tempfile
        from pathlib import Path
        from mycel._justify import pairs_from_file
        from mycel._cli import parse
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pairs.jsonl'
            good={'chunk':'fixture:@code/value.py#value','origin':format_entity_uri('req',REQ,'title')}
            path.write_text('\n'+json.dumps(good)+'\n')
            self.assertEqual(pairs_from_file(path),((good['chunk'],good['origin']),))
            for content in ('',json.dumps(good)+'\n'+json.dumps(good),
                            '{"chunk":"x","chunk":"y","origin":"z"}',
                            json.dumps({**good,'extra':True}),json.dumps({**good,'origin':False})):
                path.write_text(content)
                with self.subTest(content=content),self.assertRaises(MycelError):
                    pairs_from_file(path)
        for arguments in (('justify',),('justify','x'),('justify','x','y','--file','z'),
                          ('justify','--file',''),('justify','x','y','--by','')):
            with self.subTest(arguments=arguments),self.assertRaises(MycelError):
                parse(arguments)
        self.assertEqual(parse(['justify','--file','pairs.jsonl','--by','owner']).arguments,
                         ('--by','owner','--file','pairs.jsonl'))


class JustifyStoreTests(unittest.TestCase):
    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest
    invoke=UriMutationStoreTests.invoke

    def state(self,connection):
        tables=('mycel_dependencies','mycel_edges','mycel_relations','mycel_verifications',
                'mycel_evidence_owners','mycel_evidence_references','mycel_snapshots','mycel_manifests',
                'mycel_stale_reasons','mycel_activity')
        # Locks and invocation outcome diagnostics are administrative; feature
        # evidence, policy, verification and applied activity must all roll back.
        return {table:connection.execute('SELECT to_jsonb(t) FROM public.'+table+' t ORDER BY to_jsonb(t)::text').fetchall()
                for table in tables}

    @proves('MYC-17.8','MYC-17.9','MYC-6.23',kind='store')
    def test_atomic_stated_link_and_verification_persist_only_in_index_store(self):
        from mycel._justify import JustifyStore,checked_link
        before={path:path.read_bytes() for root in (self.fixture.clone,self.origins,self.fixture.artifact)
                for path in root.rglob('*') if path.is_file() and '.git' not in path.parts}
        with self.base.connect() as connection:
            reply=JustifyStore(connection).apply(self.secondary,self.ref,self.uri,by='owner',build=1)
            self.assertEqual(reply['chunk'],self.ref)
            self.assertEqual(reply['origin'],format_entity_uri('req',REQ,'keep the value stable','origins'))
            self.assertEqual(reply['link']['method'],'stated')
            self.assertEqual((reply['link']['confidenceScore'],reply['link']['confidence']),(1.0,'asserted'))
            self.assertEqual(reply['link']['who'],'owner')
            self.assertTrue(reply['verification']['current'])
            self.assertEqual(checked_link(reply['link']),reply['link'])
            row=connection.execute("SELECT state,baseline_owner FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
            self.assertEqual(row[0]['originLink'],reply['link'])
            self.assertEqual(row[0]['originId'],REQ)
            self.assertIsNotNone(row[1])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],1)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='justify'").fetchone()[0],1)
        self.assertEqual(before,{path:path.read_bytes() for path in before})
        status,reply=self.invoke('justify',self.other,self.ref,'--by','owner')
        self.assertEqual(status,0,reply)
        self.assertEqual(reply['link']['origin'],self.ref)
        # Re-ingesting preserves the statement and its independent evidence.
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            links=connection.execute("SELECT state->'originLink' FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchall()
            self.assertEqual(len(links),2)

    @proves('MYC-17.8','MYC-17.10',kind='store')
    def test_all_pairs_resolve_before_mutation_and_changed_or_generated_inputs_refuse(self):
        from mycel._justify import JustifyStore
        from mycel._derive import DeriveStore
        with self.base.connect() as connection:
            before=self.state(connection)
            with patch.object(DeriveStore,'apply_in_transaction',side_effect=AssertionError('No writes before all pairs resolve')):
                with self.assertRaises(MycelError):
                    JustifyStore(connection).apply_pairs(self.secondary,((self.ref,self.uri),(self.other,'fixture:@code/absent.py#x')),build=1)
            self.assertEqual(self.state(connection),before)
            (self.fixture.clone/'value.py').write_text('def value():\n    return 2\n')
            with self.assertRaises(MycelError):
                JustifyStore(connection).apply(self.secondary,self.ref,self.uri,build=1)
            self.assertEqual(self.state(connection),before)
            (self.fixture.clone/'value.py').write_text('def value():\n    return 1\n')
            for chunk,origin in ((self.ref,format_entity_uri('dec',REQ,'wrong tag')),
                                 (self.ref,'fixture:@index/overview'),('fixture:@code/value.py',self.uri)):
                with self.subTest(chunk=chunk,origin=origin),self.assertRaises(MycelError):
                    JustifyStore(connection).apply(self.secondary,chunk,origin)
                self.assertEqual(self.state(connection),before)
        generated=self.fixture.artifact/'generated.md'
        generated.write_text('---\ngenerated: true\n---\n# Generated\nComputed answer.\n')
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            from mycel._resolver import SourceResolver
            selection=SourceResolver.from_store(connection,self.secondary).resolve('fixture:@artifact/generated.md',purpose='read').selection
            before=self.state(connection)
            for chunk,origin in ((selection.members[0].place.address,self.uri),(self.ref,selection.members[0].place.address)):
                with self.subTest(chunk=chunk,origin=origin),self.assertRaises(MycelError):
                    JustifyStore(connection).apply(self.secondary,chunk,origin,build=1)
                self.assertEqual(self.state(connection),before)

    @proves('MYC-17.8','MYC-17.9','MYC-17.10',kind='store')
    def test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically(self):
        from mycel._justify import JustifyStore
        from mycel._verification import ConfirmationStore
        original=ConfirmationStore.apply_in_transaction
        count=0
        def edit_after_second(store,*args,**kwargs):
            nonlocal count
            reply=original(store,*args,**kwargs)
            count+=1
            if count==2:
                (self.fixture.clone/'value.py').write_text('def value():\n    return 9\n')
            return reply
        pairs=((self.ref,self.uri),(self.other,'fixture:@code/value.py'))
        with self.base.connect() as connection:
            before=self.state(connection)
            with patch.object(ConfirmationStore,'apply_in_transaction',edit_after_second),self.assertRaises(MycelError):
                JustifyStore(connection).apply_pairs(self.secondary,pairs,by='owner',build=1)
            self.assertEqual(count,2)
            self.assertEqual(self.state(connection),before)
        (self.fixture.clone/'value.py').write_text('def value():\n    return 1\n')
        path=self.base.base/'pairs.jsonl'
        path.write_text('\n'.join(json.dumps(dict(zip(('chunk','origin'),pair))) for pair in pairs)+'\n')
        status,reply=self.invoke('justify','--file',str(path),'--by','owner')
        self.assertEqual(status,0,reply)
        self.assertEqual(len(reply['justifications']),2)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchone()[0],2)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],2)


class ClonePolicyStoreTests(unittest.TestCase):
    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest
    invoke=UriMutationStoreTests.invoke

    @proves('MYC-17.10','MYC-6.22','MYC-1.38',kind='store')
    def test_equal_clone_versions_keep_independent_policies_staleness_and_verification_readback(self):
        from mycel._justify import JustifyStore
        from mycel._verification import ConfirmationStore
        from mycel._verification_reader import VerificationReader
        from mycel._provenance_reports import ProvenanceReports
        with self.base.connect() as connection:
            primary=JustifyStore(connection).apply(self.primary,self.ref,self.uri,by='primary')
            secondary=JustifyStore(connection).apply(self.secondary,self.ref,self.other,by='secondary')
            self.assertEqual(primary['chunkVersion'],secondary['chunkVersion'])
            for settings,actor in ((self.primary,'primary'),(self.secondary,'secondary')):
                from mycel._locks import snapshot_transaction
                from mycel._store import checked_store
                with checked_store(connection),snapshot_transaction(connection):
                    report=VerificationReader(connection,settings).list_in_transaction('fixture',history=True)
                current=[record for record in report['verifications'] if record['current']]
                self.assertEqual([record['by'] for record in current],[actor])
        self.spec.write_text(SPEC.replace('keep the value stable','keep the value very stable'))
        self.ingest(self.primary,'origins')
        with self.base.connect() as connection:
            primary_reasons=connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall()
            self.assertTrue(primary_reasons)
        # A refresh and confirmation of the secondary policy cannot clear
        # primary marks even though both dependant versions are identical.
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall(),primary_reasons)
            ConfirmationStore(connection).apply(self.secondary,self.ref,by='secondary-again')
            self.assertEqual(connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall(),primary_reasons)
            self.assertEqual(ProvenanceReports(connection,self.secondary).stale('fixture')['count'],0)
            self.assertEqual(ProvenanceReports(connection,self.primary).stale('fixture')['count'],1)
        for settings,uri in ((self.primary,REQ),(self.secondary,OTHER)):
            status,reply=self.invoke('refs','--repo','fixture',settings=settings)
            self.assertEqual(status,0,reply)
            refs=reply['repositories'][0]['result']['refs']
            self.assertEqual(len(refs),1,refs)
            self.assertIn(uri,refs[0]['originLink']['origin'])


class JustifySelectionStoreTests(unittest.TestCase):
    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest

    @proves('MYC-17.8','MYC-17.9',kind='store')
    def test_complete_class_family_and_existing_review_are_retained(self):
        from psycopg.types.json import Jsonb
        from mycel._justify import JustifyStore
        from mycel._resolver import SourceResolver
        source=self.fixture.clone/'value.py'
        source.write_text(source.read_text()+'\nclass Policy:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
        self.ingest(self.secondary)
        origin='fixture:@code/value.py#Policy'
        with self.base.connect() as connection:
            selected=SourceResolver.from_store(connection,self.secondary).resolve(origin,purpose='source').selection
            self.assertEqual(selected.kind,'family')
            store=JustifyStore(connection)
            reply=store.apply(self.secondary,self.ref,origin,by='owner')
            row=connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
            edges=connection.execute('SELECT source_version FROM public.mycel_edges WHERE dependency=%s',(row[0],)).fetchall()
            self.assertEqual({value[0] for value in edges},{member.chunk.version for member in selected.members})
            review={'who':'reviewer','when':reply['link']['when'],'outcome':'Reviewed the complete class selection.'}
            state=row[1];state['originLink']['review']=review
            connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',(Jsonb(state),row[0]))
            repeated=store.apply(self.secondary,self.ref,origin,by='owner-again')
            self.assertEqual(repeated['link']['review'],review)
            self.assertEqual(repeated['link']['who'],'owner-again')
            self.assertEqual(len(repeated['verification']['sources']),len(selected.members))


class CloneAbsenceStoreTests(unittest.TestCase):
    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest

    @proves('MYC-6.22','MYC-1.38',kind='store')
    def test_absence_guard_compares_only_the_selected_clones_retained_witnesses(self):
        source=self.base.code/'primary-only.md'
        source.write_text('# Source\nA source absent from the other clone.\n')
        self.base.commit()
        for root in (self.base.code,self.fixture.clone,self.fixture.artifact):
            (root/'ambiguous.md').write_text('# Source\nOne of two root candidates.\n')
        answer=self.fixture.artifact/'answer.md'
        answer.write_text('---\nsources: ["fixture:@code/primary-only.md#Source", "fixture:ambiguous.md#Source"]\n---\n# Answer\nThe source governs this answer.\n')
        self.ingest(self.primary)
        self.ingest(self.secondary)
        with self.base.connect() as connection:
            rows=connection.execute("SELECT state FROM public.mycel_dependencies WHERE repository='fixture' AND kind='declared'").fetchall()
            self.assertEqual(len(rows),4)
            ambiguous=[row[0] for row in rows if bytes.fromhex(row[0]['rawRef']).decode()=='fixture:ambiguous.md#Source']
            self.assertEqual(len(ambiguous),2)
            self.assertTrue(all(row['resolution']['fault']=='ambiguous_path' for row in ambiguous))
            rows=[row for row in rows if bytes.fromhex(row[0]['rawRef']).decode()!='fixture:ambiguous.md#Source']
            primary=[row[0] for row in rows if row[0]['declarationLocation']['location']=='disk']
            secondary=[row[0] for row in rows if row[0]['declarationLocation']['location']!='disk']
            self.assertEqual(primary[0]['resolution']['state'],'resolved')
            self.assertEqual(secondary[0]['resolution']['state'],'unresolved')


class CloneEntityMoveStoreTests(unittest.TestCase):
    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest
    invoke=UriMutationStoreTests.invoke

    @proves('MYC-1.38','MYC-17.10',kind='store')
    def test_refs_keep_each_entitys_actual_file_when_its_row_moves_in_only_one_clone(self):
        from mycel._justify import JustifyStore
        identifier='22222222-3333-4444-8555-666666666666'
        other='bbbbbbbb-cccc-4ddd-8eee-ffffffffffff'
        text=SPEC.replace(REQ,identifier).replace(OTHER,other)
        for root in (self.base.code,self.fixture.clone):
            (root/'spec.md').write_text(text)
        self.ingest(self.primary);self.ingest(self.secondary)
        entity=format_entity_uri('req',identifier,'keep the value stable','fixture')
        with self.base.connect() as connection:
            JustifyStore(connection).apply(self.primary,entity,self.uri)
            JustifyStore(connection).apply(self.secondary,entity,self.other)
        lines=text.splitlines(keepends=True)
        (self.fixture.clone/'spec.md').write_text(''.join(line for line in lines if identifier not in line))
        (self.fixture.clone/'moved.md').write_text(''.join(line for line in lines if other not in line))
        self.ingest(self.secondary)
        for settings,path in ((self.primary,'spec.md'),(self.secondary,'moved.md')):
            status,reply=self.invoke('refs','--repo','fixture',settings=settings)
            self.assertEqual(status,0,reply)
            refs=reply['repositories'][0]['result']['refs']
            self.assertEqual(len(refs),1,refs)
            self.assertTrue(refs[0]['ownerLocationAvailable'],refs)
            self.assertEqual(refs[0]['chunk']['path'],path)
