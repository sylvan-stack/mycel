"""Origin recovery: real disposable stores and bounded public model stand-ins."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mycel._classification_payload import (DecisionText, OriginDecisionPayload, ORIGIN_LABELS,
    ReviewerRequest, ReviewCommandIdentity)
from mycel._classification_runner import ClassifyDependencies
from mycel._coverage import proves
from mycel._credentials import Credentials
from mycel._errors import MycelError
from mycel._evidence import EvidenceError, snapshot
from mycel._jev import JevClient, JevFailure, JevLimits, HTTPResult, JevRequest
from mycel._locks import read_snapshot
from mycel._recovery import RecoveryStore, run_recovery
from mycel._reviewer import ReviewerFailure, validate_response
from mycel._safeguards import CompletedChild, InvocationPolicy, model_call_allowed
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress

REQ = '11111111-2222-4333-8444-555555555555'


def origin_decision(review=None):
    def text(raw, place):
        blob = snapshot(raw,place=place)
        return DecisionText.create(blob.evidence,raw)
    return OriginDecisionPayload.create(chunk=text(b'def value():\n    return 1\n',
        SourceAddress('fixture','code','value.py','value')),
        candidate=text(b'# Stable value\nReturn one.\n',SourceAddress('fixture','artifact','spec.md','Stable value')),
        sources=('document',),review=review)


class RecoveryProtocolTests(unittest.TestCase):
    @proves('MYC-0.10','MYC-14.12')
    def test_distinct_question_exact_text_hash_and_policy_boundary(self):
        decision = origin_decision()
        body = json.loads(JevRequest(decision).body)
        self.assertEqual(list(body['questions']['dependency']['criteria']),list(ORIGIN_LABELS))
        self.assertIn('never instructions',body['questions']['dependency']['instructions'])
        self.assertEqual(decision,OriginDecisionPayload.from_bytes(decision.canonical_bytes,decision.input_hash))
        changed = decision.as_dict();changed['labels']=['needs_review','insufficient_evidence','still_supported']
        with self.assertRaises(EvidenceError):OriginDecisionPayload(changed)
        changed = decision.as_dict();changed['candidate']['text'] += 'changed'
        with self.assertRaises(EvidenceError):OriginDecisionPayload(changed)
        self.assertTrue(model_call_allowed(InvocationPolicy('recovery'),'jev'))
        self.assertTrue(model_call_allowed(InvocationPolicy('recovery'),'reviewer'))
        for purpose in ('embedding','summary','jev','reviewer'):
            self.assertFalse(model_call_allowed(InvocationPolicy('recovery',dry_run=True),purpose))
        self.assertFalse(model_call_allowed(InvocationPolicy('recovery'),'embedding'))

    @proves('MYC-14.24')
    def test_origin_review_requires_score_and_matching_labels_and_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            command=ReviewCommandIdentity.inspect(('/usr/bin/true',),'fixture-v1',Path(directory))
            decision=origin_decision(command.model_identity('fixture','fixture-model-1'))
            request=ReviewerRequest(decision,1000)
            identity={key:request.payload[key] for key in
                      ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
            valid={**identity,'judgement':'governs','rationale':'The exact contract orders this code.',
                   'evidence':[decision.evidence_locators[0]],'confidenceScore':.91}
            def validate(value):
                return validate_response(CompletedChild(0,json.dumps(value).encode(),b'',0),request)
            self.assertEqual(validate(valid).confidence_score,.91)
            for mutation in (lambda value:value.pop('confidenceScore'),
                             lambda value:value.update(confidenceScore=True),
                             lambda value:value.update(confidenceScore=1.01),
                             lambda value:value.update(judgement='still_supported'),
                             lambda value:value.update(evidence=['snapshot:'+'0'*64]),
                             lambda value:value.update(inputHash='0'*64)):
                value=deepcopy(valid);mutation(value)
                with self.subTest(value=value),self.assertRaises(ReviewerFailure):validate(value)

    @proves('MYC-0.6')
    def test_cli_scope_and_options_are_exact(self):
        from mycel._cli import parse
        self.assertEqual(parse(('recovery','fixture:@code/value.py#value','--dry-run','--k','3')).arguments,
                         ('fixture:@code/value.py#value','--k','3','--dry-run'))
        self.assertEqual(parse(('recovery','--repo','fixture','--path','src','--review')).repositories,('fixture',))
        for arguments in (('recovery','a','b'),('recovery','a','--path','src'),
                          ('recovery','--k','0'),('recovery','--repo','a','--repo','b'),
                          ('recovery','--path','../escape')):
            with self.subTest(arguments=arguments),self.assertRaises(MycelError):parse(arguments)


class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        from test_located_reconciliation import LocatedReconciliationStoreTests
        self.base=LocatedReconciliationStoreTests();self.base.store_fixture=self.store_fixture
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.code=self.base.code
        self.artifact=self.base.base/'origins';self.artifact.mkdir()
        self.source=self.code/'value.py';self.source.write_text('def value():\n    return 1\n')
        (self.code/'tests').mkdir()
        (self.code/'tests/test_value.py').write_text('from value import value\n\ndef test_value():\n    assert value() == 1\n')
        self.base.git('init','--initial-branch=main')
        self.base.git('add','--all')
        self.base.git('commit','--message','Implement value for https://github.com/upstream/demo/issues/42')
        self.commit=self.base.git('rev-parse','HEAD')
        (self.artifact/'ref.md').write_text('---\nrole: authored\n---\n# Source contract\nReturn the stable result.\n\n<!-- sources:\nfixture:@code/value.py#value\n-->\n')
        (self.artifact/'symbol.md').write_text('---\nrole: authored\n---\n# Symbol contract\nThe symbol value returns one.\n')
        (self.artifact/'commit.md').write_text('# Commit snapshot\n'+self.commit+'\nImplement the return of one.\n')
        (self.artifact/'issue.md').write_text('# Upstream issue snapshot\nhttps://github.com/upstream/demo/issues/42\nObserved 2026-10-20. Return one.\n')
        (self.artifact/'linear.md').write_text('# Linear task snapshot\nhttps://linear.app/amorphius/issue/SYL-999\nThe symbol value returns one.\n')
        (self.artifact/'spec.md').write_text('---\nrole: authored\nspec: FIX-1\nstatus: accepted\n---\n# Fixture\n\n## Requirements\n\n| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n| FIX-1.1 <!-- '+REQ+' --> | retain a stable return result | New | store |\n')
        self.settings=self.base.configure(artifact=self.artifact)
        self.ref='fixture:@code/value.py#value'
        self.calls=[]
        self.ingest()
        self.old_files()

    def old_files(self):
        stamp=(datetime.now(timezone.utc)-timedelta(hours=1)).timestamp()
        for root in (self.code,self.artifact):
            for path in root.rglob('*'):
                if path.is_file() and '.git' not in path.parts:os.utime(path,(stamp,stamp))

    def ingest(self,settings=None):
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        with patch('mycel._build_identity.current_build',return_value=1):
            result=ingest(Invocation('ingest',repositories=('fixture',),settings=settings or self.settings))
        self.assertEqual(result.status,0,result.value)

    def dependencies(self,*,changed=None,top=.9,label=None,limits=None,failure=None):
        def factory(settings,policy):
            def credential(*args,**kwargs):
                return CompletedChild(0,b'public-fixture-only\n',b'',0)
            def transport(body,key,**kwargs):
                request=json.loads(body);self.calls.append(request)
                if changed:changed(request)
                if failure:raise failure
                path=request['state']['candidate']['snapshot']['place']['path']
                chosen=label or ('unrelated' if path.endswith('test_value.py') else 'related' if path=='symbol.md' else 'governs')
                probabilities={item:(1-top)/2 for item in ORIGIN_LABELS};probabilities[chosen]=top
                value={'model':settings.values['drifts']['model'],
                    'answers':{'dependency':{'type':'choice','choice':chosen,'probabilities':probabilities,
                                            'confidence':(3*top-1)/2}},
                    'usage':{'input_tokens':100,'output_tokens':8}}
                return HTTPResult(200,json.dumps(value).encode(),{})
            return JevClient(Credentials(settings,policy,_runner=credential),policy,
                limits=limits or JevLimits.from_settings(settings),_transport=transport)
        return ClassifyDependencies(jev_factory=factory)

    def run_recovery(self,**options):
        settings=options.pop('settings',self.settings)
        with self.base.connect() as connection:
            return run_recovery(RecoveryStore(connection),settings,'fixture',chunk=options.pop('chunk',self.ref),**options)

    def origins(self):
        from mycel._origins import origins_in_transaction
        with self.base.connect() as connection,read_snapshot(connection):
            return origins_in_transaction(connection,self.settings,'fixture',chunk=self.ref)['chunks'][0]['links']

    def state(self):
        from mycel._store import TABLES
        with self.base.connect() as connection:
            return {table.name:connection.execute('SELECT to_jsonb(t),xmin::text FROM public.'+table.name+
                ' t ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    @proves('MYC-17.13',kind='store')
    def test_dry_run_lists_each_local_source_without_writes_or_model_credentials(self):
        before=self.state()
        with patch('mycel._credentials.Credentials.require_jev_key',side_effect=AssertionError('no model key')), \
             patch('mycel._classification_runner._jev',side_effect=AssertionError('no model client')), \
             patch('mycel._recovery.run_git',wraps=__import__('mycel._safeguards',fromlist=['run_git']).run_git) as git:
            reply=self.run_recovery(dry_run=True)
        self.assertEqual(reply['status'],0,reply)
        self.assertEqual((reply['jevCalls'],reply['reviewCalls']),(0,0))
        self.assertTrue(reply['chunks'][0]['history']['available'],reply['chunks'][0]['history'])
        candidates=reply['chunks'][0]['candidates']
        self.assertTrue(candidates,reply)
        self.assertEqual({source for item in candidates for source in item['sources']},{'document','test','commit','issue'})
        self.assertEqual(reply['chunks'][0]['embedding'],{'available':False,'reason':'chunk_vectors_unavailable'})
        self.assertTrue(all(item['origin'].startswith('fixture:@') for item in candidates))
        self.assertTrue(all(item['status']=='pending_jev' for item in candidates),candidates)
        self.assertFalse(any('linear.md' in item['origin'] for item in candidates))
        self.assertEqual(before,self.state())
        self.assertEqual({call.args[0][0] for call in git.call_args_list},{'rev-parse','log'})

    @proves('MYC-17.13',kind='store')
    def test_embedding_candidates_use_existing_complete_vectors_and_uuid_uri(self):
        from mycel._resolver import SourceResolver
        from test_retrieval_store import RetrievalStoreTests
        with self.base.connect() as connection:
            catalog=SourceResolver.from_store(connection,self.settings)
            for ref in (self.ref,'fixture:@artifact/spec.md#FIX-1.1'):
                selected=catalog.resolve(ref,purpose='endpoint').selection
                chunk=selected.members[0].chunk
                RetrievalStoreTests().plan(connection,chunk.identifier,chunk.version,chunk.source.decode())
        reply=self.run_recovery(dry_run=True)
        self.assertEqual(reply['status'],0,reply)
        self.assertTrue(reply['chunks'][0]['embedding']['available'])
        entities=[item for item in reply['chunks'][0]['candidates'] if 'embedding' in item['sources']]
        self.assertTrue(entities,reply)
        entity=entities[0]
        self.assertEqual(entity['status'],'pending_jev',entity)
        self.assertIn(':req:'+REQ+':',entity['origin'])
        self.assertEqual((reply['jevCalls'],reply['reviewCalls']),(0,0))

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_complete_judgements_write_exact_scores_and_methods_without_verification(self):
        reply=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        self.assertEqual(reply['completed'],reply['selected'])
        self.assertEqual(reply['jevCalls'],len(self.calls))
        links=self.origins();self.assertEqual(len(links),4,links)
        self.assertEqual({link['method'] for link in links},{'inferred','recovered'})
        self.assertTrue(all(link['confidenceScore']==.85 and link['confidence']=='inferred' for link in links))
        self.assertFalse(any('test_value' in link['origin'] for link in links))
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(),(0,))
            manifests=connection.execute("SELECT hash,bytes,metadata FROM public.mycel_manifests WHERE kind='origin_recovery'").fetchall()
            self.assertEqual(len(manifests),reply['selected'])
            for digest,raw,metadata in manifests:
                self.assertEqual(OriginDecisionPayload.from_bytes(bytes(raw),digest).input_hash,digest)
                self.assertEqual(metadata['record']['status'],'complete')
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='origin_recovery' AND invocation IS NOT NULL").fetchone(),(0,))

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_changed_inputs_after_call_have_no_link_or_verification_effect(self):
        def changed(request):self.source.write_text('def value():\n    return 2\n')
        reply=self.run_recovery(k=1,dependencies=self.dependencies(changed=changed))
        self.assertEqual(reply['status'],1,reply)
        self.assertEqual(reply['jevCalls'],1)
        self.assertEqual(reply['completed'],0)
        self.assertEqual(self.origins(),[])
        self.assertIn(reply['pairs'][0]['reason'],{'obsolete','changed_since_ingest'})
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(),(0,))

    def reviewer_settings(self,unrelated=False):
        adapter=self.base.base/'reviewer'
        adapter.write_text('#!'+sys.executable+'\n'+'''import json,sys
r=json.load(sys.stdin)
p=r['payload']['candidate']['snapshot']['place']['path']
v={k:r[k] for k in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
v.update(judgement='governs',rationale='Fixture contract review.',evidence=r['evidenceLocators'][:1],confidenceScore=.35 if p=='symbol.md' else .95)
print(json.dumps(v))
''');adapter.chmod(0o700)
        if unrelated:adapter.write_text(adapter.read_text().replace("judgement='governs'","judgement='unrelated'"))
        self.base.config.write_text(self.base.config.read_text()+'\n[drifts]\nreview_command='+json.dumps([str(adapter)])+
            '\nreview_provider="fixture"\nreview_model="fixture-review-1"\nreview_revision="fixture-v1"\n')
        return load_settings(path=self.base.config,home=self.base.base)

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_real_isolated_standin_review_raises_and_lowers_scores_and_bands(self):
        self.settings=self.reviewer_settings()
        first=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(first['status'],0,first)
        reviewed=self.run_recovery(review=True,dependencies=self.dependencies())
        self.assertEqual(reviewed['status'],0,reviewed)
        self.assertEqual(reviewed['jevCalls'],0)
        self.assertEqual(reviewed['reviewCalls'],4,reviewed)
        links=self.origins();self.assertEqual(len(links),4)
        lowered=next(link for link in links if 'symbol.md' in link['origin'])
        raised=next(link for link in links if 'ref.md' in link['origin'])
        self.assertEqual((lowered['confidenceScore'],lowered['confidence']),(.35,'candidate'))
        self.assertEqual((raised['confidenceScore'],raised['confidence']),(.95,'inferred'))
        self.assertTrue(all(link['review']['outcome']=='governs' for link in links))
        self.assertTrue(all(link['review']['who']=='fixture-review-1' for link in links))

    @proves('MYC-17.15',kind='store')
    def test_third_party_snapshots_recover_without_linear_or_remote_reads(self):
        before={str(path):path.read_bytes() for path in self.artifact.glob('*.md')}
        with patch('urllib.request.urlopen',side_effect=AssertionError('no remote read')):
            reply=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        origins={link['origin'] for link in self.origins()}
        self.assertTrue(any('issue.md' in origin for origin in origins))
        self.assertTrue(any('commit.md' in origin for origin in origins))
        self.assertFalse(any('linear.md' in origin for origin in origins))
        self.assertFalse(any('linear.app' in json.dumps(call) for call in self.calls))
        self.assertEqual(before,{str(path):path.read_bytes() for path in self.artifact.glob('*.md')})

    @proves('MYC-17.13','MYC-14.28',kind='store')
    def test_pending_debounce_and_missing_reviewer_have_no_paid_or_link_effect(self):
        os.utime(self.source,None)
        pending=self.run_recovery(k=1,dependencies=self.dependencies())
        self.assertEqual(pending['status'],0,pending)
        self.assertEqual(pending['jevCalls'],0)
        self.assertEqual(pending['pairs'][0]['status'],'pending_debounce')
        self.assertEqual(self.origins(),[])
        self.old_files()
        # An unchanged byte version retains its original observation, even if
        # someone restores an older mtime. Re-ingest a new exact version first.
        self.source.write_text('def value():\n    return 2\n');self.ingest();self.old_files()
        observed=self.run_recovery(k=1,dependencies=self.dependencies(top=.7))
        self.assertEqual(observed['pairs'][0]['status'],'pending_debounce')
        later=(datetime.now(timezone.utc)+timedelta(seconds=301)).isoformat()
        dependencies=replace(self.dependencies(top=.7),utc_now=lambda:later)
        uncertain=self.run_recovery(k=1,dependencies=dependencies)
        self.assertEqual(uncertain['status'],0,uncertain)
        self.assertEqual(uncertain['pairs'][0]['status'],'needs_llm_review')
        self.assertEqual(uncertain['pairs'][0]['reason'],'reviewer_unconfigured')
        self.assertEqual((uncertain['jevCalls'],uncertain['reviewCalls']),(1,0))
        self.assertEqual(self.origins(),[])

    @proves('MYC-17.13',kind='store')
    def test_path_repository_and_public_chunk_commands_use_same_candidates(self):
        from mycel._cli import run
        with self.base.connect() as connection:
            paths=run_recovery(RecoveryStore(connection),self.settings,'fixture',paths=('value.py',),dry_run=True)
        self.assertEqual([row['chunk'] for row in paths['chunks']],[self.ref])
        with self.base.connect() as connection:
            repository=run_recovery(RecoveryStore(connection),self.settings,'fixture',dry_run=True)
        self.assertIn(self.ref,[row['chunk'] for row in repository['chunks']])
        output,diagnostic=StringIO(),StringIO()
        with patch('mycel._cli.load_settings',return_value=self.settings):
            status=run(('recovery',self.ref,'--dry-run'),stdout=output,stderr=diagnostic)
        self.assertEqual(status,0,output.getvalue())
        self.assertEqual(diagnostic.getvalue(),'')
        self.assertEqual(json.loads(output.getvalue())['repository'],'fixture')

    @proves('MYC-17.14',kind='store')
    def test_model_claims_survive_ingest_without_source_cycles_and_statement_supersedes(self):
        from mycel._justify import JustifyStore
        reply=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        self.ingest()
        self.assertEqual(len(self.origins()),4)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_stale_reasons').fetchone(),(0,))
            result=JustifyStore(connection).apply(self.settings,self.ref,'fixture:@artifact/symbol.md#Symbol%20contract')
            self.assertEqual(result['link']['method'],'stated')
        links=[link for link in self.origins() if 'symbol.md' in link['origin']]
        self.assertEqual(len(links),1,links)
        self.assertEqual((links[0]['confidenceScore'],links[0]['confidence']),(1.0,'asserted'))
        reviewed=self.run_recovery(review=True,dry_run=True)
        self.assertFalse(any('symbol.md' in pair['origin'] for pair in reviewed['pairs']))

    @proves('MYC-17.13','MYC-17.14','MYC-14.28',kind='store')
    def test_clone_clock_and_equal_version_links_belong_only_to_calling_location(self):
        clone=self.base.base/'blue'
        self.base.git('clone','--no-hardlinks',str(self.code),str(clone),cwd=self.base.base)
        self.base.config.write_text(self.base.config.read_text()+'code_clones='+json.dumps([str(clone)])+'\n')
        settings=load_settings(path=self.base.config,home=self.base.base)
        primary=replace(settings,_cwd=self.code);secondary=replace(settings,_cwd=clone)
        self.settings=primary
        self.ingest(secondary)
        os.utime(clone/'value.py',None)
        pending=self.run_recovery(settings=secondary,k=1,dependencies=self.dependencies())
        self.assertEqual(pending['status'],0,pending)
        self.assertEqual(pending['pairs'][0]['status'],'pending_debounce')
        self.assertEqual(pending['jevCalls'],0)
        stamp=(datetime.now(timezone.utc)-timedelta(hours=1)).timestamp()
        for path in clone.rglob('*.py'):os.utime(path,(stamp,stamp))
        later=(datetime.now(timezone.utc)+timedelta(seconds=301)).isoformat()
        result=self.run_recovery(settings=secondary,dependencies=replace(self.dependencies(),utc_now=lambda:later))
        self.assertEqual(result['status'],0,result)
        self.assertEqual(self.origins(),[])
        self.settings=secondary
        self.assertEqual(len(self.origins()),4)

    @proves('MYC-14.28',kind='store')
    def test_byte_budget_and_terminal_fault_never_write_a_link(self):
        oversized=self.run_recovery(k=1,dependencies=self.dependencies(limits=JevLimits(max_input_bytes=1)))
        self.assertEqual(oversized['status'],0,oversized)
        self.assertEqual((oversized['jevCalls'],oversized['reviewCalls']),(0,0))
        self.assertEqual(oversized['pairs'][0]['status'],'needs_llm_review')
        failed=self.run_recovery(k=1,dependencies=self.dependencies(failure=JevFailure('provider_result_invalid')))
        self.assertEqual(failed['status'],1,failed)
        self.assertEqual(failed['jevCalls'],1)
        self.assertEqual(len(failed['pairs'][0]['attempts']),1)
        self.assertEqual(self.origins(),[])

    @proves('MYC-14.28',kind='store')
    def test_interrupt_preserves_completed_prefix_and_releases_evidence_leases(self):
        def interrupt(request):
            if len(self.calls)==2:raise KeyboardInterrupt()
        result=self.run_recovery(dependencies=self.dependencies(changed=interrupt))
        self.assertEqual(result['status'],2,result)
        self.assertEqual(result['completed'],1,result)
        self.assertEqual(result['jevCalls'],2)
        self.assertEqual(len(self.origins()),1)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='origin_recovery' AND invocation IS NOT NULL").fetchone(),(0,))

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_edit_during_final_audit_rolls_back_the_origin_claim_and_edge(self):
        source=self.source
        class EditingAudit:
            def record_in_transaction(self,*args):
                source.write_text('def value():\n    return 3\n')
        reply=self.run_recovery(k=1,dependencies=self.dependencies(),activity=EditingAudit())
        self.assertEqual(reply['status'],1,reply)
        self.assertEqual(reply['jevCalls'],1)
        self.assertEqual(self.origins(),[])
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='origin'").fetchone(),(0,))

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_validated_result_reuse_and_corrupt_cache_refusal(self):
        from psycopg.types.json import Jsonb
        first=self.run_recovery(k=1,dependencies=self.dependencies(label='unrelated'))
        self.assertEqual(first['status'],0,first)
        self.assertEqual(self.origins(),[])
        second=self.run_recovery(k=1,dependencies=self.dependencies(label='unrelated'))
        self.assertEqual(second['status'],0,second)
        self.assertEqual(second['jevCalls'],0)
        self.assertTrue(second['pairs'][0]['reused'])
        with self.base.connect() as connection:
            digest,metadata=connection.execute("SELECT hash,metadata FROM public.mycel_manifests WHERE kind='origin_recovery'").fetchone()
            metadata['record']['confidenceScore']=.99
            connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                               (Jsonb(metadata),'fixture',digest))
        corrupt=self.run_recovery(k=1,dependencies=self.dependencies())
        self.assertEqual(corrupt['status'],1,corrupt)
        self.assertEqual(corrupt['jevCalls'],0)
        self.assertEqual(corrupt['pairs'][0]['reason'],'snapshot_corrupt')
        self.assertEqual(self.origins(),[])

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_unrelated_review_withdraws_only_model_claims(self):
        from mycel._activity import MutationActivity
        self.settings=self.reviewer_settings(unrelated=True)
        result=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(result['status'],0,result)
        self.assertEqual(len(self.origins()),4)
        with self.base.connect() as connection,MutationActivity(connection,build=1).session() as activity:
            reviewed=run_recovery(RecoveryStore(connection),self.settings,'fixture',chunk=self.ref,
                                 review=True,dependencies=self.dependencies(),activity=activity)
            self.assertEqual(reviewed['status'],0,reviewed)
            activity.finish('done',counts={('fixture','recovery'):reviewed})
        self.assertEqual(self.origins(),[])
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='recovery'").fetchone(),(1,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(),(0,))

    @proves('MYC-17.14','MYC-14.28',kind='store')
    def test_numbered_public_command_records_committed_origin_mutations(self):
        from mycel._cli import run
        output,diagnostic=StringIO(),StringIO()
        with patch('mycel._cli.load_settings',return_value=self.settings), \
             patch('mycel._recovery.ClassifyDependencies',return_value=self.dependencies()), \
             patch('mycel._build_identity.current_build',return_value=1):
            status=run(('recovery',self.ref),stdout=output,stderr=diagnostic)
        self.assertEqual(status,0,output.getvalue())
        reply=json.loads(output.getvalue());self.assertEqual(reply['completed'],5,reply)
        self.assertEqual(diagnostic.getvalue(),'')
        with self.base.connect() as connection:
            counts,outcome=connection.execute("SELECT counts,outcome FROM public.mycel_activity WHERE kind='recovery'").fetchone()
            self.assertEqual(outcome,'done')
            self.assertEqual(counts['completed'],5)
        self.assertEqual(len(self.origins()),4)

    @proves('MYC-14.28',kind='store')
    def test_busy_and_expired_deadline_make_no_model_call(self):
        from mycel._locks import operation_guard
        from mycel._freshness import Deadline
        with self.base.connect() as connection,operation_guard(connection,'fixture','classify'):
            busy=self.run_recovery(k=1,dependencies=self.dependencies())
        self.assertEqual(busy['status'],1,busy)
        self.assertEqual(busy['jevCalls'],0)
        expired=self.run_recovery(k=1,dependencies=self.dependencies(),deadline=Deadline.after(.000001))
        self.assertEqual(expired['status'],1,expired)
        self.assertTrue(expired['incomplete'])
        self.assertEqual(expired['jevCalls'],0)
        self.assertEqual(self.origins(),[])

    @proves('MYC-14.28',kind='store')
    def test_transient_attempts_stop_at_configured_cap(self):
        reply=self.run_recovery(k=1,dependencies=self.dependencies(failure=JevFailure('connection')))
        self.assertEqual(reply['status'],1,reply)
        self.assertEqual(reply['jevCalls'],2)
        self.assertEqual(len(reply['pairs'][0]['attempts']),2)
        self.assertEqual(self.origins(),[])

    @proves('MYC-17.13','MYC-17.14',kind='store')
    def test_entity_title_edit_keeps_uuid_origin_and_review_updates_one_link(self):
        from mycel._resolver import SourceResolver
        from mycel._origins import origins_in_transaction
        from test_retrieval_store import RetrievalStoreTests
        self.settings=self.reviewer_settings()
        with self.base.connect() as connection:
            catalog=SourceResolver.from_store(connection,self.settings)
            for ref in (self.ref,'fixture:@artifact/spec.md#FIX-1.1'):
                selected=catalog.resolve(ref,purpose='endpoint').selection
                chunk=selected.members[0].chunk
                RetrievalStoreTests().plan(connection,chunk.identifier,chunk.version,chunk.source.decode())
        initial=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(initial['status'],0,initial)
        self.assertEqual(len(self.origins()),5)
        spec=self.artifact/'spec.md';spec.write_text(spec.read_text().replace('retain a stable return result','retain an unchanged return result'))
        self.ingest();self.old_files()
        with self.base.connect() as connection,read_snapshot(connection):
            report=origins_in_transaction(connection,self.settings,'fixture',unresting=True)
            self.assertFalse(any(REQ in row['origin'] for row in report['unresting']))
        observed=self.run_recovery(review=True,dependencies=self.dependencies())
        self.assertEqual(observed['status'],0,observed)
        later=(datetime.now(timezone.utc)+timedelta(seconds=301)).isoformat()
        reviewed=self.run_recovery(review=True,dependencies=replace(self.dependencies(),utc_now=lambda:later))
        self.assertEqual(reviewed['status'],0,reviewed)
        entities=[link for link in self.origins() if REQ in link['origin']]
        self.assertEqual(len(entities),1,entities)
        self.assertEqual(entities[0]['confidenceScore'],.95)
        self.assertIn('review',entities[0])

    @proves('MYC-17.14',kind='store')
    def test_statement_supersedes_moved_uuid_proposal_without_duplicate(self):
        from mycel._resolver import SourceResolver
        from mycel._justify import JustifyStore
        from mycel._source_refs import format_entity_uri
        from test_retrieval_store import RetrievalStoreTests
        with self.base.connect() as connection:
            catalog=SourceResolver.from_store(connection,self.settings)
            for ref in (self.ref,'fixture:@artifact/spec.md#FIX-1.1'):
                selected=catalog.resolve(ref,purpose='endpoint').selection
                chunk=selected.members[0].chunk
                RetrievalStoreTests().plan(connection,chunk.identifier,chunk.version,chunk.source.decode())
        reply=self.run_recovery(dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        (self.artifact/'spec.md').rename(self.artifact/'moved.md');self.ingest()
        with self.base.connect() as connection:
            stated=JustifyStore(connection).apply(self.settings,self.ref,format_entity_uri('req',REQ,'old display title'))
            self.assertEqual(stated['link']['method'],'stated')
        entities=[link for link in self.origins() if REQ in link['origin']]
        self.assertEqual(len(entities),1,entities)
        self.assertEqual(entities[0]['method'],'stated')

    @proves('MYC-17.13','MYC-14.28',kind='store')
    def test_pair_cap_bounds_exact_preparation_and_repo_skips_authored_roots(self):
        original=RecoveryStore.prepare_pair;calls=[]
        def counted(*args,**kwargs):
            calls.append(args[4]);return original(*args,**kwargs)
        with patch.object(RecoveryStore,'prepare_pair',counted):
            reply=self.run_recovery(k=1,dry_run=True)
        self.assertEqual(reply['status'],0,reply)
        self.assertEqual(reply['selected'],1)
        self.assertEqual(len(calls),1,calls)
        repository=self.run_recovery(chunk=None,k=1,dry_run=True)
        self.assertEqual(repository['status'],0,repository)
        self.assertTrue(repository['capped'])
        for row in repository['chunks']:
            self.assertFalse(any(path in row['chunk'] for path in ('ref.md','symbol.md','spec.md')),row)

    @proves('MYC-1.38','MYC-14.15',kind='store')
    def test_foreign_clone_ref_fault_does_not_make_unchanged_pass_mutate(self):
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        clone=self.base.base/'blue'
        self.base.git('clone','--no-hardlinks',str(self.code),str(clone),cwd=self.base.base)
        self.base.config.write_text(self.base.config.read_text()+'code_clones='+json.dumps([str(clone)])+'\n')
        settings=load_settings(path=self.base.config,home=self.base.base)
        primary=replace(settings,_cwd=self.code);secondary=replace(settings,_cwd=clone)
        (self.artifact/'missing.md').write_text('# Missing source\n\n<!-- sources:\nfixture:@code/only.py#only\n-->\n')
        (clone/'only.py').write_text('def only():\n    return 1\n')
        def capture(selected):
            with patch('mycel._build_identity.current_build',return_value=1):
                result=ingest(Invocation('ingest',repositories=('fixture',),settings=selected))
            self.assertEqual(result.status,0,result.value)
            return result.value['repositories']['fixture']
        capture(primary);capture(secondary)
        again=capture(secondary)
        self.assertFalse(again['changed'],again)
        again=capture(primary)
        self.assertFalse(again['changed'],again)
        self.assertFalse(capture(secondary)['changed'])
