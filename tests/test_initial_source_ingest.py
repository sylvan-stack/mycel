"""Initial declared sources remain unresolved until a named source pass."""

from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from mycel import _dependency_inputs as inputs
from mycel._capture import capture_repository
from mycel._cli import run
from mycel._coverage import proves

try:
    from .test_classification_store import ClassificationStoreFixture
except ImportError:
    from test_classification_store import ClassificationStoreFixture


class InitialSourceIngestStoreTests(ClassificationStoreFixture):
    initialize_store = staticmethod(lambda backend, settings_file: None)

    def invoke(self, *arguments, successful=True):
        package = self.store_fixture.root / 'fictional-numbered-package'
        (package / 'data').mkdir(parents=True, exist_ok=True)
        (package / 'data/build-identity.json').write_bytes(b'{"schemaVersion":1,"build":26}\n')
        output, diagnostics = StringIO(), StringIO()
        with patch('mycel._build_identity.files', return_value=package), patch.dict(
                os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(list(arguments), stdout=output, stderr=diagnostics)
        reply = json.loads(output.getvalue())
        if successful:
            self.assertEqual((status, diagnostics.getvalue()), (0, ''), reply)
        else:
            self.assertEqual(status, 1, reply)
        return reply

    def dependencies(self, connection):
        return self.fixture.fixture.dependencies(connection)

    @proves('MYC-2.8', kind='store')
    def test_initial_unindexed_sources_remain_visible_without_broadening_scope_and_source_pass_retries(self):
        self.invoke('init')
        source_bytes = {path: path.read_bytes() for path in
                        (self.fixture.fixture.source, *self.fixture.extra)}
        dependant_bytes = self.fixture.fixture.answer.read_bytes()
        reply = self.invoke('ingest', '--repo', 'downstream')
        self.assertEqual(set(reply['repositories']), {'downstream'})
        with self.base.connect() as connection:
            rows = self.dependencies(connection)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row[6] is None and row[7] is None for row in rows))
            self.assertEqual({row[5]['sourceState'] for row in rows}, {'unresolved'})
            self.assertEqual({row[5]['resolution']['fault'] for row in rows}, {'missing_file'})
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM public.mycel_files WHERE repository='fixture'").fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
        self.invoke('ingest', '--repo', 'fixture')
        with self.base.connect() as connection:
            rows = self.dependencies(connection)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row[6] is not None and row[7] is not None for row in rows))
            self.assertEqual({row[5]['resolution']['state'] for row in rows}, {'resolved'})
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 3)
        self.assertEqual(self.fixture.fixture.answer.read_bytes(), dependant_bytes)
        self.assertEqual({path: path.read_bytes() for path in source_bytes}, source_bytes)

    @proves('MYC-2.8', kind='store')
    def test_empty_store_all_processes_downstream_before_sources_and_captures_new_baselines(self):
        self.invoke('init')
        reply = self.invoke('ingest', '--all')
        self.assertEqual(list(reply['repositories']), ['downstream', 'fixture'])
        self.assertTrue(all(value['ran'] for value in reply['repositories'].values()))
        with self.base.connect() as connection:
            rows = self.dependencies(connection)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row[6] is not None and row[7] is not None for row in rows))
            self.assertEqual({row[5]['resolution']['state'] for row in rows}, {'resolved'})
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 3)

    @proves('MYC-2.8', 'MYC-1.37', kind='store')
    def test_changed_initial_unindexed_source_does_not_stop_the_dependant_pass_and_stays_unresolved(self):
        # Since 20 October 2026 a pass publishes the capture it read and takes
        # another repository's sources from the index (MYC-1.37): a change to
        # the unindexed source's disk neither stops nor broadens the pass.
        self.invoke('init')
        source = self.fixture.fixture.source
        source.write_bytes(source.read_bytes() + b'Changed before the dependant pass.\n')
        reply = self.invoke('ingest', '--repo', 'downstream')
        self.assertEqual(set(reply['repositories']), {'downstream'})
        self.assertNotIn('changedDuringPass', reply['repositories']['downstream'])
        with self.base.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM public.mycel_files WHERE repository='downstream'").fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM public.mycel_files WHERE repository='fixture'").fetchone()[0], 0)
            rows = self.dependencies(connection)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row[6] is None and row[7] is None for row in rows))
            self.assertEqual({row[5]['sourceState'] for row in rows}, {'unresolved'})
            self.assertEqual({row[5]['resolution']['fault'] for row in rows}, {'missing_file'})
        self.invoke('ingest', '--repo', 'fixture')
        with self.base.connect() as connection:
            self.assertEqual({row[5]['resolution']['state'] for row in self.dependencies(connection)}, {'resolved'})

    @proves('MYC-1.37', kind='store')
    def test_resolved_uningested_source_change_preserves_existing_pins_and_the_pass_completes(self):
        self.invoke('init')
        self.invoke('ingest', '--repo', 'fixture')
        self.invoke('ingest', '--repo', 'downstream')
        with self.base.connect() as connection:
            before = self.dependencies(connection)
            pins = [(row[0], row[6], row[7]) for row in before]
        source = self.fixture.fixture.source
        source.write_bytes(source.read_bytes() + b'Changed before the source ingest.\n')
        # The source's disk is its own pass's business: the dependant's pass
        # completes against the indexed source and changes no pin.
        reply = self.invoke('ingest', '--repo', 'downstream')
        self.assertFalse(reply['repositories']['downstream']['files']['changed'])
        self.assertNotIn('changedDuringPass', reply['repositories']['downstream'])
        with self.base.connect() as connection:
            self.assertEqual([(row[0], row[6], row[7]) for row in self.dependencies(connection)], pins)

if __name__ == '__main__':
    unittest.main()
