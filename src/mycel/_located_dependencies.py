"""Private dependency producer for a complete checked located publication.

The caller holds the complete repository guards. Identity decisions select
which exact location-owned reference version may supply prior pins; physical
and retained captures are reread without substituting disk text for Git text.
This producer exposes no command and performs no provider call.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from ._activity import MutationActivity
from ._capture import CaptureManifest, LocationId
from ._declared_refs import _text
from ._errors import MycelError
from ._located_reconciliation import location_key
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddressError, parse_source_address


class LocatedDependencyProducer:
    refresh_unchanged = True

    def __init__(self, settings: SettingsSnapshot, *, captured_at: str,
                 settings_home: Path | None = None,
                 collection_manifest: CaptureManifest | None = None,
                 activity: MutationActivity | None = None,
                 guarded_repositories: tuple[str, ...] | None = None,
                 pending_repositories: tuple[str, ...] = (),
                 defer_changed_dependants: bool = False,
                 snapshot: CaptureManifest | None = None):
        if type(defer_changed_dependants) is not bool:
            raise MycelError('invalid_input', 'Foreign dependant deferral requires an explicit boolean.')
        if snapshot is not None and not isinstance(snapshot, CaptureManifest):
            raise MycelError('invalid_input', 'A publication snapshot must be the complete capture manifest.')
        self.snapshot = snapshot
        self.settings = settings
        self.captured_at = captured_at
        self.settings_home = settings_home
        self.collection_manifest = collection_manifest
        self.activity = activity
        self.guarded_repositories = guarded_repositories
        self.pending_repositories = pending_repositories
        self.defer_changed_dependants = defer_changed_dependants
        self._publication = None

    def __call__(self, connection, result):
        from ._dependency_application import DependencyApplicationStore
        from ._dependency_inputs import DependencyCaptureInputs
        from ._relations import RelationApplicationStore, _relation_raw
        # A pass that publishes its capture reads each location's catalog once
        # for the whole run; files, chunks and locations do not change while
        # dependencies, pins and relations are written (SYL-232).
        catalogs = {} if self.snapshot is not None else None
        inputs = DependencyCaptureInputs(connection, self.settings, settings_home=self.settings_home,
                                         guarded_repositories=self.guarded_repositories, snapshot=self.snapshot,
                                         catalogs=catalogs)
        totals = {}

        store = DependencyApplicationStore(connection)
        relations = RelationApplicationStore(connection)

        self._publication = None
        activity = self.activity if self.activity is not None else result.activity
        if (activity is not None and activity.connection is not connection
                or self.activity is not None and result.activity is not None and self.activity is not result.activity):
            raise MycelError('invalid_input', 'Dependency activity requires the exact publishing connection.')

        own_scopes = tuple((file.binding.location, version) for file in result.files for _, version in file.chunk_versions)
        published = {file.binding.primary.repository for file in result.files}
        if self.collection_manifest is not None:
            published.add(self.collection_manifest.repository)
        # A deletion can leave no files at all; the complete result retains its
        # publishing repository even without a collection callback.
        published.add(result.repository)
        incoming = {}
        rows = connection.execute("""SELECT d.repository,d.declaration,d.source_place,d.state,
            l.id,l.kind,l.location,l.metadata,d.dependant_version,d.id
            FROM public.mycel_dependencies d
            JOIN public.mycel_file_locations l ON l.id::text=d.state->'declarationLocation'->>'file'
            JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id AND f.repository=d.repository
            JOIN public.mycel_locations c ON c.file_location=l.id AND c.chunk_version=d.dependant_version
            WHERE d.kind=ANY(ARRAY['declared','asserted']) ORDER BY d.repository,l.id,d.dependant_version""").fetchall()
        rows = [(False, row) for row in rows]
        rows += [(True, row) for row in connection.execute("""SELECT r.repository,r.state->>'rawRef',r.right_place,r.state,
            l.id,l.kind,l.location,l.metadata,r.left_version,r.id FROM public.mycel_relations r
            JOIN public.mycel_file_locations l ON l.id::text=r.state->'declarationLocation'->>'file'
            JOIN public.mycel_file_versions v ON v.id=l.file_version
            JOIN public.mycel_files f ON f.id=v.file_id AND f.repository=r.repository
            JOIN public.mycel_locations c ON c.file_location=l.id AND c.chunk_version=r.left_version
            ORDER BY r.repository,l.id,r.left_version""").fetchall()]
        for relation, (owner, declaration, place, state, file_id, kind, location, metadata, version, reference_id) in rows:
            if owner in published or not self.settings.values['repos'].get(owner, {}).get('enabled'):
                continue
            # Dependency spellings are hex encoded to retain malformed/NUL
            # input; retained relation spellings are literal valid refs.
            # Both are strings, so their owning row determines decoding.
            raw = (_relation_raw(state) if relation else _text(state['rawRef'])) if 'rawRef' in state else declaration
            targets = set()
            for value in (raw, place):
                try:
                    targets.add(parse_source_address(value).repository)
                except SourceAddressError:
                    pass
            if not targets.intersection(published):
                continue
            if self.guarded_repositories is not None and owner not in self.guarded_repositories:
                if owner not in self.pending_repositories:
                    raise MycelError('invalid_input', 'Affected dependency ownership changed before guarded publication.')
                continue
            selected = state['declarationLocation']
            if (selected.get('kind'), selected.get('location')) != (kind, location):
                raise MycelError('invalid_input', 'Dependency ownership differs from its current location.')
            record = metadata.get('captureLocation')
            if not isinstance(record, dict) or set(record) != {'kind', 'checkout', 'identity'}:
                raise MycelError('invalid_input', 'Dependency refresh requires the exact captured location.')
            identifier = LocationId(**record)
            if identifier.kind != kind or location_key(identifier) != location:
                raise MycelError('invalid_input', 'Dependency refresh requires the exact captured location.')
            item = incoming.setdefault((str(file_id), version), {'owner': owner, 'location': identifier,
                'commit': metadata.get('commit'), 'dependencies': set(), 'relations': set()})
            item['relations' if relation else 'dependencies'].add(str(reference_id))
        if self.defer_changed_dependants:
            # An upstream search check must be able to publish before a dirty
            # dependant's own ingest. Observe its exact physical input, retain
            # existing pins/reasons and report its update as pending instead of
            # qualifying old indexed text or aborting the required source pass.
            from ._resolver import SourceResolver
            dirty = set()
            catalogs = {}
            for (file_id, version), item in sorted(incoming.items()):
                owner, identifier = item['owner'], item['location']
                key = (identifier.kind, location_key(identifier))
                if key not in catalogs:
                    catalogs[key] = SourceResolver.from_transaction(connection, self.settings,
                        kind=identifier.kind, location=key[1],
                        guarded_repositories=self.guarded_repositories)
                logical = connection.execute('SELECT fv.file_id FROM public.mycel_file_locations fl '
                    'JOIN public.mycel_file_versions fv ON fv.id=fl.file_version WHERE fl.id=%s',
                    (file_id,)).fetchone()
                stored = next((file for file in catalogs[key].files if logical is not None
                    and file.identifier == str(logical[0])
                    and any(chunk.version == version for chunk in file.chunks)), None)
                manifest = inputs.observe(owner)
                places = [place for place in manifest.locations if place.id == identifier]
                actual = [file for place in places for file in place.files if stored is not None
                    and any(alias.root == stored.primary.root and alias.path == stored.primary.path
                            for alias in file.aliases)]
                if stored is None or len(actual) != 1 or actual[0].source != stored.source:
                    dirty.add(owner)
            if dirty:
                incoming = {key: item for key, item in incoming.items() if item['owner'] not in dirty}
                self.pending_repositories = tuple(sorted(set(self.pending_repositories) | dirty))
        foreign_scopes = {scope: tuple(sorted(item['dependencies'])) for scope, item in incoming.items()
                          if item['dependencies']}
        scopes = own_scopes + tuple(sorted(foreign_scopes))
        downstream = {}
        downstream_changed = set()
        primary_changed = False
        context = store.batch_in_transaction(self.settings, scopes=scopes,
            guarded_repositories=self.guarded_repositories,
            observation_dependencies=foreign_scopes) if scopes else nullcontext(None)
        with context as batch:
            for located in result.files:
                prior = dict(located.previous_versions)
                reread = inputs.rereader(located.location, located.binding.primary.repository, located.commit)
                for decision, (identifier, version) in zip(located.identity.decisions, located.chunk_versions):
                    if decision.pin_decision == 'inherit_existing':
                        mode, pin_version = 'inherit', decision.pin_version
                        authorization = ('recognized_rename' if decision.reason == 'renamed'
                                         else 'normalized_equivalent_edit')
                    elif decision.pin_decision == 'restore_existing':
                        mode, pin_version = 'restore', version
                        authorization = 'normalized_equivalent_edit'
                    else:
                        mode, pin_version = 'edit', prior.get(identifier)
                        authorization = 'normalized_equivalent_edit'
                    applied = store.apply_in_transaction(
                        self.settings, located.binding.location, version, mode=mode,
                        pin_version=pin_version, reference_location=located.binding.location,
                        captured_at=self.captured_at, reread=reread,
                        inheritance_authorization=authorization, batch=batch,
                        guarded_repositories=self.guarded_repositories, catalogs=catalogs)
                    primary_changed = primary_changed or applied.mutated
                    for name, value in applied.counts.items():
                        totals[name] = totals.get(name, 0) + value
                    for observed in (relations.apply_in_transaction(self.settings, located.binding.location, version,
                            captured_at=self.captured_at, reread=reread, mode=mode,
                            pin_version=pin_version if mode != 'edit' else prior.get(identifier),
                            reference_location=located.binding.location,
                            inheritance_authorization=authorization,
                            guarded_repositories=self.guarded_repositories, catalogs=catalogs),):
                        primary_changed = primary_changed or observed.mutated
                        for name, value in observed.counts.items():
                            totals[name] = totals.get(name, 0) + value
            for (file_id, version), item in sorted(incoming.items()):
                owner, identifier, commit = item['owner'], item['location'], item['commit']
                counts = downstream.setdefault(owner, {})
                if item['dependencies']:
                    applied = store.apply_in_transaction(self.settings, file_id, version,
                        captured_at=self.captured_at, reread=inputs.rereader(identifier, owner, commit),
                        mode='observe', batch=batch, guarded_repositories=self.guarded_repositories,
                        observation_dependencies=tuple(sorted(item['dependencies'])), catalogs=catalogs)
                    for name, value in applied.counts.items():
                        counts[name] = counts.get(name, 0) + value
                    if applied.mutated:
                        downstream_changed.add(owner)
                for observed in (() if not item['relations'] else (relations.apply_in_transaction(self.settings, file_id, version,
                        captured_at=self.captured_at, mode='observe',
                        reread=inputs.rereader(identifier, owner, commit),
                        guarded_repositories=self.guarded_repositories,
                        observation_relations=tuple(sorted(item['relations'])), catalogs=catalogs),)):
                    for name, value in observed.counts.items():
                        counts[name] = counts.get(name, 0) + value
                    if observed.mutated:
                        downstream_changed.add(owner)
        if self.pending_repositories:
            totals['dependencyPending'] = list(self.pending_repositories)
        # A substantive dependant edit answers its previous version's work.
        # Equivalent/rename inheritance retains unresolved work and exact
        # evidence; collection below labels only genuinely removed versions.
        from ._drift_store import DriftStore
        drifts = DriftStore(connection)
        for located in result.files:
            if located.location.kind != 'disk':
                continue
            previous = dict(located.previous_versions)
            edited = tuple(previous[identifier] for decision, (identifier, version) in
                zip(located.identity.decisions, located.chunk_versions)
                if decision.pin_decision == 'requires_authorized_capture' and identifier in previous
                and previous[identifier] != version)
            if edited:
                primary_changed = drifts.close_versions_in_transaction(located.binding.primary.repository,
                    edited, because='edited', at=self.captured_at) or primary_changed
        if self.collection_manifest is not None and not self.pending_repositories:
            from ._collection import CollectionStore
            removed_edges = connection.execute("""SELECT d.repository,count(*) FROM public.mycel_edges e
                JOIN public.mycel_dependencies d ON d.id=e.dependency
                JOIN public.mycel_chunk_versions v ON v.id=e.source_version
                JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository=%s AND c.file_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM public.mycel_locations l WHERE l.chunk_version=v.id)
                GROUP BY d.repository""", (self.collection_manifest.repository,)).fetchall()
            collected = CollectionStore(connection).collect_in_transaction(self.settings, self.collection_manifest,
                published=self.snapshot is not None)
            totals['collected'] = {name: getattr(collected, name) for name in
                ('versions', 'chunks', 'file_versions', 'files', 'owners', 'snapshots', 'manifests')}
            primary_changed = primary_changed or any(totals['collected'].values())
            for owner, count in removed_edges:
                if owner == result.repository:
                    totals['sourceEdgesCollected'] = count
                else:
                    downstream.setdefault(owner, {})['sourceEdgesCollected'] = count
                    downstream_changed.add(owner)
        elif self.collection_manifest is not None:
            # A source deletion would cascade an unheld owner's edge. Keep its
            # unlocated rows for this explicitly incomplete pass and retry on
            # the next unchanged pass after every affected guard is available.
            totals['collectionPending'] = list(self.pending_repositories)
        # Each selected cross-repository acquisition remains exact after all
        # producers, including a source absent from the publishing repository.
        inputs.verify()
        if downstream:
            totals['dependencyRepositories'] = downstream
        result.counts.update(totals)
        result.dependency_changes.update(downstream_changed)
        self._publication = (connection, result, inputs)
        return primary_changed

    def verify_in_transaction(self, connection, result):
        """Recheck all foreign inputs after reply/audit callbacks, before commit."""
        from ._locks import require_transaction_guards
        require_transaction_guards(connection, tuple(self.settings.values['repos'])
            if self.guarded_repositories is None else self.guarded_repositories)
        if (self._publication is None or self._publication[0] is not connection
                or self._publication[1] is not result):
            raise MycelError('invalid_input', 'Dependency final checks require their exact publication.')
        self.settings.require_current()
        self._publication[2].verify()
