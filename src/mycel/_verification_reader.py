"""Immutable verification history and read-only current-input applicability.

Exact searchable versions are disposable. A record owns all its evidence and
belongs to its logical chunk; neither reporting nor validation repairs it.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
import re
from uuid import UUID

from ._capture import capture_repository
from ._cli import Invocation, Result, invocation_store
from ._errors import MycelError
from ._evidence import (ComparisonRecord, EvidenceError, EvidenceStore, chunk_comparison,
                       _read_place)
from ._locks import snapshot_transaction
from ._resolver import SourceResolver, require_read_transaction
from ._scope import RepositoryLocations
from ._store import exact_bytes


SCHEMA = 'mycel-verification-v1'
_PUBLIC = ('id', 'chunk', 'chunkId', 'version', 'textHash', 'dependantSnapshot',
           'baselineManifests', 'sources', 'by', 'how', 'at')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ROWS_SQL = """SELECT id,repository,chunk_id,recorded_at,record,evidence_owner
    FROM public.mycel_verifications WHERE repository=%s ORDER BY recorded_at DESC,id DESC"""
_OWNER_SQL = 'SELECT repository,kind,identity,invocation FROM public.mycel_evidence_owners WHERE id=%s'
_REFS_SQL = """SELECT ordinal,snapshot_hash,manifest_hash FROM public.mycel_evidence_references
    WHERE owner=%s AND repository=%s ORDER BY ordinal"""
_SNAPSHOT_SQL = 'SELECT bytes,metadata FROM public.mycel_snapshots WHERE repository=%s AND hash=%s'
_CURRENT_FAULT_SQL = """SELECT 1 FROM public.mycel_ref_faults f
    WHERE f.repository=%s AND f.chunk_version=%s AND (
      EXISTS (SELECT 1 FROM public.mycel_dependencies d WHERE d.id=f.id
        AND d.repository=f.repository AND d.dependant_version=f.chunk_version
        AND d.state->'declarationLocation'->>'file'=%s)
      OR EXISTS (SELECT 1 FROM public.mycel_relations r WHERE r.id=f.id
        AND r.repository=f.repository AND r.left_version=f.chunk_version
        AND r.state->'declarationLocation'->>'file'=%s)) LIMIT 1"""


def has_verification_fault(connection, repository, version, file_location) -> bool:
    """Read faults belonging to the checked disk declaration location only.

Branches can share the same exact dependant version while resolving sources
differently. Their observations must not invalidate a current disk check.
"""
    return connection.execute(_CURRENT_FAULT_SQL,
        (repository, version, str(file_location), str(file_location))).fetchone() is not None


def _bad_record():
    raise MycelError('store_format', 'A verification has incompatible immutable record or evidence ownership.')


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError()
    return value


def _digest(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError()
    return value


def _snapshot(value):
    if not isinstance(value, str) or not value.startswith('snapshot:'):
        raise ValueError()
    return _digest(value[9:])


def _time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise ValueError()
    return parsed


def _member(value, *, internal=False):
    keys = {'place', 'hash', 'comparisonHash', 'snapshot'}
    allowed = (keys, keys | {'chunkId', 'versionId'}) if internal else (keys,)
    if not isinstance(value, dict) or set(value) not in allowed:
        raise ValueError()
    _read_place(value['place'])
    for key in ('hash', 'comparisonHash'):
        _digest(value[key])
    if _snapshot(value['snapshot']) != value['hash']:
        raise ValueError()
    if 'chunkId' in value:
        _uuid(value['chunkId'])
        if type(value['versionId']) is not int or value['versionId'] <= 0:
            raise ValueError()


def verification_record(row) -> dict:
    """Validate identity/shape without requiring presently readable blobs."""
    try:
        identifier, repository, chunk_id, recorded_at, record, owner = row
        if not isinstance(record, dict) or set(record) != set(_PUBLIC) | {'schema', 'dependant', 'selections'}:
            raise ValueError()
        if (record['schema'] != SCHEMA or _uuid(record['id']) != str(identifier)
                or _uuid(record['chunkId']) != str(chunk_id)
                or _read_place(record['chunk']).repository != repository
                or _read_place(record['chunk']).name is None
                or _digest(record['version']) != _digest(record['textHash'])
                or _snapshot(record['dependantSnapshot']) != record['textHash']
                or _time(record['at']) != _time(recorded_at)
                or record['how'] not in {'read', 'check'}
                or not isinstance(record['by'], str) or not record['by']):
            raise ValueError()
        dependant = record['dependant']
        if (not isinstance(dependant, dict) or set(dependant) !=
                {'versionId', 'textHash', 'comparisonHash', 'place', 'snapshot'}
                or type(dependant['versionId']) is not int or dependant['versionId'] <= 0
                or dependant['place'] != record['chunk'] or dependant['textHash'] != record['textHash']
                or dependant['snapshot'] != record['dependantSnapshot']):
            raise ValueError()
        _digest(dependant['comparisonHash'])
        if (not isinstance(record['baselineManifests'], list) or not isinstance(record['sources'], list)
                or not isinstance(record['selections'], list)):
            raise ValueError()
        for source in record['sources']:
            _member(source)
        public_sources, manifests = [], []
        for selection in record['selections']:
            if (not isinstance(selection, dict) or set(selection) not in
                    ({'edgeKind', 'rawRef', 'manifest', 'members'},
                     {'edgeKind', 'rawRef', 'manifest', 'members', 'endpoint'})
                    or selection['edgeKind'] not in {'declared', 'asserted', 'related'}
                    or not isinstance(selection['rawRef'], str) or not selection['rawRef']
                    or not isinstance(selection['members'], list) or not selection['members']
                    or ('endpoint' in selection and type(selection['endpoint']) is not bool)):
                raise ValueError()
            manifests.append(_digest(selection['manifest']))
            for source in selection['members']:
                _member(source, internal=True)
                public_sources.append({key: source[key] for key in ('place', 'hash', 'comparisonHash', 'snapshot')})
        if record['baselineManifests'] != manifests or record['sources'] != public_sources:
            raise ValueError()
        UUID(str(owner))
        return record
    except (KeyError, TypeError, ValueError, AttributeError, EvidenceError):
        _bad_record()


def validate_verification_record(connection, row, *, legacy_version=None) -> dict:
    """Validate record-owned immutable bytes without consulting live sources.

The writer, migration and selected logical-chunk deletion share this binding
check. A predecessor's SQL row identity is validated as audit data, never used
to fabricate its public version or original Place.
"""
    record = verification_record(row)
    identifier, repository, chunk_id, _, _, owner = row
    try:
        if connection.execute(_OWNER_SQL, (owner,)).fetchone() != (repository, 'verification', str(identifier), None):
            raise ValueError()
        owning = connection.execute('SELECT repository FROM public.mycel_chunks WHERE id=%s', (chunk_id,)).fetchone()
        if owning != (repository,):
            raise ValueError()
        hashes = {_snapshot(record['dependantSnapshot'])}
        manifests = set(record['baselineManifests'])
        for selection in record['selections']:
            baseline = EvidenceStore(connection)._read_baseline(repository, selection['manifest'])
            payload = json.loads(baseline.manifest.canonical_bytes)
            dependant = payload['dependant']
            if (payload['dependantId'] != record['chunkId']
                    or payload['dependantVersion'] != str(record['dependant']['versionId'])
                    or dependant['hash'] != record['textHash'] or dependant['place'] != record['chunk']
                    or dependant['comparison']['hash'] != record['dependant']['comparisonHash']
                    or payload['kind'] != selection['edgeKind']
                    or payload.get('ref', selection['rawRef']) != selection['rawRef']):
                raise ValueError()
            expected = []
            for member in payload['members']:
                evidence = member['evidence']
                expected.append({'place': member['place'], 'hash': evidence['hash'],
                    'comparisonHash': evidence['comparison']['hash'], 'snapshot': evidence['snapshot'],
                    **({'chunkId': member['id']} if 'id' in member and payload['selection'] != 'file' else {})})
            actual = [{key: value for key, value in member.items() if key != 'versionId'}
                      for member in selection['members']]
            if actual != expected:
                raise ValueError()
            hashes.update(blob.evidence.hash for blob in baseline.snapshots)
        refs = connection.execute(_REFS_SQL, (owner, repository)).fetchall()
        expected_refs = {(digest, None) for digest in hashes} | {(None, digest) for digest in manifests}
        if ([(number, snapshot, manifest) for number, (_, snapshot, manifest) in enumerate(refs)] != refs
                or len(refs) != len(expected_refs) or {(snapshot, manifest) for _, snapshot, manifest in refs} != expected_refs):
            raise ValueError()
        snapshot = connection.execute(_SNAPSHOT_SQL, (repository, _snapshot(record['dependantSnapshot']))).fetchone()
        if snapshot is None:
            raise EvidenceError('baseline_missing')
        source = exact_bytes(snapshot[0])
        if (sha256(source).hexdigest() != record['textHash']
                or snapshot[1] != {'schema': 1, 'bytes': len(source), 'encoding': 'utf-8'}):
            raise EvidenceError('snapshot_corrupt')
        source.decode('utf-8')
        if legacy_version is not None:
            version, original_chunk, original_repository, digest, raw, comparison = legacy_version
            if (version != record['dependant']['versionId'] or str(original_chunk) != record['chunkId']
                    or original_repository != repository or digest != record['textHash']
                    or exact_bytes(raw) != source):
                raise ValueError()
            value = comparison.get('body', comparison) if isinstance(comparison, Mapping) else None
            if not isinstance(value, Mapping) or value.get('hash') != record['dependant']['comparisonHash']:
                raise ValueError()
            ComparisonRecord.from_record(value).require_supported()
        return record
    except EvidenceError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError):
        _bad_record()


class VerificationReader:
    def __init__(self, connection, settings):
        self.connection, self.settings = connection, settings
        self._captures = {}

    def _disk_file(self, file):
        """Establish indexed inputs against a complete current disk capture."""
        if file.repository not in self._captures:
            self._captures[file.repository] = capture_repository(self.settings, file.repository)
        capture = self._captures[file.repository]
        if not capture.deletion_safe:
            return False
        disk = [location for location in capture.locations if location.id.kind == 'disk']
        if len(disk) != 1 or not disk[0].complete:
            return False
        aliases = tuple(sorted((alias.root, alias.path) for alias in file.aliases))
        matches = [item for item in disk[0].files if any(
            alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
        return (len(matches) == 1 and matches[0].source == file.source
                and tuple(sorted((alias.root, alias.path) for alias in matches[0].aliases)) == aliases)

    def _current(self, row, catalog):
        record = verification_record(row)
        try:
            validate_verification_record(self.connection, row)
            dependants = [(file, chunk) for file in catalog.files for chunk in file.chunks
                          if chunk.identifier == record['chunkId'] and chunk.snapshot_hash == record['textHash']]
            if len(dependants) != 1:
                return False
            file, chunk = dependants[0]
            if (not self._disk_file(file) or chunk_comparison(chunk).hash != record['dependant']['comparisonHash']):
                return False
            locations = self.connection.execute('SELECT DISTINCT file_location FROM public.mycel_locations '
                "WHERE chunk_version=%s AND kind='disk' AND file_location IS NOT NULL", (chunk.version,)).fetchall()
            if len(locations) != 1:
                return False
            if has_verification_fault(self.connection, file.repository, chunk.version, locations[0][0]):
                return False
            from ._dependency_application import (_ROWS_SQL as dependencies_sql, _current_raw,
                                                  RetainedDependencyResolver)
            from ._relations import RELATION_ROWS_SQL, _relation_raw
            dependencies = self.connection.execute(dependencies_sql.replace(' FOR UPDATE NOWAIT', ''),
                (file.repository, chunk.version, str(locations[0][0]))).fetchall()
            relations = self.connection.execute(RELATION_ROWS_SQL.replace(' FOR UPDATE NOWAIT', ''),
                (file.repository, chunk.version, str(locations[0][0]))).fetchall()
            located_links = [((item[5], _current_raw(item), False), item[6].get('anchor'))
                             for item in dependencies if item[5] in {'declared', 'asserted'}]
            located_links += [(('related', _relation_raw(item[4]), item[4].get('endpoint', False)),
                               item[4].get('anchor')) for item in relations]
            expected_links = [(item['edgeKind'], item['rawRef'], item.get('endpoint', False))
                              for item in record['selections']]
            if sorted(link for link, _ in located_links) != sorted(expected_links):
                return False
            for selection in record['selections']:
                endpoint = selection.get('endpoint', False)
                anchors = [anchor for link, anchor in located_links
                           if link == (selection['edgeKind'], selection['rawRef'], endpoint)]
                if len(anchors) != 1:
                    return False
                # Each producer row owns its anchor and selection purpose.
                # A shared spelling can select a dependency family and an
                # asserted relation header independently, including after moves.
                selected_resolver = RetainedDependencyResolver(catalog,
                    {selection['rawRef']: anchors[0]} if anchors[0] else {},
                    endpoint_refs=(selection['rawRef'],) if endpoint else ())
                resolution = selected_resolver.resolve(selection['rawRef'])
                if resolution.state != 'resolved' or not self._disk_file(resolution.selection.file):
                    return False
                baseline = EvidenceStore(self.connection)._read_baseline(file.repository, selection['manifest'])
                if resolution.selection.kind != baseline.manifest.payload['selection']:
                    return False
                members = resolution.selection.members
                if resolution.selection.kind == 'file':
                    raw = resolution.selection.file.source
                    actual = [{'place': _place_dict(resolution.selection.place), 'hash': sha256(raw).hexdigest(),
                               'comparisonHash': sha256(raw).hexdigest(), 'snapshot': 'snapshot:' + sha256(raw).hexdigest()}]
                else:
                    actual = [{'chunkId': member.chunk.identifier, 'place': _place_dict(member.place),
                        'hash': member.chunk.snapshot_hash, 'comparisonHash': chunk_comparison(member.chunk).hash,
                        'snapshot': 'snapshot:' + member.chunk.snapshot_hash} for member in members]
                if len(actual) != len(selection['members']):
                    return False
                remaining = list(actual)
                for old in selection['members']:
                    matches = [member for member in remaining if
                        (member['place'] == old['place'] or 'chunkId' in old and member.get('chunkId') == old['chunkId']
                         or resolution.selection.kind == 'file' and baseline.manifest.payload['members'][0].get('id')
                            == resolution.selection.file.identifier)
                        and all(member[key] == old[key] for key in ('hash', 'comparisonHash', 'snapshot'))]
                    if len(matches) != 1:
                        return False
                    remaining.remove(matches[0])
            return True
        except (EvidenceError, MycelError, OSError, ValueError):
            # Presently uncheckable evidence/settings/disk inputs invalidate
            # applicability; reporting never repairs or silently recaptures it.
            return False

    def list_in_transaction(self, repository: str, *, history=False) -> dict:
        require_read_transaction(self.connection)
        rows = self.connection.execute(_ROWS_SQL, (repository,)).fetchall()
        if not rows:
            return {'repository': repository, 'verifications': []}
        records = [verification_record(row) for row in rows]
        try:
            catalog = SourceResolver.from_read_transaction(self.connection, self.settings)
        except MycelError:
            catalog = None
        newest = set()
        seen = set()
        for record in sorted(records, key=lambda value: (_time(value['at']), value['id']), reverse=True):
            exact = (record['chunkId'], record['textHash'])
            if exact not in seen:
                seen.add(exact)
                newest.add(record['id'])
        output = []
        for row, record in zip(rows, records):
            current = catalog is not None and record['id'] in newest and self._current(row, catalog)
            if history or record['id'] in newest and current:
                output.append({**{key: record[key] for key in _PUBLIC}, 'current': current})
        # Stable sort preserves the prescribed address ascending/time descending
        # order without comparing timestamps as arbitrary textual spellings.
        output.sort(key=lambda value: (_time(value['at']), value['id']), reverse=True)
        output.sort(key=lambda value: (value['chunk']['root'], value['chunk']['path'], value['chunk'].get('name', '')))
        return {'repository': repository, 'verifications': output}


def _place_dict(place):
    return {'repository': place.repository, 'root': place.root, 'path': place.path,
            'address': place.address, **({'name': place.name} if place.name is not None else {})}


def handle_verifications(invocation: Invocation) -> Result:
    if invocation.arguments not in ((), ('--history',)) or invocation.all_repositories or len(invocation.repositories) > 1:
        raise MycelError('invalid_input', 'Use mycel verifications [--repo <repository>] [--history].')
    if invocation.settings is None:
        raise MycelError('internal', 'Verification reporting requires loaded settings.')
    locations = RepositoryLocations(invocation.settings)
    if invocation.repositories and invocation.repositories[0] not in invocation.settings.values['repos']:
        raise MycelError('unknown_repository', 'Verification reporting requires a configured repository name.')
    selected = (locations.named(invocation.repositories[0]) if invocation.repositories else locations.resolve_scope())
    if len(selected) != 1:
        raise MycelError('invalid_input', 'Verification reporting requires one repository.')
    repository = selected[0]
    with invocation_store(invocation) as (connection, _), snapshot_transaction(connection):
        return Result(VerificationReader(connection, invocation.settings).list_in_transaction(
            repository.name, history=bool(invocation.arguments)))
