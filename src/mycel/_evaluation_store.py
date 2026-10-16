"""Transaction-bound evaluation through the ordinary retrieval producer.

Normal candidates and ranking borrow the evaluator's single snapshot. Controlled
callbacks remain available to internal checks without replacing production
ranking. The fingerprint covers the complete enabled disk/index catalog:
expectation faults can depend on files outside the selected result scope too.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from hashlib import sha256
import json
from types import MappingProxyType
from uuid import UUID

import psycopg

from ._errors import MycelError
from ._evaluation import PreparedQueryVector, RetrievalPlace, RetrievalQuery, RetrievalReply
from ._locks import snapshot_transaction
from ._location_corpus import location_corpus
from ._resolver import (SelectionMember, SourceResolver, require_read_transaction)
from ._search_reply import SEARCH_REPLY
from ._settings import SettingsSnapshot, _freeze
from ._store import checked_store


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(member) for key, member in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(member) for member in value]
    if isinstance(value, (bytes, memoryview)):
        return {"bytes": bytes(value).hex()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _hash(value) -> str:
    return sha256(json.dumps(_plain(value), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _shared(settings: SettingsSnapshot, repository: str, path: str) -> bool:
    for selection in settings.values["search"]["shared_documents"]:
        if selection["repo"] == repository and any(
                prefix == "." or path == prefix or path.startswith(prefix.rstrip("/") + "/")
                for prefix in selection["paths"]):
            return True
    return False


@dataclass
class _Lease:
    active: bool = True


@dataclass(frozen=True)
class StoreRetrievalSnapshot:
    resolver: SourceResolver
    index_generation: str
    index_fingerprint: str
    settings_hash: str
    search_reply: int
    repository: str
    _connection: object = field(repr=False, compare=False)
    _search: Callable | None = field(repr=False, compare=False)
    _origins: Mapping[tuple[str, int], str] = field(repr=False, compare=False)
    _members: Mapping[tuple[str, int], SelectionMember] = field(repr=False, compare=False)
    _artifact_paths: Mapping[tuple[str, int], tuple[str, ...]] = field(repr=False, compare=False)
    _lease: _Lease = field(repr=False, compare=False)
    _candidates: object | None = field(default=None, repr=False, compare=False)
    _store_dimensions: int | None = field(default=None, repr=False, compare=False)

    def _require_active(self) -> None:
        if not self._lease.active:
            raise MycelError("invalid_input", "The evaluation index snapshot has ended.")
        require_read_transaction(self._connection)

    def eligible(self, query: RetrievalQuery, member: SelectionMember) -> bool:
        """Use corpus origin and retained binding, never the filename suffix."""
        self._require_active()
        key = (member.chunk.identifier, member.chunk.version)
        if self._members.get(key) != member:
            return False
        origin = self._origins[key]
        if query.only == "code" and origin != "code":
            return False
        if query.only == "docs" and origin != "documents":
            return False
        if member.place.repository == self.repository:
            return True
        # Shared paths select the document's artifact aliases. Its retained
        # primary can still be code, and remains the canonical returned place.
        return (query.only != "code" and origin == "documents"
                and any(_shared(self.resolver.settings, member.place.repository, path)
                        for path in self._artifact_paths.get(key, ())))

    def search(self, query: RetrievalQuery, prepared: PreparedQueryVector, *,
               k: int = 10, freshness: bool = False) -> RetrievalReply:
        self._require_active()
        if k != 10 or freshness is not False:
            raise MycelError("invalid_input", "Evaluation requires ten results without freshness checking.")
        if self._search is None:
            raise MycelError("refused", "Normal retrieval is not implemented; a nonempty retrieval evaluation cannot run.")
        reply = self._search(self._connection, self, query, prepared, k=k, freshness=freshness)
        if not isinstance(reply, RetrievalReply):
            raise MycelError("internal", "Normal retrieval returned an incompatible evaluation reply.")
        if type(reply.results) is not tuple:
            raise MycelError("internal", "Normal retrieval returned incompatible evaluation places.")
        for result in reply.results:
            if not isinstance(result, RetrievalPlace):
                raise MycelError("internal", "Normal retrieval returned an incompatible evaluation place.")
            member = self._members.get((result.identifier, result.version))
            if (member is None or result.address != member.place or not self.eligible(query, member)):
                raise MycelError("internal", "Normal retrieval returned a place outside the evaluation snapshot's result scope.")
        return reply


class StoreRetrieval:
    """Freeze one invocation's settings and delegate only inside its snapshot.

    search(connection, snapshot, query, prepared, *, k, freshness) must be the
    normal retrieval handoff. Its default uses CandidateSnapshot.ranked; checks
    may inject controlled replies over actual stored places. This adapter
    supplies no alternative scorer or vector provider.
    """

    def __init__(self, connection, settings: SettingsSnapshot, *, search: Callable | None = None,
                 search_reply: int = SEARCH_REPLY):
        settings.require_valid()
        if type(search_reply) is not int or search_reply < 1 or search is not None and not callable(search):
            raise MycelError("invalid_input", "Evaluation requires a valid normal retrieval handoff.")
        self._connection = connection
        self._settings = replace(settings, values=_freeze(_plain(settings.values)))
        self._settings_hash = _hash(self._settings.values)
        self._search = normal_search if search is None else search
        self._search_reply = search_reply

    @contextmanager
    def snapshot(self, repository: str) -> Iterator[StoreRetrievalSnapshot]:
        repositories = self._settings.values["repos"]
        if repository not in repositories or not repositories[repository]["enabled"]:
            raise MycelError("invalid_input", "Evaluation requires a registered enabled repository.")
        try:
            with checked_store(self._connection) as inspection, snapshot_transaction(self._connection):
                resolver = SourceResolver.from_read_transaction(self._connection, self._settings)
                generation = self._connection.execute(
                    "SELECT index_generation FROM public.mycel_store WHERE singleton=true").fetchone()
                if generation is None or not isinstance(generation[0], UUID):
                    raise MycelError("store_format", "The evaluation snapshot lacks an index generation.")
                origins, members, artifact_paths, fingerprint = _inputs(self._connection, resolver)
                lease = _Lease()
                candidates = None
                if self._search is normal_search:
                    from ._retrieval_store import candidate_snapshot_in_transaction
                    candidates = candidate_snapshot_in_transaction(self._connection, resolver,
                                                                   (repository,), lease=lease)
                snapshot = StoreRetrievalSnapshot(resolver, str(generation[0]), fingerprint,
                    self._settings_hash, self._search_reply, repository, self._connection,
                    self._search, origins, members, artifact_paths, lease,
                    candidates, inspection.dimensions)
                try:
                    yield snapshot
                finally:
                    lease.active = False
        except psycopg.Error:
            raise MycelError("store_unavailable", "The retrieval evaluation snapshot could not be read.") from None


class NormalQueryVectors:
    """Adapt normal query planning, transport and explicit fallback reasons.

    The caller obtains store dimensions before any vector work. Each prepare
    call runs outside the evaluator's retrieval snapshot. The supplied policy
    identifies explicitly selected retrieval evaluation at both credential and
    provider boundaries, while normal searches keep their existing policy.
    """
    def __init__(self, settings: SettingsSnapshot, *, store_dimensions: int,
                 credentials=None, prepare=None, client_factory=None):
        from ._credentials import Credentials
        from ._safeguards import InvocationPolicy

        settings.require_valid()
        if (type(store_dimensions) is not int or store_dimensions <= 0
                or prepare is not None and not callable(prepare)
                or client_factory is not None and not callable(client_factory)):
            raise MycelError("invalid_input", "Evaluation query preparation requires valid store dimensions and adapters.")
        self._settings = replace(settings, values=_freeze(_plain(settings.values)))
        self._store_dimensions = store_dimensions
        self._policy = InvocationPolicy("evaluate", kind="retrieval")
        self._credentials = Credentials(self._settings, self._policy) if credentials is None else credentials
        self._prepare, self._client_factory = prepare, client_factory

    def prepare(self, query: RetrievalQuery) -> PreparedQueryVector:
        from ._search import QueryEmbedding, prepare_query

        if not isinstance(query, RetrievalQuery):
            raise MycelError("invalid_input", "Evaluation query preparation requires a validated retrieval query.")
        if self._store_dimensions != self._settings.values["embedding"]["dimensions"]:
            return PreparedQueryVector(None, "The store vector dimensions differ from settings. Run mycel init before using meaning search.")
        options = {"credentials": self._credentials, "policy": self._policy}
        if self._client_factory is not None:
            options["_client_factory"] = self._client_factory
        embedded = (self._prepare or prepare_query)(self._settings, query.text, **options)
        if not isinstance(embedded, QueryEmbedding):
            raise MycelError("internal", "Normal query preparation returned an incompatible evaluation result.")
        return PreparedQueryVector(embedded.vector, embedded.reason)


def normal_search(connection, snapshot: StoreRetrievalSnapshot, query: RetrievalQuery,
                  prepared: PreparedQueryVector, *, k: int, freshness: bool) -> RetrievalReply:
    """Use the production candidate and ranking path in the existing snapshot."""
    snapshot._require_active()
    if (connection is not snapshot._connection or k != 10 or freshness is not False
            or snapshot._candidates is None or not isinstance(prepared, PreparedQueryVector)):
        raise MycelError("invalid_input", "Normal evaluation retrieval requires its exact active snapshot.")
    vector = prepared.vector
    if snapshot._store_dimensions != snapshot.resolver.settings.values["embedding"]["dimensions"]:
        vector = None
    rankings = snapshot._candidates.ranked(query.text, vector, k=10, only=query.only)
    if len(rankings) != 1 or rankings[0].repository != snapshot.repository:
        raise MycelError("internal", "Normal evaluation retrieval returned an incompatible repository scope.")
    ranking = rankings[0]
    return RetrievalReply(ranking.route, ranking.meaning_used,
        tuple(RetrievalPlace(entry.chunk.identifier, entry.chunk.version, entry.chunk.place)
              for entry in ranking.results))


def _inputs(connection, resolver: SourceResolver):
    members = {}
    owning_files = {}
    artifact_paths = {}
    files = []
    for file in sorted(resolver.files, key=lambda item: item.identifier):
        files.append((file.identifier, file.repository, file.primary.address,
                      tuple(alias.address for alias in file.aliases), file.snapshot_hash,
                      tuple(prior.address for prior in file.recognized_moves)))
        for chunk in file.chunks:
            key = (chunk.identifier, chunk.version)
            members[key] = SelectionMember(resolver._place(file, chunk), chunk)
            owning_files[key] = file
            artifact_paths[key] = tuple(alias.path for alias in file.aliases if alias.root == "artifact")
    for place, chunk in resolver.index:
        members[(chunk.identifier, chunk.version)] = SelectionMember(place, chunk)
    versions = sorted({member.chunk.version for member in members.values()})
    identifiers = sorted({member.chunk.identifier for member in members.values()})
    corpus_rows = connection.execute("""SELECT c.id,v.id,l.id,l.kind,l.location,
        fl.id,fl.kind,fl.location,fl.metadata,f.id,f.repository,f.root,f.path,
        fv.id,fv.snapshot_hash
        FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
        JOIN public.mycel_locations l ON l.chunk_version=v.id
        LEFT JOIN public.mycel_file_locations fl ON fl.id=l.file_location
        LEFT JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=c.file_id
        LEFT JOIN public.mycel_files f ON f.id=fv.file_id AND f.repository=c.repository
        WHERE c.id=ANY(%s::uuid[]) AND v.id=ANY(%s) AND l.kind='disk'
        ORDER BY c.id,v.id,l.id""", (identifiers, versions)).fetchall()
    by_member = {}
    for row in corpus_rows:
        by_member.setdefault((str(row[0]), row[1]), []).append(row)
    origins = {}
    for key, member in members.items():
        # Both generated index namespaces are document text, not source code.
        if member.place.root == "index" and key not in owning_files:
            origins[key] = 'documents'
            continue
        rows = by_member.get(key, ())
        if len(rows) != 1:
            raise MycelError('store_format', 'The evaluation member needs one exact owning disk file location.')
        row = rows[0]
        file = owning_files[key]
        corpus = location_corpus(row[8])
        if (row[3:5] != ('disk', 'disk') or row[6:8] != row[3:5]
                or str(row[9]) != file.identifier or row[10] != member.place.repository
                or row[8].get('root', row[11]) != member.place.root
                or row[8].get('path', row[12]) != member.place.path
                or row[14] != file.snapshot_hash
                or (member.chunk.kind == 'document') != (corpus == 'documents')):
            raise MycelError('store_format', 'The evaluation member corpus contradicts its exact owning disk file location.')
        origins[key] = corpus
    model = resolver.settings.values["embedding"]["model"]
    dimensions = resolver.settings.values["embedding"]["dimensions"]
    plans = connection.execute("""SELECT id,chunk_version,model,dimensions,plan_hash,place_line,provenance,failure
        FROM public.mycel_embedding_plans WHERE chunk_version=ANY(%s) AND model=%s AND dimensions=%s
        ORDER BY id""", (versions, model, dimensions)).fetchall()
    plan_ids = [row[0] for row in plans]
    parts = connection.execute("""SELECT p.plan_id,p.part_order,p.byte_start,p.byte_end,p.input_bytes,
        p.submitted_tokens,p.planning_tokens,p.failure,v.model,v.dimensions,v.embedding::text
        FROM public.mycel_embedding_parts p LEFT JOIN public.mycel_vectors v
          ON v.plan_id=p.plan_id AND v.part_order=p.part_order
        WHERE p.plan_id=ANY(%s::uuid[]) ORDER BY p.plan_id,p.part_order""", (plan_ids,)).fetchall()
    rows = {
        "store": connection.execute("SELECT format,dimensions FROM public.mycel_store WHERE singleton=true").fetchall(),
        "versions": connection.execute("SELECT id,chunk_id,snapshot_hash,metadata,comparison "
            "FROM public.mycel_chunk_versions WHERE id=ANY(%s) ORDER BY id", (versions,)).fetchall(),
        "locations": connection.execute("SELECT id,chunk_version,file_location,kind,location,metadata "
            "FROM public.mycel_locations WHERE chunk_version=ANY(%s) AND kind IN ('disk','index') ORDER BY id",
            (versions,)).fetchall(),
        "dependencies": connection.execute("SELECT * FROM public.mycel_dependencies "
            "WHERE dependant_version=ANY(%s) ORDER BY id", (versions,)).fetchall(),
        "edges": connection.execute("""SELECT e.dependency,e.source_version FROM public.mycel_edges e
            JOIN public.mycel_dependencies d ON d.id=e.dependency
            WHERE d.dependant_version=ANY(%s) ORDER BY e.dependency,e.source_version""", (versions,)).fetchall(),
        "faults": connection.execute("SELECT * FROM public.mycel_ref_faults "
            "WHERE chunk_version=ANY(%s) ORDER BY id", (versions,)).fetchall(),
        "stale": connection.execute("SELECT * FROM public.mycel_stale_reasons "
            "WHERE chunk_version=ANY(%s) ORDER BY id", (versions,)).fetchall(),
        "generated": connection.execute("SELECT * FROM public.mycel_generated_state "
            "WHERE chunk_id=ANY(%s::uuid[]) ORDER BY chunk_id", (identifiers,)).fetchall(),
    }
    places = [(key, member.place.address, origins[key], member.chunk.name,
               member.chunk.kind, member.chunk.title, member.chunk.family,
               member.chunk.span, member.chunk.body_span)
              for key, member in sorted(members.items())]
    fingerprint = _hash({"version": 1, "files": files, "places": places,
                         "corpora": corpus_rows, "plans": plans, "parts": parts, **rows})
    return (MappingProxyType(origins), MappingProxyType(members),
            MappingProxyType(artifact_paths), fingerprint)
