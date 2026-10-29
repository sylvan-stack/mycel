# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Origin audit proofs over real isolated stores and public classifier stand-ins."""
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

from mycel._audit import AuditStore
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
    check_kind = "store"


class AuditProtocolTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class SemanticAuditStoreTests(AuditFixture):
    check_kind = "store"

    def dependencies(self, *, changed=None, top=.9, label=None, limits=None, failure=None, positive=False):
        from mycel._classification_runner import ClassifyDependencies
        from mycel._credentials import Credentials
        from mycel._jev import HTTPResult, JevClient, JevLimits
        from mycel._safeguards import CompletedChild
        def factory(settings, policy):
            def credential(*args, **kwargs):return CompletedChild(0,b'public-fixture-only\n',b'',0)
            def transport(body,key,**kwargs):
                request=json.loads(body);self.calls.append(request)
                if changed:changed(request)
                if failure:raise failure
                state=request['state'];question=state['question']
                labels=state['labels'];chosen=label or labels[0]
                if label is None and not positive:
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
        from mycel._audit_semantic import SemanticAuditStore, run_audit
        with self.base.connect() as connection:
            return run_audit(SemanticAuditStore(connection),self.settings,'fixture',**options)

    def links(self):
        from mycel._origins import origins_in_transaction
        with self.base.connect() as connection,read_snapshot(connection):
            return origins_in_transaction(connection,self.settings,'fixture',chunk=self.ref)['chunks'][0]['links']

    def two_origins(self):
        self.justify();self.justify('fixture:@artifact/other.md#FIX-2.1')


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
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.

# Archived complete imports; restore needed names in their original scope, not at this file tail.
