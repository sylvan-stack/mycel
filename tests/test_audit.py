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


class AuditFixture(unittest.TestCase):
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


class AuditStoreTests(AuditFixture):
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
        term=next(item for item in findings if item['kind']=='missing_term')
        with self.base.connect() as connection:
            retained=[bytes(row[0]) for row in connection.execute('SELECT s.bytes FROM public.mycel_evidence_owners o '
                'JOIN public.mycel_evidence_references r ON r.owner=o.id JOIN public.mycel_snapshots s '
                'ON s.repository=r.repository AND s.hash=r.snapshot_hash WHERE o.identity=%s',(term['observationHash'],)).fetchall()]
        self.assertIn((self.artifact/'GLOSSARY.md').read_bytes(),retained)
        status,public=public_audit(self,('audit','--repo','fixture','--deterministic'))
        self.assertEqual(status,0,public);self.assertEqual(len(public['findings']),7)
        self.assertEqual({row['kind'] for row in public['findings']},set(DETERMINISTIC))
        self.assertEqual((public['jevCalls'],public['reviewCalls']),(0,0))
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
        self.spec.write_text(self.spec.read_text().replace('retain an unused contract','Withdrawn: retain an unused contract'));self.ingest()
        current,_=self.deterministic(dry_run=True)
        proposed=[row for row in current if row['state']=='proposed' and row['kind']=='unresting_requirement']
        self.assertFalse(any(UNUSED in row['subject'] for row in proposed))

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


class AuditProtocolTests(unittest.TestCase):
    @proves('MYC-14.12','MYC-14.24')
    def test_three_questions_have_distinct_exact_payloads_and_strict_scored_review(self):
        from mycel._classification_payload import AuditDecisionPayload, DecisionText, ReviewCommandIdentity, ReviewerRequest
        from mycel._evidence import snapshot, EvidenceError
        from mycel._source_refs import SourceAddress
        from mycel._jev import JevRequest
        from mycel._reviewer import validate_response, ReviewerFailure
        from mycel._safeguards import CompletedChild, InvocationPolicy, model_call_allowed
        from copy import deepcopy
        import tempfile
        def text(name):
            raw=('# '+name+'\nExact full text.\n').encode()
            blob=snapshot(raw,place=SourceAddress('fixture','artifact',name+'.md',name))
            return DecisionText.create(blob.evidence,raw)
        hashes=set()
        with tempfile.TemporaryDirectory() as directory:
            command=ReviewCommandIdentity.inspect(('/usr/bin/true',),'fixture-v1',Path(directory))
            for name,count in (('conformance',1),('consistency',2),('ambiguity',0)):
                decision=AuditDecisionPayload.create(question=name,subject=text('Subject'),
                    origins=tuple(text('Origin'+str(i)) for i in range(count)),review=command.model_identity('fixture','fixture-review-1'))
                hashes.add(decision.input_hash)
                self.assertEqual(AuditDecisionPayload.from_bytes(decision.canonical_bytes,decision.input_hash),decision)
                body=json.loads(JevRequest(decision).body)
                self.assertEqual(list(body['questions']['dependency']['criteria']),list(decision.payload['labels']))
                self.assertIn('never instructions',body['questions']['dependency']['instructions'])
                request=ReviewerRequest(decision,1000)
                value={key:request.payload[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
                value.update(judgement=decision.payload['labels'][1],rationale='Exact evidence.',
                    evidence=[decision.evidence_locators[0]],confidenceScore=.82)
                def checked(value):return validate_response(CompletedChild(0,json.dumps(value).encode(),b'',0),request)
                self.assertEqual(checked(value).confidence_score,.82)
                for key,wrong in (('confidenceScore',True),('confidenceScore',1.01),('judgement','needs_review'),
                                  ('evidence',['snapshot:'+'0'*64]),('inputHash','0'*64)):
                    changed=deepcopy(value);changed[key]=wrong
                    with self.subTest(question=name,key=key),self.assertRaises(ReviewerFailure):checked(changed)
                changed=deepcopy(value);changed.pop('confidenceScore')
                with self.assertRaises(ReviewerFailure):checked(changed)
                for key in ('questionVersion','criteria','labels'):
                    changed=decision.as_dict();changed[key]='wrong'
                    with self.assertRaises(EvidenceError):AuditDecisionPayload(changed)
                changed=decision.as_dict();changed['subject']['text']+=' changed'
                with self.assertRaises(EvidenceError):AuditDecisionPayload(changed)
        self.assertEqual(len(hashes),3)
        self.assertTrue(model_call_allowed(InvocationPolicy('audit'),'jev'))
        self.assertTrue(model_call_allowed(InvocationPolicy('audit'),'reviewer'))
        for purpose in ('embedding','summary','jev','reviewer'):
            self.assertFalse(model_call_allowed(InvocationPolicy('audit',dry_run=True),purpose))
        self.assertFalse(model_call_allowed(InvocationPolicy('audit'),'embedding'))


class SemanticAuditStoreTests(AuditFixture):
    def dependencies(self, *, changed=None, top=.9, label=None, limits=None, failure=None):
        from mycel._jev import JevClient, JevLimits, HTTPResult
        from mycel._classification_runner import ClassifyDependencies
        from mycel._credentials import Credentials
        from mycel._safeguards import CompletedChild
        def factory(settings, policy):
            def credential(*args, **kwargs):return CompletedChild(0,b'public-fixture-only\n',b'',0)
            def transport(body,key,**kwargs):
                request=json.loads(body);self.calls.append(request)
                if changed:changed(request)
                if failure:raise failure
                state=request['state'];question=state['question']
                labels=state['labels'];chosen=label or labels[0]
                if label is None:
                    if question=='conformance' and state['origins'][0]['snapshot']['place']['path']=='spec.md':chosen='nonconforming'
                    elif question=='consistency':chosen='contradictory'
                    elif question=='ambiguity' and REQ in json.dumps(state['subject']):chosen='ambiguous'
                probabilities={item:(1-top)/2 for item in labels};probabilities[chosen]=top
                return HTTPResult(200,json.dumps({'model':settings.values['drifts']['model'],
                    'answers':{'dependency':{'type':'choice','choice':chosen,'probabilities':probabilities,'confidence':(3*top-1)/2}},
                    'usage':{'input_tokens':100,'output_tokens':8}}).encode(),{})
            return JevClient(Credentials(settings,policy,_runner=credential),policy,
                limits=limits or JevLimits.from_settings(settings),_transport=transport)
        return ClassifyDependencies(jev_factory=factory)

    def audit(self, **options):
        from mycel._audit_semantic import run_audit, SemanticAuditStore
        with self.base.connect() as connection:
            return run_audit(SemanticAuditStore(connection),self.settings,'fixture',**options)

    def links(self):
        from mycel._origins import origins_in_transaction
        with self.base.connect() as connection,read_snapshot(connection):
            return origins_in_transaction(connection,self.settings,'fixture',chunk=self.ref)['chunks'][0]['links']

    def two_origins(self):
        self.justify();self.justify('fixture:@artifact/other.md#FIX-2.1')

    @proves('MYC-17.17','MYC-17.18','MYC-14.29',kind='store')
    def test_three_negative_questions_retain_exact_evidence_lower_only_disputed_link_and_reuse(self):
        from mycel._classification_payload import AuditDecisionPayload
        self.two_origins()
        with self.base.connect() as connection:
            before=connection.execute('SELECT to_jsonb(t),xmin::text FROM public.mycel_verifications t ORDER BY id').fetchall()
        reply=self.audit(dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        negatives=[row for row in reply['findings'] if row['mode']=='semantic']
        self.assertEqual({r['kind'] for r in negatives},{'nonconforming','contradictory','ambiguous'},negatives)
        self.assertEqual(len(negatives),3,negatives)
        self.assertEqual(reply['completed'],6,reply)
        links=self.links();lowered=next(link for link in links if REQ in link['origin'])
        conforming=next(link for link in links if OTHER in link['origin'])
        self.assertEqual((lowered['confidenceScore'],lowered['confidence'],lowered['method']),(.15,'candidate','stated'))
        self.assertEqual(conforming['confidenceScore'],1)
        self.assertEqual(lowered['who'],'fixture-owner')
        self.assertEqual(lowered['review']['outcome'],'nonconforming')
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT to_jsonb(t),xmin::text FROM public.mycel_verifications t ORDER BY id').fetchall(),before)
            for digest,raw,metadata in connection.execute("SELECT hash,bytes,metadata FROM public.mycel_manifests WHERE kind='origin_audit_request'").fetchall():
                payload=AuditDecisionPayload.from_bytes(bytes(raw),digest)
                self.assertEqual(payload.input_hash,metadata['record']['inputHash'])
                self.assertEqual(metadata['record']['status'],'complete')
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='origin_audit_request' AND invocation IS NOT NULL").fetchone(),(0,))
        again=self.audit(dependencies=self.dependencies())
        self.assertEqual(again['status'],0,again);self.assertEqual(again['jevCalls'],0,again)
        self.assertEqual(again['reused'],6);self.assertEqual(again['newFindings'],0)
        disputed=next(row for row in negatives if row['kind']=='nonconforming')
        with self.base.connect() as connection:
            from psycopg.types.json import Jsonb
            AuditStore(connection).settle(self.settings,'fixture',disputed['id'],reason='The owner accepts this discrepancy.',by='fixture-owner')
            # Restoring a score without changing the claim cannot make an
            # accepted exact observation reopen or lower the link again.
            identifier=disputed['links'][0]['id']
            state=connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s',(identifier,)).fetchone()[0]
            state['originLink'].update(confidenceScore=1,confidence='asserted')
            connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',(Jsonb(state),identifier))
        settled=self.audit(dependencies=self.dependencies())
        self.assertEqual(settled['status'],0,settled);self.assertEqual(settled['jevCalls'],0)
        self.assertNotIn(disputed['id'],[r['id'] for r in settled['findings']])
        self.assertEqual(next(link for link in self.links() if REQ in link['origin'])['confidenceScore'],1)

    @proves('MYC-17.17','MYC-14.29',kind='store')
    def test_changed_input_and_late_activity_edit_roll_back_findings_and_score(self):
        self.justify()
        reply=self.audit(k=1,paths=('value.py',),dependencies=self.dependencies(changed=lambda request:self.source.write_text('def value():\n    return 9\n')))
        self.assertEqual(reply['status'],1,reply);self.assertEqual(reply['jevCalls'],1)
        self.assertEqual(self.links()[0]['confidenceScore'],1)
        self.assertFalse(any(r['mode']=='semantic' for r in reply['findings']))
        self.source.write_text('def value():\n    return 1\n\ndef spare():\n    return 2\n');self.old_files()
        # First collect mechanical findings so this callback happens only
        # inside the semantic effect transaction.
        self.deterministic(paths=('value.py',))
        source=self.source
        class EditingActivity:
            def record_in_transaction(self,*args):source.write_text('def value():\n    return 3\n')
        reply=self.audit(k=1,paths=('value.py',),dependencies=self.dependencies(),activity=EditingActivity())
        self.assertEqual(reply['status'],1,reply);self.assertEqual(reply['jevCalls'],1)
        self.assertEqual(self.links()[0]['confidenceScore'],1)
        findings,_=self.deterministic();self.assertFalse(any(r['mode']=='semantic' for r in findings))

    def reviewer_settings(self):
        import sys
        adapter=self.base.base/'reviewer'
        adapter.write_text('#!'+sys.executable+'\n'+'''import json,sys
r=json.load(sys.stdin)
p=r['payload'];q=p['question']
v={k:r[k] for k in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
v.update(judgement=p['labels'][1],rationale='Exact fixture contract comparison.',evidence=r['evidenceLocators'][:1],confidenceScore=.82)
print(json.dumps(v))
''');adapter.chmod(0o700)
        self.base.config.write_text(self.base.config.read_text()+'\n[drifts]\nreview_command='+json.dumps([str(adapter)])+
            '\nreview_provider="fixture"\nreview_model="fixture-review-1"\nreview_revision="fixture-v1"\n')
        return load_settings(path=self.base.config,home=self.base.base)

    @proves('MYC-17.17','MYC-14.29',kind='store')
    def test_real_isolated_reviewer_routes_each_question_with_exact_scored_evidence(self):
        self.settings=self.reviewer_settings();self.two_origins()
        reply=self.audit(dependencies=self.dependencies(top=.7))
        self.assertEqual(reply['status'],0,reply)
        self.assertEqual((reply['jevCalls'],reply['reviewCalls'],reply['completed']),(6,6,6))
        negatives=[r for r in reply['findings'] if r['mode']=='semantic']
        self.assertEqual({r['kind'] for r in negatives},{'nonconforming','contradictory','ambiguous'})
        self.assertTrue(all(r['confidenceScore']==.82 and r['evidence']['record']['review']['evidence'] for r in negatives))
        self.assertTrue(all(link['confidenceScore']==.18 and link['review']['who']=='fixture-review-1' for link in self.links()))
        again=self.audit(dependencies=self.dependencies(top=.7))
        self.assertEqual((again['jevCalls'],again['reviewCalls'],again['reused']),(0,0,6))

    @proves('MYC-17.17','MYC-14.29',kind='store')
    def test_every_method_and_band_is_audited_without_changing_policy_or_verification(self):
        from psycopg.types.json import Jsonb
        self.two_origins();self.justify(chunk='fixture:@code/value.py#spare')
        self.justify('fixture:@artifact/other.md#FIX-2.1',chunk='fixture:@code/value.py#spare')
        with self.base.connect() as connection:
            rows=connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE state ? 'originLink' ORDER BY id").fetchall()
            expected={}
            for (identifier,state),(method,score,band) in zip(rows,[('stated',.1,'candidate'),('proven',.9,'proven'),
                    ('inferred',.95,'inferred'),('recovered',.4,'candidate')],strict=True):
                state['originLink'].update(method=method,confidenceScore=score,confidence=band)
                expected[str(identifier)]=state.copy()
                connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',(Jsonb(state),identifier))
            verifications=connection.execute('SELECT to_jsonb(t),xmin::text FROM public.mycel_verifications t ORDER BY id').fetchall()
        reply=self.audit(k=4,dependencies=self.dependencies(label='nonconforming'))
        self.assertEqual(reply['status'],0,reply);self.assertEqual(reply['completed'],4)
        self.assertTrue(reply['capped'])
        with self.base.connect() as connection:
            rows=connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchall()
            self.assertEqual({state['originLink']['method'] for _,state in rows},{'stated','proven','inferred','recovered'})
            for identifier,state in rows:
                old=expected[str(identifier)];self.assertEqual(state['originLink']['confidenceScore'],min(old['originLink']['confidenceScore'],.15))
                self.assertEqual({k:v for k,v in state.items() if k!='originLink'},{k:v for k,v in old.items() if k!='originLink'})
                for key in ('chunk','origin','method','who','when'):self.assertEqual(state['originLink'][key],old['originLink'][key])
            self.assertEqual(connection.execute('SELECT to_jsonb(t),xmin::text FROM public.mycel_verifications t ORDER BY id').fetchall(),verifications)

    @proves('MYC-14.29','MYC-17.18',kind='store')
    def test_quiet_period_byte_budget_and_uncertain_handoff_have_no_claim_effect(self):
        from mycel._jev import JevLimits
        self.justify();os.utime(self.source,None)
        pending=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual(pending['status'],0,pending);self.assertEqual(pending['jevCalls'],0)
        self.assertEqual(pending['pairs'][0]['status'],'pending_debounce')
        later=(datetime.now(timezone.utc)+timedelta(seconds=301)).isoformat()
        small=replace(self.dependencies(limits=JevLimits(max_input_bytes=1)),utc_now=lambda:later)
        oversized=self.audit(k=1,dependencies=small)
        self.assertEqual(oversized['status'],0,oversized);self.assertEqual(oversized['jevCalls'],0)
        self.assertEqual(oversized['pairs'][0]['status'],'needs_llm_review')
        uncertain=self.audit(k=1,dependencies=replace(self.dependencies(top=.7),utc_now=lambda:later))
        self.assertEqual(uncertain['status'],0,uncertain);self.assertEqual(uncertain['jevCalls'],1)
        self.assertEqual(uncertain['pairs'][0]['reason'],'reviewer_unconfigured')
        self.assertEqual(self.links()[0]['confidenceScore'],1)

    @proves('MYC-14.29',kind='store')
    def test_candidate_cap_bounds_unresolved_preparation_before_assembly(self):
        from mycel._audit_semantic import SemanticAuditStore
        from psycopg.types.json import Jsonb
        self.two_origins()
        with self.base.connect() as connection:
            for identifier,state in connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE state ? 'originLink' ORDER BY id").fetchall():
                state['originLink']['origin']='fixture:@artifact/absent.md#Missing'
                connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',(Jsonb(state),identifier))
        before=self.state();original=SemanticAuditStore.prepare_pair;attempts=[]
        def counted(*args,**kwargs):attempts.append(args[5]);return original(*args,**kwargs)
        with patch.object(SemanticAuditStore,'prepare_pair',counted):reply=self.audit(k=1,dry_run=True)
        self.assertEqual(reply['status'],0,reply);self.assertEqual(len(attempts),1)
        self.assertEqual(reply['selected'],0);self.assertEqual(reply['attempted'],1);self.assertTrue(reply['capped'])
        self.assertEqual(reply['pairs'][0]['status'],'unresolved')
        self.assertEqual(self.state(),before)

    @proves('MYC-14.29',kind='store')
    def test_busy_deadline_terminal_and_transient_failures_are_finite(self):
        from mycel._locks import operation_guard
        from mycel._freshness import Deadline
        from mycel._jev import JevFailure
        self.justify()
        with self.base.connect() as connection,operation_guard(connection,'fixture','classify'):
            busy=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual(busy['status'],1,busy);self.assertEqual(busy['jevCalls'],0)
        expired=self.audit(k=1,dependencies=self.dependencies(),deadline=Deadline.after(.000001))
        self.assertEqual(expired['status'],1,expired);self.assertTrue(expired['incomplete'])
        self.assertEqual(expired['jevCalls'],0)
        terminal=self.audit(k=1,dependencies=self.dependencies(failure=JevFailure('authentication')))
        self.assertEqual((terminal['status'],terminal['jevCalls']),(1,1),terminal)
        transient=self.audit(k=1,dependencies=self.dependencies(failure=JevFailure('connection')))
        self.assertEqual((transient['status'],transient['jevCalls']),(1,2),transient)
        self.assertEqual(len(transient['pairs'][0]['attempts']),2)
        self.assertEqual(self.links()[0]['confidenceScore'],1)

    @proves('MYC-14.29','MYC-17.18',kind='store')
    def test_interrupt_preserves_completed_prefix_and_releases_request_leases(self):
        self.two_origins()
        def interrupt(request):
            if len(self.calls)==2:raise KeyboardInterrupt()
        reply=self.audit(dependencies=self.dependencies(changed=interrupt))
        self.assertEqual(reply['status'],2,reply);self.assertEqual(reply['completed'],1)
        self.assertEqual(reply['jevCalls'],2);self.assertTrue(reply['incomplete'])
        self.assertEqual(len([r for r in reply['findings'] if r['mode']=='semantic']),1)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE kind='origin_audit_request' AND invocation IS NOT NULL").fetchone(),(0,))

    @proves('MYC-14.29',kind='store')
    def test_corrupt_cached_stage_is_refused_without_a_call_or_claim_effect(self):
        from psycopg.types.json import Jsonb
        self.justify()
        first=self.audit(k=1,dependencies=self.dependencies(label='conforms'))
        self.assertEqual(first['status'],0,first)
        with self.base.connect() as connection:
            digest,metadata=connection.execute("SELECT hash,metadata FROM public.mycel_manifests WHERE kind='origin_audit_request'").fetchone()
            metadata['record']['confidenceScore']=.99
            connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',(Jsonb(metadata),'fixture',digest))
        reply=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual(reply['status'],1,reply);self.assertEqual(reply['jevCalls'],0)
        self.assertEqual(reply['pairs'][0]['reason'],'snapshot_corrupt')
        self.assertEqual(self.links()[0]['confidenceScore'],1)

    @proves('MYC-17.16','MYC-17.18','MYC-14.29',kind='store')
    def test_public_command_records_mutations_settlement_and_readonly_dryrun(self):
        self.justify()
        status,preview=public_audit(self,('audit','--repo','fixture','--dry-run'),self.dependencies())
        self.assertEqual(status,0,preview);self.assertEqual(preview['jevCalls'],0)
        before=self.state()
        with patch('mycel._credentials.Credentials.require_jev_key',side_effect=AssertionError('deterministic mode forbids models')):
            status,reply=public_audit(self,('audit','--repo','fixture','--deterministic'))
        self.assertEqual(status,0,reply);self.assertGreater(reply['newFindings'],0)
        target=reply['findings'][0]
        status,settled=public_audit(self,('audit','--repo','fixture','--settle',target['id'],'--reason','Reviewed and accepted.','--by','fixture-owner'))
        self.assertEqual(status,0,settled);self.assertEqual(settled['settled']['state'],'settled')
        status,history=public_audit(self,('audit','--repo','fixture','--deterministic','--closed'))
        self.assertEqual(status,0,history);self.assertIn(settled['settled'],history['findings'])
        status,semantic=public_audit(self,('audit','--repo','fixture','--k','1'),self.dependencies())
        self.assertEqual(status,0,semantic);self.assertEqual(semantic['jevCalls'],1)
        with self.base.connect() as connection:
            activities=connection.execute("SELECT counts,outcome FROM public.mycel_activity WHERE kind='audit' ORDER BY id").fetchall()
        self.assertEqual(len(activities),3,activities)
        self.assertTrue(all(outcome=='done' for _,outcome in activities))
        before=self.state()
        status,_=public_audit(self,('audit','--repo','fixture','--dry-run','--deterministic'))
        self.assertEqual(status,0);self.assertEqual(before,self.state())


    @proves('MYC-17.18','MYC-14.29',kind='store')
    def test_clone_quiet_clocks_and_findings_are_isolated_while_exact_results_are_shared(self):
        self.base.git('init','--initial-branch=main');self.base.git('add','--all');self.base.git('commit','--message','Fixture')
        clone=self.base.base/'blue';self.base.git('clone','--no-hardlinks',str(self.code),str(clone),cwd=self.base.base)
        self.base.config.write_text(self.base.config.read_text()+'code_clones='+json.dumps([str(clone)])+'\n')
        settings=load_settings(path=self.base.config,home=self.base.base)
        primary=replace(settings,_cwd=self.code);secondary=replace(settings,_cwd=clone)
        self.settings=primary;self.ingest();self.justify();self.old_files()
        first=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual((first['status'],first['jevCalls']),(0,1),first)
        primary_findings=[r['id'] for r in first['findings']]
        self.settings=secondary;self.ingest();self.justify()
        # Keep the clone's new mtime; it cannot borrow the primary's clock.
        pending=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual(pending['status'],0,pending);self.assertEqual(pending['jevCalls'],0)
        self.assertEqual(pending['pairs'][0]['status'],'pending_debounce')
        self.assertEqual(self.links()[0]['confidenceScore'],1)
        self.assertFalse(set(primary_findings)&{r['id'] for r in pending['findings']})
        self.assertEqual(first['pairs'][0]['inputHash'],pending['pairs'][0]['inputHash'])
        later=(datetime.now(timezone.utc)+timedelta(seconds=301)).isoformat()
        second=self.audit(k=1,dependencies=replace(self.dependencies(),utc_now=lambda:later))
        self.assertEqual(second['status'],0,second)
        self.assertEqual((second['jevCalls'],second['reused'],second['completed']),(0,1,1))
        self.assertEqual(self.links()[0]['confidenceScore'],.15)
        with self.base.connect() as connection:
            with self.assertRaises(MycelError):
                AuditStore(connection).settle(secondary,'fixture',primary_findings[0],reason='Wrong clone.',by='fixture-owner')
        self.settings=primary
        retained,_=self.deterministic();self.assertEqual([r['id'] for r in retained],primary_findings)
        self.assertEqual(self.links()[0]['confidenceScore'],.15)

    @proves('MYC-17.18',kind='store')
    def test_newest_thousand_closed_and_ended_bundles_preserve_open_live_and_shared_evidence(self):
        from psycopg.types.json import Jsonb
        from mycel._audit import observation, finding_id
        from mycel._audit_semantic import SemanticAuditStore
        from mycel._classification_payload import AuditDecisionPayload
        from mycel._evidence import snapshot
        from mycel._drift_store import DriftStore
        from mycel._locks import invocation_guard
        self.justify();reply=self.audit(k=1,dependencies=self.dependencies())
        self.assertEqual(reply['status'],0,reply)
        with self.base.connect() as connection:
            request,raw,metadata=connection.execute("SELECT hash,bytes,metadata FROM public.mycel_manifests WHERE kind='origin_audit_request'").fetchone()
            ended=connection.execute('SELECT id FROM public.mycel_invocations ORDER BY id LIMIT 1').fetchone()[0]
            store=SemanticAuditStore(connection)
            subject=reply['pairs'][0]['subject'];links=reply['pairs'][0]['links']
            observations=[observation('fixture','disk','nonconforming',subject,'value.py',
                links=links,facts={'retentionFixture':i},input_hash=request) for i in range(1003)]
            identifiers=sorted(finding_id(value) for value in observations)
            shared=snapshot(b'Shared exact retained evidence.');unique=snapshot(b'Only the expired finding owns this.')
            with invocation_guard(connection) as live,store.guarded(self.settings):
                protected=uuid4()
                connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
                    (protected,'fixture','baseline','retention-fixture-protection'))
                DriftStore(connection)._retain('fixture',protected,(shared,))
                for value in observations:
                    identifier=finding_id(value)
                    blobs=(shared,) if identifier==identifiers[0] else (unique,) if identifier==identifiers[1] else ()
                    finding,_=store.open_in_transaction(value,at='2026-10-01T00:00:00+00:00',blobs=blobs,
                        record=metadata['record'],request_hash=request)
                    finding={**finding,'state':'settled','settlement':{'who':'fixture-owner','when':'2026-10-02T00:00:00+00:00','reason':'Retention fixture.'}}
                    connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                        (Jsonb({'schema':1,'finding':finding}),'fixture',finding['observationHash']))
                for i in (2000,2001):
                    value=observation('fixture','disk','nonconforming',subject,'value.py',links=links,
                        facts={'retentionFixture':i},input_hash=request)
                    store.open_in_transaction(value,at='2020-01-01T00:00:00+00:00',record=metadata['record'],request_hash=request)
                def add_request(index,at,invocation=None):
                    value=AuditDecisionPayload.from_bytes(bytes(raw),request).as_dict()
                    value['models']['jev']['model']='jev-1.13.'+str(index)
                    payload=AuditDecisionPayload(value);digest=payload.input_hash
                    connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s)',
                        ('fixture',digest,'origin_audit_request',payload.canonical_bytes,Jsonb({'schema':1,'at':at,'observations':[]})))
                    owner=uuid4();connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
                        (owner,'fixture','origin_audit_request',digest,invocation))
                    connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,0)',(owner,'fixture',digest))
                    return digest
                for i in range(1003):add_request(i+1000,'2026-10-01T00:00:00+00:00')
                live_hash=add_request(9000,'1970-01-01T00:00:00+00:00',live.id)
                expired_hash=add_request(9001,'1970-01-01T00:00:00+00:00',ended)
                open_before={r['id'] for r in store.list_in_transaction(self.settings,'fixture')}
                store.prune_in_transaction('fixture')
                all_rows=store.list_in_transaction(self.settings,'fixture',closed=True)
                self.assertEqual({r['id'] for r in all_rows if r['state']=='settled'},set(identifiers[3:]))
                self.assertEqual({r['id'] for r in all_rows if r['state']=='open'},open_before)
                requests={r[0] for r in connection.execute("SELECT hash FROM public.mycel_manifests WHERE kind='origin_audit_request'").fetchall()}
                self.assertEqual(len(requests),1002)
                self.assertIn(live_hash,requests);self.assertIn(request,requests);self.assertNotIn(expired_hash,requests)
                self.assertIsNotNone(connection.execute('SELECT 1 FROM public.mycel_snapshots WHERE hash=%s',(shared.evidence.hash,)).fetchone())
                self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots WHERE hash=%s',(unique.evidence.hash,)).fetchone())

    @proves('MYC-14.29',kind='store')
    def test_adapter_cancellation_returns_interrupted_status_without_effects(self):
        self.justify();cancelled=[False]
        def stop(request):cancelled[0]=True
        dependencies=replace(self.dependencies(changed=stop),cancelled=lambda:cancelled[0])
        reply=self.audit(k=1,dependencies=dependencies)
        self.assertEqual(reply['status'],2,reply);self.assertTrue(reply['incomplete'])
        self.assertEqual(reply['jevCalls'],1);self.assertEqual(reply['completed'],0)
        self.assertEqual(self.links()[0]['confidenceScore'],1)
        self.assertFalse(any(row['mode']=='semantic' for row in reply['findings']))


def public_audit(test,arguments,dependencies=None):
    from mycel._cli import run
    output,diagnostic=StringIO(),StringIO()
    with patch('mycel._cli.load_settings',return_value=test.settings), \
         patch('mycel._build_identity.current_build',return_value=1), \
         patch('mycel._audit_semantic.ClassifyDependencies',return_value=dependencies or __import__('mycel._classification_runner',fromlist=['ClassifyDependencies']).ClassifyDependencies()):
        status=run(arguments,stdout=output,stderr=diagnostic)
    test.assertEqual(diagnostic.getvalue(),'')
    return status,json.loads(output.getvalue())


class AuditInputTests(unittest.TestCase):
    @proves('MYC-0.6')
    def test_cli_options_scopes_settlement_and_count_validation(self):
        from mycel._cli import parse
        self.assertEqual(parse(('audit','--repo','fixture','--path','src/./audit','--deterministic')).arguments,
            ('--path','src/audit','--deterministic'))
        self.assertEqual(parse(('audit','--repo','fixture','--settle',REQ,'--reason','Accepted.','--by','owner')).arguments,
            ('--settle',REQ,'--reason','Accepted.','--by','owner'))
        for arguments in (('audit','positional'),('audit','--all'),('audit','--k','0'),
                ('audit','--repo','one','--repo','two'),('audit','--path','../escape'),('audit','--reason','No target'),
                ('audit','--settle','wrong','--reason','Reason'),('audit','--settle',REQ),
                ('audit','--settle',REQ,'--reason',' '),('audit','--settle',REQ,'--reason','Reason','--dry-run')):
            with self.subTest(arguments=arguments),self.assertRaises(MycelError):parse(arguments)
