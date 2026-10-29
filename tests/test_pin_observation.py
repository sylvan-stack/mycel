# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real temporary disk observations and explicit SQL seams; no store claims."""

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_evidence import EvidenceConnection, Rows, document, member

from mycel import _evidence as evidence
from mycel import _pin_observation as observation
from mycel import _resolver as resolver
from mycel._capture import capture_repository
from mycel._errors import MycelError
from mycel._resolver import SourceResolver
from mycel._safeguards import CompletedChild
from mycel._settings import load_settings


def no_checkout(args, **kwargs):
    return CompletedChild(128, b'', b'private fixture diagnostic', 0)


class DiskCatalogConnection(EvidenceConnection):
    """Exact product resolver SQL rows over a private in-memory catalog seam."""
    def __init__(self, observed):
        super().__init__(observed)
        self.catalog_files = {file.identifier:file for file in observed.catalog.files}

    def execute(self, sql, params=()):
        if sql not in {resolver._CATALOG_SQL, resolver._FILES_SQL, resolver._ALIASES_SQL,
                       resolver._CHUNKS_SQL, resolver._INDEX_SQL}:
            return super().execute(sql, params)
        self.sql.append((sql, params))
        eligible = params[2]
        files = tuple(file for file in self.catalog_files.values() if file.repository in eligible)
        if sql == resolver._CATALOG_SQL:
            rows = []
            for file in files:
                rows.append(('file', [file.identifier, file.repository, file.primary.root,
                    file.primary.path, file.snapshot_hash, file.source.hex(),
                    {'root':file.primary.root,'path':file.primary.path,
                     'aliases':[{'root':alias.root,'path':alias.path} for alias in file.aliases]}]))
                rows.extend(('alias', [file.identifier, file.repository, alias.root, alias.path])
                            for alias in file.aliases)
                for chunk in file.chunks:
                    metadata = {'name':chunk.name,'kind':chunk.kind,'title':chunk.title,'family':chunk.family}
                    if chunk.span is not None:
                        metadata['span'] = {'start':chunk.span[0],'end':chunk.span[1]}
                    if chunk.body_span is not None:
                        metadata['bodySpan'] = {'start':chunk.body_span[0],'end':chunk.body_span[1]}
                    rows.append(('chunk', [file.identifier, file.repository, file.repository,
                        chunk.identifier, chunk.version, chunk.snapshot_hash, chunk.source.hex(),
                        json.loads(evidence.canonical_json(chunk.comparison)), metadata, {}]))
            return Rows(rows)
        if sql == resolver._FILES_SQL:
            return Rows((file.identifier,file.repository,file.primary.root,file.primary.path,file.snapshot_hash,file.source,
                         {'root':file.primary.root,'path':file.primary.path,
                          'aliases':[{'root':alias.root,'path':alias.path} for alias in file.aliases]}) for file in files)
        if sql == resolver._ALIASES_SQL:
            return Rows((file.identifier,file.repository,alias.root,alias.path) for file in files for alias in file.aliases)
        if sql == resolver._CHUNKS_SQL:
            rows = []
            for file in files:
                for chunk in file.chunks:
                    metadata = {'name':chunk.name,'kind':chunk.kind,'title':chunk.title,'family':chunk.family}
                    if chunk.span is not None:
                        metadata['span'] = {'start':chunk.span[0],'end':chunk.span[1]}
                    if chunk.body_span is not None:
                        metadata['bodySpan'] = {'start':chunk.body_span[0],'end':chunk.body_span[1]}
                    # The authoritative BYTEA migration leaves public source
                    # shapes stable. This seam accommodates its frozen/current
                    # SQL reader without claiming real PostgreSQL behavior.
                    source = chunk.source if 'v.source_bytes' in sql else chunk.source.decode('utf-8')
                    rows.append((file.identifier,file.repository,file.repository,chunk.identifier,chunk.version,
                                 chunk.snapshot_hash,source,json.loads(evidence.canonical_json(chunk.comparison)),metadata,{}))
            return Rows(rows)
        return Rows()


class PinObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.owner_root = self.home/'owner'
        self.source_artifact = self.home/'source-artifact'
        self.source_code = self.home/'source-code'
        for root in (self.owner_root,self.source_artifact,self.source_code):
            root.mkdir()
        self.owner_text = '# Answer\r\nComplete answer.\t\r\n'
        self.source_text = '# Source\r\nComplete source.\t\r\n'
        (self.owner_root/'answer.md').write_bytes(self.owner_text.encode())
        (self.source_artifact/'source.md').write_bytes(self.source_text.encode())
        self.settings_path = self.home/'settings.toml'
        self.settings_path.write_text('[store]\naddress="postgresql://fixture@localhost/mycel_check_observation"\n'
            f'[repos.owner]\nenabled=true\nartifact_root={json.dumps(str(self.owner_root))}\n'
            f'[repos.source]\nenabled=true\nartifact_root={json.dumps(str(self.source_artifact))}\n'
            f'code_root={json.dumps(str(self.source_code))}\n[repos.disabled]\nenabled=false\n')
        self.settings = load_settings(path=self.settings_path,home=self.home)
        dep = document('owner','answer.md',self.owner_text,version=1)
        src = document('source','source.md',self.source_text,version=11)
        self.catalog = SourceResolver(self.settings,(dep,src))
        source = self.catalog.resolve('source:source.md#Source')
        initial = evidence.PinInputs(self.settings,member(dep),dep,source.selection,
                                     evidence.CaptureLocation('disk'),source,self.catalog)
        self.connection = DiskCatalogConnection(initial)
        self.writer = evidence.EvidenceStore(self.connection)
        self.capture_calls = []
        self.patchers = [patch.object(resolver,'checked_store',self.checked),
                        patch.object(resolver,'read_snapshot',self.read),
                        patch.object(evidence,'checked_store',self.checked),
                        patch.object(evidence,'read_snapshot',self.read),
                        patch.object(evidence,'operation_guard',self.operation),
                        patch.object(observation,'capture_repository',self.capture)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextmanager
    def checked(self, connection):
        yield

    @contextmanager
    def read(self, connection):
        yield

    @contextmanager
    def operation(self, connection, repository, operation):
        connection.guards.append(repository)
        try:
            yield
        finally:
            connection.guards.remove(repository)

    def capture(self, snapshot, repository, **kwargs):
        self.assertIs(snapshot,self.settings)
        self.capture_calls.append(repository.name)
        return capture_repository(snapshot,repository,_git=no_checkout,**kwargs)

    def adapter(self, **kwargs):
        return observation.DiskPinObservation(self.connection,self.settings,
            kwargs.pop('dependant_ref','owner:answer.md#Answer'),kwargs.pop('declaration','source:source.md#Source'),**kwargs)

    def pin(self, adapter, expected):
        return self.writer.pin(expected,adapter.reread,dependency_id=uuid4(),kind='declared',
            declaration=adapter.declaration,captured_at='2026-10-09T00:00:00Z',authorization='initial_resolution')

    def assert_refused_without_write(self, adapter, expected):
        with self.assertRaises((evidence.EvidenceError,MycelError)) as error:
            self.pin(adapter,expected)
        if isinstance(error.exception,evidence.EvidenceError):
            self.assertEqual(error.exception.status,'changed_since_ingest')
            self.assertTrue(error.exception.addresses)
        self.assertFalse(self.connection.snapshots)
        self.assertFalse(self.connection.dependencies)


    def install_current_dependant(self, *, deleted_source=False):
        old = next(file for file in self.connection.catalog_files.values() if file.repository == 'owner')
        changed_text = '# Renamed\r\nComplete\tanswer.\r\n'
        (self.owner_root/'answer.md').write_bytes(changed_text.encode())
        changed = document('owner','answer.md',changed_text,version=2,identifier=old.chunks[0].identifier)
        self.connection.catalog_files[old.identifier] = changed
        if deleted_source:
            (self.source_artifact/'source.md').unlink()
            self.connection.catalog_files = {key:file for key,file in self.connection.catalog_files.items()
                                             if file.repository != 'source'}
            self.connection.versions = {key:row for key,row in self.connection.versions.items() if row[2] != 'source'}
            self.connection.files = {key:row for key,row in self.connection.files.items() if row[0] != 'source'}
        catalog = SourceResolver(self.settings,tuple(self.connection.catalog_files.values()))
        resolution = catalog.resolve('source:source.md#Source')
        current = evidence.InheritanceInputs(self.settings,member(changed),changed,evidence.CaptureLocation('disk'),
                                             resolution,catalog)
        # Version row seeding is explicit SQL-seam preparation, not ingest.
        self.connection.files[(changed.identifier,changed.snapshot_hash)] = ('owner',changed.source)
        self.connection.versions[changed.chunks[0].version] = (changed.chunks[0].version,
            next(row[1] for row in self.connection.versions.values() if str(row[1]) == changed.chunks[0].identifier),
            'owner',next(row[3] for row in self.connection.versions.values() if str(row[1]) == changed.chunks[0].identifier),
            changed.chunks[0].snapshot_hash,changed.chunks[0].source,dict(changed.chunks[0].comparison))
        return current


class PinObservationStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
