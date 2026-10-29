# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Resolver seams and separate genuine disposable-store selection checks."""
from dataclasses import replace
from unittest.mock import patch

from mycel._code import chunk_code
from mycel._errors import MycelError
from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from mycel import _resolver


import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._resolver import ResolvedChunk, ResolvedFile
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress
from mycel._store import search_text


def settings(*, enabled=True):
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({
        'repos': {'fixture': {'enabled': enabled}, 'disabled': {'enabled': False}},
        'store': {},}), True, True)


def chunk(name, source, *, kind='document', title=None, family=None, number=1, span=None):
    raw = source.encode()
    return ResolvedChunk(str(uuid4()), number, name, kind, raw, sha256(raw).hexdigest(), span, title, family)


def file(path, source, *, root='artifact', members=(), aliases=()):
    raw = source.encode()
    primary = SourceAddress('fixture', root, path)
    return ResolvedFile(str(uuid4()), 'fixture', primary, aliases or (primary,), raw,
                        sha256(raw).hexdigest(), tuple(members))


class ResolverUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class ResolverStoreTests(unittest.TestCase):
    check_kind = "store"

    def seed(self, connection, *, path='guide.md', root='artifact', source='# Exact\n',
             name='Exact', kind='document', title='Exact', family=None, aliases=(),
             location_kind='disk', location='disk', file_id=None, chunk_id=None,
             chunk_source=None, span=None, file_metadata=None, location_metadata=None):
        file_id=file_id or uuid4()
        file_version, file_location, chunk_id=uuid4(),uuid4(),chunk_id or uuid4()
        raw=source.encode()
        digest=sha256(raw).hexdigest()
        connection.execute("INSERT INTO public.mycel_repository_state VALUES ('fixture',NULL,'[]') ON CONFLICT DO NOTHING")
        connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (file_id,'fixture',root,path,'documents' if kind=='document' else 'code'))
        file_version=connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
                           'ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
                           (file_version,file_id,digest,raw,Jsonb({}))).fetchone()[0]
        file_location=connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) '
                           'ON CONFLICT (file_version,kind,location) DO UPDATE SET metadata=mycel_file_locations.metadata RETURNING id',
                           (file_location,file_version,location_kind,location,Jsonb(file_metadata or {}))).fetchone()[0]
        for alias_root, alias_path in aliases:
            connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                               (file_id,alias_root,alias_path))
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (chunk_id,'fixture',file_id,kind,Jsonb({})))
        chunk_source=source if chunk_source is None else chunk_source
        chunk_digest=sha256(chunk_source.encode()).hexdigest()
        metadata={'name':name,'kind':kind,'title':title,'family':family,
                  'span':span or {'start':0,'end':len(raw)}}
        version=connection.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
                                   'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                                   (chunk_id,chunk_digest,chunk_source.encode(),search_text(chunk_source.encode()),Jsonb({}),Jsonb(metadata))).fetchone()[0]
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                           (uuid4(),version,file_location,location_kind,location,Jsonb(location_metadata or {})))
        return file_id,chunk_id,version


# Archived complete imports; restore needed names in their original scope, not at this file tail.
