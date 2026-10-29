# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Transaction/audit acceptance on the configured per-check disposable store."""
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel import _activity as activity
from mycel._declared_refs import DeclaredRefStore
from mycel._markdown import split_markdown
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import read_document_declarations
from mycel._store import search_text


class ActivityStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def seed(self, c):
        c.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) VALUES ('fixture','{}'),('downstream','{}')")

    def write(self, counts=None, **details):
        def callback(c):
            c.execute("UPDATE public.mycel_repository_state SET read_locations = %s WHERE repository='fixture'", (Jsonb(counts or {'applied':1}),))
            return activity.AppliedMutation(True, counts or {'applied':1}, **details)
        return callback

    def entries(self, c):
        return c.execute('SELECT id,repository,kind,outcome,counts FROM public.mycel_activity ORDER BY id').fetchall()


class ActivityDeclaredRefStoreTests(unittest.TestCase):
    """Audit actual retained-reference writes; fixture Builds are test inputs."""
    check_kind = "store"


    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def settings(self, *, target_enabled=True):
        return SettingsSnapshot(Path('/fictional/activity-settings.toml'), _freeze({
            'repos': {'fixture': {'enabled': True}, 'downstream': {'enabled': True},
                      'target': {'enabled': target_enabled}}, 'store': {},}), True, True)

    def document(self, c, repository, path, source, name):
        raw = source.encode()
        file_id, file_version, file_location, chunk_id = (uuid4() for _ in range(4))
        c.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                  (repository, Jsonb([])))
        c.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)',
                  (file_id, repository, 'artifact', path, 'documents'))
        c.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s)',
                  (file_version, file_id, sha256(raw).hexdigest(), raw, Jsonb({})))
        c.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                  (file_location, file_version, 'disk', 'disk', Jsonb({})))
        c.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
                  (chunk_id, repository, file_id, 'document', Jsonb({})))
        metadata = {'name': name, 'kind': 'document', 'title': name,
                    'span': {'start': 0, 'end': len(raw)}}
        version = c.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
            (chunk_id, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb({}), Jsonb(metadata))).fetchone()[0]
        c.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                  (uuid4(), version, file_location, 'disk', 'disk', Jsonb({})))
        return str(file_location)

    def seed(self, c):
        settings = self.settings()
        store = DeclaredRefStore(c)
        self.document(c, 'target', 'input.md', '# Input\nExact input.\n', 'Input')
        for repository, name in (('fixture', 'Owner'), ('downstream', 'Dependant')):
            source = f'# {name}\n<!-- sources: target:@artifact/input.md#Input -->\n'
            location = self.document(c, repository, 'owner.md', source, name)
            store.retain(settings, location, read_document_declarations(split_markdown(source), file='owner.md'))
        return settings, store

    def entries(self, c):
        return c.execute('SELECT id,repository,kind,outcome,counts FROM public.mycel_activity ORDER BY id').fetchall()

    def dependency_snapshot(self, c):
        return tuple(c.execute(statement).fetchall() for statement in (
            'SELECT id,source_place,state,baseline_owner FROM public.mycel_dependencies ORDER BY id',
            'SELECT dependency,source_version FROM public.mycel_edges ORDER BY dependency,source_version',
            'SELECT id,fault FROM public.mycel_ref_faults ORDER BY id'))


# Archived complete imports; restore needed names in their original scope, not at this file tail.
