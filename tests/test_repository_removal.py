# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Configured disposable-store proofs for complete repository removal."""
from unittest.mock import patch

from psycopg.types.json import Jsonb
from mycel._activity import MutationActivity
from mycel._collection import CollectionStore
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore
from mycel._freshness import Deadline
from mycel._locks import invocation_guard, mutation_guard, operation_guard, structure_guard
from mycel._repository_removal import RepositoryRemovalStore
from mycel._read_store import read_from_store
from mycel._resolver import SourceResolver
from mycel._verification import ConfirmationStore

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from mycel._coverage import require_check_database
from mycel._locks import invocation_guard
from mycel._settings import load_settings
from mycel._store import TABLES, search_text


class RepositoryRemovalStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        if not hasattr(self, 'store_fixture'):
            self.fail('Repository removal checks require a configured disposable store.')
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        temporary = tempfile.TemporaryDirectory(prefix='mycel_removal_')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.code, self.artifacts = self.root / 'checkout', self.root / 'artifacts'
        self.code.mkdir()
        self.artifacts.mkdir()
        (self.code / 'worker.py').write_text('def work():\n    return 1\n')
        (self.artifacts / 'guide.md').write_text('# Guide\nHistorical source files stay.\n')
        self.config = self.root / 'settings.toml'
        self.configure()

    def configure(self, *, known=True, enabled=True):
        value = '[store]\naddress=' + json.dumps(self.store_fixture.backend.address(self.store_fixture.database)) + '\n'
        if known:
            value += '[repos.fixture]\nenabled=' + str(enabled).lower() + '\ncode_root=' + json.dumps(str(self.code))
            value += '\nartifact_root=' + json.dumps(str(self.artifacts)) + '\n'
        self.config.write_text(value)
        self.settings = load_settings(path=self.config, home=self.root)
        return self.settings

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def state(self, connection):
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
                if table.name not in {'mycel_store', 'mycel_lock_keys', 'mycel_invocations'}}

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    @staticmethod
    def owner(connection, repository, kind, label, *, invocation=None):
        owner = uuid4()
        raw = ('Shared immutable fixture bytes: ' + label).encode()
        digest = sha256(raw).hexdigest()
        manifest = b'{"fixture":"immutable manifest"}'
        manifest_hash = sha256(manifest).hexdigest()
        connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,\'{}\') '
            'ON CONFLICT DO NOTHING', (repository, digest, raw))
        connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,\'baseline\',%s,\'{}\') '
            'ON CONFLICT DO NOTHING', (repository, manifest_hash, manifest))
        connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
            (owner, repository, kind, label, invocation))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,NULL,0)',
            (owner, repository, digest))
        connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,1)',
            (owner, repository, manifest_hash))
        return owner

    @staticmethod
    def chunk(connection, repository, *, path='guide.md', corpus='documents', synthetic=False):
        file_id, file_version, file_location, chunk = uuid4(), uuid4(), uuid4(), uuid4()
        raw = ('# Guide\n' + repository + ' exact bytes.\n').encode()
        kind = 'summary' if synthetic else 'document' if corpus == 'documents' else 'function'
        if not synthetic:
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,\'artifact\',%s,%s)',
                (file_id, repository, path, corpus))
            connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,\'code\',%s)', (file_id, path))
            connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,\'{}\')',
                (file_version, file_id, sha256(raw).hexdigest(), raw))
            connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,\'disk\',\'disk\',\'{}\')',
                (file_location, file_version))
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,\'{}\')',
            (chunk, repository, None if synthetic else file_id, kind))
        version = connection.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
            'VALUES (%s,%s,%s,%s,\'{}\',\'{}\') RETURNING id',
            (chunk, sha256(raw).hexdigest(), raw, search_text(raw))).fetchone()[0]
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,\'{}\')',
            (uuid4(), version, None if synthetic else file_location,
             'index' if synthetic else 'disk', 'index' if synthetic else 'disk'))
        if synthetic:
            connection.execute('INSERT INTO public.mycel_generated_state VALUES (%s,%s,\'summary\',\'{}\')',
                (chunk, repository))
        return chunk, version

    def seed(self, connection, repository, *, complete=False):
        connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,\'[]\')', (repository,))
        chunk, version = self.chunk(connection, repository)
        baseline = self.owner(connection, repository, 'baseline', 'copied source evidence')
        dependency = uuid4()
        connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,\'asserted\',\'{}\',%s)',
            (dependency, repository, version, 'fixture:@artifact/guide.md#Guide',
             'fixture:@artifact/guide.md#Guide', baseline))
        connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,\'{}\',%s)',
            (uuid4(), repository, version, 'fixture:@artifact/guide.md#Guide', baseline))
        connection.execute('INSERT INTO public.mycel_embedding_receipts (id,repository,model,dimensions,payload) '
            'VALUES (%s,%s,\'voyage-code-4\',1024,%s)', (uuid4(), repository, b'obsolete result'))
        if complete:
            _, code_version = self.chunk(connection, repository, path='worker.py', corpus='code')
            self.chunk(connection, repository, synthetic=True)
            plan = uuid4()
            connection.execute('INSERT INTO public.mycel_embedding_plans VALUES '
                '(%s,%s,\'voyage-code-4\',1024,\'plan\',\'fixture place\',\'{}\',NULL)', (plan, version))
            connection.execute('INSERT INTO public.mycel_embedding_parts VALUES (%s,0,0,1,%s,1,1,NULL)', (plan, b'x'))
            vector = '[' + ','.join(['1'] + ['0'] * 1023) + ']'
            connection.execute('INSERT INTO public.mycel_vectors VALUES (%s,0,\'voyage-code-4\',1024,%s::vector)',
                (plan, vector))
            connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (dependency, code_version))
            connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,\'fixture ref\',\'{}\')',
                (dependency, repository, version))
            connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,%s,\'{}\')',
                (uuid4(), repository, version, dependency))
            for current in (version, None):
                owner = self.owner(connection, repository, 'drift', str(uuid4()))
                connection.execute('INSERT INTO public.mycel_drifts VALUES '
                    '(%s,%s,%s,clock_timestamp(),NULL,\'{}\',%s)', (uuid4(), repository, current, owner))
            verification = self.owner(connection, repository, 'verification', str(uuid4()))
            connection.execute('INSERT INTO public.mycel_verifications VALUES '
                '(%s,%s,%s,clock_timestamp(),\'{}\',%s)', (uuid4(), repository, chunk, verification))
            lease = self.owner(connection, repository, 'classification', str(uuid4()))
            connection.execute('INSERT INTO public.mycel_classification_work VALUES (%s,%s,%s,NULL,\'{}\',%s)',
                (uuid4(), repository, dependency, lease))
            with invocation_guard(connection) as invocation:
                self.owner(connection, repository, 'classification_lease', str(uuid4()), invocation=invocation.id)
                activity = connection.execute('INSERT INTO public.mycel_activity '
                    '(repository,invocation,index_generation,kind,trigger,build,started_at,ended_at,outcome,counts) '
                    'VALUES (%s,%s,%s,\'ingest\',\'command\',1,clock_timestamp(),clock_timestamp(),\'done\',\'{}\') '
                    'RETURNING id', (repository, invocation.id, invocation.index_generation)).fetchone()[0]
                connection.execute('INSERT INTO public.mycel_activity_files VALUES '
                    '(%s,0,\'artifact\',\'guide.md\',\'disk\',\'added\')', (activity,))
                connection.execute('INSERT INTO public.mycel_identity_decisions VALUES '
                    '(%s,0,\'artifact\',\'guide.md\',\'disk\',%s,\'new\',NULL,\'Guide\')', (activity, chunk))
                connection.execute('INSERT INTO public.mycel_activity_classifications VALUES '
                    '(%s,0,\'fixture bundle\',\'fixture dependant\',\'done\')', (activity,))
        return dependency, version


class RepositoryRemovalEvidenceStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
