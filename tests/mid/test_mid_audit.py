"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_audit as _support
from test_audit import (AuditStore ,MycelError ,datetime ,json ,load_settings ,replace ,timedelta ,timezone ,uuid4)


class SemanticAuditStoreTests(_support.SemanticAuditStoreTests):

# TEST-TIER-BEGIN tests/test_audit.py::SemanticAuditStoreTests.test_a_series_of_audit_steps_keeps_its_work_and_never_sends_a_pair_twice
    def test_a_series_of_audit_steps_keeps_its_work_and_never_sends_a_pair_twice(self):
        self.two_origins()
        dependencies=self.dependencies(positive=True)
        replies=[]
        for _ in range(10):
            replies.append(self.audit(k=1,dependencies=dependencies))
            self.assertEqual(replies[-1]['status'],0,replies[-1])
            if replies[-1]['complete']:
                break
        self.assertTrue(replies[-1]['complete'],replies[-1])
        self.assertGreater(len(replies),2)
        sent=[json.dumps(request['state'],sort_keys=True) for request in self.calls]
        self.assertEqual(len(sent),len(set(sent)))
        again=self.audit(k=1,dependencies=dependencies)
        self.assertEqual((again['jevCalls'],again['selected'],again['remaining'],again['complete']),(0,0,0,True),again)
        self.assertFalse([row for row in again['findings'] if row['mode']=='semantic'])
# TEST-TIER-END tests/test_audit.py::SemanticAuditStoreTests.test_a_series_of_audit_steps_keeps_its_work_and_never_sends_a_pair_twice


# TEST-TIER-BEGIN tests/test_audit.py::SemanticAuditStoreTests.test_real_isolated_reviewer_routes_each_question_with_exact_scored_evidence
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
# TEST-TIER-END tests/test_audit.py::SemanticAuditStoreTests.test_real_isolated_reviewer_routes_each_question_with_exact_scored_evidence


# TEST-TIER-BEGIN tests/test_audit.py::SemanticAuditStoreTests.test_interrupt_preserves_completed_prefix_and_releases_request_leases
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
# TEST-TIER-END tests/test_audit.py::SemanticAuditStoreTests.test_interrupt_preserves_completed_prefix_and_releases_request_leases


# TEST-TIER-BEGIN tests/test_audit.py::SemanticAuditStoreTests.test_clone_quiet_clocks_and_findings_are_isolated_while_exact_results_are_shared
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
        self.assertEqual(self.links()[0]['confidenceScore'],.1)
        with self.base.connect() as connection:
            with self.assertRaises(MycelError):
                AuditStore(connection).settle(secondary,'fixture',primary_findings[0],reason='Wrong clone.',by='fixture-owner')
        self.settings=primary
        retained,_=self.deterministic();self.assertEqual([r['id'] for r in retained],primary_findings)
        self.assertEqual(self.links()[0]['confidenceScore'],.1)
# TEST-TIER-END tests/test_audit.py::SemanticAuditStoreTests.test_clone_quiet_clocks_and_findings_are_isolated_while_exact_results_are_shared

# TEST-TIER-BEGIN tests/test_audit.py::SemanticAuditStoreTests.test_newest_thousand_closed_and_ended_bundles_preserve_open_live_and_shared_evidence
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
# TEST-TIER-END tests/test_audit.py::SemanticAuditStoreTests.test_newest_thousand_closed_and_ended_bundles_preserve_open_live_and_shared_evidence
