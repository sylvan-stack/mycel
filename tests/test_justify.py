# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""UUID compatibility and atomic stated Origin Links over disposable stores."""
import os

from mycel._errors import MycelError

import json
import unittest
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

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
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class UriMutationStoreTests(unittest.TestCase):
    check_kind = "store"

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


class JustifyInputTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class JustifyStoreTests(unittest.TestCase):
    check_kind = "store"

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


class ClonePolicyStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest
    invoke=UriMutationStoreTests.invoke


class JustifySelectionStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest


class CloneAbsenceStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest


class CloneEntityMoveStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest
    invoke=UriMutationStoreTests.invoke


class CloneGraphStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest


class JustifySharedChunkStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=UriMutationStoreTests.setUp
    ingest=UriMutationStoreTests.ingest


# Archived complete imports; restore needed names in their original scope, not at this file tail.
