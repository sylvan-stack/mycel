"""Persist verified physical disk-file bindings for the shared source resolver.

This is a seeded ingest seam: it writes file/version/location rows, but assigns
no chunk identities, performs no scan and deletes no absent files. Only verified
physical aliases or an explicitly selected, same-identity move reuse a file ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._capture import CapturedFile
from ._errors import MycelError
from ._evidence import EvidenceError
from ._locks import atomic_transaction, operation_guard, read_snapshot
from ._location_corpus import corpus_value, location_corpus, require_captured_corpus
from ._pin_observation import _read_alias
from ._scope import RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress
from ._store import checked_store


@dataclass(frozen=True)
class FileBinding:
    identifier: str
    version: str
    location: str
    primary: SourceAddress
    aliases: tuple[SourceAddress, ...]


def _observe(repository, aliases, source):
    try:
        return tuple(_read_alias(repository, alias, source, None) for alias in aliases)
    except EvidenceError:
        raise MycelError('invalid_input', 'The complete physical source binding changed during capture.') from None


def bind_disk_file(connection, settings: SettingsSnapshot, repository: str,
                   captured: CapturedFile, *, recognized_move: str | None = None) -> FileBinding:
    """Bind complete bytes after rereading all aliases under the repository lock.

    The captured primary implements first-discovery specificity/equal-root
    ordering. An existing primary survives while its alias still reaches this
    file. ``recognized_move`` names an existing ID whose recorded physical
    identity must match; matching text/path alone can never authorize reuse.
    """
    settings.require_valid(require_store=False)
    selected = RepositoryLocations(settings).named(repository)
    if (len(selected) != 1 or not selected[0].enabled or not isinstance(captured, CapturedFile)
            or type(captured.source) is not bytes or sha256(captured.source).hexdigest() != captured.file_hash
            or not captured.aliases or captured.primary not in captured.aliases
            or len(set(captured.aliases)) != len(captured.aliases)):
        raise MycelError('invalid_input', 'A binding requires one enabled repository and complete exact file aliases.')
    aliases = tuple(sorted((SourceAddress(repository, item.root, item.path) for item in captured.aliases),
                           key=lambda item: item.address))
    corpus_value(captured.corpus, code='invalid_input')
    with checked_store(connection), operation_guard(connection, repository, 'pass'):
        physical = _observe(selected[0], aliases, captured.source)
        identities = {tuple(item['fileIdentity'][:2]) for item in physical}
        if len(identities) != 1:
            raise MycelError('invalid_input', 'The proposed aliases reach different physical files.')
        identity = next(iter(identities))
        # Choose the most specific resolved containing root, with artifact
        # winning equal-root ties, independently of a caller's suggested primary.
        discovered = min(zip(aliases, physical), key=lambda pair: (
            -len(Path(pair[1]['root']).parts), pair[0].root != 'artifact', pair[0].address))[0]
        with read_snapshot(connection):
            rows = connection.execute(_LOCATIONS_SQL, (repository,)).fetchall()
            global_aliases = connection.execute(_GLOBAL_ALIASES_SQL, (repository,)).fetchall()
        for row in rows:
            location_corpus(row[5], legacy=True)
        matching = {str(row[0]) for row in rows if tuple(row[5].get('physicalIdentity', ())) == identity}
        occupied = {str(row[0]) for row in rows if any(alias == SourceAddress(repository, item['root'], item['path'])
                    for alias in aliases for item in row[5].get('aliases', [{'root': row[1], 'path': row[2]}] +
                        [{'root': root, 'path': path} for file_id, root, path in global_aliases if file_id == row[0]]))}
        if occupied - matching:
            # Atomic replacement at an existing spelling needs the caller's
            # file identity plan. Inode/contents/path alone cannot prove reuse.
            raise MycelError('invalid_input', 'The established file path has a changed physical identity; reconcile its file identity before binding.')
        if recognized_move is not None:
            try:
                recognized_move = str(UUID(recognized_move))
            except (ValueError, TypeError, AttributeError):
                raise MycelError('invalid_input', 'A recognized move requires an existing file identifier.') from None
            if matching != {recognized_move}:
                raise MycelError('invalid_input', 'The recognized move does not preserve the recorded physical identity.')
        if len(matching) > 1:
            raise MycelError('store_format', 'One physical file has conflicting stored bindings.')
        identifier = next(iter(matching), str(uuid4()))
        old = tuple(row for row in rows if str(row[0]) == identifier)
        if len(old) > 1:
            raise MycelError('store_format', 'A disk file has more than one current location.')
        primary = discovered
        moves = []
        if old:
            metadata = old[0][5]
            previous = SourceAddress(repository, metadata.get('root', old[0][1]), metadata.get('path', old[0][2]))
            prior_aliases = tuple(SourceAddress(repository, item['root'], item['path']) for item in metadata.get(
                'aliases', [{'root': old[0][1], 'path': old[0][2]}]))
            moves = list(metadata.get('recognizedMoves', ()))
            if previous in aliases:
                primary = previous
            elif not set(prior_aliases).intersection(aliases):
                if recognized_move != identifier:
                    raise MycelError('invalid_input', 'A changed physical-file path requires a recognized move binding.')
                moves.extend({'root': alias.root, 'path': alias.path} for alias in prior_aliases)
        # A second fresh observation closes replacement/retargeting races before
        # publication; no new identity can be inferred from equal bytes.
        if _observe(selected[0], aliases, captured.source) != physical:
            raise MycelError('invalid_input', 'The physical source binding changed during capture.')
        metadata = {**(old[0][5] if old else {}), 'root': primary.root, 'path': primary.path,
                    'corpus': captured.corpus,
                    'aliases': [{'root': alias.root, 'path': alias.path} for alias in aliases],
                    'physicalIdentity': list(identity),
                    'physicalBindings': [{'root': alias.root, 'path': alias.path,
                        'absoluteRoot': observed['root'], 'rootIdentity': observed['rootIdentity']}
                        for alias, observed in zip(aliases, physical)], 'recognizedMoves': sorted(
                        { (item['root'], item['path']) for item in moves })}
        metadata['recognizedMoves'] = [{'root': root, 'path': path} for root, path in metadata['recognizedMoves']]
        require_captured_corpus(metadata, captured)
        with atomic_transaction(connection):
            if (connection.execute(_LOCATIONS_SQL, (repository,)).fetchall() != rows
                    or connection.execute(_GLOBAL_ALIASES_SQL, (repository,)).fetchall() != global_aliases):
                raise MycelError('invalid_input', 'The indexed physical source bindings changed during capture.')
            connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                               (repository, Jsonb([])))
            if old:
                # Legacy seeded branch/stash locations may inherit shared file
                # columns. Freeze that prior binding before changing disk's
                # global defaults so retained locations never follow disk.
                defaults = [{'root': old[0][1], 'path': old[0][2]}]
                defaults.extend({'root': root, 'path': path} for root, path in connection.execute(
                    'SELECT root,path FROM public.mycel_file_aliases WHERE file_id=%s', (identifier,)).fetchall())
                retained = connection.execute('SELECT l.id,l.metadata FROM public.mycel_file_locations l '
                    'JOIN public.mycel_file_versions v ON v.id=l.file_version WHERE v.file_id=%s AND l.kind<>%s',
                    (identifier, 'disk')).fetchall()
                for retained_location, retained_metadata in retained:
                    if not all(key in retained_metadata for key in ('root', 'path', 'aliases')):
                        preserved = {'root': old[0][1], 'path': old[0][2], 'aliases': defaults, **retained_metadata}
                        connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                                           (Jsonb(preserved), retained_location))
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) '
                               'ON CONFLICT (id) DO UPDATE SET root=EXCLUDED.root,path=EXCLUDED.path,corpus=EXCLUDED.corpus',
                               (identifier, repository, primary.root, primary.path, captured.corpus))
            connection.execute('DELETE FROM public.mycel_file_aliases WHERE file_id=%s', (identifier,))
            for alias in aliases:
                connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)',
                                   (identifier, alias.root, alias.path))
            version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
                (uuid4(), identifier, captured.file_hash, captured.source, Jsonb({}))).fetchone()[0]
            if old and str(old[0][4]) == str(version):
                location = old[0][3]
                connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                                   (Jsonb(metadata), location))
            else:
                # Rebinding an exact file version is the caller's complete-file
                # ingest boundary. Old chunk locations are not silently carried.
                connection.execute("DELETE FROM public.mycel_file_locations l USING public.mycel_file_versions v "
                                   "WHERE l.file_version=v.id AND v.file_id=%s AND l.kind='disk'", (identifier,))
                location = uuid4()
                connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                                   (location, version, 'disk', 'disk', Jsonb(metadata)))
        return FileBinding(identifier, str(version), str(location), primary, aliases)


_LOCATIONS_SQL = """SELECT f.id,f.root,f.path,l.id,v.id,l.metadata FROM public.mycel_files f
JOIN public.mycel_file_versions v ON v.file_id=f.id JOIN public.mycel_file_locations l ON l.file_version=v.id
WHERE f.repository=%s AND l.kind='disk' ORDER BY f.id,l.id"""
_GLOBAL_ALIASES_SQL = """SELECT a.file_id,a.root,a.path FROM public.mycel_file_aliases a
JOIN public.mycel_files f ON f.id=a.file_id WHERE f.repository=%s ORDER BY a.file_id,a.root,a.path"""
