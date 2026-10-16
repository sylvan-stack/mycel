"""Repository inventory and complete embedding coverage from committed rows.

One caller-owned read-only snapshot covers selection and every reported count.
Place lines and provisional embedding plans use retained bytes, never a scan.
"""

from __future__ import annotations

from ._embed import retained_contexts
from ._embedding_store import EmbeddingStore
from ._errors import MycelError
from ._locks import snapshot_transaction
from ._provenance_reports import ProvenanceReports
from ._resolver import require_read_transaction
from ._scope import RepositoryLocations
from ._store import checked_store


_NAMES_SQL = """SELECT repository FROM public.mycel_repository_state
UNION SELECT repository FROM public.mycel_embedding_receipts ORDER BY repository"""

_DOCUMENTS_SQL = """WITH documents AS (
 SELECT f.id,
   bool_or(l.kind='disk') AS on_disk,
   bool_or(l.kind IN ('branch','stash')) AS elsewhere
 FROM public.mycel_files f
 JOIN public.mycel_file_versions v ON v.file_id=f.id
 JOIN public.mycel_file_locations l ON l.file_version=v.id
 WHERE f.repository=%s AND f.corpus='documents' GROUP BY f.id
)
SELECT count(*) FILTER (WHERE on_disk),
       count(*) FILTER (WHERE NOT on_disk AND elsewhere) FROM documents"""

_CHUNKS_SQL = """WITH chunks AS (
 SELECT c.id,
   bool_or(l.kind IN ('disk','index')) AS on_disk,
   bool_or(l.kind IN ('branch','stash')) AS elsewhere
 FROM public.mycel_chunks c
 JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
 JOIN public.mycel_locations l ON l.chunk_version=v.id
 WHERE c.repository=%s GROUP BY c.id
)
SELECT count(*) FILTER (WHERE on_disk),
       count(*) FILTER (WHERE NOT on_disk AND elsewhere) FROM chunks"""


class RepositoryReports:
    def __init__(self, connection, settings, *, locations=None, tokenizer=None):
        settings.require_valid()
        self.connection, self.settings = connection, settings
        self.locations = locations or RepositoryLocations(settings)
        self._repositories = {repository.name: repository for repository in self.locations.repositories}
        self._embedding = None
        self._tokenizer = tokenizer

    def names_in_snapshot(self):
        require_read_transaction(self.connection)
        return tuple(row[0] for row in self.connection.execute(_NAMES_SQL).fetchall())

    def status_in_snapshot(self, repository):
        require_read_transaction(self.connection)
        configured = self._repositories.get(repository)
        known = configured is not None
        provenance = ProvenanceReports(self.connection).status_in_snapshot(repository)
        documents = self.connection.execute(_DOCUMENTS_SQL, (repository,)).fetchone()
        chunks = self.connection.execute(_CHUNKS_SQL, (repository,)).fetchone()
        last = self.connection.execute('SELECT last_pass_at FROM public.mycel_repository_state '
                                       'WHERE repository=%s', (repository,)).fetchone()
        contexts, retained = retained_contexts(self.connection, repository, in_snapshot=True)
        vectors = {'embedded': 0, 'pending': 0, 'failed': 0, 'deferred': 0, 'ineligible': 0}
        parts = {'embedded': 0, 'pending': 0, 'failed': 0, 'deferred': 0}
        if retained:
            if self._embedding is None:
                self._embedding = EmbeddingStore(self.connection, self.settings, tokenizer=self._tokenizer)
            prepared = self._embedding.prepare_in_snapshot(repository, contexts=contexts)
            coverage = prepared.counts.to_dict()
            vectors, parts = coverage['versions'], coverage['parts']
            vectors['ineligible'] = prepared.counts.ineligible_versions
        folders = {}
        if known:
            if configured.code is not None:
                folders['code'] = str(configured.code.path)
            if configured.documents is not None:
                folders['documents'] = str(configured.documents.path)
        result = {**provenance, 'known': known, 'enabled': known and configured.enabled,
                  'folders': folders,
                  'documents': {'onDisk': documents[0], 'elsewhere': documents[1]},
                  # Generated index chunks are current alongside disk chunks,
                  # matching the provenance stale total and current read scope.
                  'chunks': {'onDisk': chunks[0], 'elsewhere': chunks[1], 'stale': provenance['stale']},
                  'vectors': vectors, 'parts': parts}
        if last is not None and last[0] is not None:
            result['lastPass'] = last[0].isoformat()
        return result

    def status(self, repository):
        with checked_store(self.connection, dimensions=self.settings.values['embedding']['dimensions']), \
                snapshot_transaction(self.connection):
            return self.status_in_snapshot(repository)


def report_status(invocation):
    from ._cli import invocation_store, repository_result
    if invocation.settings is None:
        raise MycelError('internal', 'Settings were not loaded for this invocation.')
    locations = RepositoryLocations(invocation.settings)
    with invocation_store(invocation) as (connection, _inspection), snapshot_transaction(connection):
        reports = RepositoryReports(connection, invocation.settings, locations=locations)
        stored = set(reports.names_in_snapshot())
        selected, entries = {}, []
        if invocation.all_repositories:
            names = stored | {repository.name for repository in locations.repositories if repository.enabled}
            selected = dict.fromkeys(sorted(names))
        elif invocation.repositories:
            for name in invocation.repositories:
                try:
                    for repository in locations.named(name):
                        selected.setdefault(repository.name)
                except MycelError as error:
                    if name in stored and name not in invocation.settings.values['organizations']:
                        selected.setdefault(name)
                    else:
                        entries.append({'repository': name, 'error': error.to_dict()['error']})
        else:
            selected = dict.fromkeys(repository.name for repository in locations.resolve_scope())
        for name in selected:
            try:
                entries.append({'repository': name, 'result': reports.status_in_snapshot(name)})
            except MycelError as error:
                entries.append({'repository': name, 'error': error.to_dict()['error']})
        return repository_result(entries, started=bool(selected))
