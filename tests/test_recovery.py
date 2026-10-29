# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Origin recovery: real disposable stores and bounded public model stand-ins."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import time

from mycel._classification_payload import (DecisionText, OriginDecisionPayload, ORIGIN_LABELS,
    ReviewerRequest, ReviewCommandIdentity)
from mycel._errors import MycelError
from mycel._evidence import EvidenceError, snapshot
from mycel._jev import JevClient, JevFailure, JevLimits, HTTPResult, JevRequest
from mycel._reviewer import ReviewerFailure, validate_response
from mycel._safeguards import CompletedChild, InvocationPolicy, model_call_allowed

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

from mycel._classification_payload import (
    ORIGIN_LABELS,
    DecisionText,
    OriginDecisionPayload,
)
from mycel._classification_runner import ClassifyDependencies
from mycel._credentials import Credentials
from mycel._evidence import snapshot
from mycel._jev import HTTPResult, JevClient, JevFailure, JevLimits
from mycel._locks import read_snapshot
from mycel._recovery import RecoveryStore, run_recovery
from mycel._safeguards import CompletedChild
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
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RecoveryStoreTests(unittest.TestCase):
    check_kind = "store"

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


    def reviewer_settings(self,unrelated=False):
        adapter=self.base.base/'reviewer'
        adapter.write_text('#!'+sys.executable+'\n'+'''import json,sys
r=json.load(sys.stdin)
p=r['payload']['candidate']['snapshot']['place']['path']
v={k:r[k] for k in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
v.update(judgement='governs',rationale='Fixture contract review.',evidence=r['evidenceLocators'][:1],confidenceScore=.35 if p in ('symbol.md','commit.md') else .95)
print(json.dumps(v))
''');adapter.chmod(0o700)
        if unrelated:adapter.write_text(adapter.read_text().replace("judgement='governs'","judgement='unrelated'"))
        self.base.config.write_text(self.base.config.read_text()+'\n[drifts]\nreview_command='+json.dumps([str(adapter)])+
            '\nreview_provider="fixture"\nreview_model="fixture-review-1"\nreview_revision="fixture-v1"\n')
        return load_settings(path=self.base.config,home=self.base.base)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
