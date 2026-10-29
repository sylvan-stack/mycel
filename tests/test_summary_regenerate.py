# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured-store stale repair proofs with deterministic local services."""

import unittest
from unittest.mock import patch

from mycel._cli import Invocation
from mycel._summary_regenerate import regenerate_summaries
from mycel._summary_store import StoreSummaries
from mycel._summary_writer import WriterResult

try:
    from . import test_summary_build as builds
except ImportError:
    import test_summary_build as builds


class SequentialWriter:
    def __init__(self, *, fail_at=None, interrupt_at=None, callback=None):
        self.requests, self.fail_at, self.interrupt_at, self.callback = [], fail_at, interrupt_at, callback

    def write_many(self, requests):
        self.requests.extend(requests)
        number = len(self.requests)
        if self.callback:
            self.callback(number, requests)
        if number == self.interrupt_at:
            raise KeyboardInterrupt
        if number == self.fail_at:
            return (WriterResult(None, "nonzero_exit", 2),)
        return (WriterResult(f" Whole regenerated response {number}.\r\n\0end. ".encode(), None, 1),)


class SummaryRegenerationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = builds.SummaryBuildStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def regenerate(self, connection, *, writer=None, client=None, before_publish=None, tokenizer=None):
        return regenerate_summaries(Invocation("summaries", repositories=("fixture",), arguments=("regenerate",),
            settings=self.base.settings), _store=(connection, None), _writer=writer or SequentialWriter(),
            _client=client or builds.LocalEmbedding(), _tokenizer=tokenizer or self.fixture.tokenizer,
            _before_publish=before_publish)

    def prepare(self, connection, *, tree=False, independent=False):
        self.fixture.prepare(connection, count=24 if tree else 12)
        if tree:
            groupings = 0

            def group(nodes):
                nonlocal groupings
                groupings += 1
                return (tuple(nodes),) if groupings == 2 else tuple(tuple(nodes[i:i+2]) for i in range(0, len(nodes), 2))

            with patch("mycel._summary_build.group_summary_nodes", side_effect=group):
                self.fixture.build(connection)
        elif independent:
            with patch("mycel._summary_build.group_summary_nodes",
                    side_effect=lambda nodes: tuple(tuple(nodes[i:i+4]) for i in range(0, len(nodes), 4))):
                self.fixture.build(connection)
        else:
            self.fixture.build(connection)

    def snapshot(self, connection):
        with StoreSummaries(connection, self.base.settings).snapshot(("fixture",)) as snapshot:
            return snapshot._summaries, snapshot.status(), snapshot.regeneration_plan()

    def current(self, connection):
        return {str(row[0]): row for row in connection.execute("SELECT c.id,v.id,v.source_bytes,l.location,g.state "
            "FROM public.mycel_chunks c JOIN public.mycel_generated_state g ON g.chunk_id=c.id "
            "JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id "
            "WHERE c.kind='summary' AND l.kind='index' ORDER BY l.location").fetchall()}

    def change(self, connection, summary, *, text="Changed current section.\n"):
        pin = next(pin for pin in summary.state.members if pin.place.root == "artifact")
        path = self.base.artifact / pin.place.path
        source = path.read_text()
        path.write_text(source.splitlines()[0] + "\n" + text)
        self.base.apply(connection)
        return path

    def generated(self, connection, version):
        return connection.execute("SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,"
            "d.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d "
            "JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 "
            "WHERE d.kind='generated' AND d.dependant_version=%s ORDER BY d.id", (version,)).fetchall()

    def no_leases(self, connection):
        self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL").fetchone(), (0,))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
