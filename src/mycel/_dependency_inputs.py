"""Fresh complete capture guards shared by located publication and assertions.

The guard rereads exact disk/Git inputs and settings; it never ingests or changes
any source. Explicit absence checks include every relevant retained location.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ._capture import CaptureManifest, capture_repository
from ._dependency_application import RetainedDependencyResolver
from ._disk_reconciliation import _same_capture
from ._errors import MycelError
from ._evidence import EvidenceError, PinInputs
from ._located_reconciliation import location_key
from ._resolver import SourceResolver
from ._settings import SettingsSnapshot, load_settings
from ._source_refs import SourceAddressError, parse_source_address


class DependencyCaptureInputs:
    """Reread the inputs of a guarded mutation.

    Without a snapshot every observation is fresh and must match the first one
    exactly, as `derive`, `relate` and `confirm` require (MYC-16). With a
    snapshot, the capture a complete pass publishes, the pass's own repository
    is observed through that capture, another repository is observed once and
    never compared with its index (its own pass does that), and later disk
    changes are the next pass's business (MYC-1.37, MYC-D64).
    """
    def __init__(self, connection, settings: SettingsSnapshot, *, settings_home: Path | None = None,
                 guarded_repositories: tuple[str, ...] | None = None,
                 snapshot: CaptureManifest | None = None):
        if snapshot is not None and not isinstance(snapshot, CaptureManifest):
            raise MycelError('invalid_input', 'A capture snapshot must be a complete capture manifest.')
        self.connection = connection
        self.settings = settings
        self.settings_home = settings._home if settings_home is None else settings_home
        self.captures = {} if snapshot is None else {snapshot.repository: snapshot}
        self.guarded_repositories = guarded_repositories
        self.snapshot = snapshot

    def observe(self, repository):
        if self.snapshot is not None and repository in self.captures:
            return self.captures[repository]
        observed = capture_repository(self.settings, repository)
        if not observed.deletion_safe:
            raise EvidenceError('changed_since_ingest')
        previous = self.captures.setdefault(repository, observed)
        if self.snapshot is None and not _same_capture(previous, observed):
            raise EvidenceError('changed_since_ingest')
        return observed

    def _physical(self, repository) -> bool:
        """Whether this repository's disk is compared with the catalog."""
        return self.snapshot is None or repository == self.snapshot.repository

    def rereader(self, identifier, owner, commit):
        connection = self.connection
        key = location_key(identifier)
        def reread(expected):
            settings = load_settings(path=self.settings.file, home=self.settings_home)
            try:
                settings.require_valid(require_store=False)
            except MycelError:
                raise EvidenceError('changed_since_ingest') from None
            if settings.values != self.settings.values:
                raise EvidenceError('changed_since_ingest')
            catalog = SourceResolver.from_transaction(connection, settings,
                kind=identifier.kind, location=key, guarded_repositories=self.guarded_repositories)
            catalog = RetainedDependencyResolver(catalog, expected.catalog.anchors,
                                                 expected.catalog.syntax_faults,
                                                 endpoint_refs=expected.catalog.endpoint_refs)
            endpoint = catalog.resolve(expected.dependant.place.address, purpose='endpoint')
            if endpoint.state != 'resolved' or len(endpoint.selection.members) != 1:
                raise EvidenceError('changed_since_ingest')
            resolution = catalog.resolve(expected.resolution.declaration)
            selected = (endpoint.selection.file,)
            if resolution.state == 'resolved':
                selected += (resolution.selection.file,)
            try:
                address = parse_source_address(expected.resolution.declaration)
            except SourceAddressError:
                address = None
            if (address is not None and settings.values['repos'].get(address.repository, {}).get('enabled')
                    and self._physical(address.repository)):
                from ._locks import require_transaction_guards
                require_transaction_guards(connection, (address.repository,))
                manifest = self.observe(address.repository)
                places = [place for place in manifest.locations if place.id == identifier]
                current_files = tuple(file for file in catalog.files if file.repository == address.repository
                    and any(alias.path == address.path and address.root in {None, alias.root} for alias in file.aliases))
                selected += current_files
                actual_files = [item for place in places for item in place.files if any(
                    alias.path == address.path and address.root in {None, alias.root} for alias in item.aliases)]
                # The complete raw-path candidate set must still match
                # the indexed catalog. A recreated path or newly colliding
                # root cannot hide behind a retained move or old selection.
                def inputs(files):
                    return sorted((tuple(sorted((alias.root, alias.path) for alias in file.aliases)),
                                   file.source) for file in files)
                retained = expected.catalog.anchors.get(expected.resolution.declaration)
                natural = None
                if resolution.state != 'resolved':
                    natural = expected.guards['dependencyApplication']['sourcePlaces'].get(
                        expected.resolution.declaration)
                initially_unindexed = (not isinstance(expected, PinInputs)
                    and resolution.state == 'unresolved' and resolution.fault == 'missing_file'
                    and not current_files and retained is None and natural is None)
                # A never-resolved declared ref stays retryable until a named
                # source pass indexes its target. Observing physical files here
                # cannot make them indexed authority or broaden ingest scope.
                # observe()/verify() still guard the complete physical capture;
                # resolved and retained selections keep the exact index check.
                if not initially_unindexed and inputs(actual_files) != inputs(current_files):
                    raise EvidenceError('changed_since_ingest')
                if resolution.state != 'resolved':
                    if not initially_unindexed:
                        self._check_absence_inventory(connection, address, retained, natural, manifest)
            for file in selected:
                if not self._physical(file.repository):
                    continue
                manifest = self.observe(file.repository)
                places = [place for place in manifest.locations if place.id == identifier]
                if len(places) != 1:
                    raise EvidenceError('changed_since_ingest')
                place = places[0]
                if file.repository == owner and place.commit != commit:
                    raise EvidenceError('changed_since_ingest')
                files = [item for item in place.files if any(
                    alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
                if len(files) != 1 or files[0].source != file.source:
                    raise EvidenceError('changed_since_ingest')
            values = dict(settings=settings, dependant=endpoint.selection.members[0],
                dependant_file=endpoint.selection.file, resolution=resolution, catalog=catalog)
            if isinstance(expected, PinInputs):
                if resolution.state != 'resolved':
                    raise EvidenceError('changed_since_ingest')
                values['selection'] = resolution.selection
            return replace(expected, **values)
        return reread

    def verify(self):
        try:
            self.settings.require_current()
        except MycelError:
            raise EvidenceError('changed_since_ingest') from None
        if self.snapshot is not None:
            return  # The pass publishes its capture; later changes are the next pass's.
        for repository, expected in self.captures.items():
            if not _same_capture(expected, capture_repository(self.settings, repository)):
                raise EvidenceError('changed_since_ingest')

    @staticmethod
    def _check_absence_inventory(connection, address, anchor, natural, manifest):
        """Validate the located witnesses that distinguish away from deleted."""
        anchors = set()
        if anchor is not None:
            anchors = {row[0] for row in connection.execute("""SELECT id FROM public.mycel_files
                WHERE repository=%s AND id::text=%s UNION SELECT file_id FROM public.mycel_chunks
                WHERE repository=%s AND id::text=%s""",
                (address.repository, anchor, address.repository, anchor)).fetchall()}
        rows = connection.execute("""SELECT f.id,l.kind,l.location,l.metadata,v.source_bytes
            FROM public.mycel_files f JOIN public.mycel_file_versions v ON v.file_id=f.id
            JOIN public.mycel_file_locations l ON l.file_version=v.id WHERE f.repository=%s""",
            (address.repository,)).fetchall()
        retained_paths = {(item['root'], item['path']) for identifier, _, _, metadata, _ in rows
                          if identifier in anchors for item in metadata.get('aliases', ())}
        if natural is not None:
            place = parse_source_address(natural)
            if place.repository != address.repository:
                raise EvidenceError('changed_since_ingest')
            retained_paths.add((place.root, place.path))

        def relevant(aliases):
            return any((path == address.path and address.root in {None, root})
                       or (root, path) in retained_paths for root, path in aliases)

        stored = []
        for _, kind, location, metadata, raw in rows:
            aliases = tuple(sorted((item['root'], item['path']) for item in metadata.get('aliases', ())))
            if relevant(aliases):
                stored.append((kind, location, metadata.get('commit'), aliases, bytes(raw)))
        actual = []
        for place in manifest.locations:
            for file in place.files:
                aliases = tuple(sorted((item.root, item.path) for item in file.aliases))
                if relevant(aliases):
                    actual.append((place.id.kind, location_key(place.id), place.commit, aliases, file.source))
        if sorted(stored, key=repr) != sorted(actual, key=repr):
            raise EvidenceError('changed_since_ingest')
