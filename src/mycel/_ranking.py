"""Deterministic result ranking over immutable, already scoped candidates.

No store, provider, refresh or mutation runs here. A graph contains only the
current disk-owned document citations resolved by the snapshot adapter. Full
current-model pools determine bridge choices, document margins and citers;
the independently limited candidate arms retain their own one-based ranks.

Every ordering uses descending score, then the candidate canonical tuple:
(path, root, name, repository, logical identifier, exact version). Question
wording hits occupy a separate tier below all scored hits, including negative
cosines; their own score is BM25 after the same family weighting.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
from pathlib import PurePosixPath
import re
from typing import Literal, TYPE_CHECKING

from ._errors import MycelError
from ._retrieval import (Candidate, RetrievalChunk, _disk_chunks, _tie, _unit_vector,
                        select_chunks, validate_search)
from ._settings import SettingsSnapshot

if TYPE_CHECKING:
    from ._retrieval_store import RepositoryCandidates


Route = Literal["identifier", "question"]
ScoreTier = Literal["scored", "wording_tail"]
_IDENTIFIER = re.compile(r"[\w.#/-]+", re.UNICODE)
_TEST_QUERY = re.compile(r"\b(tests?|specs?|e2e|mocks?|fixtures?)\b", re.IGNORECASE)
_GENERATED_QUERY = re.compile(r"\b(types?|schemas?|graphql|gql|codegen|generated)\b", re.IGNORECASE)
_STRUCTURAL = frozenset(("file", "module", "markup", "style"))
_ROUTING_FILES = frozenset(("INDEX.md", "README.md"))
_RRF_CONSTANT = 60
_BRIDGE_DOCUMENTS = 8
_BRIDGE_CODE = 3
_BRIDGE_FACTOR = 0.92
_BRIDGE_AGREEMENT = 0.05
_DOCUMENT_MARGIN = 0.03
_DOCUMENT_LIMIT = 2


@dataclass(frozen=True)
class DocumentCitation:
    """One validated current document and its deduplicable code destinations."""

    document: RetrievalChunk
    code: tuple[RetrievalChunk, ...]


@dataclass(frozen=True)
class RankingGraph:
    """Own document cues and visible citers, with one-hop resolved citations.

    ``documents`` includes own documents even for a code-only selection.
    Shared documents can be visible citers but cannot deliver bridge code.
    Graph readers, rather than this pure layer, prove disk declaration ownership.
    """

    documents: tuple[RetrievalChunk, ...] = ()
    citations: tuple[DocumentCitation, ...] = ()


@dataclass(frozen=True)
class RankEntry:
    chunk: RetrievalChunk
    score: float
    score_tier: ScoreTier
    meaning_rank: int | None
    wording_rank: int | None
    raw_direct_cosine: float | None
    raw_bridge_cosine: float | None
    via: RetrievalChunk | None
    documented_in: tuple[RetrievalChunk, ...]


@dataclass(frozen=True)
class RepositoryRanking:
    repository: str
    route: Route
    meaning_used: bool
    without_vector: int
    results: tuple[RankEntry, ...]


def classify_route(query: str) -> Route:
    """Keep the accepted Unicode identifier shape, including one plain word."""
    validate_search(query)
    return "identifier" if _IDENTIFIER.fullmatch(query.strip()) else "question"


def _cosines(query_vector: Sequence[float] | None,
             chunks: Iterable[RetrievalChunk]) -> dict[tuple[str, int], float]:
    if query_vector is None:
        return {}
    query = _unit_vector(query_vector)
    result = {}
    for chunk in _disk_chunks(chunks):
        if not chunk.fully_embedded:
            continue
        if not chunk.part_vectors:
            raise MycelError("store_format", "A completely embedded ranking chunk has no recorded vectors.")
        parts = (_unit_vector(part, dimensions=len(query)) for part in chunk.part_vectors)
        result[chunk.key] = max(max(-1.0, min(1.0, math.fsum(
            left * right for left, right in zip(query, part)))) for part in parts)
    return result


def _arm(candidates: Iterable[Candidate], scope: dict[tuple[str, int], RetrievalChunk]
         ) -> dict[str, tuple[Candidate, int]]:
    """Defend against repeated logical rows before ranks without sorting an arm."""
    result = {}
    for candidate in candidates:
        if candidate.chunk.key not in scope:
            continue
        if scope[candidate.chunk.key] != candidate.chunk:
            raise MycelError("store_format", "A ranking candidate conflicts with its scoped chunk version.")
        if not math.isfinite(candidate.score):
            raise MycelError("store_format", "A ranking candidate has a nonfinite score.")
        if candidate.chunk.identifier not in result:
            result[candidate.chunk.identifier] = candidate, len(result) + 1
    return result


def _patterns(settings: SettingsSnapshot, repositories: Iterable[str]
              ) -> dict[str, tuple[tuple[re.Pattern, ...], tuple[re.Pattern, ...]]]:
    result = {}
    for repository in sorted(set(repositories)):
        value = settings.values["repos"][repository]
        try:
            result[repository] = tuple(re.compile(pattern) for pattern in value["test_patterns"]), tuple(
                re.compile(pattern) for pattern in value["generated_patterns"])
        except (re.error, TypeError):
            raise MycelError("invalid_input", "Repository ranking patterns must be valid regular expressions.") from None
    return result


def _family_factor(chunk: RetrievalChunk, route: Route, query: str, patterns) -> float:
    tests, generated = patterns[chunk.repository]
    # Keep relative-path anchors usable while giving folder patterns a leading
    # boundary, including the packaged /__tests__/ pattern at the root.
    path = PurePosixPath(chunk.path.replace("\\", "/")).as_posix()

    def matches(expressions):
        return any(expression.search(path) or expression.search("/" + path)
                   for expression in expressions)

    factor = 1.0
    if matches(tests) and not _TEST_QUERY.search(query):
        factor *= 0.85 if route == "identifier" else 0.93
    if matches(generated) and not _GENERATED_QUERY.search(query) and route == "question":
        factor *= 0.93
    if chunk.kind in _STRUCTURAL:
        factor *= 0.75 if route == "identifier" else 0.9
    return factor


def _best_distinct(chunks: Iterable[RetrievalChunk], cosines) -> tuple[RetrievalChunk, ...]:
    unique = {}
    for chunk in sorted((chunk for chunk in chunks if chunk.key in cosines),
                        key=lambda chunk: (-cosines[chunk.key], _tie(chunk))):
        unique.setdefault(chunk.identifier, chunk)
    return tuple(unique.values())


def _clears_margin(similarity: float, code_bar: float | None) -> bool:
    if code_bar is None:
        return True
    threshold = code_bar + _DOCUMENT_MARGIN
    # Unit-vector normalization and addition may put a mathematically equal
    # boundary a few representable floats apart (.8 + .03 versus .83). Allow
    # only their rounding distance, without changing the accepted .03 margin.
    return similarity >= threshold or math.isclose(
        similarity, threshold, rel_tol=0.0, abs_tol=4 * math.ulp(threshold))


def rank_repository(settings: SettingsSnapshot, query: str,
                    candidates: RepositoryCandidates, graph: RankingGraph,
                    query_vector: Sequence[float] | None = None, *,
                    k: int = 10, only: str | None = None) -> RepositoryRanking:
    """Fuse one repository's arms and evidence without broadening its scope.

    Bridge raw cosine records the supplying section before inheritance. An
    agreement boost requires direct meaning and bridge membership, not wording
    alone, and is applied once before multiplying every family factor. Mixed
    document admission uses full raw cosine pools: no vector excludes mixed
    document results; no eligible code removes the margin comparison; negative
    code cosines retain their actual maximum. Docs-only bypasses these rules.
    """
    settings.require_valid()
    validate_search(query, k, only)
    route = classify_route(query)
    selected = select_chunks(settings, candidates.repository, candidates.chunks, only=only)
    scope = {chunk.key: chunk for chunk in selected}
    meaning = _arm(candidates.meaning, scope) if query_vector is not None else {}
    wording = _arm(candidates.wording, scope)
    visible_documents = select_chunks(settings, candidates.repository, graph.documents)
    documents = tuple(chunk for chunk in visible_documents if chunk.origin in {"documents", "summary", "overview"}
                      and (only != "code" or chunk.repository == candidates.repository))
    document_scope = {chunk.key: chunk for chunk in documents}
    cosines = _cosines(query_vector, (*selected, *documents))
    patterns = _patterns(settings, (chunk.repository for chunk in selected))

    edges: dict[tuple[str, int], dict[tuple[str, int], RetrievalChunk]] = {}
    for citation in graph.citations:
        if citation.document.key not in document_scope:
            continue
        if document_scope[citation.document.key] != citation.document:
            raise MycelError("store_format", "A ranking citation conflicts with its document version.")
        destinations = edges.setdefault(citation.document.key, {})
        for chunk in citation.code:
            if chunk.key in scope and chunk.origin == "code" and chunk.repository == candidates.repository:
                if scope[chunk.key] != chunk:
                    raise MycelError("store_format", "A ranking citation conflicts with its code version.")
                destinations[chunk.key] = chunk

    bridge: dict[str, tuple[RetrievalChunk, RetrievalChunk, float]] = {}
    if route == "question" and query_vector is not None and only != "docs":
        cues = _best_distinct((doc for doc in documents
                              if doc.repository == candidates.repository), cosines)[:_BRIDGE_DOCUMENTS]
        for document in cues:
            destinations = _best_distinct(edges.get(document.key, {}).values(), cosines)[:_BRIDGE_CODE]
            for chunk in destinations:
                # Cues are already strongest-first with canonical ties, so
                # repeated edges, sections and parts can contribute only once.
                bridge.setdefault(chunk.identifier, (chunk, document, cosines[document.key]))

    citers: dict[str, tuple[RetrievalChunk, ...]] = {}
    for document in _best_distinct(documents, cosines):
        for chunk in edges.get(document.key, {}).values():
            previous = citers.get(chunk.identifier, ())
            if len(previous) < _DOCUMENT_LIMIT:
                citers[chunk.identifier] = (*previous, document)

    code_cosines = [cosines[chunk.key] for chunk in selected
                    if chunk.origin == "code" and chunk.key in cosines]
    code_bar = max(code_cosines) if code_cosines else None
    entries = []
    for identifier in sorted(set(meaning) | set(wording) | set(bridge)):
        direct = meaning.get(identifier)
        lexical = wording.get(identifier)
        inherited = bridge.get(identifier)
        chunk = (direct[0].chunk if direct else inherited[0] if inherited else lexical[0].chunk)
        direct_cosine = direct[0].score if direct else None
        bridge_cosine = inherited[2] if inherited else None
        via = inherited[1] if inherited else None
        if chunk.origin in {"documents", "summary", "overview"} and only != "docs":
            similarity = cosines.get(chunk.key)
            if (PurePosixPath(chunk.path).name in _ROUTING_FILES or similarity is None
                    or not _clears_margin(similarity, code_bar)):
                continue
        tier: ScoreTier = "scored"
        if route == "identifier":
            score = math.fsum(1 / (_RRF_CONSTANT + item[1])
                              for item in (direct, lexical) if item is not None)
        elif direct is not None or inherited is not None:
            score = max(value for value in (direct_cosine,
                None if bridge_cosine is None else bridge_cosine * _BRIDGE_FACTOR) if value is not None)
            if direct is not None and inherited is not None:
                score += _BRIDGE_AGREEMENT
        else:
            tier = "wording_tail"
            score = lexical[0].score
        score *= _family_factor(chunk, route, query, patterns)
        entries.append(RankEntry(chunk, score, tier,
            direct[1] if direct else None, lexical[1] if lexical else None,
            direct_cosine, bridge_cosine, via, citers.get(identifier, ())))

    entries.sort(key=lambda entry: (entry.score_tier == "wording_tail", -entry.score, _tie(entry.chunk)))
    results, document_count = [], 0
    for entry in entries:
        if entry.chunk.origin in {"documents", "summary", "overview"} and only != "docs":
            if document_count == _DOCUMENT_LIMIT:
                continue
            document_count += 1
        results.append(entry)
        if len(results) == k:
            break
    return RepositoryRanking(candidates.repository, route, query_vector is not None,
                             candidates.without_vector, tuple(results))
