"""Configured store proofs of generated-target faults and mutation refusal."""
from contextlib import ExitStack
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from mycel._cli import run
from mycel._derive import DeriveStore
from mycel._errors import MycelError
from mycel._relate import RelateStore
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._store import TABLES

try:
    from . import test_summary_build as builds
except ImportError:
    import test_summary_build as builds


class SummaryTargetFaultStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = builds.SummaryBuildStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def invoke(self, command, *arguments):
        output, diagnostics = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run([command, *arguments], stdout=output, stderr=diagnostics)
        self.assertEqual(diagnostics.getvalue(), '')
        return status, json.loads(output.getvalue())

    def state(self, connection):
        return {table.name: connection.execute(
            f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t ORDER BY to_jsonb(t)::text'
        ).fetchall() for table in TABLES}

    def disk_refs(self):
        status, reply = self.invoke('refs', '--repo', 'fixture', '--unresolved')
        self.assertEqual(status, 0, reply)
        return [row for row in reply['repositories'][0]['result']['refs']
                if row['location']['kind'] == 'disk']

    def ingest(self, *options):
        status, reply = self.invoke('ingest', '--repo', 'fixture', *options)
        self.assertEqual(status, 0, reply)
        return reply

    def prohibit_generation(self, stack):
        for target in ('mycel._summary_writer.SummaryWriter', 'mycel._embed.VoyageClient',
                       'mycel._credentials.Credentials.require_embedding_key',
                       'mycel._credentials.Credentials.jev_key'):
            stack.enter_context(patch(target, side_effect=AssertionError('fault operation called a provider')))

    def test_real_built_summary_source_and_related_faults_keep_occurrences_without_generated_edges(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            result = self.fixture.build(connection)
            self.assertEqual(result.status, 0, result.value)
            summaries = self.fixture.summaries(connection)
            self.assertEqual(len(summaries), 1)
            generated = SourceResolver.from_store(connection, self.base.settings).index
            place = next(place for place, chunk in generated if chunk.kind == 'summary')
            legacy = f'fixture:summaries#{place.name}'
            missing = SourceAddress('fixture', 'index', 'summaries', 'missing').address
            (self.base.artifact / 'guide.md').write_text(
                '---\nsources: ' + json.dumps([place.address, legacy, missing]) +
                '\n---\n# Guide\n<!-- related:\n' + place.address + '\n' + legacy + '\n-->\nBody.\n')
            with ExitStack() as stack:
                self.prohibit_generation(stack)
                self.ingest()
                before = self.state(connection)
                refs = self.disk_refs()
                self.assertEqual(len(refs), 5)
                self.assertEqual({row['fault'] for row in refs}, {'generated_text'})
                self.assertEqual({row['resolutionFault'] for row in refs}, {'generated_text'})
                self.assertEqual([row['parsedRef'] for row in refs].count(place.address), 2)
                self.assertEqual([row['parsedRef'] for row in refs].count(legacy), 2)
                self.assertEqual({row['kind'] for row in refs if 'kind' in row}, {'related'})
                self.assertTrue(all(row['resolvedAddress'] is None for row in refs))
                self.assertTrue(all(row['baselineStatus'] == 'baseline_missing' for row in refs))
                self.assertEqual(self.state(connection), before)
                self.ingest()
                self.assertEqual({row['fault'] for row in self.disk_refs()}, {'generated_text'})
            self.assertEqual(connection.execute(
                "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_dependencies d ON d.id=e.dependency "
                "WHERE d.kind!='generated' AND e.source_version=ANY(%s)",
                ([row[1] for row in summaries],)).fetchall(), [])
            self.assertEqual(connection.execute(
                "SELECT 1 FROM public.mycel_relations WHERE baseline_owner IS NOT NULL").fetchall(), [])
            self.assertEqual(self.fixture.summaries(connection), summaries)

    def test_first_overview_projection_repeat_missing_section_and_recreation_report_generated_text(self):
        file = self.base.code / 'src' / 'work.py'
        file.parent.mkdir()
        file.write_text('def work():\n    return 1\n')
        qualified = 'fixture:@index/overview#src'
        legacy = 'fixture:overview#src'
        missing = 'fixture:@index/overview#missing'
        (self.base.artifact / 'guide.md').write_text(
            '---\nsources: ' + json.dumps([qualified, legacy, missing]) + '\n---\n# Guide\nBody.\n')
        with self.base.connect() as connection, ExitStack() as stack:
            self.prohibit_generation(stack)
            for repeat in range(2):
                self.ingest()
                before = self.state(connection)
                refs = self.disk_refs()
                self.assertEqual({row['parsedRef'] for row in refs}, {qualified, legacy, missing})
                self.assertEqual({row['fault'] for row in refs}, {'generated_text'})
                self.assertEqual(self.state(connection), before)
                self.assertEqual(connection.execute(
                    "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_chunk_versions v ON v.id=e.source_version "
                    "JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.kind='overview'").fetchall(), [])
            # Remove the generated section through a complete pass, then restore
            # it. A later stored retry may change its raw resolution, but never
            # creates a generated Source Ref edge or rewrites the declaration.
            file.unlink()
            self.ingest('--confirm-empty')
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM public.mycel_chunks WHERE kind='overview'").fetchone(), (0,))
            file.write_text('def work():\n    return 2\n')
            self.ingest()
            self.assertEqual({row['fault'] for row in self.disk_refs()}, {'generated_text'})
            self.assertEqual(connection.execute(
                "SELECT 1 FROM public.mycel_edges e JOIN public.mycel_chunk_versions v ON v.id=e.source_version "
                "JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.kind='overview'").fetchall(), [])

    def test_real_built_summary_cannot_be_derive_or_relate_endpoint_or_source_including_legacy_alias(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.assertEqual(self.fixture.build(connection).status, 0)
            catalog = SourceResolver.from_store(connection, self.base.settings)
            place = next(place for place, chunk in catalog.index if chunk.kind == 'summary')
            physical = 'fixture:@artifact/guide.md#Guide'
            for store in (DeriveStore(connection), RelateStore(connection)):
                for generated in (place.address, f'fixture:summaries#{place.name}'):
                    for dependant, source in ((physical, generated), (generated, physical)):
                        for remove in (False, True):
                            with self.subTest(store=type(store).__name__, dependant=dependant,
                                              source=source, remove=remove), ExitStack() as stack:
                                self.prohibit_generation(stack)
                                before = self.state(connection)
                                with self.assertRaises(MycelError) as error:
                                    store.apply(self.base.settings, dependant, source, remove=remove,
                                                settings_home=self.base.base)
                                self.assertEqual(error.exception.code, 'invalid_input')
                                self.assertEqual(self.state(connection), before)

    def test_real_physical_generated_names_keep_root_selection_and_legacy_collision_ambiguity(self):
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            self.assertEqual(self.fixture.build(connection).status, 0)
            catalog = SourceResolver.from_store(connection, self.base.settings)
            place = next(place for place, chunk in catalog.index if chunk.kind == 'summary')
            # The extensionless physical document is stored deliberately by the
            # existing exact parser fixture, independently of scan extensions.
            try:
                from .test_declared_refs import seed_document
            except ImportError:
                from test_declared_refs import seed_document
            seed_document(connection, 'fixture', 'summaries', '# Physical\nBody.\n', root='artifact')
            seed_document(connection, 'fixture', 'summaries', '# Physical\nOther body.\n', root='code')
            catalog = SourceResolver.from_store(connection, self.base.settings)
            ambiguous = catalog.resolve('fixture:summaries#Physical')
            self.assertEqual(ambiguous.fault, 'ambiguous_path')
            self.assertEqual(set(ambiguous.candidates),
                {'fixture:@artifact/summaries', 'fixture:@code/summaries'})
            for root in ('artifact', 'code'):
                physical = catalog.resolve(f'fixture:@{root}/summaries#Physical')
                self.assertEqual(physical.state, 'resolved')
                self.assertEqual(physical.selection.kind, 'chunk')
            read = catalog.resolve(f'fixture:summaries#{place.name}', purpose='read')
            self.assertEqual(read.fault, 'ambiguous_path')
            self.assertIn(place.address, read.candidates)
            self.assertEqual(catalog.resolve(place.address).fault, 'generated_text')
            self.assertEqual(catalog.resolve(place.address, purpose='read').selection.kind, 'index')
            self.assertEqual(catalog.resolve('fixture:overview#not_present').fault, 'missing_file')
