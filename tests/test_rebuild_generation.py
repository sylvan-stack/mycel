# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""A lost store starts new knowledge; an exact store copy preserves evidence."""

import json
import os
import unittest
from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from mycel._classification_store import ClassificationStore
from mycel._cli import run
from mycel._coverage import require_check_database
from mycel._evidence import EvidenceStore
from mycel._store import TABLES, inspect_store

try:
    from .test_classification_store import AT, ClassificationStoreFixture
except ImportError:
    from test_classification_store import AT, ClassificationStoreFixture


class RebuildGenerationStoreTests(ClassificationStoreFixture):
    check_kind = "store"

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



# Archived complete imports; restore needed names in their original scope, not at this file tail.
