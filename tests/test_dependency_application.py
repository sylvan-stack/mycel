"""Configured proofs for the location-owned guarded dependency executor.

Complete command behavior remains separate; these producers join one checked
publication or explicit caller transaction without spending provider quota.
"""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import capture_repository
from mycel._dependency_application import DependencyApplicationStore, RetainedDependencyResolver
from mycel._errors import MycelError
from mycel._evidence import EvidenceError, PinInputs
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import atomic_transaction, operation_guard
from mycel._reconciliation import AssertedRemoval, ReconciliationError
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class RetainedResolverUnitTests(unittest.TestCase):
    def test_policy_wrappers_reuse_validated_catalog_bytes_and_keep_selection_rules(self):
        from mycel import _resolver
        try:
            from .test_resolver import settings, chunk, file
        except ImportError:
            from test_resolver import settings, chunk, file
        members = tuple(chunk(f'Part{i}', f'Body {i}', number=i + 1) for i in range(100))
        retained = file('guide.md', 'whole file', members=members)
        with patch.object(_resolver, '_exact', wraps=_resolver._exact) as exact:
            catalog = SourceResolver(settings(), (retained,))
            validations = exact.call_count
            self.assertGreaterEqual(validations, len(members))
            for member in members:
                policy = RetainedDependencyResolver(catalog, {})
                ref = f'fixture:@artifact/guide.md#{member.name}'
                self.assertEqual(policy.resolve(ref), catalog.resolve(ref))
                self.assertEqual(policy.resolve('disabled:guide.md').fault, 'disabled_repository')
                self.assertEqual(policy.resolve('fixture:guide.md', purpose='endpoint').fault,
                                 'one_chunk_required')
            self.assertEqual(exact.call_count, validations,
                             'Per-chunk policy must not rehash the complete immutable catalog')
        # Invalid input still fails at the catalog boundary, before any adapter.
        with self.assertRaises(MycelError):
            SourceResolver(settings(), (replace(retained, snapshot_hash='0' * 64),))
        with self.assertRaises(MycelError):
            RetainedDependencyResolver(object(), {})


class DependencyApplicationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = fixtures.LocatedReconciliationStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def prepare(self, *, declared=True, file_selection=False):
        declaration = 'fixture:@artifact/source.md' + ('' if file_selection else '#Source')
        raw = ('---\nrole: authored\nsources: ["' + declaration + '"]\n---\n') if declared else '---\nrole: authored\n---\n'
        self.fixture.initialize((raw + '# Guide\nPlain body.\n').encode())
        (self.fixture.artifact / 'source.md').write_bytes(b'# Source\nOriginal source.\n')
        self.fixture.commit()

    def guards(self, connection):
        stack = ExitStack()
        stack.enter_context(checked_store(connection))
        for repository in sorted(self.fixture.settings.values['repos']):
            stack.enter_context(operation_guard(connection, repository, 'pass'))
        return stack

    def publish(self, connection):
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.fixture.settings,
                capture_repository(self.fixture.settings, 'fixture'),
                batch_handoff=LocatedDependencyProducer(self.fixture.settings,
                    captured_at='2026-10-09T10:00:00Z', settings_home=self.fixture.base))

    def guide(self, connection):
        return connection.execute("SELECT l.id,cl.chunk_version FROM public.mycel_file_locations l "
            "JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id "
            "JOIN public.mycel_locations cl ON cl.file_location=l.id WHERE l.kind='disk' "
            "AND l.metadata->>'path'='guide.md'").fetchone()

    def reread(self, connection, expected):
        settings = load_settings(path=self.fixture.settings.file, home=self.fixture.base)
        scope = expected.guards['dependencyApplication']
        base = SourceResolver.from_transaction(connection, settings, kind=scope['kind'], location=scope['locationKey'])
        catalog = RetainedDependencyResolver(base, expected.catalog.anchors, expected.catalog.syntax_faults)
        endpoint = catalog.resolve(expected.dependant.place.address, purpose='endpoint')
        resolution = catalog.resolve(expected.resolution.declaration)
        if endpoint.state != 'resolved':
            raise EvidenceError('changed_since_ingest')
        manifest = capture_repository(settings, 'fixture')
        places = [item for item in manifest.locations if item.id.kind == scope['kind']]
        indexed_files = (endpoint.selection.file,) + ((resolution.selection.file,) if resolution.selection else ())
        for file in indexed_files:
            current = [item for place in places for item in place.files if any(
                alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
            if len(current) != 1 or current[0].source != file.source:
                raise EvidenceError('changed_since_ingest')
        values = dict(settings=settings, dependant=endpoint.selection.members[0], dependant_file=endpoint.selection.file,
                      resolution=resolution, catalog=catalog)
        if isinstance(expected, PinInputs):
            if resolution.state != 'resolved':
                raise EvidenceError('changed_since_ingest')
            values['selection'] = resolution.selection
        return replace(expected, **values)

    def apply(self, connection, **kwargs):
        location, version = self.guide(connection)
        return DependencyApplicationStore(connection).apply_in_transaction(self.fixture.settings, str(location), version,
            captured_at='2026-10-09T10:30:00Z', reread=lambda expected: self.reread(connection, expected), **kwargs)

    def rows(self, connection):
        return connection.execute('SELECT id,dependant_version,declaration,source_place,state,baseline_owner '
            'FROM public.mycel_dependencies ORDER BY id').fetchall()

    def test_aliases_and_duplicates_keep_one_location_baseline_and_removal_releases_only_disk(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            before = self.rows(connection)
            path = self.fixture.artifact / 'guide.md'
            path.write_bytes(path.read_bytes().replace(b'sources: ["fixture:@artifact/source.md#Source"]',
                b'sources: ["fixture:source.md#Source", "fixture:@artifact/source.md#Source"]'))
            result = self.publish(connection)
            after = self.rows(connection)
            self.assertEqual([(row[0], row[5]) for row in before], [(row[0], row[5]) for row in after])
            self.assertEqual(result.counts['pinsCaptured'], 0)
            disk = next(row for row in after if row[4]['declarationLocation']['kind'] == 'disk')
            self.assertEqual(len(disk[4]['occurrences']), 2)
            self.assertEqual(disk[2], 'fixture:@artifact/source.md#Source')
            path.write_bytes(b'---\nrole: authored\n---\n# Guide\nPlain body.\n')
            released = self.publish(connection)
            surviving = self.rows(connection)
            self.assertEqual(len(surviving), 1)
            self.assertEqual(surviving[0][4]['declarationLocation']['kind'], 'branch')
            self.assertEqual(released.counts['dependenciesReleased'], 1)

    def test_assertions_match_alias_and_remove_only_the_requested_selection(self):
        self.prepare(declared=False)
        with self.fixture.connect() as connection:
            self.publish(connection)
            with self.guards(connection), atomic_transaction(connection):
                added = self.apply(connection, assertions=('fixture:@artifact/source.md#Source',
                                                          'fixture:@artifact/source.md'))
                self.assertEqual(added.captured, 2)
            before = self.rows(connection)
            with self.guards(connection), atomic_transaction(connection):
                observed = self.apply(connection, assertions=('fixture:source.md#Source',))
                self.assertEqual(observed.captured, 0)
                self.assertEqual(len(self.rows(connection)), 2)
                removed = self.apply(connection, remove_assertions=(AssertedRemoval(
                    SourceAddress('fixture', 'artifact', 'source.md', 'Source'), 'chunk'),))
                self.assertEqual(removed.released, 1)
            remaining = self.rows(connection)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0][3], 'fixture:@artifact/source.md')
            self.assertIn((remaining[0][0], remaining[0][5]), {(row[0], row[5]) for row in before})

    def test_file_selection_absent_on_disk_is_away_while_branch_file_survives(self):
        self.prepare(file_selection=True)
        with self.fixture.connect() as connection:
            self.publish(connection)
            before = self.rows(connection)
            (self.fixture.artifact / 'source.md').unlink()
            self.publish(connection)
            with self.guards(connection), atomic_transaction(connection):
                reply = self.apply(connection)
                self.assertEqual(reply.plan.decisions[0].source_state, 'away')
                self.assertEqual(reply.plan.decisions[0].reasons, ('source_removed',))
                self.assertEqual(reply.plan.role, 'derived')
            self.assertEqual([(row[0], row[5]) for row in self.rows(connection)],
                             [(row[0], row[5]) for row in before])

    def test_incomplete_baseline_owner_graph_refuses_without_fresh_capture(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            disk = next(row for row in self.rows(connection) if row[4]['declarationLocation']['kind'] == 'disk')
            with self.guards(connection), atomic_transaction(connection):
                connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s AND ordinal=0', (disk[5],))
            before = self.rows(connection)
            with self.assertRaises(EvidenceError) as error, self.guards(connection), atomic_transaction(connection):
                self.apply(connection, mode='confirm')
            self.assertEqual(error.exception.status, 'baseline_missing')
            self.assertEqual(self.rows(connection), before)

    def test_generated_authority_is_included_in_the_complete_cycle_check(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            location, guide_version = self.guide(connection)
            source_version = SourceResolver.from_store(connection, self.fixture.settings).resolve(
                'fixture:@artifact/source.md#Source').selection.members[0].chunk.version
            generated = uuid4()
            with self.guards(connection), atomic_transaction(connection):
                connection.execute("INSERT INTO public.mycel_dependencies VALUES (%s,'fixture',%s,'generated',"
                    "'fixture:@artifact/guide.md#Guide','generated','{}',NULL)", (generated, source_version))
                connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (generated, guide_version))
            before = self.rows(connection)
            with self.assertRaises(ReconciliationError) as error, self.guards(connection), atomic_transaction(connection):
                self.apply(connection)
            self.assertEqual(error.exception.status, 'dependency_cycle')
            self.assertEqual(error.exception.cycle[0], error.exception.cycle[-1])
            self.assertEqual(self.rows(connection), before)

    def test_index_generation_edges_cannot_hide_a_cycle_from_an_unrelated_document(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            source_version = SourceResolver.from_store(connection, self.fixture.settings).resolve(
                'fixture:@artifact/source.md#Source').selection.members[0].chunk.version
            index_id, generated_a, generated_b = uuid4(), uuid4(), uuid4()
            raw = b'# Summary\nExact generated bytes.\n'
            with self.guards(connection), atomic_transaction(connection):
                connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,'fixture',NULL,'index','{}')", (index_id,))
                version = connection.execute('INSERT INTO public.mycel_chunk_versions '
                    '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                    (index_id, sha256(raw).hexdigest(), raw, raw.decode(), Jsonb({}),
                     Jsonb({'name': 'Summary', 'kind': 'index', 'path': 'summaries'}))).fetchone()[0]
                connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,'index','summaries','{}')",
                                   (uuid4(), version))
                for dependency, dependant, source in ((generated_a, version, source_version),
                                                       (generated_b, source_version, version)):
                    connection.execute("INSERT INTO public.mycel_dependencies VALUES (%s,'fixture',%s,'generated','',"
                        "'generated','{}',NULL)", (dependency, dependant))
                    connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (dependency, source))
            before = self.rows(connection)
            with self.assertRaises(ReconciliationError) as error, self.guards(connection), atomic_transaction(connection):
                self.apply(connection)
            self.assertEqual(error.exception.status, 'dependency_cycle')
            self.assertIn(str(index_id), error.exception.cycle)
            self.assertEqual(self.rows(connection), before)

    def test_incomplete_and_expired_batch_tokens_cannot_hide_pending_authority(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            location, version = self.guide(connection)
            source = connection.execute("SELECT l.id,cl.chunk_version FROM public.mycel_file_locations l "
                "JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id "
                "JOIN public.mycel_locations cl ON cl.file_location=l.id WHERE l.kind='disk' "
                "AND l.metadata->>'path'='source.md'").fetchone()
            scopes = ((str(location), version), (str(source[0]), source[1]))
            before = self.rows(connection)
            with self.assertRaises(MycelError), self.guards(connection), atomic_transaction(connection):
                store = DependencyApplicationStore(connection)
                with store.batch_in_transaction(self.fixture.settings, scopes=scopes) as batch:
                    self.apply(connection, batch=batch)
            self.assertEqual(self.rows(connection), before)
            with self.guards(connection), atomic_transaction(connection):
                store = DependencyApplicationStore(connection)
                with store.batch_in_transaction(self.fixture.settings, scopes=((str(location), version),)) as batch:
                    self.apply(connection, batch=batch)
                    with self.assertRaises(MycelError):
                        self.apply(connection, batch=batch)
                with self.assertRaises(MycelError):
                    self.apply(connection, batch=batch)
            self.assertEqual(self.rows(connection), before)

    def test_no_transaction_no_guards_and_foreign_version_refuse_before_mutation(self):
        self.prepare()
        with self.fixture.connect() as connection:
            self.publish(connection)
            before = self.rows(connection)
            with self.assertRaises(MycelError):
                self.apply(connection)
            with self.assertRaises(MycelError), atomic_transaction(connection):
                self.apply(connection)
            source = SourceResolver.from_store(connection, self.fixture.settings).resolve(
                'fixture:@artifact/source.md#Source').selection.members[0].chunk.version
            with self.assertRaises(MycelError), self.guards(connection), atomic_transaction(connection):
                self.apply(connection, pin_version=source)
            self.assertEqual(self.rows(connection), before)
