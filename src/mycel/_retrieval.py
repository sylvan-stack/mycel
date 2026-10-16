"""Pure, independently limited candidate arms over an explicit disk scope.

The caller supplies an immutable catalog and proves current-model embedding
coverage. No provider, index, store, or freshness operation runs here. Equal
scores use path, root, name, repository, logical identifier, then version.
These are candidate lists; route fusion and result ranking are later work.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import math
from pathlib import Path, PurePosixPath
import re
from typing import Literal

from ._errors import MycelError
from ._scope import Repository, RepositoryLocations
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress


_TERMS = re.compile(r"\w+", re.UNICODE)
_BM25_K1 = 1.2
_BM25_B = 0.75


@dataclass(frozen=True)
class RetrievalChunk:
    identifier: str
    version: int
    repository: str
    root: Literal["code", "artifact", "index"]
    path: str
    name: str
    kind: str
    origin: Literal["code", "documents", "summary", "overview"]
    text: str = field(repr=False)
    artifact_paths: tuple[str, ...] = ()
    on_disk: bool = True
    fully_embedded: bool = False
    part_vectors: tuple[tuple[float, ...], ...] = field(default=(), repr=False)

    @property
    def key(self) -> tuple[str, int]:
        return self.identifier, self.version

    @property
    def place(self) -> SourceAddress:
        return SourceAddress(self.repository, self.root, self.path, self.name)


@dataclass(frozen=True)
class Candidate:
    chunk: RetrievalChunk
    score: float


def _validate_k(k: int) -> None:
    if type(k) is not int or not 1 <= k <= 100:
        raise MycelError("invalid_input", "Search requires a result limit from 1 to 100.")


def _validate_only(only: str | None) -> None:
    if only is not None and (not isinstance(only, str) or only not in {"code", "docs"}):
        raise MycelError("invalid_input", "Search accepts only code or docs as a corpus selection.")


def validate_search(query: str, k: int = 10, only: str | None = None) -> None:
    """All candidate entry points share the eventual command's input limits."""
    if not isinstance(query, str) or not query.strip():
        raise MycelError("invalid_input", "Search requires a nonempty query.")
    _validate_k(k)
    _validate_only(only)


def resolve_search_scope(settings: SettingsSnapshot, names: Sequence[str] = (), *,
                         cwd: Path | str | None = None) -> tuple[Repository, ...]:
    """Use configured names or the containing folder, without a fallback name."""
    selected = RepositoryLocations(settings).resolve_scope(names, cwd=cwd)
    enabled = tuple(repository for repository in selected if repository.enabled)
    if not enabled:
        raise MycelError("refused", "Search requires an enabled repository.")
    return enabled


def selected_shared_document(settings: SettingsSnapshot, repository: str, path: str) -> bool:
    """Select an enabled artifact file by an exact path or folder boundary."""
    value = settings.values["repos"].get(repository)
    if value is None or not value["enabled"]:
        return False
    parts = PurePosixPath(path).parts
    return any(selection["repo"] == repository and any(
        parts[:len(prefix)] == prefix
        for prefix in (PurePosixPath(selected).parts for selected in selection["paths"]))
        for selection in settings.values["search"]["shared_documents"])


def _tie(chunk: RetrievalChunk) -> tuple[str, str, str, str, str, int]:
    return (chunk.path, chunk.root, chunk.name, chunk.repository, chunk.identifier, chunk.version)


def _disk_chunks(chunks: Iterable[RetrievalChunk]) -> tuple[RetrievalChunk, ...]:
    """Keep disk inputs and generated index sections, excluding retained refs."""
    unique: dict[tuple[str, int], RetrievalChunk] = {}
    for chunk in chunks:
        if not chunk.on_disk or (chunk.root not in {"code", "artifact"}
                and not (chunk.root == 'index' and chunk.origin in {'summary', 'overview'})):
            continue
        previous = unique.setdefault(chunk.key, chunk)
        if previous != chunk:
            raise MycelError("store_format", "One indexed chunk version has conflicting candidate inputs.")
    return tuple(sorted(unique.values(), key=_tie))


def select_chunks(settings: SettingsSnapshot, repository: str,
                  chunks: Iterable[RetrievalChunk], *, only: str | None = None
                  ) -> tuple[RetrievalChunk, ...]:
    """Keep own corpus plus selected artifact documents, retaining real roots."""
    _validate_only(only)
    value = settings.values["repos"].get(repository)
    if value is None:
        raise MycelError("unknown_repository", "Search requires a configured repository.")
    if not value["enabled"]:
        raise MycelError("refused", "Search requires an enabled repository.")
    selected = []
    for chunk in _disk_chunks(chunks):
        owner = settings.values["repos"].get(chunk.repository)
        if owner is None or not owner["enabled"]:
            continue
        if only == "code" and chunk.origin != "code":
            continue
        if only == "docs" and chunk.origin not in {"documents", "summary", "overview"}:
            continue
        if chunk.repository == repository:
            selected.append(chunk)
        elif only != "code" and chunk.origin == "documents":
            paths = (*chunk.artifact_paths, *((chunk.path,) if chunk.root == "artifact" else ()))
            if any(selected_shared_document(settings, chunk.repository, path) for path in paths):
                selected.append(chunk)
    return tuple(selected)


def _limited(candidates: Iterable[Candidate], k: int) -> tuple[Candidate, ...]:
    """Collapse logical chunks before either arm's candidate count or rank."""
    distinct: dict[str, Candidate] = {}
    for candidate in sorted(candidates, key=lambda item: (-item.score, _tie(item.chunk))):
        distinct.setdefault(candidate.chunk.identifier, candidate)
    return tuple(distinct.values())[:max(k, 20)]


def _terms(text: str) -> tuple[str, ...]:
    return tuple(_TERMS.findall(text.casefold()))


def wording_candidates(query: str, chunks: Iterable[RetrievalChunk], *,
                       k: int = 10) -> tuple[Candidate, ...]:
    """BM25 over complete text, name and path, including unembedded versions.

    Terms are Unicode word runs after case folding, with underscore retained.
    Positive smoothed Robertson IDF and BM25's k1=1.2, b=0.75 are used; query
    terms are counted once. Nothing truncates the source to an excerpt.
    """
    validate_search(query, k)
    catalog = _disk_chunks(chunks)
    query_terms = sorted(set(_terms(query)))
    if not catalog or not query_terms:
        return ()
    frequencies = tuple(Counter(_terms("\n".join((chunk.text, chunk.name, chunk.path))))
                        for chunk in catalog)
    lengths = tuple(sum(frequency.values()) for frequency in frequencies)
    average = math.fsum(lengths) / len(catalog)
    if average == 0:
        return ()
    document_counts = Counter(term for frequency in frequencies for term in frequency)
    idf = {term: math.log1p((len(catalog) - document_counts[term] + 0.5)
                            / (document_counts[term] + 0.5)) for term in query_terms}
    scores = []
    for chunk, frequency, length in zip(catalog, frequencies, lengths):
        normalization = _BM25_K1 * (1 - _BM25_B + _BM25_B * length / average)
        score = math.fsum(idf[term] * frequency[term] * (_BM25_K1 + 1)
                          / (frequency[term] + normalization)
                          for term in query_terms if frequency[term])
        if score > 0:
            scores.append(Candidate(chunk, score))
    return _limited(scores, k)


def _unit_vector(vector: Sequence[float], *, dimensions: int | None = None) -> tuple[float, ...]:
    try:
        if not vector or (dimensions is not None and len(vector) != dimensions):
            raise ValueError
        if any(type(number) not in {int, float} for number in vector):
            raise ValueError
        numbers = tuple(float(number) for number in vector)
        if not all(math.isfinite(number) for number in numbers):
            raise ValueError
        scale = max(abs(number) for number in numbers)
        if scale == 0:
            raise ValueError
        scaled = tuple(number / scale for number in numbers)
        length = math.sqrt(math.fsum(number * number for number in scaled))
    except (OverflowError, TypeError, ValueError):
        raise MycelError("invalid_input", "Meaning candidates require nonzero finite vectors of one dimension.") from None
    return tuple(number / length for number in scaled)


def meaning_candidates(query_vector: Sequence[float] | None, chunks: Iterable[RetrievalChunk], *,
                       k: int = 10) -> tuple[Candidate, ...]:
    """One best-part cosine per completely embedded, current-model version."""
    _validate_k(k)
    if query_vector is None:
        return ()
    query = _unit_vector(query_vector)
    candidates = []
    for chunk in _disk_chunks(chunks):
        if not chunk.fully_embedded:
            continue
        if not chunk.part_vectors:
            raise MycelError("store_format", "A completely embedded candidate has no recorded vectors.")
        similarities = []
        for part in chunk.part_vectors:
            vector = _unit_vector(part, dimensions=len(query))
            cosine = math.fsum(left * right for left, right in zip(query, vector))
            similarities.append(max(-1.0, min(1.0, cosine)))
        candidates.append(Candidate(chunk, max(similarities)))
    return _limited(candidates, k)
