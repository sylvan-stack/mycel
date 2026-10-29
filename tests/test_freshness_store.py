# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real-store proofs for recursive, bounded search freshness publication."""
import json
import unittest
from contextlib import ExitStack

from mycel._capture import LocationId
from mycel._dependency_application import DependencyApplicationStore
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._ingest import _CompleteProducer, _publication_guards
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import atomic_transaction, operation_guard
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._store import TABLES, checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.connection.execute(statement, *args, **kwargs)


class FreshnessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()
        self.folders = {'fixture': self.base.artifact}
        for name in ('contract', 'glossary', 'outside', 'shared', 'consumer', 'later', 'disabled'):
            folder = self.base.base / name
            folder.mkdir()
            self.folders[name] = folder
            with self.base.config.open('a') as config:
                config.write(f'\n[repos.{name}]\nenabled={"false" if name == "disabled" else "true"}\n'
                             + 'artifact_root=' + json.dumps(str(folder)) + '\n')
        self.glossary = self.folders['glossary'] / 'glossary.md'
        self.glossary.write_bytes(b'# Glossary\nOriginal governing definition.\n')
        (self.folders['glossary'] / 'keep.md').write_bytes(b'# Keep\nAn independent surviving source.\n')
        self.contract = self.folders['contract'] / 'contract.md'
        self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary'))
        self.driver = self.folders['fixture'] / 'driver.md'
        self.driver.write_bytes(self.document('Driver', 'contract:@artifact/contract.md#Contract'))
        self.independent = self.folders['fixture'] / 'independent.md'
        self.independent.write_bytes(b'# Independent\nUnrelated result has complete dependencies.\n')
        self.outside = self.folders['outside'] / 'unrelated.md'
        self.outside.write_bytes(b'# Unrelated\nAn unrelated enabled source.\n')
        self.shared = self.folders['shared'] / 'selected.md'
        self.shared.write_bytes(b'# Selected\nSelected shared document.\n')
        self.consumer = self.folders['consumer'] / 'answer.md'
        self.consumer.write_bytes(self.document('Answer', 'glossary:@artifact/glossary.md#Glossary'))
        self.code = self.base.code / 'driver.py'
        self.code.write_bytes(b'def drive():\n    return "unchanged driver"\n')
        self.base.commit()
        self.reload()

    @staticmethod
    def document(name, *sources):
        return ('---\nrole: authored\nsources: ' + json.dumps(list(sources)) + '\n---\n# ' + name
                + '\nUnchanged dependant text.\n').encode()

    def reload(self):
        self.settings = load_settings(path=self.base.config, home=self.base.base)

    def publish(self, connection, repository):
        with checked_store(connection), operation_guard(connection, repository, 'pass'):
            store = LocatedCaptureStore(connection)
            manifest = store.capture(self.settings, repository)
            with _publication_guards(connection, self.settings, manifest) as (guards, pending):
                producer = _CompleteProducer(self.settings, captured_at='2026-10-12T08:00:00Z',
                    collection_manifest=manifest, guarded_repositories=guards, pending_repositories=pending)
                return store.apply(self.settings, manifest, batch_handoff=producer, targeted_detection=True)

    def prepare(self, connection):
        for name in ('glossary', 'contract', 'fixture', 'outside', 'shared', 'consumer'):
            self.publish(connection, name)

    def contents(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}

    def owned(self, connection, repository):
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
            'WHERE repository=%s ORDER BY to_jsonb(t)::text', (repository,)).fetchall()
            for table in ('mycel_repository_state', 'mycel_files', 'mycel_chunks', 'mycel_dependencies',
                          'mycel_ref_faults', 'mycel_stale_reasons')}

    def pins(self, connection):
        return connection.execute("""SELECT d.id,d.dependant_version,d.baseline_owner,r.manifest_hash
            FROM public.mycel_dependencies d JOIN public.mycel_evidence_references r
              ON r.owner=d.baseline_owner AND r.ordinal=0
            WHERE d.repository=ANY(ARRAY['fixture','contract','consumer']) ORDER BY d.id""").fetchall()

    def key(self, connection, ref):
        member = SourceResolver.from_store(connection, self.settings).resolve(ref).selection.members[0]
        return member.chunk.identifier, member.chunk.version

    def assert_source(self, connection, ref):
        row = connection.execute("""SELECT fl.id,l.chunk_version FROM public.mycel_file_locations fl
            JOIN public.mycel_file_versions fv ON fv.id=fl.file_version
            JOIN public.mycel_files f ON f.id=fv.file_id
            JOIN public.mycel_locations l ON l.file_location=fl.id
            JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
            WHERE f.repository='fixture' AND f.path='driver.py' AND fl.kind='disk'
              AND l.metadata->>'name'='drive'""").fetchone()
        guards = tuple(sorted(self.settings.values['repos']))
        with ExitStack() as stack:
            stack.enter_context(checked_store(connection))
            for owner in guards:
                stack.enter_context(operation_guard(connection, owner, 'pass'))
            with atomic_transaction(connection):
                inputs = DependencyCaptureInputs(connection, self.settings, guarded_repositories=guards)
                return DependencyApplicationStore(connection).apply_in_transaction(self.settings,
                    str(row[0]), row[1], captured_at='2026-10-12T08:00:00Z', assertions=(ref,),
                    reread=inputs.rereader(LocationId('disk', None, 'disk'), 'fixture', None),
                    guarded_repositories=guards)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
