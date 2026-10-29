# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Partial configured-store proofs for complete located publication.

Collection, dependency application and public command requirements remain open.
"""
from dataclasses import replace
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._capture import LocationId, capture_repository
from mycel._errors import MycelError

import json
import os
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import capture_repository
from mycel._coverage import require_check_database
from mycel._located_reconciliation import LocatedCaptureStore, location_key
from mycel._resolver import SourceResolver
from mycel._settings import load_settings


class LocatedReconciliationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('This partial acceptance check requires a configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_located_identity_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.code = self.base / 'code'
        self.artifact = self.code / 'docs'
        self.artifact.mkdir(parents=True)
        self.config = self.base / 'settings.toml'
        self.settings = self.configure()

    def configure(self, *, code=None, artifact=None):
        self.config.write_text('[store]\naddress=' + json.dumps(
            self.store_fixture.backend.address(self.store_fixture.database)) + '\n[repos.fixture]\nenabled=true\ncode_root=' +
            json.dumps(str(code or self.code)) + '\nartifact_root=' + json.dumps(str(artifact or self.artifact)) + '\n')
        return load_settings(path=self.config, home=self.base)

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def git(self, *arguments, cwd=None):
        result = subprocess.run(['/usr/bin/git', *arguments], cwd=cwd or self.code, check=True, capture_output=True,
            timeout=10, env={**os.environ, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                'GIT_TERMINAL_PROMPT': '0'})
        return result.stdout.decode().strip()

    def commit(self, *, cwd=None):
        self.git('add', '--all', cwd=cwd)
        self.git('commit', '--message', 'Fixture', cwd=cwd)
        return self.git('rev-parse', 'HEAD', cwd=cwd)

    def initialize(self, raw=b'# Guide\nOriginal body.\n'):
        (self.artifact / 'guide.md').write_bytes(raw)
        self.git('init', '--initial-branch=fixture-main')
        return self.commit()

    def apply(self, connection, *, settings=None, **kwargs):
        selected = settings or self.settings
        return LocatedCaptureStore(connection).apply(selected, capture_repository(selected, 'fixture'), **kwargs)

    def resolve(self, connection, ref='fixture:@artifact/guide.md#Guide', *, identifier=None, settings=None):
        options = {} if identifier is None else {'kind': identifier.kind, 'location': location_key(identifier)}
        return SourceResolver.from_store(connection, settings or self.settings, **options).resolve(ref)

    def state(self, connection):
        tables = ('mycel_repository_state', 'mycel_files', 'mycel_file_aliases', 'mycel_file_versions',
                  'mycel_file_locations', 'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations',
                  'mycel_dependencies', 'mycel_evidence_owners', 'mycel_evidence_references', 'mycel_snapshots')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
                for table in tables}

    def own_pin(self, connection, version, label):
        owner, dependency = uuid4(), uuid4()
        raw = label.encode()
        digest = sha256(raw).hexdigest()
        connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s)',
                           ('fixture', digest, raw, Jsonb({})))
        connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
                           (owner, 'fixture', 'baseline', label))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
                           (owner, 'fixture', digest))
        connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (dependency, 'fixture', version, 'fixture:@artifact/source.md#Source',
             'fixture:@artifact/source.md#Source', 'asserted', Jsonb({'label': label}), owner))
        return str(owner), str(dependency)


    def resolve_in_transaction(self, connection, file):
        return bytes(connection.execute('SELECT v.source_bytes FROM public.mycel_chunk_versions v '
            'JOIN public.mycel_locations l ON l.chunk_version=v.id WHERE l.file_location=%s',
            (file.binding.location,)).fetchone()[0])


# Archived complete imports; restore needed names in their original scope, not at this file tail.
