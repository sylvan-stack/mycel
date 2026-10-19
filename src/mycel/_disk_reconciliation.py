"""Checked capture/identity handoff for complete disk locations.

This private boundary persists exact files, chunks and located names together.
Cross-inode moves require checked Git evidence. Git location ingestion,
dependency pins, unlocated-version collection and the ingest command remain
with their owning producers.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
import json
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation, FileChange, IdentityChange, MutationActivity
from ._entities import publish_entities
from ._capture import (CapturedFile, CapturedLocation, CaptureManifest, FileAlias, LocationId,
                      _parse_value, capture_repository, file_from_parse_history, parse_history_record)
from ._code import CODE_IDENTITY_REVISION, CodeChunk, code_identity_key
from ._errors import MycelError
from ._evidence import ComparisonRecord, canonical_json, document_comparisons
from ._identity import ChunkInput, FileIdentityPlan, KnownChunk, KnownVersion, reconcile_file
from ._locks import atomic_transaction, operation_guard, read_snapshot
from ._location_corpus import location_corpus, require_captured_corpus
from ._markdown import MarkdownDocument
from ._safeguards import run_git
from ._scope import RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_bindings import FileBinding, _observe
from ._source_refs import SourceAddress
from ._store import ENTITY_KINDS, checked_store, search_text

_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


def _invalid(message):
    raise MycelError('invalid_input', message)


@dataclass(frozen=True)
class GitFileMove:
    """An explicitly selected local Git rename, verified again before writes.

    Both commits are full object IDs, not movable refs. The old exact file
    version and both root-qualified names bind the proposed file identity.
    Git's rename record and both complete blobs must corroborate the proposal.
    """
    identifier: str
    previous_version: str
    before_commit: str
    after_commit: str
    source: FileAlias
    destination: FileAlias

    def __post_init__(self):
        try:
            object.__setattr__(self, 'identifier', str(UUID(self.identifier)))
            object.__setattr__(self, 'previous_version', str(UUID(self.previous_version)))
        except (ValueError, TypeError, AttributeError):
            _invalid('A recognized Git move needs exact existing file and version UUIDs.')
        if (not all(isinstance(value, str) and _OID.fullmatch(value)
                    for value in (self.before_commit, self.after_commit))
                or not isinstance(self.source, FileAlias) or not isinstance(self.destination, FileAlias)):
            _invalid('A recognized Git move needs full local commit IDs and qualified aliases.')


@dataclass(frozen=True)
class AppliedDiskFile:
    binding: FileBinding
    identity: FileIdentityPlan
    chunk_versions: tuple[tuple[str, int], ...]
    changed: bool


@dataclass(frozen=True)
class DiskCaptureResult:
    files: tuple[AppliedDiskFile, ...]
    retired_locations: tuple[str, ...]
    changed: bool
    counts: dict


_FILES_SQL = """SELECT f.id,f.root,f.path,l.metadata->>'corpus',l.id,v.id,v.source_bytes,l.metadata
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
JOIN public.mycel_file_locations l ON l.file_version=v.id
WHERE f.repository=%s AND l.kind='disk' ORDER BY f.id,l.id"""
_ALIASES_SQL = """SELECT a.file_id,a.root,a.path FROM public.mycel_file_aliases a
JOIN public.mycel_files f ON f.id=a.file_id WHERE f.repository=%s ORDER BY a.file_id,a.root,a.path"""
_CHUNKS_SQL = """SELECT c.file_id,c.id,v.id,v.source_bytes,v.comparison,v.metadata,
l.id,l.file_location,l.kind,l.location,l.metadata FROM public.mycel_chunks c
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
LEFT JOIN public.mycel_locations l ON l.chunk_version=v.id
WHERE c.repository=%s ORDER BY c.id,v.id,l.id"""


def _catalog(connection, repository):
    return (_location_rows(connection.execute(_FILES_SQL, (repository,)).fetchall()),
            connection.execute(_ALIASES_SQL, (repository,)).fetchall(),
            connection.execute(_CHUNKS_SQL, (repository,)).fetchall())


def _location_rows(rows):
    """Validate JSON itself; SQL text coercion cannot authorize a corpus."""
    return [(*row[:3], location_corpus(row[7], legacy=True), *row[4:]) for row in rows]


def _cached_file(row, corpus):
    metadata = row[7]
    try:
        aliases = tuple(sorted(FileAlias(item['root'], item['path']) for item in metadata['aliases']))
        primary = FileAlias(metadata['root'], metadata['path'])
        return file_from_parse_history(bytes(row[6]), corpus, primary, aliases, metadata.get('parseHistory'))
    except (ValueError, TypeError, KeyError):
        return None


def _prior_disk_corpus(row):
    """Recover missing legacy ownership only from complete checked parser data."""
    corpus = location_corpus(row[7], legacy=True)
    checked = [value for value in ('documents', 'code') if _cached_file(row, value) is not None]
    if corpus is not None:
        if checked and checked != [corpus]:
            raise MycelError('store_format', 'A file location corpus contradicts its exact parser evidence.')
        return corpus
    if len(checked) != 1:
        raise MycelError('refused', 'The previous on-disk corpus is unknown; a checked parse history or explicit empty-corpus confirmation is required.')
    return checked[0]


def _guard_disk_corpora(rows, manifest, confirm_empty):
    # Confirmation authorizes unknown/empty prior ownership only. Malformed
    # values and contradictory exact parser evidence always remain refusals.
    previous = set()
    for row in rows:
        if location_corpus(row[7], legacy=True) is None and confirm_empty:
            continue
        previous.add(_prior_disk_corpus(row))
    if not confirm_empty:
        for corpus in sorted(previous):
            if not any(captured.corpus == corpus for captured in manifest.disk.files):
                raise MycelError('refused', f'The on-disk {corpus} corpus became empty; explicit confirmation is required.')


def _parse_history(repository, rows, inventory=()):
    """Prepare advisory parse reuse from committed exact located file bytes.

    The actual scanner still selects roots, reads disk bytes, checks policy and
    enumerates local refs. Incomplete cached Git locations never bypass tree
    acquisition. Legacy rows simply provide no reusable parser result.
    """
    policies = {row[7]['parseHistory']['policyHash'] for row in rows
                if isinstance(row[7].get('parseHistory'), dict)
                and isinstance(row[7]['parseHistory'].get('policyHash'), str)}
    if len(policies) != 1:
        return None
    policy = next(iter(policies))
    groups, counts, observations = {}, {}, {}
    for row in rows:
        metadata = row[7]
        try:
            raw_location = metadata.get('captureLocation', {'kind': 'disk', 'checkout': None, 'identity': 'disk'})
            identifier = LocationId(**raw_location)
            counts[identifier] = counts.get(identifier, 0) + 1
            observations.setdefault(identifier, []).append(metadata)
            aliases = tuple(sorted(FileAlias(item['root'], item['path']) for item in metadata['aliases']))
            primary = FileAlias(metadata['root'], metadata['path'])
            record = metadata.get('parseHistory')
            corpus = location_corpus(metadata, legacy=True)
            captured = None if corpus is None else file_from_parse_history(bytes(row[6]), corpus, primary, aliases, record)
            if corpus is not None and captured is None and _cached_file(row,
                    'code' if corpus == 'documents' else 'documents') is not None:
                raise MycelError('store_format', 'A file location corpus contradicts its exact parser evidence.')
            if captured is not None and record['policyHash'] == policy:
                groups.setdefault(identifier, []).append(captured)
        except (ValueError, TypeError, KeyError):
            continue
    disk_id = LocationId('disk', None, 'disk')
    # Disk reuse is always per file and never skips physical acquisition.
    locations = [CapturedLocation(disk_id, None, tuple(sorted(groups.get(disk_id, ()),
                                                           key=lambda file: file.primary)), False)]
    for item in inventory or ():
        try:
            identifier = LocationId(**item['location'])
            if identifier.kind == 'disk':
                continue
            cached = groups.get(identifier, ())
            observed = observations.get(identifier, ())
            trees = observed[0].get('trees', ()) if observed else ()
            complete = (item['policyHash'] == policy and bool(observed)
                        and len(cached) == counts.get(identifier, 0)
                        and all(type(data.get('captureFileCount')) is int
                                and data['captureFileCount'] == len(cached)
                                and data.get('commit') == item['commit']
                                and data.get('trees') == trees for data in observed))
            locations.append(CapturedLocation(identifier, item['commit'],
                tuple(sorted(cached, key=lambda file: file.primary)), complete, tuple(trees)))
        except (ValueError, TypeError, KeyError):
            continue
    return CaptureManifest(repository, policy, tuple(locations), False)


def _aliases(row, repository, global_aliases):
    metadata = row[7]
    records = metadata.get('aliases', [{'root': row[1], 'path': row[2]}] +
        [{'root': root, 'path': path} for file_id, root, path in global_aliases if file_id == row[0]])
    return tuple(SourceAddress(repository, item['root'], item['path']) for item in records)


def _absolute(binding):
    return str(Path(binding['absoluteRoot']) / binding['path'])


def _same_capture(expected, fresh):
    # A prior capture can legitimately retain another primary among the same
    # observed aliases. Normalize only that choice/order; exact parse data,
    # bytes, roots, policy and all Git location observations must still match.
    def normalized(manifest):
        locations = []
        for location in manifest.locations:
            files = []
            for captured in location.files:
                if not isinstance(captured, CapturedFile) or captured.primary not in captured.aliases:
                    _invalid('The capture primary must belong to its exact observed aliases.')
                # Tagged inert values also compare supported YAML NaN values
                # canonically; ordinary float equality would reject identical
                # complete source after reconstructing an unchanged parse.
                try:
                    parsed = _parse_value(captured.parsed)
                except (ValueError, TypeError, RecursionError):
                    _invalid('The capture requires an inert supported parse.')
                files.append(replace(captured, primary=min(captured.aliases), parsed=parsed))
            locations.append(replace(location, files=tuple(sorted(files,
                key=lambda item: tuple(alias.address(manifest.repository) for alias in item.aliases)))))
        return replace(manifest, locations=tuple(locations))
    left, right = normalized(expected), normalized(fresh)
    return left == right and left.manifest_hash == right.manifest_hash


def _chunk_input(source, comparison, metadata):
    raw = bytes(source)
    if metadata['kind'] == 'document':
        body_span = metadata['bodySpan']
        body = raw[body_span['start']:body_span['end']].decode('utf-8', errors='strict')
        return ChunkInput(metadata['name'], 'document', raw,
            ComparisonRecord.from_record(comparison['body']), body, metadata.get('title'),
            ComparisonRecord.from_record(comparison['title']))
    span = metadata.get('declarationNameSpan')
    parsed = CodeChunk('', metadata['name'], metadata['kind'], metadata.get('language', 'unknown'),
                       raw.decode('utf-8', errors='strict'), 1, 1, 0, len(raw),
                       None if span is None else tuple(span))
    key = code_identity_key(parsed)
    if metadata.get('identityKey') != key or (key is not None
            and metadata.get('identityRevision') != CODE_IDENTITY_REVISION):
        raise MycelError('store_format', 'A retained code identity projection is incompatible.')
    return ChunkInput(metadata['name'], 'code', raw, ComparisonRecord.from_record(comparison),
                      code_rename_key=key)


def _known(file_id, old_location, rows):
    by_chunk = {}
    for row in rows:
        # An entity row keeps its UUID in every location; the two matching
        # rounds never see it (MYC-17).
        if str(row[0]) == file_id and row[5].get('kind') not in ENTITY_KINDS:
            by_chunk.setdefault(str(row[1]), []).append(row)
    known = []
    for identifier, history in sorted(by_chunk.items()):
        located = [row for row in history if row[6] is not None]
        if not located:
            continue  # Unlocated leftovers do not supply a guessed identity.
        current = min(located, key=lambda row: (str(row[7]) != old_location,
                      {'disk': 0, 'branch': 1, 'stash': 2, 'index': 3}[row[8]], row[9], row[2]))
        versions = []
        for version in sorted({row[2] for row in history}):
            records = [row for row in history if row[2] == version]
            first = records[0]
            metadata = dict(first[5])
            if version == current[2]:
                metadata.update({key: value for key, value in current[10].items()
                                 if key in {'name', 'kind', 'title'}})
            names = tuple(name for row in records if row[6] is not None
                          if (name := row[10].get('name', row[5]['name'])))
            versions.append(KnownVersion(version, _chunk_input(first[3], first[4], metadata), names))
        known.append(KnownChunk(identifier, current[2], tuple(versions)))
    return tuple(known)


def _inputs(captured):
    parsed = captured.parsed
    if captured.failure is not None:
        _invalid('A failed complete-file parse cannot publish a disk identity plan.')
    if isinstance(parsed, MarkdownDocument):
        if parsed.source != captured.source or parsed.file_hash != captured.file_hash:
            _invalid('The parsed document does not reproduce its complete captured bytes.')
        return tuple(ChunkInput.document(chunk) for chunk in parsed.chunks)
    if isinstance(parsed, tuple) and all(isinstance(chunk, CodeChunk) for chunk in parsed):
        for chunk in parsed:
            if captured.source[chunk.byte_start:chunk.byte_end] != chunk.text.encode('utf-8'):
                _invalid('A parsed code chunk does not reproduce its captured byte range.')
        return tuple(ChunkInput.code(chunk) for chunk in parsed)
    _invalid('A disk identity handoff requires a complete supported parse.')


def _metadata(captured, index):
    chunk = captured.parsed.chunks[index] if isinstance(captured.parsed, MarkdownDocument) else captured.parsed[index]
    raw = chunk.text.encode('utf-8')
    if isinstance(captured.parsed, MarkdownDocument):
        return {'name': chunk.name, 'kind': 'document', 'title': chunk.title,
                'span': {'start': chunk.span.byte_start, 'end': chunk.span.byte_end},
                'bodySpan': {'start': len(raw) - len(chunk.body.encode('utf-8')), 'end': len(raw)}}
    metadata = {'name': chunk.symbol, 'kind': chunk.kind, 'language': chunk.language,
                'span': {'start': chunk.byte_start, 'end': chunk.byte_end}}
    # The parser's structural class membership is represented by its qualified
    # symbol, independently of this conservative rename projection.
    if '.' in chunk.symbol:
        metadata['family'] = chunk.symbol.rsplit('.', 1)[0]
    key = code_identity_key(chunk)
    if key is not None:
        metadata.update({'identityKey': key, 'identityRevision': CODE_IDENTITY_REVISION,
                         'declarationNameSpan': list(chunk.declaration_name_span)})
    return metadata


def _git_bytes(args, checkout, expected):
    reply = run_git(args, cwd=checkout, stdout_limit=max(1, len(expected) + 1))
    if reply.returncode or reply.stdout != expected:
        _invalid('The recognized Git move does not reproduce its complete exact file versions.')


def _verify_git_move(repository, row, captured, physical, move):
    if str(row[0]) != move.identifier or str(row[5]) != move.previous_version:
        _invalid('The recognized Git move has an obsolete existing file version.')
    prior = [item for item in row[7].get('physicalBindings', ())
             if item['root'] == move.source.root and item['path'] == move.source.path]
    incoming = [(alias, observed) for alias, observed in zip(captured.aliases, physical)
                if alias == move.destination]
    if len(prior) != 1 or len(incoming) != 1:
        _invalid('The recognized Git move does not name exact old and new physical bindings.')
    old_path = Path(_absolute(prior[0]))
    try:
        old_path.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        _invalid('The original physical move source cannot be checked.')
    else:
        _invalid('A recognized move cannot override an existing original physical path.')
    alias, observed = incoming[0]
    root = Path(observed['root'])
    reply = run_git(('rev-parse', '--show-toplevel'), cwd=root)
    if reply.returncode:
        _invalid('The recognized move requires one readable local Git checkout.')
    try:
        checkout = Path(reply.stdout.decode('utf-8', errors='strict').rstrip('\n'))
        before = old_path.relative_to(checkout).as_posix()
        after = (root / alias.path).relative_to(checkout).as_posix()
    except (ValueError, UnicodeError):
        _invalid('The recognized move must stay within the same checked Git checkout.')
    # Require commit objects, not a tree/blob that happens to reproduce text.
    for commit in (move.before_commit, move.after_commit):
        kind = run_git(('cat-file', '-t', commit), cwd=checkout)
        if kind.returncode or kind.stdout != b'commit\n':
            _invalid('The recognized move commits are unavailable local commit objects.')
    _git_bytes(('show', f'{move.before_commit}:{before}'), checkout, bytes(row[6]))
    _git_bytes(('show', f'{move.after_commit}:{after}'), checkout, captured.source)
    reply = run_git(('diff', '-M', '--name-status', '-z', move.before_commit, move.after_commit, '--'), cwd=checkout)
    if reply.returncode:
        _invalid('The local Git rename evidence cannot be read.')
    try:
        fields = reply.stdout.decode('utf-8', errors='strict').split('\0')
        if fields[-1] != '':
            _invalid('The local Git rename evidence is incomplete.')
        fields.pop()
        renames = []
        while fields:
            status = fields.pop(0)
            if status.startswith(('R', 'C')):
                source, destination = fields.pop(0), fields.pop(0)
                if re.fullmatch(r'R(?:100|0[0-9]{2}|[0-9]{1,2})', status):
                    renames.append((source, destination))
            else:
                fields.pop(0)
    except (UnicodeError, IndexError):
        _invalid('The local Git rename evidence is malformed.')
    if renames.count((before, after)) != 1:
        _invalid('Git did not recognize the selected source/destination as a rename.')
    return {'kind': 'git', 'beforeCommit': move.before_commit, 'afterCommit': move.after_commit,
            'previousVersion': move.previous_version, 'source': move.source.address(repository.name),
            'destination': move.destination.address(repository.name)}


class DiskCaptureStore:
    """Apply one complete disk capture, retaining every other stored location.

    ``file_handoff(connection, AppliedDiskFile)`` runs after exact identity rows
    are present, inside the same transaction. A dependency producer can consume
    the explicit pin decisions there; it must not commit, nest a transaction or
    invoke a provider. Failure rolls back file/hash/chunk/location/audit writes.
    """
    def __init__(self, connection):
        self.connection = connection

    def capture(self, settings: SettingsSnapshot, repository: str) -> CaptureManifest:
        """Read a fresh complete capture, reusing committed unchanged parses."""
        settings.require_valid(require_store=False)
        settings.require_current()
        with checked_store(self.connection), read_snapshot(self.connection):
            rows, _, _ = _catalog(self.connection, repository)
        return capture_repository(settings, repository, previous=_parse_history(repository, rows))

    def apply(self, settings: SettingsSnapshot, manifest: CaptureManifest | str, *,
              recognized_moves: tuple[GitFileMove, ...] = (), confirm_empty: bool = False,
              file_handoff: Callable | None = None, activity: MutationActivity | None = None,
              reply_counts: Callable | None = None) -> DiskCaptureResult:
        settings.require_valid(require_store=False)
        if not isinstance(manifest, (CaptureManifest, str)):
            _invalid('A disk handoff requires a complete captured manifest.')
        name = manifest if isinstance(manifest, str) else manifest.repository
        selected = RepositoryLocations(settings).named(name)
        if (len(selected) != 1 or not selected[0].enabled
                or (isinstance(manifest, CaptureManifest) and not manifest.deletion_safe)
                or type(recognized_moves) is not tuple
                or any(not isinstance(move, GitFileMove) for move in recognized_moves)
                or len({move.identifier for move in recognized_moves}) != len(recognized_moves)
                or (file_handoff is not None and not callable(file_handoff))
                or (reply_counts is not None and not callable(reply_counts))
                or (activity is not None and activity.connection is not self.connection)):
            _invalid('A disk handoff requires one enabled repository, a complete parse and exact transaction callbacks.')
        repository = selected[0]
        with checked_store(self.connection), operation_guard(self.connection, repository.name, 'pass'):
            settings.require_current()
            with read_snapshot(self.connection):
                original = _catalog(self.connection, repository.name)
            rows, aliases, chunks = original
            history = _parse_history(repository.name, rows)
            if isinstance(manifest, str):
                manifest = capture_repository(settings, repository.name, previous=history)
            if not manifest.deletion_safe:
                _invalid('A disk handoff requires a complete supported parse.')
            _guard_disk_corpora(rows, manifest, confirm_empty)
            # The actual configured scanner, not a caller's asserted complete
            # flag, proves every location and closes the enumeration guard.
            fresh = capture_repository(settings, repository.name, previous=history)
            if not fresh.deletion_safe or not _same_capture(manifest, fresh):
                _invalid('The complete capture changed before disk reconciliation.')
            prepared, used, move_evidence = [], set(), {}
            moves = {move.destination: move for move in recognized_moves}
            if len(moves) != len(recognized_moves):
                _invalid('Recognized moves must have distinct destinations.')
            observed_files = []
            for captured in manifest.disk.files:
                addresses = tuple(SourceAddress(repository.name, alias.root, alias.path) for alias in captured.aliases)
                physical = _observe(repository, addresses, captured.source)
                identities = {tuple(item['fileIdentity'][:2]) for item in physical}
                if len(identities) != 1:
                    _invalid('The complete captured aliases reach different physical files.')
                observed_files.append((captured, addresses, physical, next(iter(identities))))
            present_identities = {item[3] for item in observed_files}
            for captured, addresses, physical, identity in observed_files:
                inputs = _inputs(captured)
                bindings = [{'root': alias.root, 'path': alias.path, 'absoluteRoot': observed['root'],
                             'rootIdentity': observed['rootIdentity']} for alias, observed in zip(captured.aliases, physical)]
                stable_paths = {(_absolute(item), tuple(item['rootIdentity'])) for item in bindings}
                matching = [row for row in rows if tuple(row[7].get('physicalIdentity', ())) == identity
                    or (tuple(row[7].get('physicalIdentity', ())) not in present_identities
                        and stable_paths.intersection((_absolute(item), tuple(item['rootIdentity']))
                                                      for item in row[7].get('physicalBindings', ())))]
                move = next((moves[alias] for alias in captured.aliases if alias in moves), None)
                if move is not None:
                    proposed = [row for row in rows if str(row[0]) == move.identifier]
                    if len(proposed) != 1 or (matching and matching != proposed):
                        _invalid('The recognized move conflicts with current physical file identity.')
                    move_evidence[move.identifier] = _verify_git_move(repository, proposed[0], captured, physical, move)
                    matching = proposed
                if len(matching) > 1 or (matching and str(matching[0][0]) in used):
                    _invalid('The capture does not establish one unambiguous file identity.')
                old = matching[0] if matching else None
                identifier = str(old[0]) if old else str(uuid4())
                used.add(identifier)
                discovered = min(zip(addresses, physical), key=lambda pair:
                    (-len(Path(pair[1]['root']).parts), pair[0].root != 'artifact', pair[0].address))[0]
                previous = None if old is None else SourceAddress(repository.name,
                    old[7].get('root', old[1]), old[7].get('path', old[2]))
                primary = previous if previous in addresses else discovered
                prior_aliases = () if old is None else _aliases(old, repository.name, aliases)
                historical = set((item['root'], item['path']) for item in (() if old is None else old[7].get('recognizedMoves', ())))
                historical.update((alias.root, alias.path) for alias in prior_aliases if alias not in addresses)
                metadata = {**({} if old is None else old[7]), 'root': primary.root, 'path': primary.path,
                    'corpus': captured.corpus,
                    'aliases': [{'root': alias.root, 'path': alias.path} for alias in addresses],
                    'parseHistory': parse_history_record(replace(captured, primary=FileAlias(primary.root, primary.path)),
                                                        manifest.policy_hash),
                    'physicalIdentity': list(identity), 'physicalBindings': bindings,
                    'recognizedMoves': [{'root': root, 'path': path} for root, path in sorted(historical)]}
                if identifier in move_evidence:
                    metadata['moveEvidence'] = [*metadata.get('moveEvidence', ()), move_evidence[identifier]]
                known = _known(identifier, None if old is None else str(old[4]), chunks)
                plan = reconcile_file(inputs, known)
                prior_disk_ids = set() if old is None else {str(item[1]) for item in chunks if item[7] == old[4]}
                # Branch-only chunks remain candidates for restoration, but
                # their continuing absence is not another disk removal/write.
                plan = replace(plan, removed=tuple(item for item in plan.removed if item.chunk_id in prior_disk_ids))
                prepared.append((captured, old, identifier, primary, addresses, metadata, known, plan, physical))
            if {move.identifier for move in recognized_moves} != set(move_evidence):
                _invalid('Every recognized move must bind exactly one captured destination.')
            output = None

            def write(connection):
                nonlocal output
                settings.require_current()
                if _catalog(connection, repository.name) != original:
                    _invalid('The stored identity catalog changed before publication.')
                final_capture = capture_repository(settings, repository.name, previous=fresh)
                if not final_capture.deletion_safe or not _same_capture(manifest, final_capture):
                    _invalid('The complete capture changed before location retirement.')
                for captured, old, _, _, addresses, _, _, _, physical in prepared:
                    if _observe(repository, addresses, captured.source) != physical:
                        _invalid('The complete physical file changed before publication.')
                    for move in recognized_moves:
                        if old is not None and move.identifier == str(old[0]):
                            _verify_git_move(repository, old, captured, physical, move)
                retired = tuple(str(row[4]) for row in rows if str(row[0]) not in used)
                applied, file_changes, decisions = [], [], []
                counts = {'files': {'scanned': len(prepared), 'changed': 0, 'removed': len(retired)},
                          'chunks': {reason: 0 for reason in ('unchanged', 'edited', 'renamed', 'new', 'removed')}}
                for captured, old, identifier, primary, addresses, metadata, known, plan, _ in prepared:
                    unchanged = (old is not None and bytes(old[6]) == captured.source and old[3] == captured.corpus
                        and old[7] == metadata and all(item.reason == 'unchanged' and item.version_action == 'reuse_existing'
                                                       for item in plan.decisions) and not plan.removed)
                    if unchanged:
                        binding = FileBinding(identifier, str(old[5]), str(old[4]), primary, addresses)
                        versions = tuple((item.chunk_id, item.version_id) for item in plan.decisions)
                    else:
                        binding, versions = self._write_file(connection, repository.name, captured, old,
                                                             identifier, primary, addresses, metadata, plan)
                        counts['files']['changed'] += 1
                        file_changes.append(FileChange(primary.root, primary.path, 'disk', 'added' if old is None else 'changed'))
                        by_id = {chunk.identifier: chunk for chunk in known}
                        for item, (chunk_id, _) in zip(plan.decisions, versions):
                            previous_name = by_id[item.chunk_id].current.chunk.name if item.reason == 'renamed' else None
                            decisions.append(IdentityChange(primary.root, primary.path, 'disk', UUID(chunk_id),
                                                            item.reason, item.incoming.name, previous_name))
                        decisions.extend(IdentityChange(primary.root, primary.path, 'disk', UUID(item.chunk_id),
                            'removed', by_id[item.chunk_id].current.chunk.name) for item in plan.removed)
                    current = AppliedDiskFile(binding, plan, versions, not unchanged)
                    if file_handoff is not None and current.changed:
                        file_handoff(connection, current)
                    applied.append(current)
                    for item in (*plan.decisions, *plan.removed):
                        counts['chunks'][item.reason] += 1
                for row in rows:
                    if str(row[4]) in retired:
                        removed_chunks = {str(item[1]): item for item in chunks if item[7] == row[4]}
                        for identifier, item in sorted(removed_chunks.items()):
                            counts['chunks']['removed'] += 1
                            decisions.append(IdentityChange(row[7].get('root', row[1]), row[7].get('path', row[2]),
                                'disk', UUID(identifier), 'removed', item[10].get('name', item[5]['name'])))
                        connection.execute('DELETE FROM public.mycel_locations WHERE file_location=%s', (row[4],))
                        connection.execute('DELETE FROM public.mycel_file_locations WHERE id=%s', (row[4],))
                        file_changes.append(FileChange(row[7].get('root', row[1]), row[7].get('path', row[2]), 'disk', 'removed'))
                changed = bool(file_changes)
                output = DiskCaptureResult(tuple(applied), retired, changed, counts)
                cumulative = counts if reply_counts is None else reply_counts(repository.name, counts)
                settings.require_current()
                complete = capture_repository(settings, repository.name, previous=fresh)
                if not complete.deletion_safe or not _same_capture(manifest, complete):
                    _invalid('The complete capture changed during disk publication.')
                for captured, old, _, _, addresses, _, _, _, physical in prepared:
                    if _observe(repository, addresses, captured.source) != physical:
                        _invalid('The complete physical file changed during disk publication.')
                    for move in recognized_moves:
                        if old is not None and move.identifier == str(old[0]):
                            _verify_git_move(repository, old, captured, physical, move)
                return AppliedMutation(changed, cumulative, tuple(file_changes), tuple(decisions))

            if activity is None:
                with atomic_transaction(self.connection):
                    write(self.connection)
            else:
                activity.apply(repository.name, 'ingest', write)
            return output

    @staticmethod
    def _write_file(connection, repository, captured, old, identifier, primary, aliases, metadata, plan):
        require_captured_corpus(metadata, captured)
        connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                           (repository, Jsonb([])))
        if old is not None:
            inherited = [{'root': item.root, 'path': item.path} for item in _aliases(old, repository, connection.execute(
                _ALIASES_SQL, (repository,)).fetchall())]
            retained = connection.execute('SELECT l.id,l.metadata FROM public.mycel_file_locations l '
                'JOIN public.mycel_file_versions v ON v.id=l.file_version WHERE v.file_id=%s AND l.kind<>%s',
                (identifier, 'disk')).fetchall()
            for location, data in retained:
                if not all(key in data for key in ('root', 'path', 'aliases')):
                    connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                        (Jsonb({'root': old[1], 'path': old[2], 'aliases': inherited, **data}), location))
        connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE '
            'SET root=EXCLUDED.root,path=EXCLUDED.path,corpus=EXCLUDED.corpus',
            (identifier, repository, primary.root, primary.path, captured.corpus))
        connection.execute('DELETE FROM public.mycel_file_aliases WHERE file_id=%s', (identifier,))
        for alias in aliases:
            connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)', (identifier, alias.root, alias.path))
        version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
            'ON CONFLICT(file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
            (uuid4(), identifier, captured.file_hash, captured.source, Jsonb({}))).fetchone()[0]
        location = old[4] if old is not None and str(old[5]) == str(version) else uuid4()
        if old is not None:
            connection.execute('DELETE FROM public.mycel_locations WHERE file_location=%s', (old[4],))
            if location != old[4]:
                connection.execute('DELETE FROM public.mycel_file_locations WHERE id=%s', (old[4],))
        connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) '
            'ON CONFLICT(id) DO UPDATE SET metadata=EXCLUDED.metadata', (location, version, 'disk', 'disk', Jsonb(metadata)))
        persisted = []
        for item in plan.decisions:
            chunk_id = item.chunk_id or str(uuid4())
            details = _metadata(captured, item.incoming_index)
            connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',
                               (chunk_id, repository, identifier, details['kind'], Jsonb({})))
            comparison = document_comparisons(item.incoming.body, item.incoming.title or '') if item.incoming.kind == 'document' else item.incoming.comparison.as_dict()
            exact = connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id',
                (chunk_id, item.incoming.snapshot_hash, item.incoming.source, search_text(item.incoming.source),
                 Jsonb(json.loads(canonical_json(comparison))), Jsonb(details))).fetchone()[0]
            connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                               (uuid4(), exact, location, 'disk', 'disk', Jsonb(details)))
            persisted.append((chunk_id, exact))
        publish_entities(connection, repository, identifier, location, captured)
        return FileBinding(identifier, str(version), str(location), primary, aliases), tuple(persisted)
