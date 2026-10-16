"""Read-only disk snapshots for the two retrieval candidate arms.

Query vectors arrive already prepared; this adapter never contacts a provider,
refreshes files, writes an index or supplies final search ranking. Organization
members receive independent candidate lists over the same guarded snapshot.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

import psycopg

from ._embedding_plan import PlanningError, load_tokenizer
from ._embedding_store import RetainedVersion, _decode_plan, _vector
from ._errors import MycelError
from ._locks import snapshot_transaction
from ._resolver import SourceResolver, require_read_transaction
from ._retrieval import (Candidate, RetrievalChunk, meaning_candidates,
                        resolve_search_scope, select_chunks, validate_search,
                        wording_candidates)
from ._settings import SettingsSnapshot, _freeze
from ._store import checked_store, exact_text


def _copy(value):
    if isinstance(value, Mapping):
        return {key: _copy(member) for key, member in value.items()}
    if isinstance(value, (tuple, list)):
        return [_copy(member) for member in value]
    return value


@dataclass(frozen=True)
class RepositoryCandidates:
    """Distinct chunk candidates for one repository, before route ranking."""

    repository: str
    chunks: tuple[RetrievalChunk, ...]
    meaning: tuple[Candidate, ...]
    wording: tuple[Candidate, ...]
    without_vector: int


@dataclass
class _Lease:
    active: bool = True


@dataclass(frozen=True)
class CandidateSnapshot:
    repositories: tuple[str, ...]
    resolver: SourceResolver
    chunks: tuple[RetrievalChunk, ...]
    _connection: object = field(repr=False, compare=False)
    _settings: SettingsSnapshot = field(repr=False, compare=False)
    _lease: _Lease = field(repr=False, compare=False)

    def _require_active(self) -> None:
        if not self._lease.active:
            raise MycelError("invalid_input", "The retrieval candidate snapshot has ended.")
        require_read_transaction(self._connection)

    def candidates(self, query: str, query_vector: Sequence[float] | None = None, *,
                   k: int = 10, only: str | None = None) -> tuple[RepositoryCandidates, ...]:
        """Run each arm independently per enabled member; never merge scores."""
        self._require_active()
        validate_search(query, k, only)
        prepared = (None if query_vector is None else
                    _vector(query_vector, self._settings.values["embedding"]["dimensions"]))
        replies = []
        for repository in self.repositories:
            selected = select_chunks(self._settings, repository, self.chunks, only=only)
            replies.append(RepositoryCandidates(repository, selected,
                () if prepared is None else meaning_candidates(prepared, selected, k=k),
                wording_candidates(query, selected, k=k),
                sum(not chunk.fully_embedded for chunk in selected)))
        return tuple(replies)

    def ranked(self, query: str, query_vector: Sequence[float] | None = None, *,
               k: int = 10, only: str | None = None):
        """Rank each member with current, location-owned one-step citations."""
        from ._ranking import rank_repository
        from ._ranking_store import graph_for

        candidates = self.candidates(query, query_vector, k=k, only=only)
        return tuple(rank_repository(self._settings, query, member,
            graph_for(self, member.repository, only=only), query_vector,
            k=k, only=only) for member in candidates)


class StoreCandidates:
    """Freeze settings and retain disk text, places and coverage together.

    Scope is resolved before opening the transaction. Callers must prepare any
    paid query vector before entering ``snapshot``; no provider is called here.
    """

    def __init__(self, connection, settings: SettingsSnapshot):
        settings.require_valid()
        self._connection = connection
        self._settings = replace(settings, values=_freeze(_copy(settings.values)))

    @contextmanager
    def snapshot(self, names: Sequence[str] = (), *, cwd=None) -> Iterator[CandidateSnapshot]:
        repositories = resolve_search_scope(self._settings, names, cwd=cwd)
        dimensions = self._settings.values["embedding"]["dimensions"]
        try:
            with checked_store(self._connection, dimensions=dimensions), snapshot_transaction(self._connection):
                resolver = SourceResolver.from_read_transaction(self._connection, self._settings)
                chunks = _disk_inputs(self._connection, resolver)
                lease = _Lease()
                current = CandidateSnapshot(tuple(repository.name for repository in repositories),
                    resolver, chunks, self._connection, self._settings, lease)
                try:
                    yield current
                finally:
                    lease.active = False
        except psycopg.Error:
            raise MycelError("store_unavailable", "The retrieval candidate snapshot could not be read.") from None


def candidate_snapshot_in_transaction(connection, resolver: SourceResolver,
                                      repositories: tuple[str, ...], *, lease) -> CandidateSnapshot:
    """Borrow one caller-owned read snapshot and its exact resolver lifetime.

    Evaluation prepares every query vector before opening its own snapshot.
    This handoff reads ordinary candidate inputs inside that same transaction;
    it acquires no guard, opens no snapshot and makes no provider or freshness
    call. The caller invalidates the shared lease when its snapshot ends.
    """
    require_read_transaction(connection)
    if (not isinstance(resolver, SourceResolver) or type(repositories) is not tuple
            or not repositories
            or any(not isinstance(name, str) or not name
                   or not resolver.settings.values["repos"].get(name, {}).get("enabled", False)
                   for name in repositories)
            or len(repositories) != len(set(repositories))
            or getattr(lease, "active", None) is not True):
        raise MycelError("invalid_input", "Candidate handoff requires active enabled repository selections.")
    return CandidateSnapshot(repositories, resolver, _disk_inputs(connection, resolver),
                             connection, resolver.settings, lease)


def _disk_inputs(connection, resolver: SourceResolver) -> tuple[RetrievalChunk, ...]:
    files = tuple(sorted(resolver.files, key=lambda file: file.identifier))
    identifiers = [file.identifier for file in files]
    corpora = {str(identifier): corpus for identifier, corpus in connection.execute(
        "SELECT id,corpus FROM public.mycel_files WHERE id=ANY(%s::uuid[])", (identifiers,)).fetchall()}
    versions = sorted({chunk.version for file in files for chunk in file.chunks}
                      | {chunk.version for _, chunk in resolver.index})
    model = resolver.settings.values["embedding"]["model"]
    dimensions = resolver.settings.values["embedding"]["dimensions"]
    plans = {row[1]: row for row in connection.execute("""SELECT id,chunk_version,plan_hash,
        place_line,provenance,failure FROM public.mycel_embedding_plans
        WHERE chunk_version=ANY(%s) AND model=%s AND dimensions=%s ORDER BY chunk_version""",
        (versions, model, dimensions)).fetchall()}
    parts = {row[0]: [] for row in plans.values()}
    if parts:
        for row in connection.execute("""SELECT p.plan_id,p.part_order,p.byte_start,p.byte_end,
            p.input_bytes,p.submitted_tokens,p.planning_tokens,p.failure,v.embedding::text
            FROM public.mycel_embedding_parts p LEFT JOIN public.mycel_vectors v
              ON v.plan_id=p.plan_id AND v.part_order=p.part_order AND v.model=%s AND v.dimensions=%s
            WHERE p.plan_id=ANY(%s::uuid[]) ORDER BY p.plan_id,p.part_order""",
            (model, dimensions, list(parts))).fetchall():
            parts[row[0]].append(row)
    try:
        tokenizer = load_tokenizer(model) if plans else None
    except PlanningError:
        # Unverifiable plan coverage cannot prevent complete wording search.
        tokenizer = None
    result, inputs = [], []
    for file in files:
        origin = corpora.get(file.identifier)
        if origin not in {"code", "documents"}:
            raise MycelError("store_format", "The retrieval catalog has an incompatible corpus origin.")
        aliases = tuple(alias.path for alias in file.aliases if alias.root == "artifact")
        for chunk in file.chunks:
            inputs.append((file.repository, file.primary, chunk, origin, aliases))
    for place, chunk in resolver.index:
        if chunk.kind not in {'summary', 'overview'}:
            raise MycelError('store_format', 'The generated retrieval catalog has an incompatible origin.')
        inputs.append((place.repository, place, chunk, chunk.kind, ()))
    for repository, place, chunk, origin, aliases in inputs:
        text = exact_text(chunk.source)
        complete, vectors = False, ()
        row = plans.get(chunk.version)
        if row is not None and row[5] is None and tokenizer is not None:
            retained = RetainedVersion(repository, chunk.identifier, chunk.kind, _freeze({}),
                str(chunk.version), chunk.snapshot_hash, text, _freeze({}))
            try:
                embedded = _decode_plan(retained, row, parts[row[0]], tokenizer=tokenizer,
                                        model=model, dimensions=dimensions)
                complete = (embedded.complete and all(part.failure is None and any(part.vector)
                                                      for part in embedded.parts))
                if complete:
                    vectors = tuple(part.vector for part in embedded.parts)
            except PlanningError:
                # A broken saved plan is still searchable by complete text.
                pass
        result.append(RetrievalChunk(chunk.identifier, chunk.version, repository,
            place.root, place.path, chunk.name, chunk.kind, origin, text,
            artifact_paths=aliases, fully_embedded=complete, part_vectors=vectors))
    return tuple(result)
