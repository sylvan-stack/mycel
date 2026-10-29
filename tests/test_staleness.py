# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Offline all-path mechanical reasoning and configured disposable-store proofs."""
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._errors import MycelError
from mycel._source_refs import SourceAddress
from mycel._staleness import StaleEdge, StaleNode, StaleReason, compare_dependency, plan_staleness

import json
import unittest
from contextlib import ExitStack

from mycel._capture import capture_repository
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import operation_guard
from mycel._settings import load_settings
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class StalenessUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class MechanicalStalenessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize(b'# Guide\nRepository guide.\n')
        self.source = self.base.artifact / 'source.md'
        self.source.write_bytes(b'# Source\nOriginal source body.\n')
        self.code = self.base.code / 'worker.py'
        self.code.write_bytes(b'def work():\n    return 1\n')
        self.base.commit()
        self.roots = {}
        for owner in ('left', 'right', 'tail', 'unrelated'):
            root = self.base.base / owner
            root.mkdir()
            self.roots[owner] = root
            self.base.config.write_text(self.base.config.read_text() + '\n[repos.' + owner + ']\nenabled=true\n'
                + 'artifact_root=' + json.dumps(str(root)) + '\n')
        self.write('left', 'Left', ('fixture:@artifact/source.md#Source',))
        self.write('right', 'Right', ('fixture:@artifact/source.md#Source',))
        self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'right:@artifact/answer.md#Right'))
        self.write('unrelated', 'Other', ())
        self.reload()

    def reload(self):
        self.settings = load_settings(path=self.base.config, home=self.base.base)

    def write(self, owner, title, sources, *, metadata='', body='Unchanged claim.'):
        raw = '---\nrole: authored\n' + metadata + 'sources: ' + json.dumps(list(sources)) + '\n---\n'
        (self.roots[owner] / 'answer.md').write_text(raw + '# ' + title + '\n' + body + '\n')

    def guards(self, connection):
        held = ExitStack()
        held.enter_context(checked_store(connection))
        for owner in sorted(self.settings.values['repos']):
            held.enter_context(operation_guard(connection, owner, 'pass'))
        return held

    def publish(self, connection, owner='fixture', *, producer=True, activity=None, reply_counts=None):
        manifest = capture_repository(self.settings, owner)
        handoff = LocatedDependencyProducer(self.settings, captured_at='2026-10-09T21:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest) if producer else None
        with self.guards(connection) if producer else checked_store(connection):
            return LocatedCaptureStore(connection).apply(self.settings, manifest, batch_handoff=handoff,
                activity=activity, reply_counts=reply_counts)

    def prepare(self, connection):
        for owner in ('fixture', 'left', 'right', 'tail', 'unrelated'):
            self.publish(connection, owner)
        self.assertEqual(self.reasons(connection), [])

    def reasons(self, connection, owner=None):
        return connection.execute("""SELECT r.id,r.repository,r.chunk_version,r.dependency,r.reason,xmin::text
            FROM public.mycel_stale_reasons r WHERE (%s::text IS NULL OR r.repository=%s)
            ORDER BY r.repository,(r.reason->>'kind'='upstream_stale'),r.reason::text""", (owner, owner)).fetchall()

    def pins(self, connection):
        return connection.execute('SELECT id,repository,dependant_version,baseline_owner FROM public.mycel_dependencies '
                                  'ORDER BY id').fetchall()

    def unrelated_state(self, connection):
        return {table: connection.execute(f"SELECT to_jsonb(t),xmin::text FROM public.{table} t "
            "WHERE repository='unrelated' ORDER BY to_jsonb(t)::text").fetchall()
            for table in ('mycel_dependencies', 'mycel_chunks', 'mycel_stale_reasons', 'mycel_activity')}


# Archived complete imports; restore needed names in their original scope, not at this file tail.
