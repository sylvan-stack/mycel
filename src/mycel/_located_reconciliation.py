"""Checked publication of complete disk, local-branch and stash captures.

This private seam publishes exact identity/location rows. It retains unlocated
versions and their own dependency/evidence rows for a later guarded collection
producer; it does not implement dependency reconciliation or public ingest.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from inspect import getattr_static
from pathlib import Path
import json
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._entities import publish_entities
from ._activity import AppliedMutation, FileChange, IdentityChange, MutationActivity
from ._capture import CaptureManifest, FileAlias, LocationId, capture_repository, parse_history_record
from ._disk_reconciliation import (_ALIASES_SQL, _CHUNKS_SQL, GitFileMove, _absolute,
    _aliases, _guard_disk_corpora, _inputs, _invalid, _known, _location_rows, _metadata,
    _parse_history, _same_capture, _verify_git_move)
from ._errors import MycelError
from ._evidence import canonical_json, document_comparisons
from ._identity import FileIdentityPlan, reconcile_file
from ._git_correspondence import GitFileSnapshot, GitPlace, build_correspondences
from ._locks import atomic_transaction, operation_guard, read_snapshot
from ._location_corpus import require_captured_corpus
from ._safeguards import run_git
from ._scope import RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_bindings import FileBinding, _observe
from ._source_refs import SourceAddress
from ._source_refs import read_document_declarations
from ._declared_refs import _safe_json
from ._store import checked_store, search_text


@dataclass(frozen=True)
class AppliedLocatedFile:
    location: LocationId
    commit: str | None
    binding: FileBinding
    identity: FileIdentityPlan
    chunk_versions: tuple[tuple[str, int], ...]
    changed: bool
    previous_versions: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class LocatedCaptureResult:
    files: tuple[AppliedLocatedFile, ...]
    retired_locations: tuple[str, ...]
    changed: bool
    counts: dict
    repository: str
    activity: MutationActivity | None = None
    reply_counts: Callable | None = None
    dependency_changes: set[str] = field(default_factory=set)


_FILES_SQL = """SELECT f.id,f.root,f.path,l.metadata->>'corpus',l.id,v.id,v.source_bytes,l.metadata,l.kind,l.location
FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
JOIN public.mycel_file_locations l ON l.file_version=v.id
WHERE f.repository=%s ORDER BY f.id,l.id"""


# Reconciliation of one file needs all of that file's retained versions, not
# every other file's chunks and parse metadata again.
_FILE_CHUNKS_SQL = _CHUNKS_SQL.replace('WHERE c.repository=%s',
                                      'WHERE c.repository=%s AND c.file_id=%s')
_FILE_LOCATIONS_SQL = _FILES_SQL.replace('WHERE f.repository=%s',
                                        'WHERE f.repository=%s AND f.id=%s')


def _catalog(connection, repository):
    return (_location_rows(connection.execute(_FILES_SQL, (repository,)).fetchall()),
            connection.execute(_ALIASES_SQL, (repository,)).fetchall(),
            connection.execute(_CHUNKS_SQL, (repository,)).fetchall(),
            connection.execute('SELECT read_locations FROM public.mycel_repository_state WHERE repository=%s',
                               (repository,)).fetchone(),
            connection.execute('SELECT f.id,f.root,f.path,f.corpus,v.id,v.snapshot_hash,v.source_bytes,v.metadata '
                'FROM public.mycel_files f LEFT JOIN public.mycel_file_versions v ON v.file_id=f.id '
                'WHERE f.repository=%s ORDER BY f.id,v.id', (repository,)).fetchall())


def location_key(identifier: LocationId) -> str:
    """Unambiguous persisted selector, including the configured checkout anchor."""
    if identifier.kind == 'disk':
        return 'disk'
    return canonical_json(identifier.record()).decode('utf-8')


def capture_differences(repository: str, expected: CaptureManifest, actual: CaptureManifest) -> list[str]:
    """Name every file and location of `actual` that differs from `expected`.

    A file is named by its address, `repo:@root/path`; a location that appeared,
    disappeared, moved to another commit or could not be read completely by its
    kind and identity, such as `branch refs/heads/feature`. The list is what a pass reports
    under `changedDuringPass` (MYC-1.37): the next pass picks these up.
    """
    names = set()
    before = {location.id: location for location in expected.locations}
    after = {location.id: location for location in actual.locations}
    for identifier in set(before) | set(after):
        label = f'{identifier.kind} {identifier.identity}'
        if identifier not in before or identifier not in after:
            names.add(label)
            continue
        left, right = before[identifier], after[identifier]
        if left.commit != right.commit or not right.complete:
            names.add(label)
        files_before = {file.primary: file for file in left.files}
        files_after = {file.primary: file for file in right.files}
        for primary in set(files_before) | set(files_after):
            one, other = files_before.get(primary), files_after.get(primary)
            if (one is None or other is None or one.source != other.source or other.failure is not None
                    or set(one.aliases) != set(other.aliases)):
                names.add(primary.address(repository))
    return sorted(names)


def _scopes(repository):
    scopes = {}
    try:
        for root, folder in (('code', repository.code), ('artifact', repository.documents)):
            if folder is None:
                continue
            path = folder.path.resolve(strict=True)
            info = path.stat()
            reply = run_git(('rev-parse', '--show-toplevel'), cwd=path)
            if reply.returncode == 0:
                checkout = Path(reply.stdout.decode('utf-8', errors='strict').removesuffix('\n')).resolve(strict=True)
                if not path.is_relative_to(checkout):
                    _invalid('A located binding has an invalid Git checkout scope.')
                scope_info = checkout.stat()
                scope = {'path': str(checkout), 'identity': [scope_info.st_dev, scope_info.st_ino]}
            else:
                # Complete capture already proved whether this is a checkout.
                scope = {'path': str(path), 'identity': [info.st_dev, info.st_ino]}
            scopes[root] = {'absoluteRoot': str(path), 'rootIdentity': [info.st_dev, info.st_ino],
                            'scope': scope}
    except (OSError, RuntimeError, UnicodeError, ValueError):
        _invalid('The configured physical roots changed before located publication.')
    return scopes


def _logical(bindings):
    return {(str(Path(item['absoluteRoot']) / item['path']), item['scope']['path'],
             tuple(item['scope']['identity'])) for item in bindings}


def _bindings(captured, scopes):
    return [{'root': alias.root, 'path': alias.path, **scopes[alias.root]} for alias in captured.aliases]


def _prior_logical(row, scopes):
    if 'logicalBindings' in row[7]:
        return _logical(row[7]['logicalBindings'])
    # Upgrade verified disk bindings without assigning a legacy branch's bare
    # portable address to today's possibly retargeted physical root.
    verified = []
    for item in row[7].get('physicalBindings', ()):
        scope = scopes.get(item['root'])
        if scope is not None and item['absoluteRoot'] == scope['absoluteRoot'] and item['rootIdentity'] == scope['rootIdentity']:
            verified.append({**item, 'scope': scope['scope']})
    return _logical(verified)


def _git_snapshots(manifest, rows, scopes):
    inputs = []
    for location in manifest.locations:
        if location.id.kind == 'disk':
            continue
        scope = scopes[location.id.checkout]['scope']
        checkout = Path(scope['path'])
        for captured in location.files:
            places = {str((Path(item['absoluteRoot']) / item['path']).relative_to(checkout))
                      for item in _bindings(captured, scopes) if item['scope'] == scope}
            if len(places) != 1:
                _invalid('A captured Git file needs one checked checkout-relative place.')
            inputs.append(GitFileSnapshot(GitPlace(str(checkout), tuple(scope['identity']), next(iter(places))),
                                          location.commit, captured.source, captured.aliases))
    for row in rows:
        if row[8] == 'disk' or row[7].get('commit') is None:
            continue
        bindings = [item for item in row[7].get('logicalBindings', ()) if item['root'] in scopes
                    and item['absoluteRoot'] == scopes[item['root']]['absoluteRoot']
                    and item['rootIdentity'] == scopes[item['root']]['rootIdentity']
                    and item['scope'] == scopes[item['root']]['scope']]
        if not bindings:
            continue
        # A retained proof belongs only to its original checked physical roots.
        # Retargeting a root cannot make yesterday's name today's file identity.
        places = {(item['scope']['path'], tuple(item['scope']['identity']),
                   str((Path(item['absoluteRoot']) / item['path']).relative_to(item['scope']['path'])))
                  for item in bindings}
        if len(places) != 1:
            _invalid('A retained Git file has conflicting checked checkout scopes.')
        inputs.append(GitFileSnapshot(GitPlace(*next(iter(places))), row[7]['commit'], bytes(row[6]),
            tuple(sorted(FileAlias(item['root'], item['path']) for item in bindings))))
    return tuple(inputs)


def _git_matches(captured, logical, candidates, correspondences, scopes):
    matches = []
    for peer, chain in correspondences.peers(_logical(logical), captured.source):
        for row in candidates:
            verified = (_logical(item for item in row[7]['logicalBindings'] if item['root'] in scopes
                        and item['absoluteRoot'] == scopes[item['root']]['absoluteRoot']
                        and item['rootIdentity'] == scopes[item['root']]['rootIdentity']
                        and item['scope'] == scopes[item['root']]['scope'])
                        if 'logicalBindings' in row[7] else _prior_logical(row, scopes))
            if peer.place.logical in verified and bytes(row[6]) == peer.source:
                matches.append((row, peer, chain))
    return matches


class LocatedCaptureStore:
    """Publish one complete capture atomically, retiring only absent locations.

    On a changed capture, callbacks run after all prospective identity rows and
    location retirements within this transaction. No-op captures invoke no
    handoff callbacks; reply_counts still receives their complete local counts.
    Callbacks must not commit, nest transactions or call a provider. Dependency
    changes on otherwise unchanged captures need their producer's refresh hook.
    Mechanical detection always follows both corpora and those handoffs in this
    publication transaction. Baseline application and collection remain external.
    """
    def __init__(self, connection):
        self.connection = connection

    def capture(self, settings: SettingsSnapshot, repository: str) -> CaptureManifest:
        """Read actual source inputs with committed, fingerprinted parse reuse."""
        settings.require_valid(require_store=False)
        settings.require_current()
        with checked_store(self.connection), read_snapshot(self.connection):
            rows, _, _, state, _ = _catalog(self.connection, repository)
        history = _parse_history(repository, rows, () if state is None else state[0])
        return capture_repository(settings, repository, previous=history)

    def apply(self, settings: SettingsSnapshot, manifest: CaptureManifest | str, *,
              recognized_moves: tuple[GitFileMove, ...] = (), confirm_empty: bool = False,
              file_handoff: Callable | None = None, batch_handoff: Callable | None = None,
              activity: MutationActivity | None = None, reply_counts: Callable | None = None,
              targeted_detection: bool = False, publish_capture: bool = False) -> LocatedCaptureResult:
        """Publish one complete capture.

        With `publish_capture` the pass publishes the capture it read (MYC-1.37,
        MYC-D64): a disk or Git change after the capture is named in the counts
        under `changedDuringPass` instead of refusing the publication, and the
        producers observe the pass's own repository through the capture. Without
        it every reread must match the capture exactly, as internal callers and
        the mutations of MYC-16 require.
        """
        settings.require_valid(require_store=False)
        if not isinstance(manifest, (CaptureManifest, str)):
            _invalid('Located publication requires a complete captured manifest.')
        name = manifest if isinstance(manifest, str) else manifest.repository
        selected = RepositoryLocations(settings).named(name)
        if (len(selected) != 1 or not selected[0].enabled
                or (isinstance(manifest, CaptureManifest) and not manifest.deletion_safe)
                or type(recognized_moves) is not tuple
                or any(not isinstance(move, GitFileMove) for move in recognized_moves)
                or len({move.identifier for move in recognized_moves}) != len(recognized_moves)
                or len({move.destination for move in recognized_moves}) != len(recognized_moves)
                or type(targeted_detection) is not bool or type(publish_capture) is not bool
                or any(callback is not None and not callable(callback)
                       for callback in (file_handoff, batch_handoff, reply_counts))
                or (activity is not None and activity.connection is not self.connection)):
            _invalid('Located publication requires one enabled repository and exact transaction callbacks.')
        repository = selected[0]
        from ._staleness import MechanicalStalenessStore, detection_guards
        with checked_store(self.connection), operation_guard(self.connection, repository.name, 'pass'):
            settings.require_current()
            with read_snapshot(self.connection):
                original = _catalog(self.connection, repository.name)
            rows, aliases, chunks, state, _ = original
            history = _parse_history(repository.name, rows, () if state is None else state[0])
            if isinstance(manifest, str):
                manifest = capture_repository(settings, repository.name, previous=history)
            if not manifest.deletion_safe:
                _invalid('Located publication requires a complete supported parse.')
            _guard_disk_corpora([row for row in rows if row[8] == 'disk'], manifest, confirm_empty)
            fresh = manifest
            if not publish_capture:
                fresh = capture_repository(settings, repository.name, previous=history)
                if not fresh.deletion_safe or not _same_capture(manifest, fresh):
                    _invalid('The complete capture changed before located reconciliation.')
            scopes = _scopes(repository)
            correspondences = build_correspondences(_git_snapshots(manifest, rows, scopes))
            observed = {}
            for captured in manifest.disk.files:
                addresses = tuple(SourceAddress(repository.name, alias.root, alias.path) for alias in captured.aliases)
                # A pass that publishes its capture records the physical identity
                # of each file and does not require its bytes to be the capture's.
                physical = _observe(repository, addresses, None if publish_capture else captured.source)
                identities = {tuple(item['fileIdentity'][:2]) for item in physical}
                if len(identities) != 1:
                    _invalid('Captured disk aliases reach different physical files.')
                observed[captured.primary] = (addresses, physical, next(iter(identities)))
            present_identities = {value[2] for value in observed.values()}
            output = None
            final_verify = None

            def write(connection):
                nonlocal output, final_verify
                settings.require_current()
                if _catalog(connection, repository.name) != original:
                    _invalid('The stored located identity catalog changed before publication.')
                if _scopes(repository) != scopes:
                    _invalid('The physical root scope changed before publication.')
                if not publish_capture:
                    final = capture_repository(settings, repository.name, previous=fresh)
                    if not final.deletion_safe or not _same_capture(manifest, final):
                        _invalid('The complete capture changed before publication.')
                if build_correspondences(_git_snapshots(manifest, rows, scopes)) != correspondences:
                    _invalid('The checked local Git rename correspondence changed before publication.')
                if not publish_capture:
                    for captured in manifest.disk.files:
                        addresses, physical, _ = observed[captured.primary]
                        if _observe(repository, addresses, captured.source) != physical:
                            _invalid('The complete physical file changed before publication.')
                applied, file_changes, decisions, kept, used_moves = [], [], [], set(), set()
                # Include each newly published location in later files' identity
                # catalog. Their real version IDs make exact pin decisions usable.
                candidates = list(rows)
                disk_file_ids = {str(row[0]) for row in rows if row[8] == 'disk'}
                counts = {'files': {'scanned': sum(len(location.files) for location in manifest.locations),
                                   'changed': 0, 'removed': 0},
                          'chunks': {reason: 0 for reason in ('unchanged', 'edited', 'renamed', 'new', 'removed')}}
                for location in manifest.locations:
                    key, used = location_key(location.id), set()
                    for captured in location.files:
                        addresses = tuple(SourceAddress(repository.name, alias.root, alias.path) for alias in captured.aliases)
                        logical = _bindings(captured, scopes)
                        matching = []
                        physical = ()
                        if location.id.kind == 'disk':
                            addresses, physical, identity = observed[captured.primary]
                            stable = {(_absolute(item), tuple(item['rootIdentity'])) for item in logical}
                            matching = [row for row in candidates if row[8] == 'disk' and (
                                tuple(row[7].get('physicalIdentity', ())) == identity
                                or (tuple(row[7].get('physicalIdentity', ())) not in present_identities
                                    and stable.intersection((_absolute(item), tuple(item['rootIdentity']))
                                                           for item in row[7].get('physicalBindings', ()))))]
                            if not matching:
                                matching = [row for row in candidates if str(row[0]) not in disk_file_ids
                                            and _logical(logical).intersection(_prior_logical(row, scopes))]
                            move = next((move for move in recognized_moves if move.destination in captured.aliases), None)
                            if move is not None:
                                prior = [row for row in rows if row[8] == 'disk' and str(row[0]) == move.identifier]
                                if len(prior) != 1 or (matching and {str(row[0]) for row in matching} != {move.identifier}):
                                    _invalid('The recognized move conflicts with located file identity.')
                                evidence = _verify_git_move(repository, prior[0], captured, physical, move)
                                matching, used_moves = prior, used_moves | {move.identifier}
                            else:
                                evidence = None
                                if not matching:
                                    proofs = _git_matches(captured, logical, rows, correspondences, scopes)
                                    prior = [proof for proof in proofs if proof[0][8] == 'disk']
                                    if len({str(proof[0][0]) for proof in prior}) > 1:
                                        _invalid('Automatic Git moves conflict with existing disk identities.')
                                    if prior:
                                        row, peer, chain = prior[0]
                                        anchors = [endpoint for rename in chain for endpoint in (rename.before, rename.after)
                                                   if endpoint.place.logical in _logical(logical)
                                                   and endpoint.source == captured.source]
                                        if len({endpoint.commit for endpoint in anchors}) != 1 or len(chain) != 1:
                                            _invalid('An automatic disk move needs one direct checked commit pair.')
                                        source = next((alias for alias in peer.aliases if any(
                                            item['root'] == alias.root and item['path'] == alias.path
                                            for item in row[7].get('physicalBindings', ()))), None)
                                        if source is not None:
                                            automatic = GitFileMove(str(row[0]), str(row[5]), peer.commit,
                                                anchors[0].commit, source, captured.primary)
                                            evidence = _verify_git_move(repository, row, captured, physical, automatic)
                                            matching = [row]
                        else:
                            # A retained location's own binding precedes newer
                            # disk paths. In particular an old branch must not
                            # follow a distinct file reusing a moved disk path.
                            same_place = lambda row: _logical(logical).intersection(_prior_logical(row, scopes))
                            matching = [row for row in rows if row[8] == location.id.kind and row[9] == key and same_place(row)]
                            if not matching:
                                matching = [row for row in rows if same_place(row)]
                            if not matching:
                                matching = [row for row in candidates if same_place(row)]
                            evidence = None
                            if not matching:
                                proofs = _git_matches(captured, logical, candidates, correspondences, scopes)
                                matching = [row for row, _, _ in proofs]
                                if proofs:
                                    evidence = [proof.record(repository.name) for proof in proofs[0][2]]
                        identities = {str(row[0]) for row in matching}
                        if len(identities) > 1 or identities.intersection(used):
                            _invalid('The complete capture has conflicting located file identities.')
                        identifier = next(iter(identities), str(uuid4()))
                        used.add(identifier)
                        prior = [row for row in rows if str(row[0]) == identifier and row[8] == location.id.kind and row[9] == key]
                        if len(prior) > 1:
                            _invalid('A file has more than one version in one retained location.')
                        old = prior[0] if prior else None
                        previous = None if old is None else SourceAddress(repository.name,
                            old[7].get('root', old[1]), old[7].get('path', old[2]))
                        primary = previous if previous in addresses else SourceAddress(repository.name,
                            captured.primary.root, captured.primary.path)
                        metadata = {**({} if old is None else old[7]), 'root': primary.root, 'path': primary.path,
                            'corpus': captured.corpus,
                            'aliases': [{'root': alias.root, 'path': alias.path} for alias in addresses],
                            'logicalBindings': logical, 'captureLocation': location.id.record(),
                            'commit': location.commit, 'trees': list(location.trees), 'policyHash': manifest.policy_hash,
                            'captureFileCount': len(location.files),
                            'parseHistory': parse_history_record(replace(captured,
                                primary=FileAlias(primary.root, primary.path)), manifest.policy_hash)}
                        if captured.corpus == 'documents':
                            declarations = read_document_declarations(captured.parsed, file=primary.address)
                            metadata['documentDeclarations'] = {'metadata': _safe_json(declarations.metadata),
                                'diagnostics': [{'code': item.code, 'message': item.message,
                                    'key': item.key, 'line': item.line} for item in declarations.diagnostics]}
                        if location.id.kind == 'disk':
                            # Preserve recognized disk moves independently of
                            # each branch's own original path and source bytes.
                            disk_prior = next((row for row in matching if row[8] == 'disk'), None)
                            metadata.setdefault('recognizedMoves', [])
                            if disk_prior is not None:
                                historical = {(item['root'], item['path']) for item in disk_prior[7].get('recognizedMoves', ())}
                                historical.update((alias.root, alias.path) for alias in _aliases(disk_prior, repository.name, aliases)
                                                  if alias not in addresses)
                                metadata['recognizedMoves'] = [{'root': root, 'path': path} for root, path in sorted(historical)]
                            metadata.update({'physicalIdentity': list(identity), 'physicalBindings': [
                                {'root': alias.root, 'path': alias.path, 'absoluteRoot': item['root'], 'rootIdentity': item['rootIdentity']}
                                for alias, item in zip(addresses, physical)]})
                            if evidence is not None:
                                metadata['moveEvidence'] = [*metadata.get('moveEvidence', ()), evidence]
                        elif evidence is not None:
                            metadata['gitCorrespondence'] = evidence
                        current_chunks = connection.execute(_FILE_CHUNKS_SQL, (repository.name, identifier)).fetchall()
                        known = _known(identifier, None if old is None else str(old[4]), current_chunks)
                        plan = reconcile_file(_inputs(captured), known)
                        prior_ids = set() if old is None else {str(item[1]) for item in current_chunks if item[7] == old[4]}
                        plan = replace(plan, removed=tuple(item for item in plan.removed if item.chunk_id in prior_ids))
                        unchanged = (old is not None and bytes(old[6]) == captured.source and old[3] == captured.corpus
                            and old[7] == metadata and all(item.reason == 'unchanged' and item.version_action == 'reuse_existing'
                                                         for item in plan.decisions) and not plan.removed)
                        if unchanged:
                            binding = FileBinding(identifier, str(old[5]), str(old[4]), primary, addresses)
                            versions = tuple((item.chunk_id, item.version_id) for item in plan.decisions)
                        else:
                            binding, versions = self._write_file(connection, repository.name, captured, old, identifier,
                                                               primary, addresses, metadata, plan, location.id.kind, key)
                            counts['files']['changed'] += 1
                            file_changes.append(FileChange(primary.root, primary.path, key, 'added' if old is None else 'changed'))
                            by_id = {chunk.identifier: chunk for chunk in known}
                            for item, (chunk_id, _) in zip(plan.decisions, versions):
                                previous_name = by_id[item.chunk_id].current.chunk.name if item.reason == 'renamed' else None
                                decisions.append(IdentityChange(primary.root, primary.path, key, UUID(chunk_id),
                                    item.reason, item.incoming.name, previous_name))
                            decisions.extend(IdentityChange(primary.root, primary.path, key, UUID(item.chunk_id),
                                'removed', by_id[item.chunk_id].current.chunk.name) for item in plan.removed)
                        kept.add(binding.location)
                        previous_versions = tuple(sorted((str(item[1]), item[2]) for item in current_chunks
                            if old is not None and item[7] == old[4]))
                        applied.append(AppliedLocatedFile(location.id, location.commit, binding, plan, versions,
                                                          not unchanged, previous_versions))
                        for item in (*plan.decisions, *plan.removed):
                            counts['chunks'][item.reason] += 1
                        if not unchanged:
                            # Only this file's locations changed. Retain the
                            # other candidates for subsequent move/restore checks.
                            updated = _location_rows(connection.execute(
                                _FILE_LOCATIONS_SQL, (repository.name, identifier)).fetchall())
                            candidates = sorted([row for row in candidates if str(row[0]) != identifier] + updated,
                                                key=lambda row: (str(row[0]), str(row[4])))
                if used_moves != {move.identifier for move in recognized_moves}:
                    _invalid('Every recognized move must bind one captured disk destination.')
                retired = tuple(str(row[4]) for row in rows if str(row[4]) not in kept)
                # Replaced locations were already removed by _write_file; old
                # absent location rows retire here. Versions and owners survive.
                for row in rows:
                    if str(row[4]) not in retired or connection.execute(
                            'SELECT 1 FROM public.mycel_file_locations WHERE id=%s', (row[4],)).fetchone() is None:
                        continue
                    connection.execute('DELETE FROM public.mycel_file_locations WHERE id=%s', (row[4],))
                    counts['files']['removed'] += 1
                    file_changes.append(FileChange(row[7].get('root', row[1]), row[7].get('path', row[2]), row[9], 'removed'))
                    removed_chunks = {str(item[1]): item for item in chunks if item[7] == row[4]}
                    for chunk_id, item in sorted(removed_chunks.items()):
                        counts['chunks']['removed'] += 1
                        decisions.append(IdentityChange(row[7].get('root', row[1]), row[7].get('path', row[2]), row[9],
                            UUID(chunk_id), 'removed', item[10].get('name', item[5]['name'])))
                inventory = [{'location': location.id.record(), 'commit': location.commit,
                              'policyHash': manifest.policy_hash} for location in manifest.locations]
                inventory_changed = state is None or state[0] != inventory
                if inventory_changed:
                    connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) '
                        'ON CONFLICT(repository) DO UPDATE SET read_locations=EXCLUDED.read_locations',
                        (repository.name, Jsonb(inventory)))
                changed = bool(file_changes) or inventory_changed
                output = LocatedCaptureResult(tuple(applied), retired, changed, counts, repository.name, activity, reply_counts)
                for file in output.files:
                    if file.changed and file_handoff is not None:
                        file_handoff(connection, file)
                refresh_unchanged = getattr(batch_handoff, 'refresh_unchanged', False) is True
                handoff_ran = batch_handoff is not None and (changed or refresh_unchanged)
                if handoff_ran:
                    dependency_changed = batch_handoff(connection, output)
                    if refresh_unchanged and type(dependency_changed) is not bool:
                        _invalid('A complete producer must return a typed mutation decision.')
                    changed = changed or refresh_unchanged and dependency_changed is True
                stale_counts, stale_changed, pending_stale = detector.apply_in_transaction(
                    settings, repository.name, stale_guards, targeted=targeted_detection)
                counts.update(stale_counts.pop(repository.name, {}))
                counts['stalePending'] = list(pending_stale)
                downstream = counts.setdefault('dependencyRepositories', {})
                for owner, portion in stale_counts.items():
                    downstream.setdefault(owner, {}).update(portion)
                output.dependency_changes.update(stale_changed - {repository.name})
                changed = changed or repository.name in stale_changed
                for owner in sorted(downstream):
                    portion = downstream[owner]
                    if reply_counts is not None:
                        portion = reply_counts(owner, portion)
                        downstream[owner] = portion
                    if activity is not None and owner in output.dependency_changes:
                        activity.record_in_transaction(owner, 'ingest', AppliedMutation(True, portion))
                if not downstream:
                    counts.pop('dependencyRepositories')
                # Optional hooks must be explicitly declared. Dynamic callback
                # attributes (including Mock children) do not install a hook.
                finalize = (None if getattr_static(batch_handoff, 'finalize_in_transaction', None) is None
                            else getattr(batch_handoff, 'finalize_in_transaction'))
                if finalize is not None:
                    if not callable(finalize):
                        _invalid('The complete producer final projection must be callable.')
                    projection_changed = finalize(connection, output)
                    if type(projection_changed) is not bool:
                        _invalid('The complete producer final projection must return a typed mutation decision.')
                    changed = changed or projection_changed
                if publish_capture:
                    # The pass publishes the capture it read. One more read of
                    # the disk names what moved meanwhile for the next pass.
                    complete = capture_repository(settings, repository.name, previous=manifest)
                    differences = capture_differences(repository.name, manifest, complete)
                    if differences:
                        counts['changedDuringPass'] = differences
                cumulative = counts if reply_counts is None else reply_counts(repository.name, counts)
                def verify_complete(result=output):
                    settings.require_current()
                    if handoff_ran:
                        verify = getattr(batch_handoff, 'verify_in_transaction', None)
                        if verify is not None:
                            if not callable(verify):
                                _invalid('The complete producer final input check must be callable.')
                            verify(connection, result)
                    detector.verify_in_transaction(settings, stale_guards)
                    if _scopes(repository) != scopes or build_correspondences(
                            _git_snapshots(manifest, rows, scopes)) != correspondences:
                        _invalid('The complete capture changed during located publication.')
                    if publish_capture:
                        return
                    complete = capture_repository(settings, repository.name, previous=fresh)
                    if not complete.deletion_safe or not _same_capture(manifest, complete):
                        _invalid('The complete capture changed during located publication.')
                    for captured in manifest.disk.files:
                        addresses, physical, _ = observed[captured.primary]
                        if _observe(repository, addresses, captured.source) != physical:
                            _invalid('The complete physical file changed during located publication.')
                final_verify = verify_complete
                final_verify()
                output = replace(output, changed=changed)
                return AppliedMutation(changed, cumulative, tuple(file_changes), tuple(decisions))

            with detection_guards(self.connection, settings, repository.name) as stale_guards:
                detector = MechanicalStalenessStore(self.connection, snapshot=manifest if publish_capture else None)
                if activity is None:
                    with atomic_transaction(self.connection):
                        write(self.connection)
                else:
                    activity.apply(repository.name, 'ingest', write,
                        verify=lambda: final_verify())
            return output

    @staticmethod
    def _write_file(connection, repository, captured, old, identifier, primary, aliases, metadata, plan, kind, key):
        require_captured_corpus(metadata, captured)
        connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                           (repository, Jsonb([])))
        existing = connection.execute('SELECT 1 FROM public.mycel_files WHERE id=%s', (identifier,)).fetchone()
        if existing is None or kind == 'disk':
            connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE '
                'SET root=EXCLUDED.root,path=EXCLUDED.path,corpus=EXCLUDED.corpus',
                (identifier, repository, primary.root, primary.path, captured.corpus))
            connection.execute('DELETE FROM public.mycel_file_aliases WHERE file_id=%s', (identifier,))
            for alias in aliases:
                connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)', (identifier, alias.root, alias.path))
        version = connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
            'ON CONFLICT(file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
            (uuid4(), identifier, captured.file_hash, captured.source, Jsonb({}))).fetchone()[0]
        located = old[4] if old is not None else uuid4()
        if old is not None:
            connection.execute('DELETE FROM public.mycel_file_locations WHERE id=%s', (old[4],))
        connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
                           (located, version, kind, key, Jsonb(metadata)))
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
                               (uuid4(), exact, located, kind, key, Jsonb(details)))
            persisted.append((str(chunk_id), exact))
        if kind == 'disk':
            # The entity rows of the document, keyed by their UUID (MYC-17). Branch
            # and stash locations follow when every clone becomes a location.
            publish_entities(connection, repository, identifier, located, captured)
        return FileBinding(identifier, str(version), str(located), primary, aliases), tuple(persisted)
