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
