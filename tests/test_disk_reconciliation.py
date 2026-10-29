# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured disposable-store proofs for the capture/identity handoff."""
from dataclasses import replace
import shutil
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._disk_reconciliation import DiskCaptureStore, GitFileMove
from mycel._errors import MycelError

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import capture_repository
from mycel._coverage import require_check_database
from mycel._disk_reconciliation import DiskCaptureStore
from mycel._resolver import SourceResolver
from mycel._settings import load_settings


class DiskReconciliationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('This acceptance check requires a genuine configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_disk_identity_')
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

    def apply(self, connection, settings=None, **kwargs):
        selected = settings or self.settings
        return DiskCaptureStore(connection).apply(selected, capture_repository(selected, 'fixture'), **kwargs)

    def disk(self, connection, ref='fixture:@artifact/guide.md#Guide', settings=None):
        return SourceResolver.from_store(connection, settings or self.settings).resolve(ref).selection

    def state(self, connection):
        tables = ('mycel_files', 'mycel_file_aliases', 'mycel_file_versions', 'mycel_file_locations',
                  'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t ORDER BY to_jsonb(t)::text').fetchall()
                for table in tables}

    def retain_branch(self, connection, file, *, metadata=None):
        location = uuid4()
        connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
            (location, file.binding.version, 'branch', 'retained-main', Jsonb(metadata or {})))
        for identifier, version in file.chunk_versions:
            connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                (uuid4(), version, location, 'branch', 'retained-main', Jsonb({})))
        return location


    def git(self, *arguments):
        result = subprocess.run(['/usr/bin/git', *arguments], cwd=self.code, check=True, capture_output=True,
            timeout=10, env={**os.environ, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                'GIT_TERMINAL_PROMPT': '0'})
        return result.stdout.decode().strip()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
