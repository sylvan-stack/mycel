# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured clones share repository identity and retain independent locations."""
import os

from mycel._errors import MycelError
from mycel._scope import RepositoryLocations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mycel._settings import load_settings


class CloneScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.primary = self.base / 'fixture'
        self.clone = self.base / 'blue' / 'fixture'
        self.readonly = self.base / 'readonly' / 'fixture'
        self.documents = self.base / 'documents'
        for path in (self.primary, self.clone, self.readonly, self.documents):
            path.mkdir(parents=True)
            (path / '.git').mkdir()
        self.config = self.base / 'settings.toml'

    def settings(self, *, clones=None, readonly=None):
        lines = ['[store]', 'address="postgresql://fixture@unreachable.invalid/owner"',
                 '[organizations.stack]', 'root='+json.dumps(str(self.base)),
                 '[repos.fixture]', 'enabled=true', 'code_root='+json.dumps(str(self.primary)),
                 'artifact_root='+json.dumps(str(self.documents)),
                 'code_clones='+json.dumps([str(self.clone),str(self.readonly)] if clones is None else clones)]
        if readonly is not None:
            lines.append('readonly_root='+json.dumps(str(readonly)))
        self.config.write_text('\n'.join(lines)+'\n')
        return load_settings(path=self.config, home=self.base)


class CloneStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        try:
            from . import test_located_reconciliation as fixtures
        except ImportError:
            import test_located_reconciliation as fixtures
        self.base=fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture=self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.artifact=self.base.base/'artifacts';self.artifact.mkdir()
        self.source=self.base.code/'value.py'
        self.source.write_text('def value():\n    return 1\n')
        self.base.git('init','--initial-branch=main')
        self.base.commit()
        self.clone=self.base.base/'blue'
        self.base.git('clone','--no-hardlinks',str(self.base.code),str(self.clone),cwd=self.base.base)
        self.base.config.write_text('[store]\naddress='+json.dumps(
            self.store_fixture.backend.address(self.store_fixture.database))+
            '\n[repos.fixture]\nenabled=true\ncode_root='+json.dumps(str(self.base.code))+
            '\nartifact_root='+json.dumps(str(self.artifact))+
            '\ncode_clones='+json.dumps([str(self.clone)])+
            '\nreadonly_root='+json.dumps(str(self.base.code))+'\n')
        settings=load_settings(path=self.base.config,home=self.base.base)
        self.primary=replace(settings,_cwd=self.base.code)
        self.secondary=replace(settings,_cwd=self.clone)
        self.ref='fixture:@code/value.py#value'

    def ingest(self, settings):
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        with patch('mycel._build_identity.current_build',return_value=1):
            result=ingest(Invocation('ingest',repositories=('fixture',),settings=settings))
        self.assertEqual(result.status,0,result.value)
        return result.value

    def member(self, connection, settings):
        from mycel._resolver import SourceResolver
        resolution=SourceResolver.from_store(connection,settings).resolve(self.ref,purpose='endpoint')
        self.assertEqual(resolution.state,'resolved',resolution)
        return resolution.selection.members[0].chunk


# Archived complete imports; restore needed names in their original scope, not at this file tail.
