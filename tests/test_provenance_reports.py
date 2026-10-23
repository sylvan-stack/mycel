"""Public offline provenance reports over configured disposable PostgreSQL."""

from contextlib import contextmanager, ExitStack
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from mycel._cli import Invocation, run
from mycel._errors import MycelError
from mycel._provenance_reports import (ProvenanceReports, handle_drifts,
                                      handle_stale, handle_status)
from mycel._store import TABLES

try:
    from . import test_drift_lifecycle as fixtures
except ImportError:
    import test_drift_lifecycle as fixtures


HANDLERS = {'drifts': handle_drifts, 'stale': handle_stale, 'status': handle_status}


class ProvenanceReportUnitTests(unittest.TestCase):
    def test_invalid_report_arguments_stop_before_settings_store_and_children(self):
        with patch('mycel._cli.invocation_store') as store, patch('subprocess.Popen') as child:
            for handler, arguments in ((handle_stale, ('extra',)), (handle_status, ('extra',)),
                    (handle_drifts, ('extra',)), (handle_drifts, ('--closed', '--closed')),
                    (handle_drifts, ('--dry-run',))):
                with self.subTest(arguments=arguments), self.assertRaises(MycelError) as failure:
                    handler(Invocation('drifts', arguments=arguments))
                self.assertEqual(failure.exception.code, 'invalid_input')
            store.assert_not_called()
            child.assert_not_called()


class ProvenanceReportStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.helper = fixtures.DriftLifecycleStoreTests()
        self.helper.store_fixture = self.store_fixture
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.base, self.fixture = self.helper.base, self.helper.fixture

    def state(self, connection):
        rows = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}
        sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences WHERE schemaname='public'").fetchall()
        rows['sequences'] = tuple((name, connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone())
                                  for (name,) in sequences)
        return rows

    def no_work(self):
        stack = ExitStack()
        for target in ('mycel._capture.capture_repository', 'mycel._drift_store.DriftStore.reconcile',
                       'mycel._declared_refs.DeclaredRefStore.recheck',
                       'mycel._credentials.Credentials.embedding_key', 'mycel._credentials.Credentials.jev_key',
                       'mycel._locks.allocate_key', 'subprocess.Popen'):
            stack.enter_context(patch(target, side_effect=AssertionError('A report performed work: ' + target)))
        return stack

    def invoke(self, connection, command, *options, repositories=('downstream',)):
        @contextmanager
        def connected(credentials):
            self.assertEqual(credentials.store_target().address, self.base.settings.values['store']['address'])
            yield connection
        stdout, stderr = StringIO(), StringIO()
        arguments = [command, *options]
        for repository in repositories:
            arguments.extend(('--repo', repository))
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                patch('mycel._database.store_connection', connected):
            status = run(arguments, handlers=HANDLERS, stdout=stdout, stderr=stderr)
        self.assertEqual(stderr.getvalue(), '')
        return status, json.loads(stdout.getvalue())

    def test_public_current_closed_reports_count_work_pairs_and_completed_support_without_writes(self):
        with self.base.connect() as connection:
            self.helper.prepare(connection)
            self.helper.change(connection)
            before = self.state(connection)
            with self.no_work():
                status, reply = self.invoke(connection, 'drifts')
            self.assertEqual(status, 0, reply)
            result = reply['repositories'][0]['result']
            self.assertEqual((len(result['drifts']), len(result['drifts'][0]['sources'])), (1, 3))
            self.assertEqual(result['counts']['work']['currentOpen'], 1)
            self.assertEqual(result['counts']['pairs']['currentOpen'], 3)
            self.assertEqual(result['counts']['stages']['pending_jev'], 3)
            self.assertEqual(self.state(connection), before)
            drift = self.helper.one(connection)
            first = self.helper.reason(drift, 1)
            self.helper.record(connection, drift, first, status='pending_debounce')
            self.assertEqual(ProvenanceReports(connection).drifts('downstream')['counts']['stages']['pending_debounce'], 1)
            self.helper.record(connection, drift, first, status='needs_llm_review',
                canonical_input_hash='a' * 64,
                evidence={'jev': {'provider': 'typesafe', 'model': 'jev-1.13.0', 'inputHash': 'a' * 64}})
            self.helper.record(connection, drift, self.helper.reason(drift, 2), status='error',
                               evidence={'reason': 'authentication'})
            self.helper.record(connection, drift, self.helper.reason(drift, 3), judgement='insufficient_evidence')
            before = self.state(connection)
            with self.no_work():
                mixed = ProvenanceReports(connection).drifts('downstream')
            stages = mixed['counts']['stages']
            self.assertEqual((stages['needs_llm_review'], stages['error'], stages['complete']), (1, 1, 1))
            self.assertEqual(mixed['counts']['judgements']['insufficient_evidence'], 1)
            self.assertEqual(mixed['counts']['unresolvedFaults'], 1)
            evidence = self.helper.reason(mixed['drifts'][0], 1)['classification']
            self.assertEqual((evidence['inputHash'], evidence['evidence']['jev']['model']), ('a' * 64, 'jev-1.13.0'))
            self.assertEqual(self.state(connection), before)
            drift = self.helper.one(connection)
            for source in list(drift['sources']):
                drift = self.helper.support(connection, drift, source)
            before = self.state(connection)
            with self.no_work():
                status, opened = self.invoke(connection, 'drifts')
                closed_status, closed = self.invoke(connection, 'drifts', '--closed')
                current_status, current = self.invoke(connection, 'status')
            self.assertEqual((status, closed_status, current_status), (0, 0, 0))
            self.assertEqual(opened['repositories'][0]['result']['drifts'], [])
            report = closed['repositories'][0]['result']
            self.assertEqual((len(report['drifts']), report['drifts'][0]['state']), (1, 'closed'))
            self.assertEqual(report['drifts'][0]['closed']['because'], 'still_supported')
            self.assertEqual(report['counts']['pairs']['currentClosed'], 3)
            self.assertEqual(report['counts']['stages']['complete'], 3)
            self.assertEqual(report['counts']['judgements']['still_supported'], 3)
            self.assertEqual(current['repositories'][0]['result']['drifts'], report['counts'])
            self.assertEqual(self.state(connection), before)

    def test_generated_index_staleness_keeps_separate_regeneration_work_and_canonical_sources(self):
        from mycel._locks import invocation_guard
        helper = fixtures.generated.GeneratedStoreTests()
        helper.fixture, helper.base = self.fixture, self.base
        with self.base.connect() as connection:
            self.helper.prepare(connection)
            with invocation_guard(connection) as invocation:
                capture = helper.capture(connection, self.helper.addresses[0], owner='fixture')
                summary = helper.publish(connection, invocation, helper.lease(connection, invocation, capture))
            self.helper.change(connection, 1)
            before = self.state(connection)
            with self.no_work():
                reports = ProvenanceReports(connection)
                work = reports.drifts('fixture')
                stale = reports.stale('fixture')
                status = reports.status('fixture')
            self.assertEqual(work['drifts'], [])
            regeneration, = work['regeneration']
            self.assertEqual(regeneration['place']['address'], summary.place.address)
            self.assertEqual(work['counts']['regeneration'], 1)
            self.assertEqual(work['counts']['work']['currentOpen'], 0)
            generated, = stale['stale']
            self.assertEqual(generated['chunk']['address'], summary.place.address)
            self.assertEqual(generated['chunk']['root'], 'index')
            self.assertEqual(generated['sources'][0]['address'], self.helper.addresses[0])
            self.assertEqual((status['stale'], status['drifts']['regeneration']), (1, 1))
            self.assertEqual(self.state(connection), before)

    def test_off_disk_work_and_removed_version_history_require_explicit_filters_and_keep_locations(self):
        (self.fixture.downstream / 'keep.md').write_bytes(b'# Keep\nIndependent document.\n')
        self.base.git('init', '--initial-branch=dependant-main', cwd=self.fixture.downstream)
        self.base.commit(cwd=self.fixture.downstream)
        self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
            '[repos.downstream]\nenabled=true\ncode_root=' + json.dumps(str(self.fixture.downstream))))
        self.fixture.reload()
        with self.base.connect() as connection:
            self.helper.prepare(connection)
            self.helper.change(connection, 1)
            original = self.helper.one(connection)
            self.fixture.answer.unlink()
            self.fixture.publish(connection, 'downstream')
            self.helper.sync(connection)
            before = self.state(connection)
            with self.no_work():
                reports = ProvenanceReports(connection)
                self.assertEqual(reports.drifts('downstream')['drifts'], [])
                self.assertEqual(reports.drifts('downstream', closed=True)['drifts'], [])
                all_versions = reports.drifts('downstream', all_versions=True)
                status = reports.status('downstream')
            inactive, = all_versions['drifts']
            self.assertEqual((inactive['id'], inactive['current'], inactive['state']), (original['id'], False, 'open'))
            self.assertTrue(any(location['kind'] == 'branch' for location in inactive['locations']))
            self.assertEqual((all_versions['counts']['work']['inactiveOpen'],
                              all_versions['counts']['pairs']['inactiveOpen'],
                              all_versions['counts']['inactiveVersions']), (1, 1, 1))
            self.assertEqual(status['stale'], 0)
            self.assertEqual(self.state(connection), before)
            self.base.commit(cwd=self.fixture.downstream)
            self.fixture.publish(connection, 'downstream')
            self.helper.sync(connection)
            before = self.state(connection)
            with self.no_work():
                self.assertEqual(reports.drifts('downstream', all_versions=True)['drifts'], [])
                removed, = reports.drifts('downstream', closed=True, all_versions=True)['drifts']
            self.assertEqual((removed['id'], removed['closed']['because']), (original['id'], 'version_removed'))
            self.assertEqual(removed['locations'], [])
            self.assertEqual(self.state(connection), before)

    def test_stale_report_keeps_all_changed_removed_and_upstream_sources_and_classification_evidence(self):
        tail = self.base.base / 'tail'
        tail.mkdir()
        (tail / 'tail.md').write_bytes(b'---\nsources: ["downstream:@artifact/answer.md#Answer", '
            b'"fixture:@artifact/source3.md#Source3"]\n---\n# Tail\nUnchanged tail.\n')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.tail]\nenabled=true\n'
                                    + 'artifact_root=' + json.dumps(str(tail)) + '\n')
        self.fixture.reload()
        with self.base.connect() as connection:
            self.helper.prepare(connection)
            self.fixture.publish(connection, 'tail')
            self.helper.extra[0].unlink()
            self.helper.change(connection, 1, 3)
            drift = self.helper.one(connection)
            self.helper.support(connection, drift, self.helper.reason(drift, 1))
            before = self.state(connection)
            with self.no_work():
                status, reply = self.invoke(connection, 'stale', repositories=('downstream', 'tail'))
            self.assertEqual(status, 0, reply)
            downstream, later = (entry['result'] for entry in reply['repositories'])
            first, = downstream['stale']
            last, = later['stale']
            self.assertEqual((downstream['count'], later['count']), (1, 1))
            self.assertEqual(first['chunk']['address'], 'downstream:@artifact/answer.md#Answer')
            self.assertEqual({reason['kind'] for reason in first['reasons']}, {'source_changed', 'source_removed'})
            self.assertEqual({source['address'] for source in first['sources']}, set(self.helper.addresses))
            classified = next(reason for reason in first['reasons'] if reason['source']['address'] == self.helper.addresses[0])
            self.assertEqual(classified['classification']['judgement'], 'still_supported')
            self.assertEqual(classified['classification']['status'], 'complete')
            self.assertEqual(len(last['reasons']), 4)
            self.assertEqual(last['reasons'][0]['kind'], 'source_changed')
            for reason in last['reasons'][1:]:
                self.assertEqual(reason['kind'], 'upstream_stale')
                self.assertEqual([place['address'] for place in reason['via']], ['downstream:@artifact/answer.md#Answer'])
            self.assertTrue(all(reason['source']['root'] == 'artifact' and reason['source']['path']
                                for reason in first['reasons'] + last['reasons']))
            self.assertEqual(self.state(connection), before)

    def test_repository_status_counts_current_stale_and_every_unresolved_invalid_ref_occurrence(self):
        self.helper.write_answer(*self.helper.addresses, 'fixture:@artifact/missing.md#Missing',
            'fixture:missing.md#Missing', 'unknown:@artifact/source.md', 'disabled:@artifact/source.md', 'not a ref')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.disabled]\nenabled=false\n')
        self.fixture.reload()
        with self.base.connect() as connection:
            self.helper.prepare(connection)
            self.helper.change(connection, 1)
            before = self.state(connection)
            with self.no_work():
                status, reply = self.invoke(connection, 'status', repositories=('downstream', 'unknown'))
                fresh_status, fresh = self.invoke(connection, 'status', repositories=('fixture',))
            self.assertEqual(status, 1, reply)
            entries = {entry['repository']: entry for entry in reply['repositories']}
            current = entries['downstream']['result']
            self.assertEqual((current['chunks']['onDisk'], current['stale'], current['refs'], current['unresolvedRefs'],
                              current['invalidRefs'], current['refFaults']), (1, 1, 8, 2, 2, 5))
            self.assertGreaterEqual(current['drifts']['unresolvedFaults'], 4)
            self.assertEqual(entries['unknown']['error']['code'], 'unknown_repository')
            self.assertEqual(fresh_status, 0, fresh)
            source = fresh['repositories'][0]['result']
            self.assertEqual((source['stale'], source['unresolvedRefs'], source['invalidRefs']), (0, 0, 0))
            self.assertEqual(self.state(connection), before)


if __name__ == '__main__':
    unittest.main()
