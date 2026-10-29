# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Actual init producer with an immutable fixture Build and native transactions."""
from pathlib import Path
import tempfile

from mycel import _activity as activity, _store as store
from mycel._build_identity import current_build
from mycel._errors import MycelError
from mycel._locks import bootstrap_invocation_guard, invocation_is_live


import io
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings


class BuildIdentityTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class InitActivityStoreTests(unittest.TestCase):
    check_kind = "store"

    initialize_store = staticmethod(lambda backend, settings_file: None)

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    @contextmanager
    def package(self, raw='{"schemaVersion":1,"build":26}'):
        root = self.store_fixture.root / 'fictional-package'
        (root / 'data').mkdir(parents=True, exist_ok=True)
        (root / 'data/build-identity.json').write_text(raw)
        with patch('mycel._build_identity.files', return_value=root):
            yield

    def invoke(self, dimensions=None):
        snapshot = load_settings(path=self.store_fixture.settings_file)
        if dimensions is not None:
            from mycel._settings import SettingsSnapshot, _freeze
            values = {
                **snapshot.values, 'embedding': {**snapshot.values['embedding'], 'dimensions': dimensions}}
            snapshot = SettingsSnapshot(snapshot.file, _freeze(values), snapshot.exists, snapshot.readable)
        out = io.StringIO()
        with patch('mycel._cli.load_settings', return_value=snapshot):
            status = run(['init'], stdout=out, stderr=io.StringIO())
        return status, json.loads(out.getvalue())

    def entries(self, connection):
        return connection.execute('SELECT id FROM public.mycel_activity ORDER BY id').fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
