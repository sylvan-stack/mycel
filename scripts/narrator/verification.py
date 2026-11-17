"""Check Narrator summary units against the exact RAPTOR request evidence."""

from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import TypedDict


class _SourceSlice(TypedDict):
    start: int
    end: int
    text: str


class _Passage(_SourceSlice):
    request_digest: str
    passage_id: str


type _Record = dict[str, object]
type _UnitKey = tuple[str, int]


def _source_context(
    request_text: str, source_spans: Sequence[tuple[int, int]]
) -> list[_SourceSlice]:
    if not source_spans:
        raise ValueError("verification needs admitted source spans")

    context: list[_SourceSlice] = []
    for span in source_spans:
        if not isinstance(span, Sequence) or len(span) != 2:
            raise ValueError("invalid admitted source span")
        start, end = span
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(request_text)
        ):
            raise ValueError("invalid admitted source span")
        context.append({"start": start, "end": end, "text": request_text[start:end]})

    context.sort(key=lambda section: section["start"])
    if any(left["end"] > right["start"] for left, right in pairwise(context)):
        raise ValueError("overlapping admitted source spans")
    return context


def _resolve_passages(
    request_text: str,
    request_digest: str,
    source_spans: Sequence[tuple[int, int]],
    passages: Sequence[Mapping[str, object]],
) -> tuple[dict[str, _Passage], list[_SourceSlice]]:
    """Resolve unambiguous citations inside the sections admitted by the writer."""
    if not isinstance(request_digest, str) or not request_digest.strip():
        raise ValueError("verification needs a request digest")

    context = _source_context(request_text, source_spans)
    resolved: dict[str, _Passage] = {}
    seen_ids: set[str] = set()
    for passage in passages:
        if not isinstance(passage, Mapping):
            continue
        passage_id = passage.get("passage_id")
        if not isinstance(passage_id, str) or not passage_id.strip():
            continue
        if passage_id in seen_ids:
            resolved.pop(passage_id, None)
            continue
        seen_ids.add(passage_id)

        if passage.get("request_digest") != request_digest:
            continue
        start, end = passage.get("start"), passage.get("end")
        if type(start) is not int or type(end) is not int:
            continue
        if not any(section["start"] <= start < end <= section["end"] for section in context):
            continue
        text = request_text[start:end]
        if passage.get("text") != text:
            continue

        resolved[passage_id] = {
            "request_digest": request_digest,
            "passage_id": passage_id,
            "start": start,
            "end": end,
            "text": text,
        }
    return resolved, context


def _unit_key(record: object) -> _UnitKey | None:
    if not isinstance(record, Mapping):
        return None
    unit_id = record.get("unit_id")
    revision = record.get("revision")
    if not isinstance(unit_id, str) or not unit_id.strip():
        return None
    if type(revision) is not int or revision < 1:
        return None
    return unit_id, revision


def _disposition(key: _UnitKey, outcome: str, reason: str) -> _Record:
    return {
        "unit_id": key[0],
        "revision": key[1],
        "stage": "verification",
        "outcome": outcome,
        "reason": reason,
    }


def _normalize_units(
    units: Sequence[Mapping[str, object]], passages: Mapping[str, _Passage]
) -> tuple[list[_Record], list[_Record], list[_Record]]:
    checked: list[_Record] = []
    verdicts: list[_Record] = []
    dispositions: list[_Record] = []
    seen_ids: set[str] = set()
    for unit in units:
        key = _unit_key(unit)
        if key is None:
            raise ValueError("verification needs a unit_id and positive integer revision")
        unit_id, previous_revision = key
        if unit_id in seen_ids:
            raise ValueError("verification needs one current revision per unit_id")
        seen_ids.add(unit_id)

        cited_ids = unit.get("cited_passage_ids")
        if not isinstance(cited_ids, list):
            raise ValueError("verification needs a list of cited passage IDs")
        surviving_ids = []
        invalid_citations = []
        for position, passage_id in enumerate(cited_ids, start=1):
            if isinstance(passage_id, str) and passage_id in passages:
                surviving_ids.append(passage_id)
            else:
                invalid_citations.append((position, passage_id))

        revision = previous_revision + 1 if invalid_citations else previous_revision
        current_key = (unit_id, revision)
        for position, passage_id in invalid_citations:
            excluded = _disposition(current_key, "invalid_citation", "citation does not resolve")
            excluded["previous_revision"] = previous_revision
            excluded["citation_position"] = position
            if isinstance(passage_id, str):
                excluded["passage_id"] = passage_id
            dispositions.append(excluded)

        if surviving_ids:
            checked.append({**unit, "revision": revision, "cited_passage_ids": surviving_ids})
        else:
            reason = "no cited passage resolves to the request"
            verdicts.append({
                "unit_id": unit_id,
                "revision": revision,
                "verdict": "unsupported",
                "affected_part": "whole unit",
                "reason": reason,
                "evidence_passage_ids": [],
            })
            dispositions.append(_disposition(current_key, "unsupported", reason))
    return checked, verdicts, dispositions
