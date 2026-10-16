"""A lost store starts new knowledge; an exact store copy preserves evidence."""

from contextlib import contextmanager
from hashlib import sha256
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch
from uuid import UUID

from mycel._classification_store import ClassificationStore
from mycel._cli import run
from mycel._coverage import proves, require_check_database
from mycel._drift_store import DriftStore
from mycel._evidence import EvidenceStore
from mycel._store import TABLES, inspect_store

try:
    from .test_classification_store import ClassificationStoreFixture, AT
except ImportError:
    from test_classification_store import ClassificationStoreFixture, AT


class RebuildGenerationStoreTests(ClassificationStoreFixture):
    initialize_store = staticmethod(lambda backend, settings_file: None)

    @contextmanager
    def package(self):
        root = self.store_fixture.root / 'numbered-package'
        (root / 'data').mkdir(parents=True, exist_ok=True)
        (root / 'data/build-identity.json').write_bytes(b'{"schemaVersion":1,"build":26}\n')
        with patch('mycel._build_identity.files', return_value=root):
            yield

    def invoke(self, *arguments):
        output, diagnostics = StringIO(), StringIO()
        with self.package(), patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(list(arguments), stdout=output, stderr=diagnostics)
        reply = json.loads(output.getvalue())
        self.assertEqual((status, diagnostics.getvalue()), (0, ''), reply)
        return reply

    def generation(self):
        return self.invoke('info')['store']['indexGeneration']

    def ingest_files(self):
        self.invoke('ingest', '--repo', 'fixture')
        self.invoke('ingest', '--repo', 'downstream')

    def history(self):
        """Make the state that files alone cannot recreate, using real writers."""
        initialized = self.invoke('init')
        generation = initialized['indexGeneration']
        self.assertEqual(str(UUID(generation)), generation)
        self.ingest_files()
        guide = 'fixture:@artifact/guide.md#Guide'
        self.invoke('derive', self.fixture.ref, guide)
        self.invoke('relate', self.fixture.ref, guide)
        verification = self.invoke('confirm', self.fixture.ref, '--by', 'owner', '--how', 'check')
        with self.base.connect() as connection:
            baseline = next(row[7] for row in self.fixture.fixture.dependencies(connection)
                            if row[4] == self.fixture.addresses[0])
            captured = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.assertIn(self.fixture.fixture.source_bytes, [blob.source for blob in captured.snapshots])
        self.fixture.fixture.source.write_bytes(b'# Source\nChanged governing source.\n')
        self.old_files()
        self.ingest_files()
        with self.base.connect() as connection:
            drift = self.fixture.one(connection)
            reason = self.fixture.reason(drift)
            writer = ClassificationStore(connection)
            prepared = writer.prepare(self.base.settings, drift['id'], reason['id'], at=AT)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            result = writer.apply(self.base.settings, prepared, judgement='still_supported', at=AT)
            self.assertTrue(result['applied'], result)
            self.assertEqual(result['drift']['state'], 'closed')
            self.assertEqual(result['drift']['history'][-1]['inputHash'], prepared.input_hash)
            self.assertEqual(bytes(connection.execute(
                'SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                ('downstream', prepared.input_hash)).fetchone()[0]), prepared.decision.canonical_bytes)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies "
                "WHERE kind='asserted'").fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_relations').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0], 1)
        self.assertEqual(self.generation(), generation)
        return generation, baseline, verification, prepared

    def erase_store(self, connection):
        # Only the gate-created private database may be destroyed. Extensions
        # survive, as they would in an empty database ready for a fresh init.
        require_check_database(self.store_fixture.database)
        self.assertTrue(self.store_fixture.backend.owns_database(self.store_fixture.database))
        connection.execute('DROP TABLE ' + ','.join('public.' + table.name for table in TABLES) + ' CASCADE')
        self.assertEqual(inspect_store(connection).state, 'empty')

    def backup(self, connection):
        """A test-only exact PostgreSQL binary copy, including identity state.

        This is an independent database backup fixture, never a product backup
        command or reconstruction from source files.
        """
        tables, sequences = {}, {}
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for table in TABLES:
                statement = ('COPY (SELECT * FROM public.' + table.name + ' ORDER BY ' +
                             ','.join(table.primary) + ') TO STDOUT WITH (FORMAT BINARY)')
                with connection.cursor().copy(statement) as copied:
                    tables[table.name] = b''.join(bytes(block) for block in copied)
                for column in table.columns:
                    if 'IDENTITY' in column.extra:
                        name = table.name + '_' + column.name + '_seq'
                        sequences[name] = connection.execute(
                            'SELECT last_value,is_called FROM public.' + name).fetchone()
        return tables, sequences

    def restore(self, connection, backup):
        tables, sequences = backup
        with connection.transaction():
            connection.execute('TRUNCATE ' + ','.join('public.' + table.name for table in TABLES) +
                               ' RESTART IDENTITY')
            for table in TABLES:
                with connection.cursor().copy('COPY public.' + table.name + ' FROM STDIN WITH (FORMAT BINARY)') as copied:
                    copied.write(tables[table.name])
            for name, (value, called) in sequences.items():
                connection.execute('SELECT setval(%s::regclass,%s,%s)', ('public.' + name, value, called))

    @proves('MYC-16.12', kind='store')
    def test_lost_store_cli_rebuild_reports_new_generation_and_only_new_current_baselines(self):
        old_generation, old_baseline, verification, prepared = self.history()
        with self.base.connect() as connection:
            self.erase_store(connection)
        self.assertIsNone(self.generation())
        initialized = self.invoke('init')
        generation = initialized['indexGeneration']
        self.assertNotEqual(generation, old_generation)
        self.assertEqual(self.generation(), generation)
        with self.base.connect() as connection:
            entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
        detail = self.invoke('activity', '--entry', str(entry))['entries'][0]
        self.assertEqual((detail['kind'], detail['indexGeneration'], detail['counts']),
                         ('init', generation, initialized))
        self.ingest_files()
        with self.base.connect() as connection:
            dependencies = self.fixture.fixture.dependencies(connection)
            self.assertEqual({row[2] for row in dependencies}, {'declared'})
            self.assertEqual(len(dependencies), 3)
            baseline = next(row[7] for row in dependencies if row[4] == self.fixture.addresses[0])
            self.assertNotEqual(baseline, old_baseline)
            captured = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.assertIn(self.fixture.fixture.source.read_bytes(), [blob.source for blob in captured.snapshots])
            self.assertNotIn(self.fixture.fixture.source_bytes, [blob.source for blob in captured.snapshots])
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_relations').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_classification_work').fetchone()[0], 0)
            self.assertEqual(DriftStore(connection).list('downstream', closed=True, all_versions=True)['drifts'], [])
            for digest in (old_baseline, prepared.input_hash, sha256(self.fixture.fixture.source_bytes).hexdigest()):
                self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_manifests '
                    'WHERE repository=%s AND hash=%s', ('downstream', digest)).fetchone())
                self.assertIsNone(connection.execute('SELECT 1 FROM public.mycel_snapshots '
                    'WHERE repository=%s AND hash=%s', ('downstream', digest)).fetchone())
            entries = connection.execute('SELECT id,kind,index_generation FROM public.mycel_activity ORDER BY id').fetchall()
            self.assertEqual({row[1] for row in entries}, {'init', 'ingest'})
            self.assertEqual({str(row[2]) for row in entries}, {generation})
        for entry, _, _ in entries:
            self.assertEqual(self.invoke('activity', '--entry', str(entry))['entries'][0]['indexGeneration'], generation)

    @proves('MYC-16.12', kind='store')
    def test_exact_store_backup_restores_generation_pins_verification_and_classifier_bytes(self):
        generation, baseline, verification, prepared = self.history()
        with self.base.connect() as connection:
            backup = self.backup(connection)
            original = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.erase_store(connection)
        self.assertNotEqual(self.invoke('init')['indexGeneration'], generation)
        with self.base.connect() as connection:
            self.restore(connection, backup)
            self.assertEqual(inspect_store(connection).index_generation, generation)
            self.assertEqual(self.backup(connection), backup)
            restored = EvidenceStore(connection).read_baseline('downstream', baseline)
            self.assertEqual(restored, original)
            self.assertIn(self.fixture.fixture.source_bytes, [blob.source for blob in restored.snapshots])
            record = connection.execute('SELECT record FROM public.mycel_verifications WHERE id=%s',
                                        (verification['id'],)).fetchone()[0]
            self.assertEqual(record['textHash'], verification['textHash'])
            drift, = DriftStore(connection).list('downstream', closed=True, all_versions=True)['drifts']
            self.assertEqual((drift['state'], drift['history'][-1]['inputHash']), ('closed', prepared.input_hash))
            raw = bytes(connection.execute('SELECT bytes FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                ('downstream', prepared.input_hash)).fetchone()[0])
            self.assertEqual((raw, sha256(raw).hexdigest()), (prepared.decision.canonical_bytes, prepared.input_hash))
            entries = connection.execute('SELECT id FROM public.mycel_activity ORDER BY id').fetchall()
        self.assertEqual(self.generation(), generation)
        self.assertFalse(self.invoke('init')['changed'])
        for entry, in entries:
            self.assertEqual(self.invoke('activity', '--entry', str(entry))['entries'][0]['indexGeneration'], generation)
        with self.base.connect() as connection:
            self.assertEqual(self.backup(connection), backup)


if __name__ == '__main__':
    unittest.main()
