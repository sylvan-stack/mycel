# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Configured real-store proofs for retained declarations and physical bindings."""
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._capture import CapturedFile
from mycel._declared_refs import DeclaredRefStore
from mycel._evidence import canonical_json, document_comparisons
from mycel._markdown import split_markdown
from mycel._settings import SettingsSnapshot, _freeze, load_settings
from mycel._source_refs import read_document_declarations
from mycel._store import search_text


def settings(**enabled):
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({
        'repos': {name: {'enabled': value} for name, value in enabled.items()}, 'store': {}}), True, True)


def seed_document(connection, repository, path, source, *, root='artifact', kind='disk', location='disk',
                  file_id=None, chunk_ids=None):
    parsed = split_markdown(source)
    file_id = file_id or uuid4()
    connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                       (repository, Jsonb([])))
    connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                       (file_id, repository, root, path, 'documents'))
    file_version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
        'ON CONFLICT(file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
        (uuid4(), file_id, parsed.file_hash, parsed.source, Jsonb({}))).fetchone()[0]
    file_location = connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) RETURNING id',
        (uuid4(), file_version, kind, location, Jsonb({}))).fetchone()[0]
    ids, versions = [], []
    for index, chunk in enumerate(parsed.chunks):
        chunk_id = chunk_ids[index] if chunk_ids else uuid4()
        ids.append(chunk_id)
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (chunk_id, repository, file_id, 'document', Jsonb({})))
        raw = chunk.text.encode()
        metadata = {'name': chunk.name, 'kind': 'document', 'title': chunk.title,
                    'span': {'start': chunk.span.byte_start, 'end': chunk.span.byte_end},
                    'bodySpan': {'start': len(raw) - len(chunk.body.encode()), 'end': len(raw)}}
        version = connection.execute('INSERT INTO public.mycel_chunk_versions '
            '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
            'ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
            (chunk_id, chunk.snapshot_hash, raw, search_text(raw), Jsonb(json.loads(canonical_json(document_comparisons(chunk.body, chunk.title or '')))),
             Jsonb(metadata))).fetchone()[0]
        versions.append(version)
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                           (uuid4(), version, file_location, kind, location, Jsonb(metadata)))
    return str(file_location), file_id, tuple(ids), tuple(versions)


def retain(connection, snapshot, location, source):
    return DeclaredRefStore(connection).retain(snapshot, location,
        read_document_declarations(split_markdown(source), file='answer.md'))


class DeclaredRefStoreTests(unittest.TestCase):
    check_kind = "store"


class PhysicalBindingStoreTests(unittest.TestCase):
    check_kind = "store"

    def setup_disk(self, *, equal=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        code = base / 'code'
        artifact = code if equal else code / 'docs'
        artifact.mkdir(parents=True)
        config = base / 'settings.toml'
        config.write_text(f'[store]\naddress="postgresql://fixture@localhost/disposable"\n[repos.fixture]\nenabled=true\ncode_root={json.dumps(str(code))}\nartifact_root={json.dumps(str(artifact))}\n')
        return code, artifact, load_settings(path=config, home=base)

    def captured(self, path, aliases, raw=b'# Exact\n'):
        path.write_bytes(raw)
        return CapturedFile(aliases[0], tuple(aliases), 'documents', raw, sha256(raw).hexdigest(), split_markdown(raw))


class TypedMutationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setup_disk(self, owner_text, source_text, source_path='source.md'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        owner, source = home/'owner', home/'source'
        owner.mkdir()
        source.mkdir()
        (owner/'answer.md').write_bytes(owner_text.encode())
        (source/source_path).write_bytes(source_text.encode())
        config = home/'settings.toml'
        config.write_text('[store]\naddress="postgresql://fixture@localhost/disposable"\n'
            f'[repos.owner]\nenabled=true\nartifact_root={json.dumps(str(owner))}\n'
            f'[repos.source]\nenabled=true\nartifact_root={json.dumps(str(source))}\n'
            + (f'code_root={json.dumps(str(source))}\n' if source_path.endswith('.py') else ''))
        return load_settings(path=config, home=home), owner, source


# Archived complete imports; restore needed names in their original scope, not at this file tail.
