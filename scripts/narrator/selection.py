"""Resolve source references and select distinct, request-local summary units."""

from collections.abc import Sequence
from typing import Any


type Record = dict[str, Any]
type UnitKey = tuple[str, int]


def _unit_key(record: Record) -> UnitKey:
    unit_id = record.get("unit_id")
    revision = record.get("revision")
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("A unit key requires a nonempty unit_id")
    if type(revision) is not int or revision < 1:
        raise ValueError("A unit key requires a positive integer revision")
    return unit_id, revision


def _comparison_keys(comparison: Record) -> tuple[UnitKey, UnitKey]:
    left = comparison.get("left")
    right = comparison.get("right")
    equivalent = comparison.get("equivalent")
    reason = comparison.get("reason")
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ValueError("A comparison requires two unit keys")
    if type(equivalent) is not bool or not isinstance(reason, str) or not reason.strip():
        raise ValueError("A comparison requires an equivalence decision and reason")
    return _unit_key(left), _unit_key(right)


def _resolve_citations(
    unit: Record, key: UnitKey, passages: dict[str, Record]
) -> tuple[list[Record], list[Record]]:
    cited_ids = unit.get("cited_passage_ids")
    if not isinstance(cited_ids, list):
        raise ValueError("A unit requires a list of cited passage IDs")

    evidence = []
    dispositions = []
    for position, passage_id in enumerate(cited_ids, start=1):
        if isinstance(passage_id, str) and passage_id in passages:
            evidence.append(passages[passage_id])
            continue
        dispositions.append({
            "unit_id": key[0],
            "revision": key[1],
            "stage": "selection",
            "outcome": "invalid_citation",
            "reason": f"Citation {position} does not resolve to a request passage",
        })
    return evidence, dispositions


def select_distinct_units(
    units: Sequence[Record],
    candidates: Sequence[Record],
    passages: Sequence[Record],
    comparisons: Sequence[Record],
) -> Record:
    """Prepare unchanged revisions using passages already validated for this request."""
    candidate_ids = {candidate["candidate_id"] for candidate in candidates}
    passages_by_id = {passage["passage_id"]: passage for passage in passages}
    for comparison in comparisons:
        _comparison_keys(comparison)

    seen_ids: set[str] = set()
    ordered_units = []
    dispositions = []
    for unit in units:
        key = _unit_key(unit)
        unit_id, _ = key
        if unit_id in seen_ids:
            raise ValueError("Selection requires one current revision per unit_id")
        seen_ids.add(unit_id)

        origins = unit.get("originating_candidate_ids")
        if not isinstance(origins, list) or not origins or any(
            not isinstance(origin, str) or origin not in candidate_ids for origin in origins
        ):
            raise ValueError("A unit must refer to its originating candidates")

        evidence, invalid_citations = _resolve_citations(unit, key, passages_by_id)
        first_citation = min((passage["start"] for passage in evidence), default=float("inf"))
        ordered_units.append(((first_citation, unit_id), unit))
        dispositions.extend(invalid_citations)

    ordered_units.sort(key=lambda row: row[0])
    return {"groups": [{"members": [unit]} for _, unit in ordered_units], "dispositions": dispositions}
