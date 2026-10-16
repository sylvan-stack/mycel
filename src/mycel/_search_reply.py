"""Schema 3 search replies over immutable ranking and observation inputs.

The store adapter supplies current-version marks, public ref faults, line
spans and file readability observations. This module performs no file, store,
freshness or provider operations. It never treats an absent dependency check
as evidence that a chunk is current.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ._errors import MycelError
from ._freshness import FreshnessResult
from ._ranking import RepositoryRanking
from ._refs import _place
from ._retrieval import RetrievalChunk

if TYPE_CHECKING:
    from ._retrieval_store import RepositoryCandidates


SEARCH_REPLY = 3
_NO_MEANING = "The query could not be embedded; results use exact wording only."
_NO_FILE = "The chunk file has not been checked for readability."
_INDEX_FILE = "This chunk is generated in the index and has no file."
_NO_CHECK = "Freshness checking was turned off."


def _copy(value):
    if isinstance(value, Mapping):
        return {key: _copy(member) for key, member in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(member) for member in value]
    return value


def _annotations(chunk: RetrievalChunk, metadata: Mapping,
                 freshness: FreshnessResult | None, checked: bool) -> dict:
    reasons = _copy(metadata.get("staleReasons", ()))
    faults = _copy(metadata.get("faults", ()))
    complete = checked and freshness is not None and freshness.complete_for_chunk(
        chunk.repository, chunk.key)
    return {"stale": bool(reasons), "staleReasons": reasons,
            "heartwood": bool(metadata.get("heartwood", False)),
            "dependencyCheck": {"complete": bool(complete and not faults), "faults": faults}}


def _citation(chunk, metadata, freshness, checked):
    return {"id": chunk.identifier, "document": chunk.name, **_place(chunk.place),
            **_annotations(chunk, metadata.get(chunk.key, {}), freshness, checked)}


def search_reply(ranking: RepositoryRanking, candidates: RepositoryCandidates, *,
                 metadata: Mapping | None = None,
                 freshness: FreshnessResult | None = None, checked: bool = True,
                 ingested: Mapping[str, int] | None = None,
                 meaning_reason: str | None = None) -> dict:
    """Compose one independently ranked repository's public search reply.

    ``metadata`` is keyed by exact ``(identifier, version)``. Its ``faults``
    already name each original dependant, including upstream faults; no
    dependency authority is inferred from mentions or citation membership.
    ``file`` is supplied only after the adapter checked readability within the
    configured root. A missing observation receives an explicit explanation.
    A citation and a result use the same marks and exact-version check.
    """
    if ranking.repository != candidates.repository:
        raise MycelError("store_format", "Search ranking and candidate scope do not agree.")
    if type(checked) is not bool:
        raise MycelError("invalid_input", "Search requires a boolean freshness option.")
    if meaning_reason is not None and (not isinstance(meaning_reason, str) or not meaning_reason.strip()):
        raise MycelError("invalid_input", "A missing meaning arm requires a nonempty reason.")
    metadata = {} if metadata is None else metadata
    ingested = {} if ingested is None else ingested
    was_checked = bool(checked and freshness is not None)
    meaning = {"used": ranking.meaning_used}
    if not ranking.meaning_used:
        meaning["reason"] = meaning_reason or _NO_MEANING
    repositories = []
    if freshness is not None:
        for row in freshness.repositories:
            state = row.status if was_checked else "pending"
            record = {"repository": row.repository, "state": state,
                      "ingested": ingested.get(row.repository, 0) if was_checked else 0}
            if state != "done":
                record["reason"] = row.reason or (
                    "The required check is pending." if was_checked else _NO_CHECK)
            repositories.append(record)
    results = []
    for entry in ranking.results:
        chunk = entry.chunk
        observation = metadata.get(chunk.key, {})
        ranks = {}
        if entry.meaning_rank is not None:
            ranks["meaning"] = entry.meaning_rank
        if entry.wording_rank is not None:
            ranks["wording"] = entry.wording_rank
        result = {"id": chunk.identifier, **_place(chunk.place),
                  "origin": "document" if chunk.origin == "documents" else chunk.origin,
                  "kind": chunk.kind, "score": entry.score, "ranks": ranks,
                  **_annotations(chunk, observation, freshness, was_checked),
                  "documentedIn": [_citation(document, metadata, freshness, was_checked)
                                   for document in entry.documented_in],
                  "preview": chunk.text[:240]}
        if chunk.origin == "code":
            result["described"] = bool(observation.get("described", False))
        if entry.via is not None:
            result["via"] = _citation(entry.via, metadata, freshness, was_checked)
        if observation.get("lines") is not None:
            result["lines"] = _copy(observation["lines"])
        if chunk.root == "index":
            result["unreadable"] = _INDEX_FILE
        elif observation.get("file") is not None:
            result["file"] = observation["file"]
        else:
            result["unreadable"] = observation.get("unreadable") or _NO_FILE
        results.append(result)
    return {"schema": SEARCH_REPLY, "repository": ranking.repository,
            "route": ranking.route, "meaning": meaning,
            "candidates": {"meaning": len({item.chunk.identifier for item in candidates.meaning})
                           if ranking.meaning_used else 0,
                           "wording": len({item.chunk.identifier for item in candidates.wording})},
            "freshness": {"checked": was_checked,
                          "finished": bool(was_checked and freshness.finished),
                          "ingested": sum(ingested.values()) if was_checked else 0,
                          "withoutVector": ranking.without_vector,
                          "repositories": repositories},
            "results": results}
