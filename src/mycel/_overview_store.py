"""Atomic index-only projection of the applied on-disk code catalog."""
from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._errors import MycelError
from ._location_corpus import location_corpus
from ._locks import require_transaction_guards
from ._overview_render import OverviewFile, OverviewSymbol, normalize_directory, render_sections
from ._source_refs import SourceAddress
from ._store import exact_text, search_text


_SCHEMA = 'mycel-overview-v1'
_FILES = """SELECT f.id,fl.id,fl.metadata FROM public.mycel_files f
JOIN public.mycel_file_versions fv ON fv.file_id=f.id
JOIN public.mycel_file_locations fl ON fl.file_version=fv.id
WHERE f.repository=%s AND fl.kind='disk' ORDER BY f.id,fl.id"""
_CHUNKS = """SELECT l.file_location,v.metadata,l.metadata,v.source_bytes FROM public.mycel_chunks c
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
JOIN public.mycel_locations l ON l.chunk_version=v.id
JOIN public.mycel_file_locations fl ON fl.id=l.file_location
JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=c.file_id
WHERE c.repository=%s AND fl.kind='disk' AND l.kind='disk' AND l.location=fl.location
ORDER BY l.file_location,v.id"""
_SECTIONS = """SELECT c.id,v.id,v.source_bytes,l.id,l.file_location,COALESCE(l.metadata,v.metadata),g.kind,g.state
FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
LEFT JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index'
LEFT JOIN public.mycel_generated_state g ON g.chunk_id=c.id
WHERE c.repository=%s AND c.file_id IS NULL AND c.kind='overview'
ORDER BY c.id,l.id"""


def _bad():
    raise MycelError('store_format', 'The stored overview has incompatible projection metadata.')


class OverviewStore:
    def __init__(self, connection):
        self.connection = connection

    def _stored(self, repository, *, include_missing=False):
        result = {}
        for identifier, version, source, location, file_location, metadata, kind, state in self.connection.execute(
                _SECTIONS, (repository,)).fetchall():
            if location is None and not include_missing:
                continue
            if (not isinstance(metadata, dict) or not isinstance(state, dict)
                    or set(state) != {'schema', 'directory', 'files', 'symbols', 'chunkVersion'}
                    or state['schema'] != _SCHEMA or kind != 'overview'
                    or type(state['files']) is not int or state['files'] < 1
                    or type(state['symbols']) is not int or state['symbols'] < 0
                    or type(state['chunkVersion']) is not int or state['chunkVersion'] != version
                    or file_location is not None):
                _bad()
            directory = state['directory']
            try:
                normalized = normalize_directory(directory)
            except MycelError:
                _bad()
            if (normalized != directory or directory in result
                    or metadata != {'kind': 'overview', 'path': 'overview', 'name': directory}):
                _bad()
            result[directory] = (identifier, version, location,
                {'directory': directory, 'files': state['files'], 'symbols': state['symbols'],
                 'text': exact_text(source)})
        return result

    def sections(self, repository, directory=None):
        """Read stored sections only; the caller owns its read-only snapshot."""
        if directory is not None:
            directory = normalize_directory(directory)
        return [row[3] for name, row in sorted(self._stored(repository).items())
                if directory is None or name == directory]

    def _files(self, repository):
        chunks = {}
        for location, version, placed, source in self.connection.execute(_CHUNKS, (repository,)).fetchall():
            if not isinstance(version, dict) or not isinstance(placed, dict):
                _bad()
            metadata = {**version, **placed}
            try:
                name, kind, span = metadata['name'], metadata['kind'], metadata['span']
                position = span['start']
                family = metadata.get('family')
                if (not isinstance(name, str) or not isinstance(kind, str) or type(position) is not int
                        or position < 0 or family is not None and not isinstance(family, str)):
                    _bad()
                display_name = None
                if 'declarationNameSpan' in metadata:
                    start, end = metadata['declarationNameSpan']
                    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source):
                        _bad()
                    leaf = bytes(source)[start:end].decode('utf-8')
                    display_name = leaf if family is None else family + '.' + leaf
                chunks.setdefault(location, []).append(OverviewSymbol(name, kind, position, family, display_name))
            except (KeyError, TypeError, ValueError, UnicodeError):
                _bad()
        files, seen = [], set()
        for identifier, location, metadata in self.connection.execute(_FILES, (repository,)).fetchall():
            if location_corpus(metadata) != 'code':
                continue
            aliases = metadata.get('aliases', [])
            paths = sorted(item['path'] for item in aliases if item.get('root') == 'code')
            if not paths:
                _bad()
            path = paths[0]
            if not isinstance(path, str) or path in seen or normalize_directory(path) != path:
                _bad()
            seen.add(path)
            files.append(OverviewFile(path, tuple(chunks.get(location, ()))))
        return tuple(files)

    def reconcile_in_transaction(self, repository):
        """Publish only stored, successfully applied disk state under its guard."""
        require_transaction_guards(self.connection, (repository,))
        proposed = {section['directory']: section for section in render_sections(self._files(repository))}
        current = self._stored(repository, include_missing=True)
        changed = False
        for directory in sorted(set(current) - set(proposed)):
            self.connection.execute('DELETE FROM public.mycel_chunks WHERE id=%s', (current[directory][0],))
            changed = True
        for directory, section in sorted(proposed.items()):
            old = current.get(directory)
            if old is not None and old[2] is not None and old[3] == section:
                continue
            identifier = uuid4() if old is None else old[0]
            metadata = {'kind': 'overview', 'path': 'overview', 'name': directory}
            raw = section['text'].encode('utf-8')
            self.connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,%s) '
                'ON CONFLICT(id) DO NOTHING', (identifier, repository, 'overview', Jsonb({})))
            version = self.connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
                (identifier, sha256(raw).hexdigest(), raw, search_text(raw), Jsonb({}), Jsonb(metadata))).fetchone()[0]
            self.connection.execute('DELETE FROM public.mycel_locations WHERE chunk_version IN '
                '(SELECT id FROM public.mycel_chunk_versions WHERE chunk_id=%s)', (identifier,))
            self.connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,%s,%s,%s)',
                (uuid4(), version, 'index', SourceAddress(repository, 'index', 'overview', directory).address,
                 Jsonb(metadata)))
            state = {'schema': _SCHEMA, 'directory': directory, 'files': section['files'],
                     'symbols': section['symbols'], 'chunkVersion': version}
            self.connection.execute('INSERT INTO public.mycel_generated_state VALUES (%s,%s,%s,%s) '
                'ON CONFLICT(chunk_id) DO UPDATE SET state=EXCLUDED.state',
                (identifier, repository, 'overview', Jsonb(state)))
            # Overview has no pins/history: obsolete exact text and its vectors
            # are removed together, while unchanged rows are never rewritten.
            self.connection.execute('DELETE FROM public.mycel_chunk_versions WHERE chunk_id=%s AND id<>%s',
                                    (identifier, version))
            changed = True
        return changed
