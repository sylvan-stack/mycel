"""Disposable-store proofs for path-scoped undocumented code and freshness."""

from io import StringIO
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

from mycel._capture import _Capture
from mycel._cli import parse, run
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._freshness import Deadline
from mycel._undocumented import handle_undocumented, normalize_paths, undocumented_from_store

try:
    from . import test_document_links as link_fixtures
    from . import test_freshness_store as freshness_fixtures
    from . import test_overview_cli as scope_fixtures
except ImportError:
    import test_document_links as link_fixtures
    import test_freshness_store as freshness_fixtures
    import test_overview_cli as scope_fixtures


class UndocumentedUnitTests(unittest.TestCase):
    @proves('MYC-0.6', kind='unit')
    def test_cli_keeps_repeated_paths_and_refuses_invalid_or_multiple_repository_selectors(self):
        invocation = parse(['undocumented', '--repo', 'fixture', '--path', 'src',
                            '--path', 'scripts/build.py', '--no-fresh'])
        self.assertEqual(invocation.repositories, ('fixture',))
        self.assertEqual(invocation.arguments,
                         ('--path', 'src', '--path', 'scripts/build.py', '--no-fresh'))
        for arguments in (['undocumented', '--repo', 'a', '--repo', 'b'],
                          ['undocumented', '--path'], ['undocumented', 'needle'],
                          ['undocumented', '--path', '../outside'],
                          ['undocumented', '--path', '/absolute']):
            with self.subTest(arguments=arguments), self.assertRaises(MycelError) as error:
                parse(arguments)
            self.assertEqual(error.exception.code, 'invalid_input')
        self.assertEqual(normalize_paths(('src/./net/', 'src/net', 'scripts/../tests', '.')),
                         ('src/net', 'tests', '.'))

    @proves('MYC-0.6', kind='unit')
    def test_unknown_disabled_and_organization_scopes_refuse_before_opening_the_store(self):
        fixture = scope_fixtures.OverviewCliTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch('mycel._cli.invocation_store') as store:
            for name, code in (('unknown', 'unknown_repository'), ('disabled', 'refused'),
                               ('team', 'invalid_input')):
                invocation = replace(parse(['undocumented', '--repo', name, '--no-fresh']),
                                     settings=fixture.settings)
                with self.subTest(repository=name), self.assertRaises(MycelError) as error:
                    handle_undocumented(invocation)
                self.assertEqual(error.exception.code, code)
            store.assert_not_called()


class UndocumentedStoreTests(unittest.TestCase):
    def setUp(self):
        self.links = link_fixtures.DocumentLinksStoreTests()
        self.links.store_fixture = self.store_fixture
        self.links.setUp()
        self.base, self.settings = self.links.base, self.links.settings

    def report(self, connection, **options):
        options.setdefault('no_fresh', True)
        return undocumented_from_store(connection, self.settings, ('fixture',),
                                       deadline=Deadline.after(30), **options)

    @proves('MYC-2.27', kind='store')
    def test_paths_form_a_union_at_component_boundaries_and_results_sort_by_root_path_name(self):
        with self.base.connection() as connection:
            self.links.seed(connection, path='src/a.py', root='artifact', name='ArtifactCode', source='artifact\n')
            self.links.seed(connection, path='src/a.py', name='CheckoutCode', source='checkout\n')
            self.links.reads.seed(connection, 'src/multiple.py', 'alpha\nzulu\n',
                (('Zulu', 'function', 'zulu\n', {}), ('Alpha', 'function', 'alpha\n', {})))
            self.links.seed(connection, path='scripts/build.py', name='Build', source='build\n')
            self.links.seed(connection, path='srcish/outside.py', name='Outside', source='outside\n')
            self.links.seed(connection, path='src/described.py', name='Described', source='governed\n')
            document = self.links.seed(connection, root='artifact', path='guide.md', name='Guide',
                                       kind='document', source='# Guide\nDocument.\n')
            self.links.cite(connection, document, 'fixture:@code/src/described.py#Described')
            self.links.seed(connection, path='src/branch.py', name='Branch', source='branch\n', location_kind='branch')
            self.links.seed(connection, path='src/stash.py', name='Stash', source='stash\n', location_kind='stash')
            self.links.seed(connection, path='src/disabled.py', repository='disabled', source='disabled\n')
            self.links.seed(connection, path='src/other.py', repository='other', source='other\n')
            before = self.base.contents(connection)
            with patch('mycel._retrieval_store.load_tokenizer', side_effect=AssertionError('tokenizer')), \
                    patch('mycel._embed.embed', side_effect=AssertionError('embedding')):
                reply = self.report(connection, paths=('src', 'scripts/build.py'))
                exact = self.report(connection, paths=('src/a.py',))
                all_code = self.report(connection)
            self.assertEqual(reply['repository'], 'fixture')
            self.assertEqual(reply['paths'], ['src', 'scripts/build.py'])
            self.assertEqual([row['address'] for row in reply['chunks']], [
                'fixture:@artifact/src/a.py#ArtifactCode', 'fixture:@code/scripts/build.py#Build',
                'fixture:@code/src/a.py#CheckoutCode', 'fixture:@code/src/multiple.py#Alpha',
                'fixture:@code/src/multiple.py#Zulu'])
            self.assertEqual([row['root'] for row in exact['chunks']], ['artifact', 'code'])
            self.assertEqual(all_code['paths'], [])
            self.assertEqual(len(all_code['chunks']), len(reply['chunks']) + 1)
            self.assertFalse(reply['freshness']['checked'])
            self.assertFalse(reply['freshness']['finished'])
            self.assertTrue(all(row['state'] == 'pending' and row['ingested'] == 0
                                for row in reply['freshness']['repositories']))
            self.assertEqual(self.base.contents(connection), before)
            self.assertNotIn('fixture:@code/src/described.py#Described',
                             {row['address'] for row in reply['chunks']})

    @proves('MYC-2.27', kind='store')
    def test_removing_the_last_dependency_exposes_code_without_creating_another_link(self):
        with self.base.connection() as connection:
            code = self.links.seed(connection, path='work.py', name='Work', source='work\n')
            document = self.links.seed(connection, root='artifact', path='guide.md', name='Guide',
                                       kind='document', source='# Guide\nDocument.\n')
            inbound = self.links.cite(connection, document, 'fixture:@code/work.py#Work')
            outbound = self.links.cite(connection, code, 'fixture:@artifact/guide.md#Guide', kind='asserted')
            before = self.base.contents(connection)
            self.assertEqual(self.report(connection)['chunks'], [])
            self.assertEqual(self.base.contents(connection), before)
            connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (inbound,))
            self.assertEqual(self.report(connection)['chunks'], [])
            connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (outbound,))
            before = self.base.contents(connection)
            self.assertEqual([row['address'] for row in self.report(connection)['chunks']],
                             ['fixture:@code/work.py#Work'])
            self.assertEqual(self.base.contents(connection), before)


class UndocumentedFreshnessStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = freshness_fixtures.FreshnessStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    @proves('MYC-2.27', kind='store')
    def test_new_document_link_is_seen_only_after_default_freshness_ingests_it(self):
        with self.fixture.base.connect() as connection:
            self.fixture.prepare(connection)
            expected = ['fixture:@code/driver.py#drive']
            before = self.fixture.contents(connection)
            (self.fixture.folders['fixture'] / 'added-guide.md').write_bytes(
                self.fixture.document('New governing section', 'fixture:@code/driver.py#drive'))
            with patch('mycel._embed.embed', side_effect=AssertionError('embedding')):
                unchecked = undocumented_from_store(connection, self.fixture.settings, ('fixture',),
                    deadline=Deadline.after(30), no_fresh=True, build=1)
                self.assertEqual([row['address'] for row in unchecked['chunks']], expected)
                self.assertEqual(self.fixture.contents(connection), before)
                fresh = undocumented_from_store(connection, self.fixture.settings, ('fixture',),
                    deadline=Deadline.after(30), build=1)
            self.assertEqual(fresh['chunks'], [])
            self.assertTrue(fresh['freshness']['checked'])
            self.assertTrue(fresh['freshness']['finished'], fresh)
            self.assertTrue(any(row['repository'] == 'fixture' and row['state'] == 'done'
                                and row['ingested'] > 0 for row in fresh['freshness']['repositories']))
            # Ordinary ingest creates the declared edge, never an assertion.
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies "
                "WHERE kind='asserted'").fetchone(), (0,))

    @proves('MYC-2.27', kind='store')
    def test_default_freshness_ingests_new_code_and_removed_refs_while_no_fresh_preserves_old_snapshot(self):
        guide = self.fixture.folders['fixture'] / 'code.md'
        guide.write_bytes(self.fixture.document('Implementation', 'fixture:@code/driver.py#drive'))
        with self.fixture.base.connect() as connection:
            self.fixture.prepare(connection)
            before = self.fixture.contents(connection)
            initial = undocumented_from_store(connection, self.fixture.settings, ('fixture',),
                deadline=Deadline.after(30), no_fresh=True, build=1)
            self.assertEqual(initial['chunks'], [])
            self.assertEqual(self.fixture.contents(connection), before)
            guide.write_bytes(b'# Implementation\nThe reference was removed.\n')
            folder = self.fixture.base.code / 'src'
            folder.mkdir()
            (folder / 'added.py').write_bytes(b'def added():\n    return 3\n')
            captures = []
            actual_capture = _Capture.capture

            def capture(value):
                captures.append(value.repository.name)
                return actual_capture(value)

            with patch.object(_Capture, 'capture', capture), \
                    patch('mycel._embed.embed', side_effect=AssertionError('embedding')):
                unchecked = undocumented_from_store(connection, self.fixture.settings, ('fixture',),
                    deadline=Deadline.after(30), no_fresh=True, build=1)
                self.assertEqual(unchecked['chunks'], [])
                self.assertEqual(captures, [])
                self.assertEqual(self.fixture.contents(connection), before)
                fresh = undocumented_from_store(connection, self.fixture.settings, ('fixture',),
                    deadline=Deadline.after(30), build=1)
            self.assertEqual([row['address'] for row in fresh['chunks']],
                             ['fixture:@code/driver.py#drive', 'fixture:@code/src/added.py#added'])
            self.assertTrue(fresh['freshness']['checked'])
            self.assertTrue(fresh['freshness']['finished'], fresh)
            self.assertIn('fixture', captures)
            self.assertNotIn('outside', captures)
            self.assertTrue(any(row['repository'] == 'fixture' and row['state'] == 'done'
                                and row['ingested'] > 0 for row in fresh['freshness']['repositories']))
            # The report does not infer or assert a replacement description.
            version = self.fixture.key(connection, 'fixture:@code/src/added.py#added')[1]
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies '
                'WHERE dependant_version=%s', (version,)).fetchone(), (0,))

    @proves('MYC-2.27', kind='store')
    def test_public_cli_returns_the_same_path_scoped_store_reply(self):
        with self.fixture.base.connect() as connection:
            self.fixture.prepare(connection)
        output, diagnostic = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.fixture.base.config)}), \
                patch('mycel._build_identity.current_build', return_value=1):
            status = run(['undocumented', '--repo', 'fixture', '--path', 'driver.py', '--no-fresh'],
                         stdout=output, stderr=diagnostic)
        self.assertEqual(status, 0, output.getvalue())
        self.assertEqual(diagnostic.getvalue(), '')
        reply = json.loads(output.getvalue())
        self.assertEqual(reply['repository'], 'fixture')
        self.assertEqual(reply['paths'], ['driver.py'])
        self.assertEqual([row['address'] for row in reply['chunks']], ['fixture:@code/driver.py#drive'])
        self.assertFalse(reply['freshness']['checked'])
