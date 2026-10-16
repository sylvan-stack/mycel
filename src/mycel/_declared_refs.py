"""Location-owned document declarations and retained typed-resolution passes.

Ingest supplies already stored exact file/chunk locations. This module retains
every declaration and fault and reconciles current resolved edges; immutable
baseline capture/repin and document identity remain separate ingest boundaries.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from ._errors import MycelError
from ._evidence import _RELEASE_OWNER_SQL, _COLLECT_SNAPSHOTS_SQL, _COLLECT_MANIFESTS_SQL
from ._locks import atomic_transaction, operation_guard, read_snapshot, require_transaction_guards
from ._markdown import split_markdown
from ._resolver import SourceResolver
from ._settings import SettingsSnapshot
from ._source_refs import DocumentDeclarations, read_document_declarations
from ._store import checked_store, exact_bytes


def _raw(value: str) -> str:
    return value.encode('utf-8', errors='surrogatepass').hex()


def _text(value: str) -> str:
    return bytes.fromhex(value).decode('utf-8', errors='surrogatepass')


def _stored(value: str) -> str:
    # PostgreSQL TEXT/JSONB cannot contain NUL. Exact raw spellings remain in
    # hex fields, including malformed input; the display projection is bounded
    # by neither syntax success nor PostgreSQL's textual representation.
    return value if '\0' not in value and not any(0xD800 <= ord(c) <= 0xDFFF for c in value) else json.dumps(value, ensure_ascii=True)


@dataclass(frozen=True)
class RetainedRef:
    identifier: str
    repository: str
    version: int
    declaration: str
    declared: str
    raw_line: str
    origin: str
    line: int | None
    location: str
    state: str
    fault: str | None
    place: str | None
    candidates: tuple[str, ...]
    candidate_count: int
    source_state: str
    baseline_status: str


@dataclass(frozen=True)
class RefPassReply:
    checked: int
    changed: int
    refs: tuple[RetainedRef, ...]

    @property
    def faults(self) -> tuple[RetainedRef, ...]:
        return tuple(ref for ref in self.refs if ref.fault is not None)

    @property
    def activity_counts(self) -> dict:
        return {'refsChecked': self.checked, 'refsChanged': self.changed, 'refFaults': len(self.faults)}


class DeclaredRefStore:
    def __init__(self, connection):
        self.connection = connection

    def retain(self, settings: SettingsSnapshot, file_location: str,
               declarations: DocumentDeclarations, *, _in_transaction: bool = False) -> tuple[str, ...]:
        """Retain exact declarations against this located file, never a version alone.

        Its source bytes are parsed again before writing. Different locations
        that share exact chunk versions keep independent declaration ownership.
        Removed declarations release only their own dependencies/evidence.
        """
        settings.require_valid(require_store=False)
        try:
            location_id = UUID(file_location)
        except (ValueError, TypeError, AttributeError):
            raise MycelError('invalid_input', 'A declaration batch needs its exact file location.') from None
        if _in_transaction:
            require_transaction_guards(self.connection, tuple(settings.values['repos']))
        with (nullcontext() if _in_transaction else checked_store(self.connection)), (nullcontext() if _in_transaction else read_snapshot(self.connection)):
            observed = self.connection.execute(_FILE_LOCATION_SQL, (location_id,)).fetchone()
        if observed is None:
            raise MycelError('invalid_input', 'The declaration file location is absent.')
        repository, kind, location, source, metadata = observed
        configured = settings.values['repos'].get(repository)
        if not configured or not configured['enabled'] or not isinstance(declarations, DocumentDeclarations):
            raise MycelError('invalid_input', 'Declaration ownership requires one enabled repository.')
        with (nullcontext() if _in_transaction else operation_guard(self.connection, repository, 'pass')):
            actual = read_document_declarations(split_markdown(exact_bytes(source)), file=declarations.file)
            if actual != declarations:
                raise MycelError('invalid_input', 'The declarations differ from the exact located file bytes.')
            with (nullcontext() if _in_transaction else read_snapshot(self.connection)):
                chunks = self.connection.execute(_LOCATED_CHUNKS_SQL, (location_id,)).fetchall()
            by_name = {}
            for version, version_metadata, located in chunks:
                name = located.get('name', version_metadata.get('name'))
                if name in by_name:
                    raise MycelError('store_format', 'A declaration file has ambiguous stored chunk names.')
                by_name[name] = version
            desired = []
            for chunk in declarations.chunk_sources:
                if chunk.chunk not in by_name:
                    raise MycelError('invalid_input', 'A declaration chunk is absent from its exact file location.')
                for ordinal, ref in enumerate(chunk.sources):
                    identifier = uuid5(NAMESPACE_URL, f'mycel-declared-v1:{location_id}:{by_name[chunk.chunk]}:{ordinal}:{_raw(ref.declared)}')
                    state = {'declarationLocation': {'file': str(location_id), 'kind': kind, 'location': location},
                             'rawRef': _raw(ref.ref), 'rawDeclared': _raw(ref.declared), 'rawLine': _raw(ref.raw_line),
                             'origin': ref.origin, 'line': ref.line, 'syntaxFault': ref.fault}
                    desired.append((identifier, by_name[chunk.chunk], _stored(ref.ref), state))
            updated_metadata = {**metadata, 'documentDeclarations': {
                'metadata': _safe_json(declarations.metadata),
                'diagnostics': [{'code': item.code, 'message': item.message, 'key': item.key, 'line': item.line}
                                for item in declarations.diagnostics]}}
            with (nullcontext() if _in_transaction else atomic_transaction(self.connection)):
                if (self.connection.execute(_FILE_LOCATION_SQL, (location_id,)).fetchone() != observed
                        or self.connection.execute(_LOCATED_CHUNKS_SQL, (location_id,)).fetchall() != chunks):
                    raise MycelError('invalid_input', 'The located declaration inputs changed during retention.')
                previous = self.connection.execute(_OWNED_SQL, (str(location_id), repository)).fetchall()
                expected_ids = {str(item[0]) for item in desired}
                if _in_transaction and any(owner is not None and str(identifier) not in expected_ids
                                           for identifier, owner in previous):
                    raise MycelError('refused', 'Changing pinned declarations requires the complete checked identity/dependency plan.')
                for identifier, baseline_owner in previous:
                    if str(identifier) not in expected_ids:
                        self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
                        self.connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (identifier,))
                        if baseline_owner is not None:
                            self.connection.execute(_RELEASE_OWNER_SQL, (baseline_owner, repository))
                for identifier, version, declaration, state in desired:
                    self.connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL) '
                        'ON CONFLICT (id) DO UPDATE SET state=mycel_dependencies.state || EXCLUDED.state '
                        'WHERE mycel_dependencies.state IS DISTINCT FROM mycel_dependencies.state || EXCLUDED.state',
                        (identifier, repository, version, declaration, '', 'declared', Jsonb(state)))
                self.connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                                        (Jsonb(updated_metadata), location_id))
                self.connection.execute(_COLLECT_SNAPSHOTS_SQL, (repository,))
                self.connection.execute(_COLLECT_MANIFESTS_SQL, (repository,))
            return tuple(str(item[0]) for item in desired)

    def retain_in_transaction(self, settings: SettingsSnapshot, file_location: str,
                              declarations: DocumentDeclarations) -> tuple[str, ...]:
        """Join exact new declaration retention to a caller's complete change.

        The caller must hold all configured repository pass/removal guards and
        checked_store before its transaction. This method opens no transaction,
        commits nothing, and does not choose an identity/pin inheritance policy.
        Replacing or removing a pinned declaration refuses until that complete
        policy is supplied by the producer; it cannot silently repin an alias or
        release a prior exact version's evidence.
        """
        return self.retain(settings, file_location, declarations, _in_transaction=True)

    def recheck(self, settings: SettingsSnapshot, *, repository: str, activity=None, reply_counts=None,
                _in_transaction: bool = False) -> RefPassReply:
        """Retry retained refs on every pass, including settings-invalid refs.

        Registered enabled owners are checked on every pass. This includes both
        origin and target passes and immediately revokes newly ineligible edges.
        No former anchor overrides a new ambiguity. Optional MutationActivity
        commits each owner's real reference writes and audit in one transaction.
        Its producer must supply a pure ``reply_counts(owner, local_counts)``
        callback returning cumulative command counts; final no-op totals belong
        in ``activity.finish(counts=...)``. No hidden command counters are kept.
        """
        settings.require_valid(require_store=False)
        configured = settings.values['repos'].get(repository)
        if not configured or not configured['enabled']:
            raise MycelError('invalid_input', 'A reference pass requires an enabled repository.')
        if activity is not None and getattr(activity, 'connection', None) is not self.connection:
            raise MycelError('invalid_input', 'Reference activity must use the exact writing connection.')
        if activity is not None and not callable(reply_counts):
            raise MycelError('invalid_input', 'Reference activity requires the producer cumulative reply counts.')
        if activity is None and reply_counts is not None:
            raise MycelError('invalid_input', 'Cumulative reference counts require an active activity producer.')
        if _in_transaction:
            if activity is not None:
                raise MycelError('invalid_input', 'A transaction reference handoff uses its caller activity producer.')
            require_transaction_guards(self.connection, tuple(settings.values['repos']))
        eligible = sorted(name for name, repo in settings.values['repos'].items() if repo['enabled'])
        fingerprint = sha256(json.dumps(_plain(settings.values), sort_keys=True, ensure_ascii=True,
                                        separators=(',', ':')).encode()).hexdigest()
        results = []
        changed = 0
        with (nullcontext() if _in_transaction else checked_store(self.connection)), ExitStack() as stack:
            # Complete finite settings scope protects both sides of cross-repo
            # selections, including refs whose former targets just switched off.
            if not _in_transaction:
                for name in sorted(settings.values['repos']):
                    stack.enter_context(operation_guard(self.connection, name, 'pass'))
            with (nullcontext() if _in_transaction else read_snapshot(self.connection)):
                rows = self.connection.execute(_REFS_SQL, (eligible,)).fetchall()
            catalogs = {}
            grouped = defaultdict(list)
            for row in rows:
                identifier, owner, version, declaration, old_place, state, baseline_owner = row
                owned = state.get('declarationLocation')
                if not isinstance(owned, dict):
                    continue  # Other guarded evidence consumers own their rows.
                key = (owned['kind'], owned['location'])
                if key not in catalogs:
                    reader = SourceResolver.from_transaction if _in_transaction else SourceResolver.from_store
                    catalogs[key] = reader(self.connection, settings, kind=key[0], location=key[1])
                raw = _text(state['rawRef'])
                result = catalogs[key].resolve_retained(raw, state.get('anchor'))
                with (nullcontext() if _in_transaction else read_snapshot(self.connection)):
                    owning_file = self.connection.execute(_FILE_LOCATION_SQL, (owned['file'],)).fetchone()
                    owning_chunks = self.connection.execute(_LOCATED_CHUNKS_SQL, (owned['file'],)).fetchall()
                if (owning_file is None or owning_file[:3] != (owner, key[0], key[1])
                        or version not in {item[0] for item in owning_chunks}):
                    result = type(result)(raw, 'invalid', fault='owner_location_missing')
                if state.get('syntaxFault'):
                    result = type(result)(raw, 'invalid', fault=state['syntaxFault'])
                selection = result.selection
                resolution = {'state': result.state, 'fault': result.fault, 'candidates': list(result.candidates),
                              'candidateCount': result.candidate_count,
                              'place': None if selection is None else selection.place.address}
                new_state = {**state, 'resolution': resolution, 'settings': fingerprint,
                             'baselineStatus': 'baseline_missing' if baseline_owner is None else 'retained',
                             'sourceState': 'source_removed' if state.get('everResolved') and result.fault in {
                                 'missing_file', 'missing_name'} else result.state}
                place = old_place
                members = ()
                if selection is not None:
                    new_state['everResolved'] = True
                    place = selection.place.address
                    new_state['anchor'] = selection.file.identifier if selection.kind == 'file' else next(
                        member.chunk.identifier for member in selection.members if member.place == selection.place)
                    new_state['selection'] = {'kind': selection.kind, 'fileHash': selection.file.snapshot_hash,
                        'members': [{'id': member.chunk.identifier, 'version': member.chunk.version,
                                     'place': member.place.address, 'hash': member.chunk.snapshot_hash}
                                    for member in selection.members]}
                    members = tuple(sorted({member.chunk.version for member in selection.members}))
                else:
                    new_state.pop('selection', None)
                grouped[owner].append((row, new_state, place, members))
                results.append(_record(identifier, owner, version, new_state))
            for owner, updates in grouped.items():
                applied_count = []
                def apply(connection):
                    count = self._apply(connection, updates)
                    applied_count.append(count)
                    if activity is None:
                        return count
                    from ._activity import AppliedMutation
                    local_counts = {'refsChecked': len(updates), 'refsChanged': count,
                                    'refFaults': sum(item[1]['resolution']['fault'] is not None for item in updates)}
                    return AppliedMutation(bool(count), reply_counts(owner, local_counts))
                if activity is None:
                    with (nullcontext() if _in_transaction else atomic_transaction(self.connection)):
                        changed += apply(self.connection)
                else:
                    activity.apply(owner, 'ingest', apply)
                    changed += applied_count[0]
        return RefPassReply(len(results), changed, tuple(results))

    def recheck_in_transaction(self, settings: SettingsSnapshot, *, repository: str) -> RefPassReply:
        """Apply ref faults/bindings/edges in the caller's guarded transaction.

        The returned counts must be included in the caller's AppliedMutation
        and final reply. Evidence capture and identity/pin decisions are separate
        producers; this adapter never substitutes a new baseline for a missing one.
        """
        return self.recheck(settings, repository=repository, _in_transaction=True)

    @staticmethod
    def _apply(connection, updates) -> int:
        changed = 0
        for old, state, place, members in updates:
            identifier, owner, version, declaration, old_place, old_state, baseline_owner = old
            row = connection.execute('SELECT id,repository,dependant_version,declaration,source_place,state,baseline_owner '
                                     'FROM public.mycel_dependencies WHERE id=%s FOR UPDATE NOWAIT', (identifier,)).fetchone()
            if row != old:
                raise MycelError('invalid_input', 'The retained declaration changed during its reference pass.')
            previous = tuple(value[0] for value in connection.execute(
                'SELECT source_version FROM public.mycel_edges WHERE dependency=%s ORDER BY source_version', (identifier,)).fetchall())
            fault = state['resolution'] if state['resolution']['fault'] is not None else None
            old_fault = connection.execute('SELECT fault FROM public.mycel_ref_faults WHERE id=%s', (identifier,)).fetchone()
            if state == old_state and place == old_place and previous == members and old_fault == (None if fault is None else (fault,)):
                continue
            connection.execute('UPDATE public.mycel_dependencies SET source_place=%s,state=%s WHERE id=%s',
                               (place, Jsonb(state), identifier))
            connection.execute('DELETE FROM public.mycel_edges WHERE dependency=%s', (identifier,))
            for member in members:
                connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (identifier, member))
            connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (identifier,))
            if fault is not None:
                connection.execute('INSERT INTO public.mycel_ref_faults VALUES (%s,%s,%s,%s,%s)',
                                   (identifier, owner, version, declaration, Jsonb(fault)))
            changed += 1
        return changed

    def list(self, *, repository: str | None = None, faults_only: bool = False) -> tuple[RetainedRef, ...]:
        """Report retained declarations without retrying or writing any row."""
        with checked_store(self.connection), read_snapshot(self.connection):
            rows = self.connection.execute(_LIST_SQL, (repository, repository)).fetchall()
        result = tuple(_record(identifier, owner, version, {**state,
                           'baselineStatus': 'baseline_missing' if baseline_owner is None else 'retained'})
                       for identifier, owner, version, state, baseline_owner in rows
                       if 'declarationLocation' in state)
        return tuple(ref for ref in result if ref.fault is not None) if faults_only else result


def _plain(value: Any):
    if hasattr(value, 'items'):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _safe_json(value: Any):
    if isinstance(value, str):
        return _stored(value)
    if hasattr(value, 'items'):
        return {_stored(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_json(item) for item in value]
    return value


def _record(identifier, owner, version, state):
    result = state.get('resolution', {'state': 'unresolved', 'fault': 'not_checked'})
    return RetainedRef(str(identifier), owner, version, _text(state['rawRef']), _text(state['rawDeclared']),
                       _text(state['rawLine']), state['origin'], state['line'], state['declarationLocation']['file'],
                       result['state'], result['fault'], result.get('place'), tuple(result.get('candidates', ())),
                       result.get('candidateCount', 0), state.get('sourceState', 'unresolved'),
                       state.get('baselineStatus', 'baseline_missing'))


_FILE_LOCATION_SQL = """SELECT f.repository,l.kind,l.location,v.source_bytes,l.metadata FROM public.mycel_files f
JOIN public.mycel_file_versions v ON v.file_id=f.id JOIN public.mycel_file_locations l ON l.file_version=v.id WHERE l.id=%s"""
_LOCATED_CHUNKS_SQL = """SELECT v.id,v.metadata,l.metadata FROM public.mycel_locations l
JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version WHERE l.file_location=%s ORDER BY v.id"""
_OWNED_SQL = "SELECT id,baseline_owner FROM public.mycel_dependencies WHERE state->'declarationLocation'->>'file'=%s AND kind='declared' AND repository=%s"
_REFS_SQL = "SELECT id,repository,dependant_version,declaration,source_place,state,baseline_owner FROM public.mycel_dependencies WHERE kind='declared' AND repository=ANY(%s) ORDER BY repository,id"
_LIST_SQL = "SELECT id,repository,dependant_version,state,baseline_owner FROM public.mycel_dependencies WHERE kind='declared' AND (%s::text IS NULL OR repository=%s) ORDER BY repository,id"
