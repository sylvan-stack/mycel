"""Write source-grounded summaries for Mycel's optional RAPTOR command."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import BinaryIO, TypedDict


REQUEST_CHARACTERS = 48_000
REQUEST_BYTES = REQUEST_CHARACTERS * 4
PASSAGE_CHARACTERS = 1_600
PACKAGED_PROMPTS = Path(__file__).resolve().parents[2] / "src/mycel/data/summary-prompts.json"
SECTION_PLACE = re.compile(r"[^\r\n\0]+ › [^\r\n\0]*")
CUT_LINE = re.compile(r"^\[Mycel: source text cut at request limit\]\r?$", re.MULTILINE)
PARAGRAPH_GAP = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")


class NarratorError(Exception):
    """A writer failure that can be reported without source or provider data."""


class Passage(TypedDict):
    request_digest: str
    passage_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Request:
    text: str
    digest: str
    source_spans: tuple[tuple[int, int], ...]
    passages: tuple[Passage, ...]


def _request_framing(instructions: Path | None) -> tuple[str, str]:
    try:
        if instructions is None:
            profile = json.loads(PACKAGED_PROMPTS.read_bytes())
            if profile["schema_version"] != 1 or profile["profile"] != "mycel-summary-prompts-v1":
                raise ValueError
            instruction, task = profile["instruction"], profile["task"]
        else:
            instruction = (instructions / "raptor-summary.md").read_bytes().decode("utf-8")
            task = (instructions / "raptor-request.md.tmpl").read_bytes().decode("utf-8")
        if not isinstance(instruction, str) or not isinstance(task, str):
            raise ValueError
        instruction, task = instruction.strip(), task.strip()
        if not instruction or task.count("$sections") != 1 or "\0" in instruction + task:
            raise ValueError
        before, after = task.split("$sections")
        prefix = instruction + "\n\n" + before
        if len(prefix) + len(after) >= REQUEST_CHARACTERS:
            raise ValueError
        return prefix, after
    except (OSError, TypeError, ValueError, KeyError):
        raise NarratorError("invalid summary prompt profile") from None


def _source_spans(text: str, prefix: str, suffix: str) -> tuple[tuple[int, int], ...]:
    start, end = len(prefix), len(text) - len(suffix)
    if start >= end or not text.startswith(prefix) or not text.endswith(suffix):
        raise NarratorError("summary request does not match the prompt profile")
    place_end = text.find("\n", start, end)
    if place_end < 0 or SECTION_PLACE.fullmatch(text, start, place_end) is None:
        raise NarratorError("summary request has no admitted document section")

    # The template identifies the source window. The renderer's horizontal
    # rule is unescaped and cannot distinguish structure from document prose.
    spans: list[tuple[int, int]] = []
    cursor = start
    for cut in CUT_LINE.finditer(text, start, end):
        if cursor < cut.start():
            spans.append((cursor, cut.start()))
        cursor = cut.end()
    if cursor < end:
        spans.append((cursor, end))
    if not any(text[max(begin, place_end + 1):stop].strip() for begin, stop in spans):
        raise NarratorError("summary request has no admitted document text")
    return tuple(spans)


def _passages(text: str, spans: tuple[tuple[int, int], ...], digest: str) -> tuple[Passage, ...]:
    passages: list[Passage] = []

    def add_paragraph(start: int, end: int) -> None:
        while start < end:
            while start < end and text[start].isspace():
                start += 1
            if start == end:
                return
            stop = min(start + PASSAGE_CHARACTERS, end)
            if stop < end:
                word_end = max(text.rfind(" ", start, stop + 1), text.rfind("\n", start, stop + 1))
                if word_end > start:
                    stop = word_end
            passage = text[start:stop].rstrip()
            passages.append({
                "request_digest": digest,
                "passage_id": f"P{len(passages) + 1:03d}",
                "start": start,
                "end": start + len(passage),
                "text": passage,
            })
            start = stop

    for start, end in spans:
        cursor = start
        for gap in PARAGRAPH_GAP.finditer(text, start, end):
            add_paragraph(cursor, gap.start())
            cursor = gap.end()
        add_paragraph(cursor, end)
    return tuple(passages)


def read_request(source: BinaryIO, instructions: Path | None = None) -> Request:
    """Read and locate evidence in one exact framed MYC-8 request."""
    raw = source.read(REQUEST_BYTES + 1)
    if len(raw) > REQUEST_BYTES:
        raise NarratorError("summary request exceeds the byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NarratorError("summary request is not UTF-8") from None
    if len(text) > REQUEST_CHARACTERS:
        raise NarratorError("summary request exceeds the character limit")

    prefix, suffix = _request_framing(instructions)
    spans = _source_spans(text, prefix, suffix)
    digest = sha256(raw).hexdigest()
    return Request(text, digest, spans, _passages(text, spans, digest))
