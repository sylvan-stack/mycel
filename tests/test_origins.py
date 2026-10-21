"""Origin Coverage over real captures and a disposable PostgreSQL store."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._source_refs import format_entity_uri
try:
    from . import test_justify as fixtures
except ImportError:
    import test_justify as fixtures


class OriginsInputTests(unittest.TestCase):
    @proves('MYC-0.6')
    def test_report_and_requirement_mark_syntax_is_finite(self):
        from mycel._cli import parse
        for arguments in (('origins','x','y'),('origins','--repo','a','--repo','b'),
                          ('origins','--path','../escape'),('origins','--reason','x'),
                          ('origins','--needs-nothing','x'),('origins','--needs-nothing','x','--reason',' '),
                          ('origins','--needs-nothing','x','--reason','x','--missing'),
                          ('origins','--needs-nothing','x','--reason','x','--clear-needs-nothing','x')):
            with self.subTest(arguments=arguments),self.assertRaises(MycelError):
                parse(arguments)
        self.assertEqual(parse(['origins','--path','src/../lib','--missing','--no-fresh']).arguments,
                         ('--missing','--no-fresh','--path','lib'))


class OriginsStoreTests(unittest.TestCase):
    setUp=fixtures.UriMutationStoreTests.setUp
    ingest=fixtures.UriMutationStoreTests.ingest
    invoke=fixtures.UriMutationStoreTests.invoke

    def report(self,repository='fixture',settings=None,**options):
        from mycel._locks import snapshot_transaction
        from mycel._store import checked_store
        from mycel._origins import origins_in_transaction
        with self.base.connect() as connection,checked_store(connection),snapshot_transaction(connection):
            return origins_in_transaction(connection,settings or self.secondary,repository,**options)

    @proves('MYC-17.11','MYC-17.10',kind='store')
    def test_links_missing_paths_single_chunk_and_readonly_cli_use_the_calling_clone(self):
        from mycel._justify import JustifyStore
        initial=self.report(missing=True)
        self.assertIn(self.ref,[row['chunk'] for row in initial['chunks']])
        with self.base.connect() as connection:
            JustifyStore(connection).apply(self.secondary,self.ref,self.uri,by='owner')
            before=connection.execute("SELECT count(*) FROM public.mycel_activity").fetchone()
        with patch('mycel._capture.capture_repository',side_effect=AssertionError('Stored query captured disk')), \
                patch('mycel._ingest.ingest',side_effect=AssertionError('No-fresh ingested')):
            status,reply=self.invoke('origins','--repo','fixture','--no-fresh')
            self.assertEqual(status,0,reply)
            linked=next(row for row in reply['chunks'] if row['chunk']==self.ref)
            self.assertEqual(linked['links'][0]['method'],'stated')
            self.assertIn(fixtures.REQ,linked['links'][0]['origin'])
            self.assertEqual(self.report(chunk=self.ref)['chunks'],[linked])
            self.assertNotIn(self.ref,[row['chunk'] for row in self.report(missing=True)['chunks']])
            self.assertIn(self.ref,[row['chunk'] for row in self.report(settings=self.primary,missing=True)['chunks']])
            self.assertEqual(self.report(paths=('value.py',))['chunks'],[linked])
            self.assertEqual(self.report(paths=('value',))['chunks'],[])
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity").fetchone(),before)

    @proves('MYC-17.11',kind='store')
    def test_default_runs_one_scoped_ingest_then_one_report_and_empty_list_still_succeeds(self):
        from mycel._ingest import ingest
        with patch('mycel._ingest.ingest',wraps=ingest) as run_ingest:
            status,reply=self.invoke('origins','--repo','fixture','--path','absent')
        self.assertEqual(status,0,reply)
        self.assertEqual(reply['chunks'],[])
        self.assertEqual(run_ingest.call_count,1)
        invocation=run_ingest.call_args.args[0]
        self.assertEqual(invocation.repositories,('fixture',))
        self.assertFalse(invocation.arguments)

    @proves('MYC-17.11','MYC-1.39',kind='store')
    def test_changes_compare_retained_main_versions_without_git_and_keep_other_clone_unchanged(self):
        with patch('mycel._capture.run_git',side_effect=AssertionError('Changes query invoked Git')):
            self.assertEqual(self.report(changes=True)['chunks'],[])
        (self.fixture.clone/'value.py').write_text('def value():\n    return 7\n')
        self.ingest(self.secondary)
        with patch('mycel._capture.run_git',side_effect=AssertionError('Changes query invoked Git')):
            self.assertEqual([row['chunk'] for row in self.report(changes=True)['chunks']],[self.ref])
            self.assertEqual(self.report(settings=self.primary,changes=True)['chunks'],[])
        # An absent retained baseline is a visible input failure, never a
        # fabricated empty comparison against whatever Git currently says.
        with self.base.connect() as connection:
            connection.execute("UPDATE public.mycel_repository_state SET read_locations='[]'::jsonb WHERE repository='fixture'")
        with self.assertRaises(MycelError):
            self.report(changes=True)

    @proves('MYC-17.12',kind='store')
    def test_unresting_and_reasoned_requirement_marks_never_invent_edges_or_proofs(self):
        from mycel._origins import mark_needs_nothing
        from mycel._justify import JustifyStore
        self.assertEqual(len(self.report('origins',unresting=True)['unresting']),2)
        with self.base.connect() as connection:
            JustifyStore(connection).apply(self.secondary,self.ref,self.uri,by='owner')
        report=self.report('origins',unresting=True)
        self.assertEqual([row['origin'] for row in report['unresting']],[self.other])
        with self.base.connect() as connection:
            before=tuple(connection.execute('SELECT count(*) FROM public.'+table).fetchone()[0]
                         for table in ('mycel_dependencies','mycel_edges','mycel_verifications'))
            with self.assertRaises(MycelError):
                mark_needs_nothing(connection,self.secondary,self.other,reason=' ')
            with self.assertRaises(MycelError):
                mark_needs_nothing(connection,self.secondary,self.ref,reason='a code chunk is not a requirement')
        status,reply=self.invoke('origins','--needs-nothing',self.other,'--reason','A constraint checked by its conformance test.')
        self.assertEqual(status,0,reply)
        self.assertTrue(reply['needsNothing']['reason'])
        self.ingest(self.secondary,'origins')
        self.assertEqual(self.report('origins',unresting=True)['unresting'],[])
        with self.base.connect() as connection:
            self.assertEqual(tuple(connection.execute('SELECT count(*) FROM public.'+table).fetchone()[0]
                         for table in ('mycel_dependencies','mycel_edges','mycel_verifications')),before)
        status,reply=self.invoke('origins','--clear-needs-nothing',self.other)
        self.assertEqual(status,0,reply)
        self.assertEqual([row['origin'] for row in self.report('origins',unresting=True)['unresting']],[self.other])
