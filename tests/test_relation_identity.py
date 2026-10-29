# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured relation identity, located pins, exact faults and eligibility."""

from mycel._capture import LocationId
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._locks import atomic_transaction
from mycel._relate import RelateStore
from mycel._relations import RelationApplicationStore
try:
    from .test_refs import invoke, store_state
except ImportError:
    from test_refs import invoke, store_state

import json
import unittest

from mycel._evidence import EvidenceStore
from mycel._settings import load_settings

try:
    from . import test_derive as fixtures
    pass
except ImportError:
    import test_derive as fixtures


class RelationIdentityStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.DeriveStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.guide = self.base.artifact / 'guide.md'

    def declared(self, refs):
        original = self.guide.read_bytes()
        self.guide.write_bytes(original.replace(b'Original dependant.',
            b'Original dependant.\n<!-- related:\n' + refs + b'\n-->'))
        self.base.commit()
        return self.guide.read_bytes()

    def current(self, connection):
        rows = connection.execute("""SELECT r.id,r.left_version,r.right_place,r.state,r.baseline_owner,
            e.manifest_hash,fl.kind,fl.location,r.xmin::text
            FROM public.mycel_relations r
            JOIN public.mycel_file_locations fl ON fl.id::text=r.state->'declarationLocation'->>'file'
            JOIN public.mycel_locations l ON l.file_location=fl.id AND l.chunk_version=r.left_version
            JOIN public.mycel_evidence_references e ON e.owner=r.baseline_owner AND e.ordinal=0
            WHERE r.repository='fixture' ORDER BY fl.kind,fl.location,r.id""").fetchall()
        return {(row[6], row[7], row[3]['ownership'], row[2]): row for row in rows}

    def disk(self, connection):
        return {key[2:]: row for key, row in self.current(connection).items() if key[0] == 'disk'}

    def baselines(self, connection, rows):
        return {key: EvidenceStore(connection).read_baseline('fixture', row[5]) for key, row in rows.items()}

    def foreign(self, *, enabled):
        path = self.base.base / 'foreign'
        path.mkdir(exist_ok=True)
        (path / 'source.md').write_bytes(b'# Source\nForeign source.\n')
        text = self.base.config.read_text()
        text += '\n[repos.foreign]\nenabled=' + str(enabled).lower() + '\nartifact_root=' + json.dumps(str(path)) + '\n'
        self.base.config.write_text(text)
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        return path


# Archived complete imports; restore needed names in their original scope, not at this file tail.
