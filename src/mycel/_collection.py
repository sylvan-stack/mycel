"""Guarded collection after complete located publication.

Only the transaction producer calls this private boundary. It proves the fresh
complete capture is already published before deleting unlocated file-backed
versions. Evidence ownership is independent of searchable rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ._markdown import MarkdownDocument
from ._capture import CaptureManifest, capture_repository
from ._disk_reconciliation import _inputs, _metadata, _parse_history, _same_capture
from ._errors import MycelError
from ._evidence import BaselineManifest, EvidenceError
from ._located_reconciliation import _bindings, _catalog, _scopes, location_key
from ._locks import LockNamespace, invocation_is_live, require_transaction_guards
from ._location_corpus import location_corpus
from ._scope import RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_bindings import _observe
from ._source_refs import SourceAddress
from ._store import ENTITY_KINDS


def _invalid(message):
    raise MycelError('invalid_input', message)


@dataclass(frozen=True)
class CollectionResult:
    versions: int
    chunks: int
    file_versions: int
    files: int
    owners: int
    snapshots: int
    manifests: int


_RELEASE_OWNER_SQL = """DELETE FROM public.mycel_evidence_owners o
WHERE o.id=%s AND o.repository=%s AND o.invocation IS NULL
AND NOT EXISTS (SELECT 1 FROM public.mycel_dependencies d WHERE d.baseline_owner=o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_relations r WHERE r.baseline_owner=o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_drifts d WHERE d.evidence_owner=o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_classification_work w WHERE w.evidence_owner=o.id)
AND NOT EXISTS (SELECT 1 FROM public.mycel_verifications v WHERE v.evidence_owner=o.id)"""


class CollectionStore:
    def __init__(self, connection):
        self.connection = connection

    def release_baseline_owner_in_transaction(self, owner_id: UUID | str, repository: str) -> bool:
        """Release one selected replaced/withdrawn baseline, preserving history."""
        require_transaction_guards(self.connection, (repository,))
        try:
            owner_id = UUID(str(owner_id))
        except (ValueError, TypeError, AttributeError):
            _invalid('An evidence release requires one exact owner UUID.')
        row = self.connection.execute('SELECT kind FROM public.mycel_evidence_owners '
            'WHERE id=%s AND repository=%s FOR UPDATE NOWAIT', (owner_id, repository)).fetchone()
        if row is None:
            return False
        if row[0] != 'baseline':
            _invalid('A baseline release cannot release another evidence owner kind.')
        return self.connection.execute(_RELEASE_OWNER_SQL, (owner_id, repository)).rowcount == 1

    def release_dependency_in_transaction(self, dependency_id: UUID | str, repository: str) -> int:
        """Release one dependency and exactly its baseline/classification owners.

        Capture work ownership before its foreign-key cascade. History records,
        other work and invocation leases still protect selected owners. Acquire
        no guard or transaction, and sweep no unrelated orphan owner.
        """
        require_transaction_guards(self.connection, (repository,))
        try:
            dependency_id = UUID(str(dependency_id))
        except (ValueError, TypeError, AttributeError):
            _invalid('A dependency release requires one exact dependency UUID.')
        dependency = self.connection.execute('SELECT dependant_version,baseline_owner '
            'FROM public.mycel_dependencies WHERE id=%s AND repository=%s FOR UPDATE NOWAIT',
            (dependency_id, repository)).fetchone()
        if dependency is None:
            return 0
        work = self.connection.execute('SELECT id,evidence_owner FROM public.mycel_classification_work '
            'WHERE dependency=%s ORDER BY id FOR UPDATE NOWAIT', (dependency_id,)).fetchall()
        selected = {owner for _, owner in work if owner is not None}
        if dependency[1] is not None:
            selected.add(dependency[1])
        owners = self.connection.execute('SELECT id,repository,kind FROM public.mycel_evidence_owners '
            'WHERE id=ANY(%s) ORDER BY repository,id', (sorted(selected, key=str),)).fetchall()
        if len(owners) != len(selected) or (dependency[1] is not None and not any(
                identifier == dependency[1] and owner == repository and kind == 'baseline'
                for identifier, owner, kind in owners)):
            _invalid('The selected dependency has inconsistent evidence ownership.')
        repositories = tuple(sorted({repository, *(owner for _, owner, _ in owners)}))
        require_transaction_guards(self.connection, repositories)
        locked = self.connection.execute('SELECT id,repository,kind FROM public.mycel_evidence_owners '
            'WHERE id=ANY(%s) ORDER BY repository,id FOR UPDATE NOWAIT', (sorted(selected, key=str),)).fetchall()
        if locked != owners:
            _invalid('The selected dependency evidence owners changed before release.')
        fault = self.connection.execute('SELECT repository,chunk_version FROM public.mycel_ref_faults '
            'WHERE id=%s FOR UPDATE NOWAIT', (dependency_id,)).fetchone()
        if fault is not None and fault != (repository, dependency[0]):
            _invalid('The selected dependency fault belongs to another dependant.')
        self.connection.execute('DELETE FROM public.mycel_ref_faults WHERE id=%s', (dependency_id,))
        self.connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (dependency_id,))
        released = sum(self.connection.execute(_RELEASE_OWNER_SQL, (identifier, owner)).rowcount
                       for identifier, owner, _ in owners)
        for owner in repositories:
            self.collect_evidence_in_transaction(owner)
        return released

    def collect_evidence_in_transaction(self, repository: str) -> tuple[int, int]:
        """Collect wholly unreferenced blobs only in the owning writer."""
        require_transaction_guards(self.connection, (repository,))
        snapshots = self.connection.execute("""DELETE FROM public.mycel_snapshots s WHERE s.repository=%s
            AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r
              WHERE r.repository=s.repository AND r.snapshot_hash=s.hash)""", (repository,)).rowcount
        manifests = self.connection.execute("""DELETE FROM public.mycel_manifests m WHERE m.repository=%s
            AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r
              WHERE r.repository=m.repository AND r.manifest_hash=m.hash)""", (repository,)).rowcount
        return snapshots, manifests

    def remove_repository_in_transaction(self, repository: str, *, guarded_repositories: tuple[str, ...]):
        """Delete one owner's store under exclusive removal and pass guards.

        The future remove command owns settings, confirmation and foreign
        dependency fault publication. This handoff owns the atomic evidence
        release and the running-invocation gate, acquiring no locks itself.
        """
        require_transaction_guards(self.connection, guarded_repositories)
        if repository not in guarded_repositories:
            _invalid('Repository removal lacks its owning repository guard.')
        exclusive = self.connection.execute("""SELECT EXISTS (
            SELECT 1 FROM public.mycel_lock_keys k JOIN pg_catalog.pg_locks l
              ON l.classid::bigint=(k.key >> 32) AND l.objid::bigint=(k.key & 4294967295)
            WHERE k.namespace=%s AND k.identity=%s AND l.locktype='advisory'
              AND l.objsubid=1 AND l.granted AND l.mode='ExclusiveLock'
              AND l.pid=pg_catalog.pg_backend_pid()
              AND l.database=(SELECT oid FROM pg_catalog.pg_database
                              WHERE datname=pg_catalog.current_database()))""",
            (LockNamespace.MUTATION.value, repository)).fetchone()
        if exclusive != (True,):
            _invalid('Repository removal requires its exclusive removal guard.')
        leases = self.connection.execute('SELECT DISTINCT invocation FROM public.mycel_evidence_owners '
            'WHERE repository=%s AND invocation IS NOT NULL UNION SELECT invocation FROM public.mycel_activity '
            'WHERE repository=%s AND ended_at IS NULL', (repository, repository)).fetchall()
        if any(invocation_is_live(self.connection, invocation) for invocation, in leases):
            raise MycelError('busy', 'This repository still has a running invocation or evidence lease.')
        affected = tuple(row[0] for row in self.connection.execute("""SELECT DISTINCT d.repository
            FROM public.mycel_dependencies d JOIN public.mycel_edges e ON e.dependency=d.id
            JOIN public.mycel_chunk_versions v ON v.id=e.source_version
            JOIN public.mycel_chunks c ON c.id=v.chunk_id
            WHERE c.repository=%s AND d.repository<>%s ORDER BY d.repository""",
            (repository, repository)).fetchall())
        require_transaction_guards(self.connection, tuple(sorted({repository, *affected})))
        owners = self.connection.execute('SELECT id FROM public.mycel_evidence_owners '
            'WHERE repository=%s ORDER BY id FOR UPDATE NOWAIT', (repository,)).fetchall()
        # RESTRICT ownership FKs require releasing the concrete owners only
        # after every owning row has gone. All other repositories retain their
        # independent bytes and natural dependency records.
        for table in ('mycel_classification_work', 'mycel_drifts', 'mycel_verifications',
                      'mycel_dependencies', 'mycel_relations'):
            self.connection.execute(f'DELETE FROM public.{table} WHERE repository=%s', (repository,))
        released = self.connection.execute('DELETE FROM public.mycel_evidence_owners WHERE repository=%s',
                                           (repository,)).rowcount
        snapshots, manifests = self.collect_evidence_in_transaction(repository)
        removed = self.connection.execute('DELETE FROM public.mycel_repository_state WHERE repository=%s',
                                          (repository,)).rowcount
        return {'repositories': removed, 'owners': released, 'snapshots': snapshots,
                'manifests': manifests, 'affectedRepositories': affected}

    def _published(self, settings, manifest, published=False):
        """Check complete inventory, exact files and every parsed placed chunk."""
        expected = [{'location': item.id.record(), 'commit': item.commit,
                     'policyHash': manifest.policy_hash} for item in manifest.locations]
        state = self.connection.execute('SELECT read_locations FROM public.mycel_repository_state '
            'WHERE repository=%s FOR SHARE NOWAIT', (manifest.repository,)).fetchone()
        if state != (expected,):
            _invalid('Collection requires the complete published location inventory.')
        # Reuse only this transaction's published, independently validated
        # parse records; the caller's asserted manifest never supplies trust.
        catalog = _catalog(self.connection, manifest.repository)
        if published:
            fresh = manifest
        else:
            fresh = capture_repository(settings, manifest.repository,
                previous=_parse_history(manifest.repository, catalog[0], state[0]))
        if not fresh.deletion_safe or not all(item.complete for item in fresh.locations) or not _same_capture(manifest, fresh):
            _invalid('The complete capture changed before unlocated collection.')
        repository = RepositoryLocations(settings).named(manifest.repository)[0]
        scopes = _scopes(repository)
        rows = self.connection.execute("""SELECT l.id,l.kind,l.location,l.metadata->>'corpus',v.snapshot_hash,v.source_bytes,l.metadata
            FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
            JOIN public.mycel_file_locations l ON l.file_version=v.id WHERE f.repository=%s
            FOR SHARE OF f,v,l NOWAIT""", (manifest.repository,)).fetchall()
        remaining = list(rows)
        for row in rows:
            location_corpus(row[6])
        for location in manifest.locations:
            for captured in location.files:
                aliases = {(item.root, item.path) for item in captured.aliases}
                matches = [row for row in remaining if row[1:3] == (location.id.kind, location_key(location.id))
                    and row[3] == captured.corpus and row[4] == captured.file_hash and bytes(row[5]) == captured.source
                    and {(item['root'], item['path']) for item in row[6].get('aliases', ())} == aliases
                    and row[6].get('logicalBindings') == _bindings(captured, scopes)
                    and row[6].get('commit') == location.commit
                    and row[6].get('captureLocation') == location.id.record()]
                if len(matches) != 1:
                    _invalid('Collection requires every exact captured file to be published once.')
                row = matches[0]
                remaining.remove(row)
                if location.id.kind == 'disk':
                    addresses = tuple(sorted((SourceAddress(manifest.repository, item.root, item.path)
                                              for item in captured.aliases), key=lambda item: item.address))
                    observed = _observe(repository, addresses, None if published else captured.source)
                    # A pass that publishes its capture leaves a file replaced
                    # meanwhile, a `git pull` for one, to the next pass (MYC-1.37).
                    if not published and any(list(item['fileIdentity'][:2]) != row[6].get('physicalIdentity')
                                             for item in observed):
                        _invalid('The published physical file identity changed before collection.')
                chunks = self.connection.execute("""SELECT v.snapshot_hash,v.source_bytes,v.metadata,l.metadata
                    FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
                    WHERE l.file_location=%s FOR SHARE OF v,l NOWAIT""", (row[0],)).fetchall()
                inputs = _inputs(captured)
                # Entity rows (MYC-17) are located beside the section chunks on disk;
                # each must be published once with its exact bytes.
                entities = [chunk for chunk in chunks if chunk[2].get('kind') in ENTITY_KINDS]
                chunks = [chunk for chunk in chunks if chunk[2].get('kind') not in ENTITY_KINDS]
                rows_expected = (captured.parsed.entities if location.id.kind == 'disk'
                                 and isinstance(captured.parsed, MarkdownDocument) else ())
                if len(entities) != len(rows_expected):
                    _invalid('Collection requires every captured entity row to be published.')
                for row_expected in rows_expected:
                    raw = row_expected.text.encode('utf-8')
                    located = [chunk for chunk in entities if chunk[0] == row_expected.snapshot_hash
                               and bytes(chunk[1]) == raw and chunk[3].get('name') == row_expected.id]
                    if len(located) != 1:
                        _invalid('Collection requires the exact published entity row.')
                    entities.remove(located[0])
                if len(chunks) != len(inputs):
                    _invalid('Collection requires every captured chunk location to be published.')
                for number, item in enumerate(inputs):
                    metadata = _metadata(captured, number)
                    matching = [chunk for chunk in chunks if chunk[0] == item.snapshot_hash and bytes(chunk[1]) == item.source
                        and all(chunk[3].get(key, chunk[2].get(key)) == value for key, value in metadata.items())]
                    if len(matching) != 1:
                        _invalid('Collection requires the exact parsed chunk bytes and located metadata.')
                    chunks.remove(matching[0])
        if remaining:
            _invalid('Collection requires retirement of every absent file location.')

    def _required_files(self, repository):
        """Keep original full files needed to verify a later code name rename.

        Snapshots of chunks do not reproduce parser context. These file versions
        stay private and have no location; no removed source chunk is retained.
        """
        rows = self.connection.execute("""SELECT DISTINCT m.hash,m.bytes FROM public.mycel_manifests m
            JOIN public.mycel_evidence_references r ON r.repository=m.repository AND r.manifest_hash=m.hash
            WHERE m.repository=%s AND m.kind='baseline'""", (repository,)).fetchall()
        keep = set()
        for digest, raw in rows:
            baseline = BaselineManifest.from_bytes(bytes(raw), digest)
            if baseline.payload['ownerRepository'] != repository:
                raise EvidenceError('snapshot_corrupt')
            descriptor = baseline.payload['dependant']
            if descriptor['comparison']['kind'] != 'code_text':
                continue
            row = self.connection.execute('SELECT file_id FROM public.mycel_chunks WHERE id=%s AND repository=%s',
                (baseline.payload['dependantId'], repository)).fetchone()
            if row is None or row[0] is None:
                continue
            file_hash = descriptor.get('fileHash')
            version = self.connection.execute('SELECT id FROM public.mycel_file_versions '
                'WHERE file_id=%s AND snapshot_hash=%s', (row[0], file_hash)).fetchone()
            if version is None:
                raise EvidenceError('baseline_missing')
            keep.add(version[0])
        return keep

    def collect_in_transaction(self, settings: SettingsSnapshot, manifest: CaptureManifest, *,
                               published: bool = False) -> CollectionResult:
        """Join the caller's atomic publication; acquire no guard or transaction.

        Every location must have been read and published. Downstream owners whose
        resolved source edges disappear must also have their repository guards.
        This method does not implement detection, Drift closure/history pruning,
        repository removal, synthetic generated deletion or a public command.
        With `published`, the manifest is the capture a complete pass has just
        published (MYC-1.37): the disk is not read again, since a change after
        the capture is the next pass's and is named by the pass itself.
        """
        if (not isinstance(settings, SettingsSnapshot) or not isinstance(manifest, CaptureManifest)
                or type(published) is not bool):
            _invalid('Collection requires validated settings and a complete capture.')
        settings.require_valid(require_store=False)
        configured = settings.values['repos'].get(manifest.repository)
        if (configured is None or not configured['enabled'] or not manifest.deletion_safe
                or not all(item.complete for item in manifest.locations)):
            _invalid('An incomplete or ineligible pass cannot collect unlocated versions.')
        require_transaction_guards(self.connection, (manifest.repository,))
        self._published(settings, manifest, published)
        candidates = [row[0] for row in self.connection.execute("""SELECT v.id FROM public.mycel_chunk_versions v
            JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository=%s AND c.file_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM public.mycel_locations l WHERE l.chunk_version=v.id)
            ORDER BY v.id FOR UPDATE OF v,c NOWAIT""", (manifest.repository,)).fetchall()]
        affected = self.connection.execute("""SELECT DISTINCT d.repository FROM public.mycel_dependencies d
            JOIN public.mycel_edges e ON e.dependency=d.id WHERE e.source_version=ANY(%s)""", (candidates,)).fetchall()
        require_transaction_guards(self.connection, tuple(sorted({manifest.repository, *(row[0] for row in affected)})))
        # Record only the owners whose concrete owning rows this deletion removes.
        # Unrelated orphan owners are not ours to release. Drift history survives.
        owners = self.connection.execute("""SELECT repository,baseline_owner FROM public.mycel_dependencies
            WHERE dependant_version=ANY(%s) AND baseline_owner IS NOT NULL
            UNION SELECT repository,baseline_owner FROM public.mycel_relations
            WHERE left_version=ANY(%s) AND baseline_owner IS NOT NULL
            UNION SELECT w.repository,w.evidence_owner FROM public.mycel_classification_work w
            JOIN public.mycel_dependencies d ON d.id=w.dependency
            WHERE d.dependant_version=ANY(%s) AND w.evidence_owner IS NOT NULL""", (candidates,) * 3).fetchall()
        require_transaction_guards(self.connection, tuple(sorted({manifest.repository, *(row[0] for row in owners)})))
        from ._drift_store import DriftStore
        DriftStore(self.connection).close_versions_in_transaction(manifest.repository, candidates,
            because='version_removed')
        versions = self.connection.execute('DELETE FROM public.mycel_chunk_versions WHERE id=ANY(%s)', (candidates,)).rowcount
        released = sum(self.connection.execute(_RELEASE_OWNER_SQL, (owner, repository)).rowcount
                       for repository, owner in owners)
        dead = [row[0] for row in self.connection.execute("""SELECT c.id FROM public.mycel_chunks c WHERE c.repository=%s
            AND c.file_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.mycel_chunk_versions v WHERE v.chunk_id=c.id)
            ORDER BY c.id FOR UPDATE NOWAIT""", (manifest.repository,)).fetchall()]
        # Verification lifetime belongs to a logical chunk. Collecting one
        # obsolete searchable version cannot release its history or evidence.
        history = self.connection.execute("""SELECT id,repository,chunk_id,recorded_at,record,evidence_owner
            FROM public.mycel_verifications WHERE chunk_id=ANY(%s) ORDER BY id
            FOR UPDATE NOWAIT""", (dead,)).fetchall()
        require_transaction_guards(self.connection, tuple(sorted({manifest.repository, *(row[1] for row in history)})))
        from ._verification_reader import validate_verification_record
        for row in history:
            validate_verification_record(self.connection, row)
        history_owners = sorted({(row[1], row[5]) for row in history}, key=lambda item: (item[0], str(item[1])))
        for repository, owner in history_owners:
            locked = self.connection.execute('SELECT repository,kind,identity FROM public.mycel_evidence_owners '
                'WHERE id=%s FOR UPDATE NOWAIT', (owner,)).fetchone()
            expected = next(row for row in history if row[5] == owner)
            if locked != (repository, 'verification', str(expected[0])):
                _invalid('The removed logical chunk has inconsistent verification ownership.')
        # A requirement or decision entity row stays, so its withdrawn id remains
        # reserved and every edge that references the UUID keeps its end (MYC-17).
        chunks = self.connection.execute("DELETE FROM public.mycel_chunks WHERE id=ANY(%s) AND kind<>ALL(%s)",
                                         (dead, sorted(ENTITY_KINDS))).rowcount
        released += sum(self.connection.execute(_RELEASE_OWNER_SQL, (owner, repository)).rowcount
                        for repository, owner in history_owners)
        keep = self._required_files(manifest.repository)
        file_versions = self.connection.execute("""DELETE FROM public.mycel_file_versions v
            USING public.mycel_files f WHERE v.file_id=f.id AND f.repository=%s AND NOT (v.id=ANY(%s))
            AND NOT EXISTS (SELECT 1 FROM public.mycel_file_locations l WHERE l.file_version=v.id)""",
            (manifest.repository, list(keep))).rowcount
        files = self.connection.execute("""DELETE FROM public.mycel_files f WHERE f.repository=%s
            AND NOT EXISTS (SELECT 1 FROM public.mycel_file_versions v WHERE v.file_id=f.id)
            AND NOT EXISTS (SELECT 1 FROM public.mycel_chunks c WHERE c.file_id=f.id)""", (manifest.repository,)).rowcount
        snapshots, manifests = self.collect_evidence_in_transaction(manifest.repository)
        return CollectionResult(versions, chunks, file_versions, files, released, snapshots, manifests)
