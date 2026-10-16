"""Exact one-chunk reading over the shared, immutable source catalog."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ._errors import MycelError
from ._freshness import FreshnessResult
from ._markdown import split_markdown
from ._refs import _PUBLIC_FAULTS, _place
from ._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from ._scope import RepositoryLocations
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address, read_document_declarations
from ._store import exact_text


READ_REPLY = 1
MAX_TEXT_BYTES = 5 * 1024 * 1024


class ReadSelectionError(MycelError):
    """A command refusal with canonical, root-aware ambiguity candidates."""

    def __init__(self, message: str, candidates=()):
        super().__init__('invalid_input', message)
        self.candidates = tuple(_place(parse_source_address(value)) for value in candidates[:20])

    def to_dict(self):
        result = super().to_dict()
        if self.candidates:
            result['candidates'] = list(self.candidates)
        return result


@dataclass(frozen=True)
class ReadSelection:
    place: SourceAddress
    chunk: ResolvedChunk
    file: ResolvedFile | None


def validate_read(place=None, *, identifier=None, context=None, repository=None):
    if ((place is None) == (identifier is None)
            or any(value is not None and (not isinstance(value, str) or not value.strip() or '\0' in value)
                   for value in (place, identifier, repository))):
        raise MycelError('invalid_input', 'Read requires one chunk address or one identifier.')
    if context is not None and (type(context) is not int or not 0 <= context <= 50):
        raise MycelError('invalid_input', 'Read context must be an integer from 0 to 50.')


def read_address(place: str, *, repository: str | None = None) -> SourceAddress:
    """A repository selector may supply the prefix of a short address."""
    try:
        value = parse_source_address(place if ':' in place or repository is None else f'{repository}:{place}')
    except SourceAddressError:
        raise ReadSelectionError('Read requires a valid Source Ref.') from None
    if repository is not None and value.repository != repository:
        raise ReadSelectionError('The chunk address does not belong to the selected repository.')
    return value


def require_repository(settings, repository):
    value = settings.values['repos'].get(repository)
    if value is None:
        raise MycelError('unknown_repository', f'Repository {repository!r} is not configured.')
    if not value['enabled']:
        raise MycelError('refused', f'Repository {repository!r} is switched off.')


def select_chunk(resolver: SourceResolver, place=None, *, identifier=None, repository=None) -> ReadSelection:
    validate_read(place, identifier=identifier, repository=repository)
    if repository is not None:
        require_repository(resolver.settings, repository)
    if identifier is not None:
        matches = [ReadSelection(member.place, member.chunk, file) for file in resolver.files
            for member in resolver._members(file, file.chunks) if member.chunk.identifier == identifier]
        matches += [ReadSelection(address, chunk, None) for address, chunk in resolver.index
                    if chunk.identifier == identifier]
        matches = [value for value in matches if repository is None or value.place.repository == repository]
        if not matches:
            raise ReadSelectionError('No current indexed chunk has that identifier.')
        for value in matches:
            require_repository(resolver.settings, value.place.repository)
        if len(matches) != 1:
            raise ReadSelectionError('The identifier does not select one current chunk.',
                                     tuple(value.place.address for value in matches))
        return matches[0]
    address = read_address(place, repository=repository)
    require_repository(resolver.settings, address.repository)
    result = resolver.resolve(address.address, purpose='read')
    if result.state != 'resolved' or result.selection is None:
        raise ReadSelectionError('The address does not select one current indexed chunk.', result.candidates)
    selection = result.selection
    if len(selection.members) != 1:
        raise ReadSelectionError('The address must select exactly one chunk.',
                                 tuple(member.place.address for member in selection.members))
    member = selection.members[0]
    return ReadSelection(member.place, member.chunk, selection.file)


def _file(selection, settings):
    if selection.file is None:
        return None, None, 'This chunk is generated in the index and has no file.'
    root_key = 'code_root' if selection.place.root == 'code' else 'artifact_root'
    root = settings.values['repos'][selection.place.repository].get(root_key)
    try:
        if root is None and 'organizations' in settings.values:
            configured = RepositoryLocations(settings).named(selection.place.repository)[0]
            configured.require_folders()
            folder = configured.code if selection.place.root == 'code' else configured.documents
            root = None if folder is None else folder.path
        if root is None:
            return None, None, 'The configured source root is unavailable.'
        configured = Path(root) / selection.place.path
        root = Path(root).resolve()
        path = configured.resolve()
        if not path.is_relative_to(root):
            return None, None, 'The chunk file no longer belongs to its configured source root.'
        raw = path.read_bytes()
        return str(configured.absolute()), raw, None
    except (OSError, ValueError, RuntimeError, MycelError):
        return None, None, 'The chunk file cannot be read.'


def _lines(selection):
    if selection.file is None or selection.chunk.span is None:
        return None
    start, end = selection.chunk.span
    source = selection.file.source
    return {'start': source[:start].count(b'\n') + 1,
            'end': source[:max(start, end - 1)].count(b'\n') + 1}


def _copy(value):
    if isinstance(value, Mapping):
        return {key: _copy(member) for key, member in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(member) for member in value]
    return value


def dependency_faults(freshness, resolver, selected):
    """Render each reachable fault with its original dependant's place."""
    by_key = {(member.chunk.identifier, member.chunk.version): member.place for file in resolver.files
              for member in resolver._members(file, file.chunks)}
    by_key.update(((chunk.identifier, chunk.version), place) for place, chunk in resolver.index)
    key = (selected.chunk.identifier, selected.chunk.version)
    requirement = next((row for row in freshness.chunk_requirements if row.chunk == key), None)
    faults = requirement.faults if requirement is not None else freshness.faults
    records = []
    for fault in faults:
        record = {'chunk': _place(by_key.get(fault.chunk, selected.place)), 'ref': fault.ref,
                  'fault': _PUBLIC_FAULTS.get(fault.reason, 'not_found')}
        resolution = resolver.resolve(fault.ref)
        if resolution.candidates:
            record['candidates'] = [_place(parse_source_address(candidate)) for candidate in resolution.candidates]
        if record not in records:
            records.append(record)
    return records


def read_chunk(resolver: SourceResolver, place=None, *, identifier=None, context: int | None = None,
               repository: str | None = None, freshness: FreshnessResult | None = None,
               metadata: Mapping | None = None) -> dict:
    """Return schema 1 without replacing complete retained text with file text.

    ``metadata`` supplies this selected version's stored marks, public faults,
    and the freshness adapter's committed per-repository ingest counters.
    An absent freshness result never certifies the retained text as current.
    """
    validate_read(place, identifier=identifier, context=context, repository=repository)
    selected = select_chunk(resolver, place, identifier=identifier, repository=repository)
    metadata = {} if metadata is None else metadata
    chunk, address = selected.chunk, selected.place
    origin = metadata.get('origin', chunk.kind if address.root == 'index' else
                          'document' if chunk.kind == 'document' else 'code')
    if origin == 'documents':
        origin = 'document'
    if origin not in {'code', 'document', 'summary', 'overview'}:
        raise MycelError('store_format', 'The read catalog has an incompatible chunk origin.')
    text = exact_text(chunk.source)
    cut = len(chunk.source) > MAX_TEXT_BYTES
    if cut:
        text = chunk.source[:MAX_TEXT_BYTES].decode('utf-8', errors='ignore')
    reasons = _copy(metadata.get('staleReasons', ()))
    heartwood = metadata.get('heartwood')
    if heartwood is None:
        heartwood = (origin == 'document' and selected.file is not None and
            read_document_declarations(split_markdown(selected.file.source),
                                       file=selected.file.primary.address).heartwood)
    faults = _copy(metadata.get('faults', ()))
    complete = False
    if freshness is not None:
        complete = freshness.complete_for_chunk(address.repository, (chunk.identifier, chunk.version))
        for fault in dependency_faults(freshness, resolver, selected):
            if fault not in faults:
                faults.append(fault)
    checked = bool(metadata.get('checked', freshness is not None))
    ingested = metadata.get('ingested', {})
    checks = [] if freshness is None else [
        {'repository': row.repository, 'state': row.status, 'ingested': ingested.get(row.repository, 0),
         **({'reason': row.reason or 'The required check is pending.'} if row.status != 'done' else {})}
        for row in freshness.repositories]
    reply = {'schema': READ_REPLY, 'id': chunk.identifier, **_place(address), 'origin': origin,
        'kind': chunk.kind, 'text': text, 'cut': cut, 'stale': bool(reasons),
        'staleReasons': reasons, 'heartwood': bool(heartwood),
        'documents': _copy(metadata.get('documents', ())),
        'dependencyCheck': {'complete': bool(complete and not faults), 'faults': faults},
        'freshness': {'checked': checked, 'finished': bool(freshness and freshness.finished),
                      'ingested': sum(ingested.values()), 'repositories': checks}}
    lines = _lines(selected)
    if lines is not None:
        reply['lines'] = lines
    path, disk, unreadable = _file(selected, resolver.settings)
    if path is not None:
        reply['file'] = path
    elif unreadable:
        reply['unreadable'] = unreadable
    if context is not None:
        reply['context'] = {'before': '', 'after': ''}
        if origin == 'code' and disk is not None and lines is not None and context:
            try:
                surrounding = disk.decode('utf-8', errors='strict').splitlines(keepends=True)
            except UnicodeError:
                surrounding = ()
            start, end = lines['start'] - 1, lines['end']
            reply['context'] = {'before': ''.join(surrounding[max(0, start - context):start]),
                                'after': ''.join(surrounding[end:end + context])}
    return reply
